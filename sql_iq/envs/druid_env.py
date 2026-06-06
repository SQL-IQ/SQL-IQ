"""Apache Druid database environment implementation."""

from typing import Tuple, Any

try:
    import requests
except ImportError:
    requests = None

from .base import DBEnvironment
from .registry import DBRegistry


@DBRegistry.register("druid")
class DruidEnv(DBEnvironment):
    """
    Druid execution environment.
    Uses HTTP REST API (Druid SQL endpoint) for query execution.
    """

    def __init__(self, db_dir: str = None):
        self.db_dir = db_dir
        self.sql_url = "http://localhost:8888/druid/v2/sql"
        self.timeout = 60

    def execute_sql(self, sql: str, db_id: str) -> Tuple[bool, Any]:
        if not requests:
            return False, "Error: requests package not installed. Install with: pip install requests"

        sql = self.preprocess_sql(sql)

        payload = {
            "query": sql,
            "context": {
                "maxSubqueryBytes": "auto",
                "useApproximateCountDistinct": False,
            }
        }

        try:
            response = requests.post(
                self.sql_url,
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                result_json = response.json()
                # Druid returns JSON array of dicts; convert to list of tuples
                rows = [tuple(row.values()) for row in result_json]
                return True, rows
            else:
                return False, f"Druid Error: HTTP {response.status_code}: {response.text[:500]}"
        except Exception as e:
            return False, f"Druid Error: {str(e)}"

    def close(self):
        pass
