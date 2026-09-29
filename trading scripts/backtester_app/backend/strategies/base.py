"""
Base Strategy Definition for AlphaDCA.
All built-in and user-defined strategies inherit from BaseStrategy.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import pandas as pd


class Parameter:
    """
    Metadata describing a configurable parameter for the UI and API.
    """
    def __init__(
        self,
        name: str,
        label: str,
        param_type: str = "number",  # "number", "select", "text"
        default: Any = 0,
        options: Optional[List[Any]] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        step: Optional[float] = None,
        hint: Optional[str] = None
    ):
        self.name = name
        self.label = label
        self.param_type = param_type
        self.default = default
        self.options = options or []
        self.min_value = min_value
        self.max_value = max_value
        self.step = step
        self.hint = hint

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.param_type,
            "default": self.default,
            "options": self.options,
            "min": self.min_value,
            "max": self.max_value,
            "step": self.step,
            "hint": self.hint
        }


class BaseStrategy(ABC):
    """
    Abstract Base Class for an Investment Strategy.
    """
    id: str = "base"
    name: str = "Base Strategy"
    description: str = "Base strategy class"
    category: str = "Schedule"  # "Schedule", "Smart & Technical", or "Custom"
    parameters: List[Parameter] = []

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": [p.to_dict() for p in self.parameters]
        }

    @abstractmethod
    def generate_orders(
        self,
        df: pd.DataFrame,
        config: Dict[str, Any],
        budget_mode: str,
        monthly_budget: float
    ) -> Dict[str, float]:
        """
        Determines the exact capital amounts to invest on each trading day.

        Args:
            df: Historical price DataFrame with sorted columns ['Date', 'ExecutionPrice', 'Year', 'Month', 'Day', 'Weekday', 'YearMonth']
            config: User configuration dictionary containing custom parameters, step_up_pct, amount, etc.
            budget_mode: 'normalized' (equal monthly budget) or 'custom' (fixed contribution per order)
            monthly_budget: The base monthly capital budget if budget_mode is 'normalized'

        Returns:
            Dict[str, float]: Mapping from date string ('YYYY-MM-DD') to the cash amount to invest on that day.
                              Dates without orders should simply be omitted or have amount <= 0.
        """
        pass
