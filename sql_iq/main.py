"""
SQL-IQ: Unified task execution entry point.

Usage:
    # Using task configuration file (recommended)
    python -m sql_iq --tasks_config configs/tasks_config.yaml --tasks text2sql,sql_judge

    # Using global configuration (all tasks share)
    python -m sql_iq --data data/text2sql/dev.jsonl \\
        --schema data/schemas/bird_dev.jsonl \\
        --db_dir data/databases \\
        --tasks text2sql
"""

import argparse
import sys
from pathlib import Path

from .pipeline import Pipeline, PipelineConfig


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="SQL-IQ Evaluation Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Using task config file (recommended)
    python -m sql_iq --tasks_config configs/tasks_config.yaml \\
        --tasks text2sql,sql_judge

    # Using global config
    python -m sql_iq --data data/text2sql/dev.jsonl \\
        --schema data/schemas/bird_dev.jsonl \\
        --db_dir data/databases \\
        --tasks text2sql

    # Debug mode
    python -m sql_iq --tasks_config configs/tasks_config.yaml \\
        --tasks text2sql --debug --no_progress
        """
    )

    # ========== Task Configuration ==========
    parser.add_argument(
        "--tasks_config",
        type=str,
        default=None,
        help="Task configuration file path (YAML format, optional)"
    )

    parser.add_argument(
        "--tasks",
        type=str,
        default="text2sql",
        help="Tasks to run (comma-separated, default: text2sql). "
             "Available: text2sql, conversational_sql, sql_judge, "
             "sql_equ_judge, sql_err_class, sql_trans"
    )

    # ========== Data Parameters (when not using task config file) ==========
    parser.add_argument(
        "--data",
        type=str,
        default=None,
        help="Sample data file path (JSONL format, optional)"
    )

    parser.add_argument(
        "--schema",
        type=str,
        default=None,
        help="Schema file path (JSON format, optional)"
    )

    parser.add_argument(
        "--db_dir",
        type=str,
        default=None,
        help="Database file directory (optional)"
    )

    # ========== LLM Parameters ==========
    parser.add_argument(
        "--api_base",
        type=str,
        default="http://localhost:8000/v1",
        help="LLM API server address (default: http://localhost:8000/v1)"
    )

    parser.add_argument(
        "--model_name",
        type=str,
        default="meta-llama/Llama-2-7b-hf",
        help="LLM model name (default: meta-llama/Llama-2-7b-hf)"
    )

    parser.add_argument(
        "--api_key",
        type=str,
        default="dummy",
        help="API key (default: dummy)"
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="LLM temperature (default: 0.0)"
    )

    parser.add_argument(
        "--max_tokens",
        type=int,
        default=4096,
        help="LLM maximum generation tokens"
    )

    parser.add_argument(
        "--top_p",
        type=float,
        default=1.0,
        help="LLM top-p sampling parameter"
    )

    # ========== Inference & Evaluation Parameters ==========
    parser.add_argument(
        "--run_name",
        type=str,
        default=None,
        help="Run name (results will be saved under results/run_name/)"
    )

    parser.add_argument(
        "--num_workers",
        type=int,
        default=16,
        help="Inference concurrency (default: 16)"
    )

    parser.add_argument(
        "--batch_size",
        type=int,
        default=None,
        help="Batch size (optional)"
    )

    # ========== Evaluation Parameters ==========
    parser.add_argument(
        "--eval_workers",
        type=int,
        default=32,
        help="Evaluation concurrency (default: 32)"
    )

    # ========== Output Parameters ==========
    parser.add_argument(
        "--output",
        type=str,
        default="results",
        help="Output directory (default: results)"
    )

    parser.add_argument(
        "--prompt_template",
        type=str,
        default=None,
        help="Prompt template file path (optional)"
    )

    # ========== Retry Parameters ==========
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Retry mode: read existing predictions.json, only re-infer API-failed samples"
    )

    parser.add_argument(
        "--max_retry_rounds",
        type=int,
        default=3,
        help="Maximum retry rounds (default: 3)"
    )

    # ========== Other Parameters ==========
    parser.add_argument(
        "--no_progress",
        action="store_true",
        help="Disable progress bar"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Debug mode (process only the first 5 samples)"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    try:
        args = parse_args()

        # ========== Argument Validation ==========
        has_tasks_config = args.tasks_config and Path(args.tasks_config).exists()
        has_global_config = all([args.data, args.schema, args.db_dir])

        if not has_tasks_config and not has_global_config:
            print("[ERROR] Must provide one of the following:")
            print("  1. --tasks_config (task configuration file)")
            print("  2. --data, --schema, --db_dir (global configuration)")
            sys.exit(1)

        if has_global_config:
            if not Path(args.data).exists():
                print(f"[ERROR] Data file not found: {args.data}")
                sys.exit(1)
            if not Path(args.schema).exists():
                print(f"[ERROR] Schema file not found: {args.schema}")
                sys.exit(1)
            if not Path(args.db_dir).exists():
                print(f"[ERROR] Database directory not found: {args.db_dir}")
                sys.exit(1)

        # ========== Create Global Config ==========
        global_config = PipelineConfig(
            api_base=args.api_base,
            model_name=args.model_name,
            api_key=args.api_key,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            top_p=args.top_p,
            num_workers=args.num_workers,
            batch_size=args.batch_size,
            eval_workers=args.eval_workers,
            output_dir=args.output,
            show_progress=not args.no_progress,
            debug=args.debug,
        )

        if args.run_name:
            global_config.output_dir = str(Path(args.output) / args.run_name)

        # Fallback task config (when not using config file)
        fallback_task_config = None
        if has_global_config:
            fallback_task_config = {
                "data_path": args.data,
                "schema_path": args.schema,
                "db_dir": args.db_dir,
                "prompt_template": args.prompt_template,
            }

        # ========== Create and Run Pipeline ==========
        pipeline = Pipeline(
            global_config=global_config,
            tasks_config_path=args.tasks_config if has_tasks_config else None,
            fallback_task_config=fallback_task_config
        )

        task_names = [t.strip() for t in args.tasks.split(',') if t.strip()]

        if args.retry:
            pipeline.run(task_names, retry=True, max_retry_rounds=args.max_retry_rounds)
        else:
            pipeline.run(task_names)

        pipeline.close()

    except KeyboardInterrupt:
        print("\n[WARNING] Interrupted by user")
        sys.exit(1)

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
