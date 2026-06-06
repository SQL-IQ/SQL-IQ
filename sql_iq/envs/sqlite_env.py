"""SQLite database environment implementation."""

import sqlite3
import os
from typing import Tuple, Any

from .base import DBEnvironment
from .registry import DBRegistry


@DBRegistry.register("sqlite")
class SQLiteEnv(DBEnvironment):
    """
    SQLite local database execution environment.
    Executes SQL queries against local .sqlite files.
    """

    def __init__(self, db_dir: str):
        """
        Args:
            db_dir: Directory containing database files, e.g., "data/databases/bird"
        """
        self.db_dir = db_dir
        self.connections = {}  # {db_id: connection}

    def execute_sql(self, sql: str, db_id: str) -> Tuple[bool, Any]:
        """
        Execute SQL query.

        Args:
            sql: SQL query string.
            db_id: Database ID (used to locate .sqlite file).

        Returns:
            (success, result) - success=True: result is list of tuples;
            success=False: result is error message string.
        """
        sql = self.preprocess_sql(sql)

        try:
            conn = self._get_connection(db_id)
            cursor = conn.cursor()
            cursor.execute(sql)
            results = cursor.fetchall()
            return True, results
        except Exception as e:
            return False, str(e)

    def _get_connection(self, db_id: str) -> sqlite3.Connection:
        """
        Get or create a database connection.

        Args:
            db_id: Database ID.

        Returns:
            sqlite3.Connection object.

        Raises:
            FileNotFoundError: If the database file does not exist.
        """
        if db_id not in self.connections:
            db_path = os.path.join(self.db_dir, db_id, f"{db_id}.sqlite")
            if not os.path.exists(db_path):
                raise FileNotFoundError(f"Database file not found: {db_path}")
            conn = sqlite3.connect(db_path)
            self.connections[db_id] = conn
        return self.connections[db_id]

    def close(self):
        """Close all connections."""
        for conn in self.connections.values():
            conn.close()
        self.connections.clear()

    def __del__(self):
        """Destructor to ensure connections are closed."""
        self.close()
