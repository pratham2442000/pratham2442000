"""
config_loader.py - Dynamic Ingestion and Validation of Personalization Profiles.

Handles loading, validating, and persisting user personalization profiles from YAML
or JSON files, serving as the Single Source of Truth for the entire v2 architecture.
"""

from __future__ import annotations

import os
import json
import logging
from typing import Union, Dict, Any, Optional
import yaml
from pydantic import ValidationError

from v2.profile_schema import PersonalizationProfile

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "schemas", "pratham.example.yaml")
)


def load_profile(source: Union[str, Dict[str, Any]]) -> PersonalizationProfile:
    """
    Load and validate a PersonalizationProfile from a file path (YAML/JSON) or raw dictionary.

    Args:
        source: File path (str) to YAML or JSON profile, or raw dictionary.

    Returns:
        PersonalizationProfile instance.

    Raises:
        FileNotFoundError: If the specified profile path does not exist.
        ValueError: If file format is unsupported or parsing fails.
        ValidationError: If the profile data does not conform to the schema.
    """
    if isinstance(source, dict):
        return PersonalizationProfile.model_validate(source)

    if not isinstance(source, str):
        raise TypeError(f"Expected file path string or dict, got {type(source).__name__}")

    file_path = os.path.abspath(os.path.expanduser(source))
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Personalization profile not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            if ext in (".yaml", ".yml"):
                raw_data = yaml.safe_load(f)
            elif ext in (".json",):
                raw_data = json.load(f)
            else:
                # Attempt YAML parsing as fallback (YAML superset of JSON)
                raw_data = yaml.safe_load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse profile file '{file_path}': {e}") from e

    if not isinstance(raw_data, dict):
        raise ValueError(f"Profile file '{file_path}' must contain a mapping/object at its root.")

    try:
        profile = PersonalizationProfile.model_validate(raw_data)
        return profile
    except ValidationError as err:
        logger.error(f"Schema validation error in profile '{file_path}':\n{err}")
        raise


def get_default_profile() -> PersonalizationProfile:
    """
    Resolve the active personalization profile.
    Checks PERSONALIZATION_PROFILE environment variable first, then defaults
    to the shipped example profile.
    """
    env_path = os.environ.get("PERSONALIZATION_PROFILE")
    if env_path and os.path.exists(env_path):
        return load_profile(env_path)
    return load_profile(DEFAULT_PROFILE_PATH)


def save_profile(profile: PersonalizationProfile, target_path: str) -> None:
    """
    Serialize and save a PersonalizationProfile back to YAML or JSON.
    """
    target_path = os.path.abspath(os.path.expanduser(target_path))
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    ext = os.path.splitext(target_path)[1].lower()

    data_dict = profile.model_dump(mode="json", exclude_none=True)

    with open(target_path, "w", encoding="utf-8") as f:
        if ext == ".json":
            json.dump(data_dict, f, indent=2)
        else:
            yaml.dump(data_dict, f, sort_keys=False, default_flow_style=False, allow_unicode=True)

    logger.info(f"Saved personalization profile to {target_path}")
