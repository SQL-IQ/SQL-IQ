"""PostgreSQL database environment implementation."""

from typing import Tuple, Any

try:
    import psycopg2
except ImportError:
    psycopg2 = None

from .base import DBEnvironment
from .registry import DBRegistry


@DBRegistry.register("postgresql")
class PostgresEnv(DBEnvironment):
    """
    PostgreSQL execution environment.
    Connects via psycopg2 to a PostgreSQL instance.
    """

    def __init__(self, db_dir: str = None):
        self.db_dir = db_dir
        self.host = 'localhost'
        self.user = 'postgres'
        self.password = '123456'
        self.port = "5432"

    def execute_sql(self, sql: str, db_id: str) -> Tuple[bool, Any]:
        if not psycopg2:
            return False, "Error: psycopg2 package not installed. Install with: pip install psycopg2-binary"

        sql = self.preprocess_sql(sql)

        try:
            conn = psycopg2.connect(
                database=db_id if db_id else "postgres",
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port
            )
            cursor = conn.cursor()
            cursor.execute(sql)
            result = cursor.fetchall()
            conn.close()
            return True, result
        except Exception as e:
            return False, str(e)

    def close(self):
        pass
