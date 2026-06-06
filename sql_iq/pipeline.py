"""
Generic task execution pipeline.

Responsibilities:
1. Load task configuration (each task may have different data source, schema, DB, prompt).
2. Initialize shared resources (LLM, concurrency parameters).
3. Unified task execution flow.
4. Result saving and summary reporting.
5. Support multi-task sequential execution.
"""

import os
import json
import yaml
import copy
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, fields, asdict

from .core import TaskRegistry, Sample, TaskContext, BaseTask
from . import tasks  # Trigger auto-registration of all task classes
from .schemas import SchemaLoader
from .envs import DBRegistry
from .llm import LLMClient
from .evaluators import ExecutionEvaluator
from .utils.data_loader import DataLoader


@dataclass
class PipelineConfig:
    """Global pipeline configuration (LLM, concurrency, etc.)"""
    # LLM
    api_base: str = "http://localhost:8000/v1"
    model_name: str = "meta-llama/Llama-2-7b-hf"
    api_key: str = "dummy"
    temperature: float = 0.0
    max_tokens: int = 8192
    top_p: float = 1.0

    # Inference
    num_workers: int = 4
    batch_size: Optional[int] = None

    # Evaluation
    timeout: int = 20
    eval_workers: int = 4

    # Output
    output_dir: str = "results"

    # Other
    show_progress: bool = True
    debug: bool = False


@dataclass
class TaskConfig:
    """Single task configuration."""
    name: str
    data_path: str
    schema_path: str
    db_dir: str
    db_type: str = "sqlite"
    raw_config: Dict[str, Any] = None

    def __post_init__(self):
        if self.raw_config is None:
            self.raw_config = {}


