"""Execution Evaluator for comparing SQL execution results."""

from typing import List, Dict, Tuple, Optional, Any
import sqlite3
import os
import multiprocessing as mp
from functools import partial
from tqdm import tqdm

from .base import BaseEvaluator
from ..envs.base import DBEnvironment
from ..core.sample import Sample


# ========== Process-level standalone functions (no class instance dependencies) ==========

def _preprocess_sql(sql: str) -> str:
    """Preprocess SQL string (strip whitespace and trailing semicolons)."""
    if not sql:
        return sql
    sql = sql.strip()
    while sql.endswith(';'):
        sql = sql[:-1].strip()
    return sql


def _compare_sql_standalone(args, db_dir: str, timeout: int):
    """
    Standalone SQL comparison function (each process creates its own connection).

    - Creates independent sqlite3 connection per invocation.
    - Uses func_timeout for timeout protection.
    - Wraps in transaction to avoid modifying the database.
    """
    from func_timeout import func_timeout, FunctionTimedOut

    idx, pred_sql, gt_sql, db_id, sample_id = args

    def _do_compare():
        db_path = os.path.join(db_dir, db_id, f"{db_id}.sqlite")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        correctness = 0
        pred_error = None
        gt_error = None

        try:
            pred_sql_clean = _preprocess_sql(pred_sql)
            gt_sql_clean = _preprocess_sql(gt_sql)

            conn.execute("BEGIN TRANSACTION;")

            # Execute GT SQL
            try:
                cursor.execute(gt_sql_clean)
                gt_result = cursor.fetchall()
                gt_success = True
            except Exception as e:
                gt_result = str(e)
                gt_success = False
                gt_error = str(e)

            # Execute predicted SQL
            try:
                cursor.execute(pred_sql_clean)
                pred_result = cursor.fetchall()
                pred_success = True
            except Exception as e:
                pred_result = str(e)
                pred_success = False
                pred_error = str(e)

            # Compare results (set comparison, order-independent)
            if pred_success and gt_success:
                if set(pred_result) == set(gt_result):
                    correctness = 1

            conn.rollback()
        except Exception as e:
            pred_error = str(e)
            try:
                conn.rollback()
            except:
                pass
        finally:
            conn.close()

        return correctness, pred_error, gt_error

    try:
        correctness, pred_error, gt_error = func_timeout(timeout, _do_compare)
    except FunctionTimedOut:
        correctness = 0
        pred_error = f"Timeout after {timeout}s"
        gt_error = None
    except Exception as e:
        correctness = 0
        pred_error = str(e)
        gt_error = None

    return {
        "idx": idx,
        "sample_id": sample_id,
        "pred_sql": pred_sql,
        "gt_sql": gt_sql,
        "correctness": correctness,
        "error": pred_error,
        "gt_error": gt_error
    }


def _compare_sql_with_env(args, env: DBEnvironment, timeout: int):
    """
    Generic SQL comparison function (for non-SQLite environments like MSSQL, Oracle, etc.).
    Executes via env.execute_sql with func_timeout protection.
    """
    from func_timeout import func_timeout, FunctionTimedOut

    idx, pred_sql, gt_sql, db_id, sample_id = args

    def _do_compare():
        pred_success, pred_result = env.execute_sql(pred_sql, db_id)
        gt_success, gt_result = env.execute_sql(gt_sql, db_id)

        correctness = 0
        pred_error = pred_result if not pred_success else None
        gt_error = gt_result if not gt_success else None

        if pred_success and gt_success:
            if set(pred_result) == set(gt_result):
                correctness = 1

        return correctness, pred_error, gt_error

    try:
        correctness, pred_error, gt_error = func_timeout(timeout, _do_compare)
    except FunctionTimedOut:
        correctness, pred_error, gt_error = 0, f"Timeout after {timeout}s", None
    except Exception as e:
        correctness, pred_error, gt_error = 0, str(e), None

    return {
        "idx": idx,
        "sample_id": sample_id,
        "pred_sql": pred_sql,
        "gt_sql": gt_sql,
        "correctness": correctness,
        "error": pred_error,
        "gt_error": gt_error
    }


