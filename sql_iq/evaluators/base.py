"""Base Evaluator abstraction."""

from abc import ABC, abstractmethod
from typing import List, Dict


class BaseEvaluator(ABC):
    """
    Abstract base class for evaluation metric computation.
    """

    @abstractmethod
    def evaluate(self, predictions: List[str], ground_truths: List[str]) -> Dict[str, float]:
        """
        Compute evaluation metrics.

        Args:
            predictions: List of predicted values.
            ground_truths: List of ground truth values.

        Returns:
            Metrics dictionary, e.g., {"accuracy": 0.85, "precision": 0.90}
        """
        pass
