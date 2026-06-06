"""ClickHouse database environment implementation."""

from typing import Tuple, Any

try:
    import clickhouse_connect
except ImportError:
    clickhouse_connect = None

from .base import DBEnvironment
from .registry import DBRegistry


@DBRegistry.register("clickhouse")
class ClickHouseEnv(DBEnvironment):
    """
    ClickHouse execution environment.
    Uses clickhouse_connect (HTTP protocol) for connection.
    """

    def __init__(self, db_dir: str = None):
        self.db_dir = db_dir
        self.host = 'localhost'
        self.port = 8124
        self.username = 'default'
        self.password = ''

    def execute_sql(self, sql: str, db_id: str) -> Tuple[bool, Any]:
        if not clickhouse_connect:
            return False, "Error: clickhouse-connect package not installed. Install with: pip install clickhouse-connect"

        sql = self.preprocess_sql(sql)

        try:
            client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                database=db_id if db_id else 'default',
            )
            result = client.query(sql)
            rows = result.result_rows
            client.close()
            return True, rows
        except Exception as e:
            return False, str(e)

    def close(self):
        pass
