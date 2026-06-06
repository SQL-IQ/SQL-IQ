"""Task execution context encapsulating shared resources."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TaskContext:
    """
    Task execution context that holds shared resources.

    Attributes:
        llm_client: LLM API client instance.
        db_env: Database execution environment (optional).
        schema_loader: Schema loader instance (optional).
        global_config: Global pipeline configuration (optional).
    """
    llm_client: Any
    db_env: Optional[Any] = None
    schema_loader: Optional[Any] = None
    global_config: Optional[Any] = None
