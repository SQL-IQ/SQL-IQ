"""Oracle database environment implementation."""

from typing import Tuple, Any

try:
    import oracledb
except ImportError:
    oracledb = None

from .base import DBEnvironment
from .registry import DBRegistry


@DBRegistry.register("oracle")
class OracleEnv(DBEnvironment):
    """
    Oracle Database execution environment.
    Connects via python-oracledb to an Oracle instance.
    """

    def __init__(self, db_dir: str = None):
        self.db_dir = db_dir
        self.user = "system"
        self.password = "123456"
        self.dsn = "localhost:1521/xe"

    def output_type_handler(self, cursor, name, default_type, size, precision, scale):
        """
        Handle Oracle LOB types by automatically converting them
        to string or bytes.
        """
        if default_type == oracledb.CLOB:
            return cursor.var(str, arraysize=cursor.arraysize)
        if default_type == oracledb.BLOB:
            return cursor.var(bytes, arraysize=cursor.arraysize)

    def execute_sql(self, sql: str, db_id: str) -> Tuple[bool, Any]:
        if not oracledb:
            return False, "Error: oracledb package not installed. Install with: pip install oracledb"

        sql = self.preprocess_sql(sql)

        current_user = db_id.upper() if db_id else self.user
        current_password = "Bird123456"

        try:
            conn = oracledb.connect(
                user=current_user,
                password=current_password,
                dsn=self.dsn
            )

            # Register type handler for LOB auto-conversion
            conn.outputtypehandler = self.output_type_handler

            cursor = conn.cursor()

            # Set session date format for consistent output
            try:
                cursor.execute("ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS'")
            except:
                pass

            cursor.execute(sql)
            rows = cursor.fetchall()
            conn.close()
            return True, rows
        except Exception as e:
            return False, str(e)

    def close(self):
        pass
