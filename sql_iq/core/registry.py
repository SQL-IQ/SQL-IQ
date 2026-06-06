"""Task Registry for registering and retrieving task implementations."""

from typing import Dict, Type, Any, List

from .base import BaseTask
from .context import TaskContext


class TaskRegistry:
    """
    Central registry for task classes.

    Usage:
        @TaskRegistry.register("text2sql")
        class Text2SQLTask(BaseTask):
            ...

        task = TaskRegistry.get_task("text2sql", config, context)
    """

    _registry: Dict[str, Type[BaseTask]] = {}

    @classmethod
    def register(cls, name: str):
        """
        Decorator to register a task class.

        Args:
            name: Task registration name (e.g., "text2sql").
        """
        def wrapper(task_class: Type[BaseTask]):
            if not issubclass(task_class, BaseTask):
                raise TypeError(f"{task_class} must be a subclass of BaseTask")
            cls._registry[name] = task_class
            return task_class
        return wrapper

    @classmethod
    def get_task(cls, name: str, config: Dict[str, Any], context: TaskContext) -> BaseTask:
        """
        Retrieve a task instance by name.

        Args:
            name: Task registration name.
            config: Task configuration dictionary.
            context: Task execution context.

        Returns:
            Task instance.

        Raises:
            ValueError: If the task is not registered.
        """
        if name not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(
                f"Task '{name}' not registered.\n"
                f"Available tasks: {available}"
            )
        return cls._registry[name](config, context)

    @classmethod
    def list_tasks(cls) -> List[str]:
        """
        List all registered task names.

        Returns:
            List of task name strings.
        """
        return list(cls._registry.keys())
