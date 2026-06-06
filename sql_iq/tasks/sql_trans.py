"""SQL Translation task implementation."""

import re
import os
import json
from typing import Dict, Any, List

from ..core import BaseTask, TaskRegistry, TaskContext, Sample
from ..envs import DBRegistry
from ..evaluators import SQLTransEvaluator

# Optional imports for timeout
try:
    from func_timeout import func_timeout, FunctionTimedOut
except ImportError:
    func_timeout = None


@TaskRegistry.register("sql_trans")
class SQLTranslationTask(BaseTask):
    """
    SQL Translation task: Translate SQL from one dialect to another.

    Supported target dialects: oracle, mssql, postgresql, clickhouse, druid.
    """

    def __init__(self, config: Dict[str, Any], context: TaskContext):
        super().__init__(config, context)

        # Load prompt template
        template_path = config.get("prompt_template", "prompts/sql_trans.txt")
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                self.prompt_template = f.read()
        else:
            raise FileNotFoundError(
                f"Prompt template not found at '{template_path}'. "
                "Please provide 'prompts/sql_trans.txt' or specify 'prompt_template' in task config."
            )

        self.source_dialect = config.get("source_dialect", "sqlite")
        self.target_dialect = config.get("target_dialect", "oracle")
        self.db_dir = config.get("db_dir", "data/databases")
        self.schema_dir = config.get("schema_path", "data/schemas/sql_trans_schemas")

        self.schema_cache = {}

        # Initialize specialized evaluator
        self.evaluator = SQLTransEvaluator()

        # Initialize target environment
        registry_key = self.target_dialect.lower()
        self.target_env = DBRegistry.get_env(registry_key, self.db_dir)

    def _load_target_schema(self, db_id: str) -> str:
        """Load target dialect schema for a given db_id."""
        cache_key = f"{self.target_dialect}_{db_id}"
        if cache_key in self.schema_cache:
            return self.schema_cache[cache_key]

        schema_file = os.path.join(self.schema_dir, f"{self.target_dialect}_schema.json")
        if not os.path.exists(schema_file):
            schema_file = os.path.join(self.schema_dir, f"{self.target_dialect.lower()}_schema.json")

        if not os.path.exists(schema_file):
            raise FileNotFoundError(
                f"Schema file not found for dialect '{self.target_dialect}': "
                f"expected at '{os.path.join(self.schema_dir, self.target_dialect + '_schema.json')}'. "
                f"Please create the schema file before running sql_trans task."
            )

        try:
            with open(schema_file, 'r', encoding='utf-8') as f:
                loaded_schema = json.load(f)
                schema_content = loaded_schema.get(db_id, "")
                if not schema_content:
                    print(
                        f"[WARNING] Schema for db_id='{db_id}' is empty or missing "
                        f"in '{schema_file}'. The prompt will have no schema information, "
                        f"which may degrade translation quality."
                    )
                self.schema_cache[cache_key] = schema_content
                return schema_content
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse schema file '{schema_file}': {e}. "
                f"Please ensure it is valid JSON."
            )
        except Exception as e:
            raise RuntimeError(f"Error loading schema '{schema_file}': {e}")

    def build_prompt(self, sample: Sample) -> str:
        """
        Build the prompt for the LLM.
        Uses source_dialect, target_dialect, target_schema, and source_sql.
        """
        # Primary: use input_sql (new per-dialect format with source_sql field)
        source_sql = sample.input_sql or ""

        # Fallback: legacy format with SQL-{dialect} in metadata
        if not source_sql:
            source_key = f"SQL-{self.source_dialect}"
            source_sql = sample.metadata.get(source_key, "")

        if not source_sql:
            return "MISSING_SOURCE_SQL"

        target_schema_str = self._load_target_schema(sample.db_id)

        try:
            prompt = self.prompt_template.format(
                source_dialect=self.source_dialect,
                target_dialect=self.target_dialect,
                target_schema=target_schema_str,
                source_sql=source_sql
            )
            return prompt
        except KeyError as e:
            return f"Error building prompt: {e}"

    def extract_output(self, llm_response: str) -> str:
        """Extract SQL from LLM response."""
        if not llm_response:
            return ""
        return self._extract_sql(llm_response)

    def get_ground_truth(self, sample: Sample) -> str:
        """Get ground truth SQL for target dialect."""
        # Primary: use output_sql (new per-dialect format with target_sql field)
        if sample.output_sql:
            return sample.output_sql

        # Fallback: legacy format with SQL-{dialect} in metadata
        target_key = f"SQL-{self.target_dialect}"
        return sample.metadata.get(target_key, "")

    def evaluate(self, predictions: List[str], ground_truths: List[str],
                 samples: List[Sample], num_workers: int = 4, timeout: int = 10) -> Dict[str, float]:
        """Evaluate SQL translation using specialized parallel evaluator."""

        # Prepare valid samples for evaluation
        valid_indices = []
        for i, sample in enumerate(samples):
            source_sql = sample.input_sql or sample.metadata.get(f"SQL-{self.source_dialect}", "")
            ground_truth = ground_truths[i]

            if source_sql and ground_truth:
                valid_indices.append(i)

        if not valid_indices:
            return {"accuracy": 0.0, "correct": 0, "total": 0}

        valid_preds = [predictions[i] if predictions[i] is not None else "" for i in valid_indices]
        valid_gts = [ground_truths[i] for i in valid_indices]
        valid_samples = [samples[i] for i in valid_indices]

        # Call parallel evaluator
        metrics = self.evaluator.evaluate_with_execution(
            predictions=valid_preds,
            ground_truths=valid_gts,
            samples=valid_samples,
            env=self.target_env,
            num_workers=num_workers,
            timeout=timeout
        )

        return metrics
