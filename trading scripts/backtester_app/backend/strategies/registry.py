"""
Strategy Registry & Auto-Discovery System for AlphaDCA.
Allows adding new strategies via decorator or dropping new python files into this folder.
"""

import os
import sys
import importlib
import logging
from typing import Dict, Type, List, Any
from .base import BaseStrategy

logger = logging.getLogger("backtester.strategy_registry")

_REGISTRY: Dict[str, BaseStrategy] = {}


def register_strategy(cls: Type[BaseStrategy]):
    """
    Decorator to register a strategy class with the engine.
    Usage:
        @register_strategy
        class MyStrategy(BaseStrategy):
            ...
    """
    if not issubclass(cls, BaseStrategy):
        raise TypeError(f"Class {cls.__name__} must inherit from BaseStrategy")

    instance = cls()
    _REGISTRY[instance.id] = instance
    logger.info(f"Registered strategy '{instance.name}' (ID: {instance.id})")
    return cls


def get_strategy(strategy_id: str) -> BaseStrategy:
    """
    Retrieves a strategy by its ID or frequency alias.
    """
    # Normalize legacy aliases
    alias_map = {
        "monthly_1st": "monthly_day",
        "monthly_first": "monthly_day",
        "monthly_15th": "monthly_day",
        "monthly_last": "monthly_day",
    }
    key = alias_map.get(strategy_id, strategy_id)
    
    if key in _REGISTRY:
        return _REGISTRY[key]
    
    # Fallback to monthly_day if not found
    if "monthly" in strategy_id and "monthly_day" in _REGISTRY:
        return _REGISTRY["monthly_day"]

    # If key still not found, return daily as default safe fallback
    if "daily" in _REGISTRY:
        return _REGISTRY["daily"]

    raise KeyError(f"Strategy '{strategy_id}' not found in registry. Available: {list(_REGISTRY.keys())}")


def list_strategies() -> List[Dict[str, Any]]:
    """
    Returns metadata for all registered strategies for UI and API consumption.
    """
    return [strat.get_metadata() for strat in _REGISTRY.values()]


def discover_strategies():
    """
    Automatically discovers and imports all strategy modules in the current directory.
    Any .py file added to this folder will be registered automatically!
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    for filename in os.listdir(current_dir):
        if filename.endswith(".py") and not filename.startswith("__") and filename not in ("base.py", "registry.py"):
            module_name = f"strategies.{filename[:-3]}"
            try:
                # Import module to trigger @register_strategy decorators
                if module_name in sys.modules:
                    importlib.reload(sys.modules[module_name])
                else:
                    importlib.import_module(module_name)
            except Exception as e:
                logger.warning(f"Could not load strategy module {filename}: {str(e)}")
