# SQL-IQ: A Unified Benchmark for Holistic SQL Intelligence Evaluation

## Overview

**SQL-IQ** is a unified evaluation framework for assessing the holistic SQL intelligence of large language models (LLMs). While current evaluation paradigms heavily focus on single-turn Text-to-SQL generation, real-world database management demands a significantly broader set of capabilities, including error classification, cross-dialect translation, and deep query comprehension.

SQL-IQ systematically evaluates models across **four core dimensions** of SQL intelligence, encompassing **seven distinct tasks**:

| Dimension | Task | Description |
|-----------|------|-------------|
| **Generation** | Text-to-SQL | Translate natural language questions into SQL queries |
| **Generation** | Conversational SQL | Multi-turn context-aware SQL generation |
| **Comprehension** | SQL Equivalence Judge | Determine if two SQL queries are semantically equivalent |
| **Comprehension** | SQL Judge | Select the correct SQL from two candidates |
| **Debugging** | SQL Error Classification | Detect and classify error types in SQL queries |
| **Debugging** | SQL Debugging† | Fix buggy SQL queries given error messages |
| **Adaptation** | SQL Translation | Cross-dialect SQL translation (Oracle, PostgreSQL, ClickHouse, Druid, MSSQL) |

> †**SQL Debugging** is sourced from [BIRD-CRITIC](https://github.com/bird-bench/BIRD-CRITIC-1). Please refer to their repository for data and evaluation code.

## Installation

### Requirements

- Python >= 3.9
- An LLM serving endpoint compatible with the OpenAI API format (e.g., vLLM, TGI, or OpenAI API)

### Install Dependencies

```bash
# Clone the repository
git clone https://github.com/SQL-IQ/SQL-IQ.git
cd SQL-IQ

# Install core dependencies
pip install -r requirements.txt
```

> **Note:** Database drivers (psycopg2, oracledb, pymssql, clickhouse-connect) are only required for the **SQL Translation** task's execution-based evaluation. If you only need tasks without SQL execution (sql_judge, sql_equ_judge, sql_err_class), core dependencies are sufficient.

### Database Setup (for execution-based evaluation)

Tasks that require SQL execution (text2sql, conversational_sql, sql_trans) depend on the [BIRD](https://bird-bench.github.io/) benchmark's SQLite database files.

**Download BIRD databases:**

1. Visit https://bird-bench.github.io/ and download the **dev databases**.
2. Extract the database files to a local directory, e.g.:

```
/path/to/bird_databases/
├── california_schools/
│   └── california_schools.sqlite
├── card_games/
│   └── card_games.sqlite
├── ...
```

3. Update `configs/tasks_config.yaml` — replace all `<YOUR_BIRD_DB_DIR>` placeholders with the actual path:

```yaml
text2sql:
  db_dir: /path/to/bird_databases

conversational_sql:
  db_dir: /path/to/bird_databases

sql_trans:
  db_dir: /path/to/bird_databases
```

**For SQL Translation task:** The execution-based evaluation requires the 5 target dialect databases (Oracle, PostgreSQL, ClickHouse, MSSQL, Druid) to be running. See [`db_setup/README.md`](db_setup/README.md) for Docker configurations and data migration scripts.

## Usage

### Quick Start

```bash
# Run a single task
python -m sql_iq \
    --tasks_config configs/tasks_config.yaml \
    --tasks text2sql \
    --api_base http://localhost:8000/v1 \
    --model_name your-model-name \
    --api_key your-api-key \
    --run_name my_experiment

# Run multiple tasks
python -m sql_iq \
    --tasks_config configs/tasks_config.yaml \
    --tasks text2sql,sql_judge,sql_equ_judge \
    --api_base http://localhost:8000/v1 \
    --model_name your-model-name \
    --api_key your-api-key

# Run all tasks
python -m sql_iq \
    --tasks_config configs/tasks_config.yaml \
    --tasks text2sql,conversational_sql,sql_judge,sql_equ_judge,sql_err_class,sql_trans \
    --api_base http://localhost:8000/v1 \
    --model_name your-model-name \
    --api_key your-api-key
```

### Output Structure

Results are saved under the `results/` directory:

```
results/<run_name>/
├── text2sql/
│   ├── predictions.jsonl      # Model predictions with checkpointing
│   └── metrics.json           # Evaluation metrics
├── sql_judge/
│   ├── predictions.jsonl
│   └── metrics.json
└── ...
```
