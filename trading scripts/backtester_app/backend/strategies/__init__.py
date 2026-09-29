from .base import BaseStrategy, Parameter
from .registry import register_strategy, get_strategy, list_strategies, discover_strategies

# Automatically discover all built-in and user-defined strategies
discover_strategies()

__all__ = [
    "BaseStrategy",
    "Parameter",
    "register_strategy",
    "get_strategy",
    "list_strategies",
    "discover_strategies"
]
