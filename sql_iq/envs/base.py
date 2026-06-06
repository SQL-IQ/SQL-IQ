"""Database environment abstraction."""

from abc import ABC, abstractmethod
from typing import Tuple, Any


class DBEnvironment(ABC):
    """
    Abstract interface for database execution environments.

    Supported backends:
    - SQLite: local .sqlite files
    - PostgreSQL, Oracle, MSSQL, ClickHouse, Druid: network-based connections
    """

    def preprocess_sql(self, sql: str) -> str:
        """
        Preprocess SQL string (strip whitespace and trailing semicolons).
        """
        if not sql:
            return sql
        sql = sql.strip()
        while sql.endswith(';'):
            sql = sql[:-1].strip()
        return sql

    @abstractmethod
    def execute_sql(self, sql: str, db_id: str) -> Tuple[bool, Any]:
        """
        Execute SQL and return results.

        Args:
            sql: SQL query string.
            db_id: Database ID (used to locate the specific database file or schema).

        Returns:
            (success, result)
            - success (bool): Whether execution succeeded.
            - result: On success: list of row tuples. On failure: error message string.
        """
        pass

    @abstractmethod
    def close(self):
        """Release resources (e.g., close connections)."""
        pass
