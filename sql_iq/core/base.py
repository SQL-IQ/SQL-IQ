"""Base Task abstraction for all SQL evaluation tasks."""

import json
import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from .sample import Sample
from .context import TaskContext


class BaseTask(ABC):
    """
    Base class for all tasks.

    Execution flow:
    1. build_prompt() - Convert a Sample into LLM input.
    2. extract_output() - Extract structured output from LLM response.
    3. evaluate() - Compute evaluation metrics.
    """

    def __init__(self, config: Dict[str, Any], context: TaskContext):
        """
        Args:
            config: Task configuration dictionary.
            context: Task context (contains LLM client, DB env, etc.)
        """
        self.config = config
        self.context = context
        self.task_type = config.get("task_type")

        # Convenience shortcuts for backward compatibility
        self.llm_client = context.llm_client
        self.env = context.db_env

    @abstractmethod
    def build_prompt(self, sample: Sample) -> str:
        """
        Build the LLM input prompt from a sample.

        Args:
            sample: Unified sample object.

        Returns:
            LLM input prompt string.
        """
        pass

    @abstractmethod
    def extract_output(self, llm_response: str) -> str:
        """
        Extract structured output from LLM free-text response.

        Args:
            llm_response: Raw LLM response string.

        Returns:
            Extracted output (SQL string or label).
        """
        pass

    @abstractmethod
    def evaluate(self, predictions: List[str], ground_truths: List[Any],
                 samples: List[Sample], num_workers: int = 4, timeout: int = 10) -> Dict[str, float]:
        """
        Compute evaluation metrics.

        Args:
            predictions: LLM-generated predictions.
            ground_truths: Ground truth answers.
            samples: Original sample list.
            num_workers: Number of evaluation workers.
            timeout: Timeout in seconds.

        Returns:
            Metrics dictionary.
        """
        pass

    def get_ground_truth(self, sample: Sample) -> Any:
        """
        Get the ground truth for a sample. Subclasses should override.
        """
        return ""

    def has_ground_truth(self, sample: Sample) -> bool:
        """
        Check whether the sample has a ground truth annotation.
        """
        gt = self.get_ground_truth(sample)
        if gt is None:
            return False
        if isinstance(gt, str) and not gt.strip():
            return False
        return True

    def to_record(self, sample: Sample, prediction: Any) -> Dict[str, Any]:
        """
        Convert sample and prediction into a serializable dictionary.
        Subclasses may override to include additional context.
        """
        record = {
            "id": sample.id,
            "db_id": sample.db_id,
            "prediction": prediction,
            "ground_truth": self.get_ground_truth(sample)
        }

        # Inject debug information (prompt and full response)
        if hasattr(sample, 'metadata'):
            if '_debug_prompt' in sample.metadata:
                record['prompt'] = sample.metadata['_debug_prompt']
            if '_debug_response' in sample.metadata:
                record['full_response'] = sample.metadata['_debug_response']

        return record

    def load_samples(self, data_path: str) -> List[Sample]:
        """
        Load samples from a data file. Can be overridden by subclasses.
        Default implementation: load JSONL file and convert to Sample objects.

        Args:
            data_path: Data file path (JSONL format).

        Returns:
            List of Sample objects.
        """
        samples = []
        with open(data_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    sample = self._dict_to_sample(data)
                    samples.append(sample)
        return samples

    def _dict_to_sample(self, data: Dict[str, Any]) -> Sample:
        """
        Convert a dictionary to a Sample object. Subclasses may override
        to customize the mapping logic.

        Args:
            data: Data dictionary (from JSONL).

        Returns:
            Sample object.
        """
        return Sample(
            id=int(data.get("id", 0)),
            input_text=data.get("input_text"),
            input_sql=data.get("input_sql"),
            input_sql_2=data.get("input_sql_2"),
            input_plan=data.get("input_plan"),
            input_plan_2=data.get("input_plan_2"),
            db_id=data.get("db_id"),
            schema_str=data.get("schema_str"),
            evidence=data.get("evidence"),
            output_sql=data.get("output_sql"),
            output_label=data.get("output_label"),
            db_path=data.get("db_path"),
            difficulty=data.get("difficulty"),
            dialect=data.get("dialect", "sqlite"),
            history=data.get("history", []),
            metadata=data.get("metadata", {})
        )

    @staticmethod
    def _extract_sql(llm_response: str) -> str:
        """
        Extract SQL query from LLM response.

        Supports multiple formats:
        1. ```sql ... ``` (markdown code block)
        2. ```SQL ... ``` (uppercase)
        3. Direct SQL statement
        4. Falls back to returning the entire response.

        Args:
            llm_response: Raw LLM response.

        Returns:
            Extracted SQL string.
        """
        if not llm_response:
            return ""

        # Pattern: ```sql ... ```
        pattern = r"```sql\s*(.*?)\s*```"
        sql_blocks = re.findall(pattern, llm_response, re.DOTALL | re.IGNORECASE)

        if sql_blocks:
            # Return the last SQL block found
            return sql_blocks[-1].strip()

        # No code block found, return the stripped response
        return llm_response.strip()

    def infer_batch(self, samples: List[Sample], num_workers: int = 4,
                    show_progress: bool = True, on_result: callable = None) -> List[Any]:
        """
        Batch inference method using LLM client concurrency.
        Generic workflow: Samples -> Prompts -> LLM -> Raw Results -> Predictions.

        Args:
            samples: List of samples.
            num_workers: Number of workers (default 4).
            show_progress: Whether to display progress bar.
            on_result: Optional callback, signature on_result(index, sample, prediction).

        Returns:
            List of predictions (transformed by extract_output).
        """
        if not self.llm_client:
            raise RuntimeError("LLMClient not initialized in Task.")

        # 1. Build all prompts
        prompts = [self.build_prompt(sample) for sample in samples]

        # Pre-allocate predictions list
        predictions = [None] * len(samples)

        # Define LLM-level callback
        def _on_llm_result(idx, response):
            if not hasattr(samples[idx], 'metadata'):
                samples[idx].metadata = {}
            samples[idx].metadata['_debug_prompt'] = prompts[idx]

            if response is not None:
                pred = self.extract_output(response)
                predictions[idx] = pred
                samples[idx].metadata['_debug_response'] = response
            else:
                predictions[idx] = None
                samples[idx].metadata['_debug_response'] = "API Error: No response from LLM."

            # Trigger upper-level callback (immediate disk write)
            if on_result is not None:
                on_result(idx, samples[idx], predictions[idx])

        # 2. Concurrent inference with immediate callback
        self.llm_client.generate_batch(
            prompts=prompts,
            num_workers=num_workers,
            show_progress=show_progress,
            temperature=self.config.get("temperature", 0.0),
            max_tokens=self.config.get("max_tokens", 4096),
            top_p=self.config.get("top_p", 1.0),
            on_result=_on_llm_result,
        )

        return predictions

    def infer(self, sample: Sample) -> Any:
        """
        Inference on a single sample.

        Args:
            sample: Sample object.

        Returns:
            Prediction result (transformed by extract_output), or None on failure.
        """
        if not self.llm_client:
            raise RuntimeError("LLMClient not initialized in Task.")

        # 1. Build prompt
        prompt = self.build_prompt(sample)

        # Record prompt
        if not hasattr(sample, 'metadata'):
            sample.metadata = {}
        sample.metadata['_debug_prompt'] = prompt

        # 2. Call LLM
        llm_response, api_failed = self.llm_client.generate(
            prompt=prompt,
            temperature=self.config.get("temperature", 0.0),
            max_tokens=self.config.get("max_tokens", 4096),
            top_p=self.config.get("top_p", 1.0),
        )

        if api_failed:
            sample.metadata['_debug_response'] = "API Error: No response from LLM."
            return None

        # Record full response
        sample.metadata['_debug_response'] = llm_response

        # 3. Extract and return result
        return self.extract_output(llm_response)