class Pipeline:
    """
    Generic task execution pipeline.

    Supports:
    1. Global configuration (LLM, concurrency parameters).
    2. Task-specific configuration (data source, schema, prompt).
    3. Resource caching (avoids redundant loading).
    4. Multi-task sequential execution.
    5. Checkpoint/resume (JSONL-based intermediate results).
    """

    def __init__(
        self,
        global_config: PipelineConfig,
        tasks_config_path: Optional[str] = None,
        fallback_task_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize pipeline.

        Args:
            global_config: Global configuration (LLM, concurrency, etc.)
            tasks_config_path: Task configuration file path (YAML format, optional).
            fallback_task_config: Fallback task config (shared by all tasks when no config file).
        """
        self.global_config = global_config

        # Initialize LLM client (globally shared)
        print("=" * 80)
        print("[INFO] Initializing Pipeline")
        print("=" * 80)
        print()

        print("[INFO] Initializing LLM client...")
        self.llm_client = LLMClient(
            api_base=global_config.api_base,
            model_name=global_config.model_name,
            api_key=global_config.api_key,
        )
        print(f"[OK] LLM initialized")
        print(f"  API: {global_config.api_base}")
        print(f"  Model: {global_config.model_name}")
        print()

        # Load task configuration
        if tasks_config_path and Path(tasks_config_path).exists():
            print(f"[INFO] Loading task config: {tasks_config_path}")
            self.tasks_config = self._load_tasks_config(tasks_config_path)
            print(f"[OK] Task config loaded ({len(self.tasks_config)} tasks)")
        else:
            print("[INFO] Using global config as default for all tasks")
            self.tasks_config = None

        self.fallback_task_config = fallback_task_config
        print()

        # Evaluator
        self.evaluator = ExecutionEvaluator()

        # Resource cache
        self.task_resources: Dict[str, Dict[str, Any]] = {}

        # Results tracking
        self.task_results: Dict[str, Dict[str, Any]] = {}

    def _load_tasks_config(self, config_path: str) -> Dict[str, TaskConfig]:
        """Load task configuration file (YAML format)."""
        with open(config_path, 'r', encoding='utf-8') as f:
            config_dict = yaml.safe_load(f)

        tasks_config = {}
        for task_name, task_cfg in config_dict.items():
            tasks_config[task_name] = TaskConfig(
                name=task_name,
                data_path=task_cfg.get('data_path'),
                schema_path=task_cfg.get('schema_path'),
                db_dir=task_cfg.get('db_dir'),
                db_type=task_cfg.get('db_type', 'sqlite'),
                raw_config=task_cfg
            )

        return tasks_config

    def _get_task_config(self, task_name: str) -> TaskConfig:
        """Get task configuration by name."""
        if self.tasks_config and task_name in self.tasks_config:
            return self.tasks_config[task_name]

        if self.fallback_task_config:
            return TaskConfig(
                name=task_name,
                data_path=self.fallback_task_config.get('data_path'),
                schema_path=self.fallback_task_config.get('schema_path'),
                db_dir=self.fallback_task_config.get('db_dir'),
                db_type=self.fallback_task_config.get('db_type', 'sqlite'),
                raw_config=self.fallback_task_config
            )

        raise ValueError(
            f"Configuration for task '{task_name}' not found. "
            "Please provide a task config file or specify configuration for this task."
        )

    def _get_task_resources(
        self,
        task_name: str,
        task_config: TaskConfig
    ) -> Dict[str, Any]:
        """
        Get task resources (cached for efficiency).

        Returns:
            Resource dict {samples, schema_loader, db_env}
        """
        if task_name in self.task_resources:
            return self.task_resources[task_name]

        print(f"[INFO] Loading resources for task '{task_name}'...")

        # Load schema
        schema_loader = None
        if task_config.schema_path and os.path.isfile(task_config.schema_path):
            schema_loader = SchemaLoader(task_config.schema_path)
            print(f"  [OK] Schema loaded ({len(schema_loader._schemas)} databases)")
        elif task_config.schema_path and os.path.isdir(task_config.schema_path):
            print(f"  [INFO] Schema directory detected, will be loaded by task internally")
        else:
            print(f"  [WARNING] No valid schema file or directory found: {task_config.schema_path}")

        # Initialize database environment
        db_type = getattr(task_config, "db_type", "sqlite")
        try:
            db_env = DBRegistry.get_env(db_type, task_config.db_dir)
            print(f"  [OK] Database environment initialized ({db_type})")
        except Exception as e:
            print(f"  [WARNING] Database initialization failed ({db_type}): {e}")
            db_env = None

        # Load samples
        samples = DataLoader.load_samples(task_config.data_path)
        if self.global_config.debug:
            samples = samples[:5]
        print(f"  [OK] Samples loaded ({len(samples)} total)")

        # Fill schema
        if schema_loader:
            schema_loader.fill_schema_in_samples(samples)
            print(f"  [OK] Schema populated")
        print()

        resources = {
            'samples': samples,
            'schema_loader': schema_loader,
            'db_env': db_env
        }
        self.task_resources[task_name] = resources

        return resources

    def run(self, task_names: List[str], retry: bool = False, max_retry_rounds: int = 3) -> Dict[str, Any]:
        """
        Execute one or more tasks.

        Args:
            task_names: List of task names.
            retry: Whether in retry mode (only re-infer API-failed samples).
            max_retry_rounds: Maximum retry rounds.

        Returns:
            Summary of all task results.
        """
        if retry:
            print("=" * 80)
            print(f"[INFO] Retry mode: re-inferring API-failed samples only")
            print(f"  Max retry rounds: {max_retry_rounds}")
            print("=" * 80)
        else:
            print("=" * 80)
            print(f"[INFO] Running tasks: {', '.join(task_names)}")
            print("=" * 80)
        print()

        for task_name in task_names:
            print(f"\n{'=' * 80}")
            print(f"[TASK] {'Retrying' if retry else 'Running'}: {task_name}")
            print(f"{'=' * 80}\n")

            if retry:
                self._execute_task_retry(task_name, max_retry_rounds)
            else:
                self._execute_task(task_name)

        self._print_summary()

        return self.task_results

    def _execute_task(self, task_name: str):
        """
        Execute a single task. Supports target_dialect list expansion.
        When data_dir is specified (instead of data_path), automatically loads
        {data_dir}/{dialect}.json for each target dialect.
        """
        task_config = self._get_task_config(task_name)

        # Check if expansion is needed (target_dialect list)
        target_dialects = task_config.raw_config.get('target_dialect')

        if isinstance(target_dialects, list):
            print(f"[INFO] Multiple target dialects detected: {', '.join(target_dialects)}, running sequentially...")
            data_dir = task_config.raw_config.get('data_dir')

            for dialect in target_dialects:
                sub_task_config = copy.deepcopy(task_config)
                sub_task_config.raw_config['target_dialect'] = dialect

                # If data_dir is set, resolve per-dialect data file
                if data_dir:
                    dialect_data_path = os.path.join(data_dir, f"{dialect}.json")
                    sub_task_config.data_path = dialect_data_path
                    sub_task_config.raw_config['data_path'] = dialect_data_path

                display_name = f"{task_name} ({dialect})"
                print(f"\n{'-' * 40}")
                print(f"[SUBTASK] {display_name}")
                print(f"{'-' * 40}")

                sub_task_key = f"{task_name}_{dialect}"
                self._run_task_instance(sub_task_key, sub_task_config)
        else:
            self._run_task_instance(task_name, task_config)

    def _execute_task_retry(self, task_name: str, max_retry_rounds: int = 3):
        """Retry API-failed samples for a task. Supports target_dialect expansion."""
        task_config = self._get_task_config(task_name)

        target_dialects = task_config.raw_config.get('target_dialect')

        if isinstance(target_dialects, list):
            print(f"[INFO] Multiple target dialects detected: {', '.join(target_dialects)}, retrying sequentially...")
            data_dir = task_config.raw_config.get('data_dir')

            for dialect in target_dialects:
                sub_task_config = copy.deepcopy(task_config)
                sub_task_config.raw_config['target_dialect'] = dialect

                # If data_dir is set, resolve per-dialect data file
                if data_dir:
                    dialect_data_path = os.path.join(data_dir, f"{dialect}.json")
                    sub_task_config.data_path = dialect_data_path
                    sub_task_config.raw_config['data_path'] = dialect_data_path

                display_name = f"{task_name} ({dialect})"
                print(f"\n{'-' * 40}")
                print(f"[SUBTASK RETRY] {display_name}")
                print(f"{'-' * 40}")

                sub_task_key = f"{task_name}_{dialect}"
                self._run_task_retry(sub_task_key, sub_task_config, max_retry_rounds)
        else:
            self._run_task_retry(task_name, task_config, max_retry_rounds)

    def _run_task_retry(self, task_name: str, task_config: TaskConfig, max_retry_rounds: int = 3):
        """
        Retry API-failed items for a single task instance.

        Flow:
        1. Read existing predictions.json
        2. Find samples with prediction = null
        3. Re-infer only those samples
        4. Merge results
        5. Re-save and re-evaluate
        """
        task_type = task_config.name

        predictions_file = Path(self.global_config.output_dir) / task_name / "predictions.json"
        if not predictions_file.exists():
            print(f"[ERROR] No existing predictions found: {predictions_file}")
            print(f"  Please run the task normally first to generate predictions.")
            return

        print(f"[INFO] Reading existing predictions: {predictions_file}")
        with open(predictions_file, 'r', encoding='utf-8') as f:
            existing_records = json.load(f)

        total_count = len(existing_records)
        failed_indices = [i for i, r in enumerate(existing_records) if r.get('prediction') is None]

        if not failed_indices:
            print(f"[OK] No API-failed samples, no retry needed!")
            self.task_results[task_name] = {
                "predictions_file": str(predictions_file),
                "evaluation_file": str(Path(self.global_config.output_dir) / task_name / "evaluation.json"),
                "metrics": None,
                "api_error_count": 0
            }
            return

        print(f"  Total samples: {total_count}")
        print(f"  API failures: {len(failed_indices)}")
        print()

        resources = self._get_task_resources(task_type, task_config)
        samples = resources['samples']

        if len(samples) != total_count:
            print(f"[WARNING] Sample count ({len(samples)}) != prediction count ({total_count})!")
            print(f"  Skipping retry. Please check data consistency.")
            return

        print(f"[INFO] Initializing task {task_name}...")
        task = self._create_task(task_type, task_config, resources)
        print(f"[OK] Task initialized")
        print()

        predictions = [r.get('prediction') for r in existing_records]

        # Multi-round retry
        for round_num in range(1, max_retry_rounds + 1):
            current_failed = [i for i, p in enumerate(predictions) if p is None]

            if not current_failed:
                print(f"[OK] All samples succeeded, no further retry needed!")
                break

            print(f"[INFO] Retry round {round_num}/{max_retry_rounds}")
            print(f"  Samples to retry: {len(current_failed)}")

            failed_samples = [samples[i] for i in current_failed]

            retry_predictions = task.infer_batch(
                samples=failed_samples,
                num_workers=self.global_config.num_workers,
                show_progress=self.global_config.show_progress
            )

            recovered_count = 0
            still_failed = 0
            for idx, retry_pred in zip(current_failed, retry_predictions):
                if retry_pred is not None:
                    predictions[idx] = retry_pred
                    existing_records[idx]['prediction'] = retry_pred
                    if hasattr(samples[idx], 'metadata'):
                        existing_records[idx]['full_response'] = samples[idx].metadata.get('_debug_response', '')
                        existing_records[idx]['prompt'] = samples[idx].metadata.get('_debug_prompt', existing_records[idx].get('prompt', ''))
                    recovered_count += 1
                else:
                    still_failed += 1

            print(f"  Recovered: {recovered_count}, Still failed: {still_failed}")
            print()

            if still_failed == 0:
                break

        final_failed = sum(1 for p in predictions if p is None)
        api_error_count = final_failed
        print(f"[INFO] Retry summary:")
        print(f"  Original failures: {len(failed_indices)}")
        print(f"  Recovered: {len(failed_indices) - final_failed}")
        print(f"  Final failures: {final_failed}")
        print()

        # Restore debug info in samples
        for i in range(len(samples)):
            if not hasattr(samples[i], 'metadata'):
                samples[i].metadata = {}
            if '_debug_prompt' not in samples[i].metadata and 'prompt' in existing_records[i]:
                samples[i].metadata['_debug_prompt'] = existing_records[i].get('prompt', '')
            if '_debug_response' not in samples[i].metadata and 'full_response' in existing_records[i]:
                samples[i].metadata['_debug_response'] = existing_records[i].get('full_response', '')

        # Save updated predictions
        print(f"[INFO] Saving updated predictions...")
        updated_records = [task.to_record(sample, pred) for sample, pred in zip(samples, predictions)]

        output_dir = Path(self.global_config.output_dir) / task_name
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(predictions_file, 'w', encoding='utf-8') as f:
            json.dump(updated_records, f, indent=2, ensure_ascii=False)
        print(f"[OK] Predictions updated: {predictions_file}")
        print()

        # Re-evaluate
        eval_file = None
        metrics = None

        skip_eval = task_config.raw_config.get('skip_eval', False)
        if not skip_eval and self._has_ground_truth(task, samples):
            print(f"[INFO] Running evaluation ({self.global_config.eval_workers} workers)...")

            ground_truths = [task.get_ground_truth(s) for s in samples]

            metrics = task.evaluate(
                predictions=predictions,
                ground_truths=ground_truths,
                samples=samples,
                num_workers=self.global_config.eval_workers,
                timeout=self.global_config.timeout
            )

            print(f"[OK] Evaluation complete")
            for k, v in metrics.items():
                if isinstance(v, (int, float)):
                    display_key = k.replace('_', ' ').title()
                    if isinstance(v, float):
                        print(f"  {display_key}: {v:.4f}")
                    else:
                        print(f"  {display_key}: {v}")
            print()

            eval_file_path = output_dir / "evaluation.json"
            eval_result = {"metrics": metrics, "results": updated_records}
            with open(eval_file_path, 'w', encoding='utf-8') as f:
                json.dump(eval_result, f, indent=2, ensure_ascii=False)
            eval_file = str(eval_file_path)
            print(f"[OK] Evaluation saved: {eval_file}")
            print()

            self.task_results[task_name] = {
                "predictions_file": str(predictions_file),
                "evaluation_file": eval_file,
                "metrics": metrics,
                "api_error_count": api_error_count
            }
        else:
            self.task_results[task_name] = {
                "predictions_file": str(predictions_file),
                "evaluation_file": None,
                "metrics": None,
                "api_error_count": api_error_count
            }
            if skip_eval:
                print("[INFO] Evaluation skipped (skip_eval=true in config)")
            else:
                print("[WARNING] No ground truth available, skipping evaluation")
            print()

    def _run_task_instance(self, task_name: str, task_config: TaskConfig):
        """
        Execute a specific task instance. Supports checkpoint/resume:
        - Uses JSONL file for immediate result storage.
        - Automatically skips completed samples on re-run.
        - Converts to standard predictions.json format at the end.
        """
        task_type = task_config.name

        # Use task_name (e.g. "sql_trans_oracle") as cache key to avoid
        # cross-dialect data collision when the same task_type has multiple sub-tasks.
        resources = self._get_task_resources(task_name, task_config)
        samples = resources['samples']

        # Create task instance
        print(f"[INFO] Initializing task '{task_name}'...")
        task = self._create_task(task_type, task_config, resources)
        print(f"[OK] Task initialized")
        print()

        # Check for existing JSONL intermediate results (checkpoint/resume)
        output_dir = Path(self.global_config.output_dir) / task_name
        output_dir.mkdir(parents=True, exist_ok=True)
        jsonl_file = output_dir / "predictions.jsonl"

        # Load completed records
        completed_records = {}  # sample_id -> record dict
        if jsonl_file.exists():
            print(f"[INFO] Found intermediate results: {jsonl_file}")
            with open(jsonl_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            record = json.loads(line)
                            sid = record.get("id")
                            pred = record.get("prediction")
                            if sid is not None and pred is not None:
                                completed_records[sid] = record
                        except json.JSONDecodeError:
                            continue
            print(f"  Completed: {len(completed_records)}/{len(samples)}")

        # Filter pending samples
        pending_indices = []
        for i, sample in enumerate(samples):
            if sample.id not in completed_records:
                pending_indices.append(i)
        pending_samples = [samples[i] for i in pending_indices]

        print(f"  Total: {len(samples)}, Completed: {len(completed_records)}, Pending: {len(pending_samples)}")
        print()

        # Inference (only pending samples)
        if pending_samples:
            print(f"[INFO] Running inference ({self.global_config.num_workers} workers)...")

            write_lock = threading.Lock()

            def on_result(batch_idx, sample, prediction):
                """Write each result immediately to JSONL file."""
                record = task.to_record(sample, prediction)
                with write_lock:
                    with open(jsonl_file, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(record, ensure_ascii=False) + '\n')

            predictions_for_pending = task.infer_batch(
                samples=pending_samples,
                num_workers=self.global_config.num_workers,
                show_progress=self.global_config.show_progress,
                on_result=on_result
            )

            new_success = sum(1 for p in predictions_for_pending if p is not None)
            new_fail = sum(1 for p in predictions_for_pending if p is None)
            print(f"[OK] Inference complete")
            print(f"  Success: {new_success}, Failed: {new_fail}")
        else:
            print(f"[OK] All samples already completed, skipping inference")
        print()

        # Merge results from JSONL into final predictions.json
        print(f"[INFO] Merging results and saving predictions.json...")
        all_records = {}
        if jsonl_file.exists():
            with open(jsonl_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            record = json.loads(line)
                            sid = record.get("id")
                            if sid is not None:
                                all_records[sid] = record
                        except json.JSONDecodeError:
                            continue

        # Rebuild in original sample order
        predictions = []
        ordered_records = []
        for sample in samples:
            if sample.id in all_records:
                record = all_records[sample.id]
                predictions.append(record.get("prediction"))
                ordered_records.append(record)
            else:
                predictions.append(None)
                ordered_records.append(task.to_record(sample, None))

        predictions_file = output_dir / "predictions.json"
        with open(predictions_file, 'w', encoding='utf-8') as f:
            json.dump(ordered_records, f, indent=2, ensure_ascii=False)

        api_error_count = sum(1 for p in predictions if p is None)
        success_count = len(samples) - api_error_count
        print(f"[OK] Results saved to {predictions_file}")
        print(f"  Success: {success_count}/{len(samples)}")
        if api_error_count > 0:
            print(f"  [WARNING] API errors: {api_error_count}")
        print()

        # Evaluation
        eval_file = None
        metrics = None

        skip_eval = task_config.raw_config.get('skip_eval', False)
        if not skip_eval and self._has_ground_truth(task, samples):
            print(f"[INFO] Running evaluation ({self.global_config.eval_workers} workers)...")

            ground_truths = [task.get_ground_truth(s) for s in samples]

            metrics = task.evaluate(
                predictions=predictions,
                ground_truths=ground_truths,
                samples=samples,
                num_workers=self.global_config.eval_workers,
                timeout=self.global_config.timeout
            )

            print(f"[OK] Evaluation complete")
            for k, v in metrics.items():
                if isinstance(v, (int, float)):
                    display_key = k.replace('_', ' ').title()
                    if isinstance(v, float):
                        print(f"  {display_key}: {v:.4f}")
                    else:
                        print(f"  {display_key}: {v}")
            print()

            eval_file = self._save_evaluation(task_name, metrics, predictions, samples, task=task)
            print(f"[OK] Evaluation saved to {eval_file}")
            print()

            self.task_results[task_name] = {
                "predictions_file": str(predictions_file),
                "evaluation_file": str(eval_file),
                "metrics": metrics,
                "api_error_count": api_error_count
            }
        else:
            self.task_results[task_name] = {
                "predictions_file": str(predictions_file),
                "evaluation_file": None,
                "metrics": None,
                "api_error_count": api_error_count
            }
            if skip_eval:
                print("[INFO] Evaluation skipped (skip_eval=true in config)")
            else:
                print("[WARNING] No ground truth available, skipping evaluation")
            print()

    def _create_task(self, task_name: str, task_config: TaskConfig, resources: Dict[str, Any]):
        """
        Create task instance with injected resource context.
        Supports 3-level config merge: YAML task config > CLI global params > defaults.
        """
        context = TaskContext(
            llm_client=self.llm_client,
            db_env=resources.get('db_env'),
            schema_loader=resources.get('schema_loader'),
            global_config=self.global_config
        )

        # Base config from global CLI parameters
        task_inst_config = asdict(self.global_config)

        # Merge YAML task config (highest priority)
        task_inst_config.update(task_config.raw_config)

        # Inject internal context
        task_inst_config["task_type"] = task_name

        return TaskRegistry.get_task(task_name, task_inst_config, context)

    def _has_ground_truth(self, task: BaseTask, samples: List[Sample]) -> bool:
        """Check whether samples have ground truth annotations."""
        count = sum(1 for s in samples if task.has_ground_truth(s))
        if count == 0:
            return False
        if count < len(samples):
            print(f"  [WARNING] {len(samples)-count} samples missing GT (total {len(samples)}), evaluating only those with GT")
        return True

    def _save_predictions(
        self,
        task_name: str,
        predictions: List[str],
        samples: List[Sample],
        task: Any
    ) -> Path:
        """Save prediction results."""
        output_dir = Path(self.global_config.output_dir) / task_name
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / "predictions.json"
        results = [task.to_record(sample, pred) for sample, pred in zip(samples, predictions)]

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        return output_file

    def _save_evaluation(
        self,
        task_name: str,
        metrics: Dict[str, float],
        predictions: List[str],
        samples: List[Sample],
        task: Any
    ) -> Path:
        """Save evaluation results."""
        output_dir = Path(self.global_config.output_dir) / task_name
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / "evaluation.json"
        results = [task.to_record(sample, pred) for sample, pred in zip(samples, predictions)]

        eval_result = {
            "metrics": metrics,
            "results": results
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(eval_result, f, indent=2, ensure_ascii=False)

        return output_file

    def _print_summary(self):
        """Print execution summary."""
        print()
        print("=" * 80)
        print("[SUMMARY] Execution Summary")
        print("=" * 80)
        print()

        for task_name, result in self.task_results.items():
            print(f"  {task_name}:")
            print(f"    Predictions: {result['predictions_file']}")

            api_errors = result.get('api_error_count', 0)
            if api_errors > 0:
                print(f"    [WARNING] API errors: {api_errors}")

            if result['metrics']:
                metrics = result['metrics']
                for k, v in metrics.items():
                    if isinstance(v, (int, float)):
                        display_key = k.replace('_', ' ').title()
                        if isinstance(v, float):
                            print(f"    {display_key}: {v:.4f}")
                        else:
                            print(f"    {display_key}: {v}")
                print(f"    Evaluation: {result['evaluation_file']}")
            else:
                print(f"    Evaluation: skipped")
            print()

        print("=" * 80)
        print("[DONE] All tasks completed!")
        print("=" * 80)

    def close(self):
        """Release resources."""
        for task_name, resources in self.task_resources.items():
            db_env = resources.get('db_env')
            if db_env:
                db_env.close()
