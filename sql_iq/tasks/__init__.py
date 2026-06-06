"""
Task implementations for SQL-IQ benchmark.

Tasks are auto-registered via the @TaskRegistry.register decorator.
Import all task modules here to trigger registration.
"""

from . import text2sql
from . import conversational_sql
from . import sql_judge
from . import sql_equ_judge
from . import sql_err_class
from . import sql_trans
