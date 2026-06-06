"""Conversational SQL (multi-turn Text2SQL) task implementation."""

import os
from typing import List, Dict, Any

from ..core import BaseTask, Sample, TaskRegistry, TaskContext
from ..evaluators.execution import ExecutionEvaluator


@TaskRegistry.register("conversational_sql")
class ConversationalSQLTask(BaseTask):
    """
    Conversational SQL task: Convert natural language questions into SQL
    queries using conversation history context.

    Flow:
    1. Retrieve conversation history, current question, and schema from Sample.
    2. Build prompt containing history + question + schema.
    3. Call LLM API to generate SQL.
    4. Execute SQL and compare with ground truth (turn-level).
    """

    def __init__(self, config: Dict[str, Any], context: TaskContext):
        super().__init__(config, context)
        self.evaluator = ExecutionEvaluator()
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """Load prompt template from file."""
        template_path = self.config.get("prompt_template")

        if template_path and os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()

        default_path = "prompts/conversational_sql.txt"
        if os.path.exists(default_path):
            with open(default_path, 'r', encoding='utf-8') as f:
                return f.read()

        raise FileNotFoundError(
            "Prompt template not found. Please provide 'prompts/conversational_sql.txt' "
            "or specify 'prompt_template' in task config."
        )

    def build_prompt(self, sample: Sample) -> str:
        """Build LLM input prompt with conversation history."""
        schema = sample.schema_str or ""
        question = sample.input_text or ""
        evidence = sample.evidence or ""

        # Format conversation history
        history_str = ""
        if sample.history:
            history_parts = []
            for idx, turn in enumerate(sample.history, 1):
                q = turn.get("q", "")
                a = turn.get("a", "")
                history_parts.append(f"Turn {idx}:")
                history_parts.append(f"Question: {q}")
                history_parts.append(f"SQL: {a}")
                history_parts.append("")
            history_str = "\n".join(history_parts)

        prompt = self.prompt_template.format(
            schema=schema,
            evidence=evidence,
            history=history_str,
            question=question
        )
        return prompt

    def extract_output(self, llm_response: str) -> str:
        """Extract SQL from LLM response."""
        return self._extract_sql(llm_response)

    def evaluate(
        self,
        predictions: List[str],
        ground_truths: List[str],
        samples: List[Sample],
        num_workers: int = 4,
        timeout: int = 10
    ) -> Dict[str, float]:
        """Evaluate using execution accuracy."""
        if not self.env:
            raise RuntimeError("DBEnvironment not set in Task Context.")

        metrics = self.evaluator.evaluate_with_execution(
            predictions,
            ground_truths,
            samples,
            self.env,
            num_workers=num_workers,
            timeout=timeout
        )
        return metrics

    def get_ground_truth(self, sample: Sample) -> str:
        """Get ground truth SQL."""
        return sample.output_sql

    def to_record(self, sample: Sample, prediction: Any) -> Dict[str, Any]:
        """Format result record with multi-turn specific fields."""
        record = super().to_record(sample, prediction)
        record.update({
            "question": sample.input_text,
            "turn_id": sample.metadata.get("turn_id"),
            "original_question_id": sample.metadata.get("original_question_id")
        })
        if sample.difficulty:
            record["difficulty"] = sample.difficulty
        return record
