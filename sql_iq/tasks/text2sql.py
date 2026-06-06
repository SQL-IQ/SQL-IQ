"""Text2SQL task implementation."""

import os
from typing import List, Dict, Any

from ..core import BaseTask, Sample, TaskRegistry, TaskContext
from ..evaluators.execution import ExecutionEvaluator


@TaskRegistry.register("text2sql")
class Text2SQLTask(BaseTask):
    """
    Text2SQL task: Convert natural language questions into SQL queries.

    Flow:
    1. Load database schema from schema JSON.
    2. Build prompt containing question + schema.
    3. Call LLM API to generate SQL.
    4. Execute SQL and compare with ground truth.
    """

    def __init__(self, config: Dict[str, Any], context: TaskContext):
        super().__init__(config, context)
        self.evaluator = ExecutionEvaluator()
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """
        Load prompt template from file.

        Priority:
        1. Template file specified in config.
        2. Default location: prompts/text2sql.txt
        """
        template_path = self.config.get("prompt_template")

        if template_path and os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()

        default_path = "prompts/text2sql.txt"
        if os.path.exists(default_path):
            with open(default_path, 'r', encoding='utf-8') as f:
                return f.read()

        raise FileNotFoundError(
            "Prompt template not found. Please provide 'prompts/text2sql.txt' "
            "or specify 'prompt_template' in task config."
        )

    def build_prompt(self, sample: Sample) -> str:
        """Build LLM input prompt from sample."""
        schema = sample.schema_str or ""
        question = sample.input_text or ""
        evidence = sample.evidence or ""

        prompt = self.prompt_template.format(
            schema=schema,
            question=question,
            evidence=evidence
        )
        return prompt

    def extract_output(self, llm_response: str) -> str:
        """Extract SQL query from LLM response."""
        return self._extract_sql(llm_response)

    def evaluate(
        self,
        predictions: List[str],
        ground_truths: List[str],
        samples: List[Sample],
        num_workers: int = 4,
        timeout: int = 10
    ) -> Dict[str, float]:
        """Compute evaluation metrics using execution accuracy."""
        if not self.env:
            raise RuntimeError("DBEnvironment not set.")

        return self.evaluator.evaluate_with_execution(
            predictions, ground_truths, samples, self.env,
            num_workers=num_workers,
            timeout=timeout
        )

    def get_ground_truth(self, sample: Sample) -> str:
        """Get ground truth SQL."""
        return sample.output_sql

    def to_record(self, sample: Sample, prediction: Any) -> Dict[str, Any]:
        """Format sample and prediction as a serializable record."""
        record = super().to_record(sample, prediction)
        record.update({
            "question": sample.input_text,
        })
        if "difficulty" in sample.metadata:
            record["difficulty"] = sample.metadata["difficulty"]
        return record
