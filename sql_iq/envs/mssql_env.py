"""Microsoft SQL Server (MSSQL) database environment implementation."""

from typing import Tuple, Any

try:
    import pymssql
except ImportError:
    pymssql = None

from .base import DBEnvironment
from .registry import DBRegistry


@DBRegistry.register("mssql")
class MSSQLEnv(DBEnvironment):
    """
    Microsoft SQL Server (T-SQL) execution environment.
    Connects via pymssql to a SQL Server instance.
    """

    def __init__(self, db_dir: str = None):
        self.db_dir = db_dir
        self.host = 'localhost'
        self.user = 'sa'
        self.password = 'Password123!'
        self.port = 1433

    def execute_sql(self, sql: str, db_id: str) -> Tuple[bool, Any]:
        if not pymssql:
            return False, "Error: pymssql package not installed. Install with: pip install pymssql"

        sql = self.preprocess_sql(sql)

        try:
            conn = pymssql.connect(
                server=self.host,
                user=self.user,
                password=self.password,
                port=self.port,
                database=db_id if db_id else "master",
                autocommit=True,
                timeout=30
            )
            cursor = conn.cursor()
            cursor.execute(sql)
            try:
                result = cursor.fetchall()
            except pymssql.OperationalError as e:
                # Handle cases where SQL doesn't return rows (e.g., UPDATE, INSERT)
                if "The statement did not return a result set" in str(e):
                    result = []
                else:
                    raise e
            conn.close()
            return True, result
        except Exception as e:
            return False, str(e)

    def close(self):
        pass
