"""Unified data loading utility."""

import json
from typing import List, Dict, Any
from dataclasses import fields
from ..core.sample import Sample


class DataLoader:
    """
    Unified data loading utility class.
    Supports JSON list and JSONL formats.
    """

    @staticmethod
    def load_samples(data_path: str) -> List[Sample]:
        """
        Load samples from a file. Supports JSON list or JSONL format.

        Args:
            data_path: Path to the data file.

        Returns:
            List of Sample objects.
        """
        samples = []
        # Get valid field names defined in Sample dataclass
        sample_field_names = {f.name for f in fields(Sample)}

        with open(data_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return []

            # Determine format
            if content.startswith('['):
                raw_data = json.loads(content)
            else:
                raw_data = [json.loads(line) for line in content.splitlines() if line.strip()]

            for i, data in enumerate(raw_data):
                # Ensure ID exists
                if "id" not in data:
                    data["id"] = i

                # Filter to fields defined in Sample dataclass
                init_args = {k: v for k, v in data.items() if k in sample_field_names and k != 'metadata'}

                # Store extra fields in metadata
                metadata = data.get("metadata", {})
                extra_data = {k: v for k, v in data.items() if k not in sample_field_names}
                metadata.update(extra_data)

                sample = Sample(**init_args, metadata=metadata)
                samples.append(sample)

        return samples
