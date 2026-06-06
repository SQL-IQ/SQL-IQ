"""
Core module: base classes, registry, sample dataclass, and task context.
"""

from .context import TaskContext
from .sample import Sample
from .base import BaseTask
from .registry import TaskRegistry

__all__ = ["Sample", "BaseTask", "TaskRegistry", "TaskContext"]
