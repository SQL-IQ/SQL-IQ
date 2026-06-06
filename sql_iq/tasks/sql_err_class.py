"""SQL Error Classification task implementation."""

import os
import re
from typing import List, Dict, Any

from ..core import BaseTask, Sample, TaskRegistry, TaskContext


@TaskRegistry.register("sql_err_class")
class SQLErrorClassTask(BaseTask):
    """
    SQL Error Classification task: Given a natural language question,
    evidence, schema, and a candidate SQL, determine whether the SQL
    is correct. If incorrect, identify the specific error types
    (multi-label classification).
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

        default_path = "prompts/sql_err_class.txt"
        if os.path.exists(default_path):
            with open(default_path, 'r', encoding='utf-8') as f:
                return f.read()

        raise FileNotFoundError(
            "Prompt template not found. Please provide 'prompts/sql_err_class.txt' "
            "or specify 'prompt_template' in task config."
        )

    def build_prompt(self, sample: Sample) -> str:
        """Build prompt with candidate SQL and schema."""
        question = sample.input_text or sample.metadata.get("question", "")
        sql = sample.metadata.get("sql") or sample.input_sql or ""
        prompt = self.prompt_template.format(
            schema=sample.schema_str or "",
            question=question,
            evidence=sample.evidence or "",
            sql=sql
        )
        return prompt

    def extract_output(self, llm_response: str) -> Dict[str, Any]:
        """Extract structured result from LLM response, supporting <answer> tag."""
        if not llm_response:
            return {"result": "Unknown", "error_types": []}

        # Match <answer> tag content
        match = re.search(r'<answer>\s*(.*?)\s*</answer>', llm_response, re.DOTALL | re.IGNORECASE)
        if match:
            content = match.group(1).strip()
            if content.lower() == "no error":
                return {"result": "True", "error_types": []}
            else:
                # Split error types and clean
                error_types = [t.strip() for t in content.split(',') if t.strip()]
                return {"result": "False", "error_types": error_types}

        # Fallback: unable to parse
        return {"result": "Unknown", "error_types": []}

    def get_ground_truth(self, sample: Sample) -> Dict[str, Any]:
        """Get ground truth in unified format: No error or error type list."""
        if sample.output_label is True:
            return {"result": "True", "error_types": []}

        # Extract error types from ground truth
        error_types = []
        raw_errors = sample.metadata.get("error_types", [])
        for err in raw_errors:
            if isinstance(err, dict):
                error_types.append(err.get("error_type", "Other"))
            elif isinstance(err, str):
                error_types.append(err)

        # Deduplicate and sort for consistent comparison
        error_types = sorted(list(set(error_types)))

        return {
            "result": "False",
            "error_types": error_types
        }

    def evaluate(self, predictions: List[Dict[str, Any]],
                 ground_truths: List[Dict[str, Any]],
                 samples: List[Sample],
                 num_workers: int = 4,
                 timeout: int = 10) -> Dict[str, float]:
        """
        Compute evaluation metrics:
        1. Detection: Accuracy of No error / Has error classification.
        2. Classification: Multi-label F1 for error types.
        3. Accuracy: Exact match treating as 10-class (No error + 9 error types).
        """
        det_tp, det_fp, det_fn = 0, 0, 0
        type_tp, type_fp, type_fn = 0, 0, 0
        uni_tp, uni_fp, uni_fn = 0, 0, 0
        correct_all = 0

        for pred, gt in zip(predictions, ground_truths):
            # Build GT unified label set (including "No error")
            g_res = str(gt.get("result", "")).lower() == "true"
            g_tags = set(gt.get("error_types", []))
            if g_res:
                g_unified = {"No error"}
            else:
                g_unified = set(g_tags)

            # Handle Unknown or inference failure
            if not pred or pred.get("result") == "Unknown":
                det_fn += 1
                type_fn += len(g_tags)
                uni_fn += len(g_unified)
                continue

            p_res = str(pred.get("result", "")).lower() == "true"
            p_tags = set(pred.get("error_types", []))

            # Build Pred unified label set
            if p_res:
                p_unified = {"No error"}
            else:
                p_unified = set(p_tags)

            # Unified Multi-label Metrics (including "No error")
            uni_tp += len(p_unified & g_unified)
            uni_fp += len(p_unified - g_unified)
            uni_fn += len(g_unified - p_unified)

            # Detection Metrics (positive class = "has error")
            p_bug = not p_res
            g_bug = not g_res

            if p_bug and g_bug:
                det_tp += 1
            elif p_bug and not g_bug:
                det_fp += 1
            elif not p_bug and g_bug:
                det_fn += 1

            # Classification Metrics (Multi-label F1)
            type_tp += len(p_tags & g_tags)
            type_fp += len(p_tags - g_tags)
            type_fn += len(g_tags - p_tags)

            # Exact Match Accuracy
            if p_res == g_res:
                if p_res:  # Both "No error"
                    correct_all += 1
                else:  # Both "Has error", check exact set match
                    if p_tags == g_tags and len(g_tags) > 0:
                        correct_all += 1

        def calc_f1(tp, fp, fn):
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
            return prec, rec, f1

        uni_p, uni_r, uni_f1 = calc_f1(uni_tp, uni_fp, uni_fn)
        det_p, det_r, det_f1 = calc_f1(det_tp, det_fp, det_fn)
        type_p, type_r, type_f1 = calc_f1(type_tp, type_fp, type_fn)

        accuracy = correct_all / len(samples) if len(samples) > 0 else 0.0

        return {
            "unified_f1": uni_f1,
            "unified_precision": uni_p,
            "unified_recall": uni_r,
            "detection_f1": det_f1,
            "detection_precision": det_p,
            "detection_recall": det_r,
            "classification_f1": type_f1,
            "classification_precision": type_p,
            "classification_recall": type_r,
            "accuracy": accuracy,
            "correct": correct_all,
            "total": len(samples)
        }
