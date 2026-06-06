"""SQL Equivalence Judge task implementation."""

import os
import re
import math
from typing import List, Dict, Any

from ..core import BaseTask, Sample, TaskRegistry, TaskContext


@TaskRegistry.register("sql_equ_judge")
class SQLEquivalenceJudgeTask(BaseTask):
    """
    SQL Equivalence Judge task: Given two SQL statements and a schema,
    determine whether they are semantically equivalent.
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

        default_path = "prompts/sql_equ_judge.txt"
        if os.path.exists(default_path):
            with open(default_path, 'r', encoding='utf-8') as f:
                return f.read()

        raise FileNotFoundError(
            "Prompt template not found. Please provide 'prompts/sql_equ_judge.txt' "
            "or specify 'prompt_template' in task config."
        )

    def build_prompt(self, sample: Sample) -> str:
        """Build prompt with two SQL statements and schema."""
        sql1 = sample.metadata.get("sql1", "")
        sql2 = sample.metadata.get("sql2", "")
        schema = sample.metadata.get("schema", "")

        # Convert schema dict to string if needed
        if isinstance(schema, dict):
            schema_str = self._format_schema(schema)
        else:
            schema_str = str(schema)

        return self.prompt_template.format(
            schema=schema_str,
            sql1=sql1,
            sql2=sql2
        )

    def _format_schema(self, schema_dict: Dict) -> str:
        """Format schema dictionary as DDL string."""
        tables = schema_dict.get("tables", {})
        constraints = schema_dict.get("constraint", [])

        schema_str = ""

        # Format table structures
        for table_name, columns in tables.items():
            schema_str += f"CREATE TABLE {table_name} (\n"
            for col_name, col_type in columns.items():
                schema_str += f"    {col_name} {col_type},\n"
            schema_str = schema_str.rstrip(',\n') + "\n);\n\n"

        # Format constraints
        if constraints:
            schema_str += "Constraints:\n"
            for constraint in constraints:
                if "primary" in constraint:
                    pk_cols = [col["value"] for col in constraint["primary"]]
                    schema_str += f"PRIMARY KEY ({', '.join(pk_cols)})\n"
                elif "foreign" in constraint:
                    fk_cols = constraint["foreign"]
                    if len(fk_cols) >= 2:
                        schema_str += f"FOREIGN KEY ({fk_cols[0]['value']}) REFERENCES {fk_cols[1]['value']}\n"

        return schema_str.strip()

    def extract_output(self, llm_response: str) -> str:
        """Extract yes/no result from LLM response."""
        response_clean = llm_response.strip().lower()

        # Match <answer> tag
        match = re.search(r'<answer>\s*(.*?)\s*</answer>', response_clean, re.DOTALL | re.IGNORECASE)
        if match:
            answer_content = match.group(1).strip()
            if "yes" in answer_content and "no" not in answer_content:
                return "yes"
            elif "no" in answer_content and "yes" not in answer_content:
                return "no"

        # Match standalone yes/no
        if re.search(r'\byes\b', response_clean):
            return "yes"
        elif re.search(r'\bno\b', response_clean):
            return "no"
        else:
            return "undetermined"

    def get_ground_truth(self, sample: Sample) -> str:
        """Get ground truth label."""
        return sample.metadata.get("semantic equivalence", "")

    def evaluate(self, predictions: List[str],
                 ground_truths: List[str],
                 samples: List[Sample],
                 num_workers: int = 4,
                 timeout: int = 10) -> Dict[str, float]:
        """
        Compute metrics:
        1. equ_acc: Accuracy on equivalent pairs.
        2. neq_acc: Accuracy on non-equivalent pairs.
        3. gm: Geometric mean (sqrt(equ_acc * neq_acc)).
        """
        equ_correct = 0
        equ_total = 0
        neq_correct = 0
        neq_total = 0
        undetermined_count = 0

        for pred, gt in zip(predictions, ground_truths):
            gt_lower = gt.lower() if gt else ""
            pred_lower = pred.lower() if pred else "undetermined"

            if not pred or pred_lower == "undetermined":
                undetermined_count += 1
                continue

            if gt_lower == "yes":
                equ_total += 1
                if pred_lower == "yes":
                    equ_correct += 1
            elif gt_lower == "no":
                neq_total += 1
                if pred_lower == "no":
                    neq_correct += 1

        equ_acc = equ_correct / equ_total if equ_total > 0 else 0.0
        neq_acc = neq_correct / neq_total if neq_total > 0 else 0.0

        if equ_acc > 0 and neq_acc > 0:
            gm = math.sqrt(equ_acc * neq_acc)
        else:
            gm = 0.0

        total_correct = equ_correct + neq_correct
        total_samples = equ_total + neq_total
        overall_acc = total_correct / total_samples if total_samples > 0 else 0.0

        return {
            "accuracy": overall_acc,
            "correct": total_correct,
            "total": total_samples,
            "equivalent_accuracy": equ_acc,
            "non_equivalent_accuracy": neq_acc,
            "geometric_mean": gm,
            "undetermined_count": undetermined_count,
        }

    def to_record(self, sample: Sample, prediction: Any) -> Dict[str, Any]:
        """Convert to output record."""
        record = super().to_record(sample, prediction)
        record.update({
            "sql1": sample.metadata.get("sql1", ""),
            "sql2": sample.metadata.get("sql2", ""),
            "is_correct": (prediction.lower() == sample.metadata.get("semantic equivalence", "").lower()) if prediction else False
        })
        return record
