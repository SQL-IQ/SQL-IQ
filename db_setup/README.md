# Database Setup

This directory provides Docker configurations and data migration scripts to set up the 5 target SQL dialect databases for SQL-IQ evaluation.

## Prerequisites

- Docker & Docker Compose
- [BIRD dev databases](https://bird-bench.github.io/) (the `dev_databases/` directory containing SQLite files)
- Python 3.8+ with the following packages:

```bash
# Oracle
pip install oracledb
# PostgreSQL
pip install psycopg2-binary
# ClickHouse
pip install clickhouse-connect pandas sqlalchemy
# MSSQL
pip install pymssql
# Druid
pip install requests
```

## Usage

Each dialect has its own directory with a `docker-compose.yml` and an `insert_to_*.py` script.

```bash
# 1. Start the database container
cd <dialect>/
docker compose up -d

# 2. Run the migration script
python insert_to_<dialect>.py --bird-root /path/to/bird/dev_databases
```

All scripts also support the `BIRD_ROOT` environment variable:

```bash
export BIRD_ROOT=/path/to/bird/dev_databases
python insert_to_<dialect>.py
```

## Dialects

| Dialect | Directory | Notes |
|---------|-----------|-------|
| Oracle | `oracle/` | Takes ~3-5 min to initialize on first start |
| PostgreSQL | `postgresql/` | Ready in seconds |
| ClickHouse | `clickhouse/` | Ready in seconds |
| MSSQL | `mssql/` | Ready in ~10 seconds |
| Druid | `druid/` | Multi-container setup, wait ~1-2 min; console at http://localhost:8888 |