def _execute_sql_standalone(args, db_dir: str, timeout: int):
    """
    Standalone SQL execution function (each process creates its own connection).
    Used by execute_sqls_parallel.
    """
    from func_timeout import func_timeout, FunctionTimedOut

    idx, sql, db_id = args

    def _do_execute():
        db_path = os.path.join(db_dir, db_id, f"{db_id}.sqlite")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            sql_clean = _preprocess_sql(sql)
            conn.execute("BEGIN TRANSACTION;")
            cursor.execute(sql_clean)
            result = cursor.fetchall()
            conn.rollback()
            conn.close()
            return True, result
        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            conn.close()
            return False, str(e)

    try:
        success, result = func_timeout(timeout, _do_execute)
    except FunctionTimedOut:
        success, result = False, f"Timeout after {timeout}s"
    except Exception as e:
        success, result = False, str(e)

    if success:
        try:
            query_result = frozenset(result)
            valid = 1
        except TypeError:
            query_result = result
            valid = 1
    else:
        query_result = None
        valid = 0

    return {
        "idx": idx,
        "sql": sql,
        "db_id": db_id,
        "query_result": query_result,
        "valid": valid,
        "error": result if not success else None
    }


# ========== Evaluator Class ==========

class ExecutionEvaluator(BaseEvaluator):
    """
    Execution Accuracy (EX) evaluator.

    Compares generated SQL and GT SQL execution results in the database.
    Uses set comparison (order-independent).
    """

    def evaluate(self, predictions: List[str], ground_truths: List[str]) -> Dict[str, float]:
        """Basic evaluate (no database execution)."""
        if not predictions:
            return {"accuracy": 0.0}
        return {"accuracy": 0.0}

    def evaluate_with_execution(
        self,
        predictions: List[str],
        ground_truths: List[str],
        samples: List[Sample],
        env: DBEnvironment,
        num_workers: int = 4,
        timeout: int = 20,
        show_progress: bool = True
    ) -> Dict[str, float]:
        """
        Execute SQL in database and compare result sets (supports concurrency).

        Args:
            predictions: Predicted SQL list.
            ground_truths: Ground truth SQL list.
            samples: Original sample list (containing db_id, etc.)
            env: Database environment.
            num_workers: Number of worker processes (default 4).
            timeout: SQL execution timeout in seconds (default 20).
            show_progress: Whether to show progress bar.

        Returns:
            Metrics dict {"accuracy": float, "correct": int, "total": int}
        """
        if not predictions:
            return {"accuracy": 0.0, "correct": 0, "total": 0}

        total = len(predictions)

        # Determine if SQLite environment
        from ..envs.sqlite_env import SQLiteEnv
        is_sqlite = isinstance(env, SQLiteEnv)

        db_dir = getattr(env, 'db_dir', None)

        # Use multiprocessing for concurrent SQL comparison
        evaluation_results = self._evaluate_sqls_parallel(
            predictions=predictions,
            ground_truths=ground_truths,
            samples=samples,
            db_dir=db_dir,
            env=env,
            is_sqlite=is_sqlite,
            num_workers=num_workers,
            timeout=timeout,
            show_progress=show_progress
        )

        # Count correct results
        correct = sum(1 for res in evaluation_results if res.get("correctness", 0) == 1)

        accuracy = correct / total if total > 0 else 0
        return {
            "accuracy": accuracy,
            "correct": correct,
            "total": total
        }

    def _evaluate_sqls_parallel(
        self,
        predictions: List[str],
        ground_truths: List[str],
        samples: List[Sample],
        db_dir: Optional[str],
        env: DBEnvironment,
        is_sqlite: bool,
        num_workers: int,
        timeout: int,
        show_progress: bool
    ) -> List[Dict[str, Any]]:
        """
        Concurrent SQL comparison.

        For SQLite: uses _compare_sql_standalone (each process creates own connection).
        For other DBs: uses _compare_sql_with_env (executes via env object).

        Uses apply_async + callback pattern to avoid sequential blocking.
        """
        evaluation_results = []
        pbar = None

        def _callback(result):
            evaluation_results.append(result)
            if pbar:
                pbar.update(1)

        def _error_callback(e):
            evaluation_results.append({"correctness": 0, "error": str(e)})
            if pbar:
                pbar.update(1)

        # Prepare task arguments
        task_args_list = [
            (idx, pred_sql, gt_sql, sample.db_id, sample.id)
            for idx, (pred_sql, gt_sql, sample) in enumerate(
                zip(predictions, ground_truths, samples)
            )
        ]

        # Select comparison function
        if is_sqlite and db_dir:
            compare_fn = partial(_compare_sql_standalone, db_dir=db_dir, timeout=timeout)
        else:
            compare_fn = partial(_compare_sql_with_env, env=env, timeout=timeout)

        if show_progress:
            pbar = tqdm(total=len(task_args_list), desc="Evaluating")

        # Use apply_async (non-blocking)
        pool = mp.Pool(processes=num_workers)
        for task_args in task_args_list:
            pool.apply_async(
                compare_fn,
                args=(task_args,),
                callback=_callback,
                error_callback=_error_callback
            )
        pool.close()
        pool.join()

        if pbar:
            pbar.close()

        # Sort by idx to maintain order consistency
        evaluation_results.sort(key=lambda x: x.get("idx", 0))

        return evaluation_results

    def execute_sqls_parallel(
        self,
        sqls: List[str],
        db_ids: List[str],
        env: DBEnvironment,
        num_workers: int = 4,
        timeout: int = 10,
        show_progress: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple SQL statements concurrently.

        Use cases:
        - Rejection Sampling: execute multiple generated SQLs concurrently.
        - Majority Voting: validate candidate SQL validity concurrently.
        """
        db_dir = getattr(env, 'db_dir', None)
        if db_dir is None:
            raise RuntimeError("DBEnvironment must have 'db_dir' attribute for parallel execution.")

        execution_results = []
        pbar = None

        def _callback(result):
            execution_results.append(result)
            if pbar:
                pbar.update(1)

        def _error_callback(e):
            execution_results.append({"valid": 0, "error": str(e)})
            if pbar:
                pbar.update(1)

        task_args_list = [
            (idx, sql, db_id)
            for idx, (sql, db_id) in enumerate(zip(sqls, db_ids))
        ]

        execute_fn = partial(_execute_sql_standalone, db_dir=db_dir, timeout=timeout)

        if show_progress:
            pbar = tqdm(total=len(task_args_list), desc="Executing SQLs")

        pool = mp.Pool(processes=num_workers)
        for task_args in task_args_list:
            pool.apply_async(
                execute_fn,
                args=(task_args,),
                callback=_callback,
                error_callback=_error_callback
            )
        pool.close()
        pool.join()

        if pbar:
            pbar.close()

        execution_results.sort(key=lambda x: x.get("idx", 0))

        return execution_results

    @classmethod
    def _results_equal(cls, result1: List[Tuple], result2: List[Tuple]) -> bool:
        """Compare two result sets for equality."""
        try:
            norm_res1 = cls._normalize_result(result1)
            norm_res2 = cls._normalize_result(result2)
            return norm_res1 == norm_res2
        except Exception:
            return result1 == result2

    @classmethod
    def _normalize_result(cls, result: List[Tuple]) -> Any:
        """
        Normalize result set. Default: convert to set for order-independent comparison.
        Subclasses may override for more complex normalization (e.g., precision alignment).
        """
        try:
            return set(result)
        except TypeError:
            try:
                return frozenset(tuple(row) for row in result)
            except TypeError:
                return result
