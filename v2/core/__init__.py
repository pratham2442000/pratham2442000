"""
v2/core package - Core modules for user-agnostic job evaluation, scoring, and matching.
"""

from v2.core.config_loader import load_profile, save_profile, get_default_profile
from v2.core.scorer import Scorer, JobScoreResult
from v2.core.company_matcher import CompanyMatcher
from v2.core.profile_analyzer import ProfileAnalyzer

__all__ = [
    "load_profile",
    "save_profile",
    "get_default_profile",
    "Scorer",
    "JobScoreResult",
    "CompanyMatcher",
    "ProfileAnalyzer",
]
