"""SQL Translation Evaluator with cross-dialect normalization."""

from typing import List, Tuple, Any
from decimal import Decimal
import datetime
import re
from dateutil import parser as date_parser

from .execution import ExecutionEvaluator


class SQLTransEvaluator(ExecutionEvaluator):
    """
    Specialized evaluator for SQL Translation task.
    Inherits from ExecutionEvaluator; overrides normalization logic to support
    cross-database precision alignment and type tolerance.
    """

    @classmethod
    def _normalize_val(cls, val: Any) -> Any:
        """
        Normalize a single value for cross-dialect comparison.

        Handles:
        - Numeric types: round to 3 decimal places.
        - Date/time types: format as 'YYYY-MM-DD HH:MM:SS'.
        - Bytes: decode to UTF-8.
        - Strings: strip whitespace, parse date patterns.
        - None: keep as-is.
        """
        if isinstance(val, (int, float, Decimal)):
            try:
                return round(float(val), 3)
            except:
                pass
        elif isinstance(val, (datetime.date, datetime.datetime, datetime.time, datetime.timedelta)):
            if isinstance(val, datetime.datetime):
                return val.strftime('%Y-%m-%d %H:%M:%S')
            return str(val)
        elif isinstance(val, bytes):
            try:
                return val.decode('utf-8')
            except:
                pass
        elif isinstance(val, str):
            val = val.strip()
            # Try to normalize date-like strings
            time_pattern = r'^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?$'
            if re.match(time_pattern, val):
                try:
                    dt = date_parser.parse(val)
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    pass
            return val
        elif val is None:
            return None

        # All other types: convert to string for comparison
        return str(val)

    @classmethod
    def _normalize_result(cls, result: List[Tuple]) -> Any:
        """
        Override result set normalization: preprocess each row and column.
        """
        try:
            normalized_rows = []
            for row in result:
                normalized_rows.append(tuple(cls._normalize_val(v) for v in row))
            return set(normalized_rows)
        except Exception:
            return super()._normalize_result(result)
