"""Schema loader for loading and managing SQL schemas."""

import json
from typing import Dict, Optional, List


class SchemaLoader:
    """
    Load schema information from a JSON file.

    Supported formats:

    Format 1 - List:
    [
        {"db_id": "bird_001", "schema": "CREATE TABLE users (...);\n..."},
        {"db_id": "bird_002", "schema": "CREATE TABLE products (...);\n..."}
    ]

    Format 2 - Dictionary:
    {
        "bird_001": "CREATE TABLE users (...);\n...",
        "bird_002": "CREATE TABLE products (...);\n..."
    }

    Format 3 - JSONL (one JSON object per line).
    """

    def __init__(self, schema_file_path: str):
        """
        Initialize SchemaLoader.

        Args:
            schema_file_path: Path to the schema JSON file.

        Raises:
            FileNotFoundError: If the schema file does not exist.
        """
        self.schema_file_path = schema_file_path
        self._schemas = {}
        self._load_all()

    def _load_all(self):
        """Load all schemas into memory cache. Supports JSON list, JSON dict, and JSONL."""
        try:
            with open(self.schema_file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return

                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    # If full JSON parse fails, try JSONL (one object per line)
                    f.seek(0)
                    data = []
                    for line in f:
                        line = line.strip()
                        if line:
                            data.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse schema file: {self.schema_file_path}, error: {e}")
            return
        except Exception as e:
            print(f"[ERROR] Failed to read schema file: {self.schema_file_path}, error: {e}")
            return

        if isinstance(data, list):
            # List format: [{db_id, schema}, ...]
            for item in data:
                db_id = item.get("db_id") or item.get("db_name")
                schema = item.get("schema", "")
                if db_id:
                    self._schemas[db_id] = schema
        elif isinstance(data, dict):
            # Dictionary format: {db_id -> schema}
            self._schemas = data

    def get_schema(self, db_id: str) -> Optional[str]:
        """
        Get schema for a given db_id.

        Args:
            db_id: Database ID.

        Returns:
            Schema string, or None if not found.
        """
        return self._schemas.get(db_id)

    def fill_schema_in_samples(self, samples: List):
        """
        Populate schema_str field for each sample in the list.

        This is a key step in the loading flow:
        1. Samples are loaded from JSONL with db_id.
        2. This method looks up the schema by db_id.
        3. Populates sample.schema_str with the actual DDL.
        4. build_prompt() can then directly use sample.schema_str.

        Args:
            samples: List of Sample objects.
        """
        for sample in samples:
            if sample.db_id:
                sample.schema_str = self.get_schema(sample.db_id)
                if sample.schema_str is None:
                    print(f"[WARNING] Schema not found for db_id '{sample.db_id}'")
                    sample.schema_str = ""
