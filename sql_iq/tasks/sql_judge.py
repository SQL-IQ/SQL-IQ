"""SQL Judge task implementation."""

import os
import re
from typing import List, Dict, Any

from ..core import BaseTask, Sample, TaskRegistry, TaskContext


@TaskRegistry.register("sql_judge")
class SQLJudgeTask(BaseTask):
    """
    SQL Judge task: Given a schema, question, and two candidate SQL queries
    (one correct, one incorrect), determine which SQL is correct.
    """

    def __init__(self, config: Dict[str, Any], context: TaskContext):
        super().__init__(config, context)
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """Load prompt template from file."""
        template_path = self.config.get("prompt_template")
        if template_path and os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()

        default_path = "prompts/sql_judge.txt"
        if os.path.exists(default_path):
            with open(default_path, 'r', encoding='utf-8') as f:
                return f.read()

        raise FileNotFoundError(
            "Prompt template not found. Please provide 'prompts/sql_judge.txt' "
            "or specify 'prompt_template' in task config."
        )

    def build_prompt(self, sample: Sample) -> str:
        """
        Build prompt from sample.

        Reads pre-shuffled candidate SQL and correct answer from metadata
        (set during data loading to ensure deterministic ordering).
        """
        schema = sample.schema_str if sample.schema_str else ""

        # Read pre-assigned candidates from metadata
        candidate_a = sample.metadata.get("candidate_a", "")
        candidate_b = sample.metadata.get("candidate_b", "")

        # Build evidence section
        evidence = sample.evidence if sample.evidence else ""
        evidence_section = f"Evidence:\n{evidence}\n" if evidence else ""

        return self.prompt_template.format(
            schema=schema,
            evidence=evidence_section,
            question=sample.input_text,
            candidate_a=candidate_a,
            candidate_b=candidate_b
        )

    def extract_output(self, llm_response: str) -> str:
        """
        Extract A/B answer from LLM response.

        Supports:
        1. <answer>A</answer> or <answer>B</answer>
        2. Fallback: search for isolated A or B
        """
        if not llm_response:
            return ""

        response_clean = llm_response.strip()

        # Match <answer> tag
        match = re.search(r'<answer>\s*([AB])\s*</answer>', response_clean, re.IGNORECASE)
        if match:
            return match.group(1).upper()

        # Fallback: look for isolated A or B
        response_lower = response_clean.lower()
        if "a" in response_lower and "b" not in response_lower:
            return "A"
        elif "b" in response_lower and "a" not in response_lower:
            return "B"
        else:
            return "unknown"

    def get_ground_truth(self, sample: Sample) -> str:
        """Get ground truth answer (A or B) from metadata."""
        return sample.metadata.get("correct_answer", "")

    def evaluate(self, predictions: List[str],
                 ground_truths: List[str],
                 samples: List[Sample],
                 num_workers: int = 4,
                 timeout: int = 10) -> Dict[str, float]:
        """
        Compute evaluation metrics:
        - accuracy: Overall accuracy.
        - unknown_count: Number of unparseable responses.
        """
        correct = 0
        unknown_count = 0
        total = len(predictions)

        for pred, gt in zip(predictions, ground_truths):
            if not pred or pred == "unknown":
                unknown_count += 1
                continue
            if pred.upper() == gt.upper():
                correct += 1

        accuracy = correct / total if total > 0 else 0.0

        return {
            "accuracy": accuracy,
            "correct_count": correct,
            "total_count": total,
            "unknown_count": unknown_count
        }

    def to_record(self, sample: Sample, prediction: Any) -> Dict[str, Any]:
        """Convert to output record."""
        record = super().to_record(sample, prediction)
        is_correct = False
        if prediction and prediction != "unknown":
            is_correct = (prediction.upper() == sample.metadata.get("correct_answer", "").upper())

        record.update({
            "question": sample.input_text,
            "evidence": sample.evidence,
            "pos_sql": sample.metadata.get("pos_sql", ""),
            "neg_sql": sample.metadata.get("neg_sql", ""),
            "candidate_a": sample.metadata.get("candidate_a", ""),
            "candidate_b": sample.metadata.get("candidate_b", ""),
            "correct_answer": sample.metadata.get("correct_answer", ""),
            "is_correct": is_correct
        })
        return record
