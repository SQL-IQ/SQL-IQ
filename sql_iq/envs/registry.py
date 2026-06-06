"""Database environment registry."""

from typing import Dict, Type
from .base import DBEnvironment


class DBRegistry:
    """Central registry for database environment classes."""

    _registry: Dict[str, Type[DBEnvironment]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register a DB environment class."""
        def wrapper(env_class: Type[DBEnvironment]):
            if not issubclass(env_class, DBEnvironment):
                raise TypeError(f"{env_class} must be a subclass of DBEnvironment")
            cls._registry[name] = env_class
            return env_class
        return wrapper

    @classmethod
    def get_env(cls, name: str, db_dir: str) -> DBEnvironment:
        """
        Get a DB environment instance by name.

        Args:
            name: Environment name (e.g., "sqlite", "oracle").
            db_dir: Database directory path.

        Returns:
            DBEnvironment instance.

        Raises:
            ValueError: If the environment is not registered.
        """
        if name not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(f"DB Environment '{name}' not found. Available: {available}")

        return cls._registry[name](db_dir)
