"""
Database execution environments for SQL evaluation.

Supported databases:
- SQLite (built-in, no extra dependencies)
- PostgreSQL (requires psycopg2-binary)
- Oracle (requires oracledb)
- MSSQL / SQL Server (requires pymssql)
- ClickHouse (requires clickhouse-connect)
- Druid (requires requests)
"""

from .base import DBEnvironment
from .registry import DBRegistry
from .sqlite_env import SQLiteEnv
from .postgres_env import PostgresEnv
from .oracle_env import OracleEnv
from .mssql_env import MSSQLEnv
from .clickhouse_env import ClickHouseEnv
from .druid_env import DruidEnv

__all__ = [
    "DBEnvironment", "DBRegistry",
    "SQLiteEnv", "PostgresEnv", "OracleEnv",
    "MSSQLEnv", "ClickHouseEnv", "DruidEnv",
]
