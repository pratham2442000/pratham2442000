"""
test_config_loader.py - Unit tests for profile loading and error handling.
"""

import os
import json
import pytest
import yaml

from v2.core.config_loader import load_profile, DEFAULT_PROFILE_PATH
from v2.profile_schema import PersonalizationProfile


def test_load_default_profile():
    """Verify loading from DEFAULT_PROFILE_PATH works cleanly."""
    assert os.path.exists(DEFAULT_PROFILE_PATH)
    profile = load_profile(DEFAULT_PROFILE_PATH)
    assert isinstance(profile, PersonalizationProfile)
    assert profile.profile_id == "pratham_johari"


def test_load_profile_file_not_found():
    """Verify loading non-existent path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_profile("v2/schemas/non_existent_profile_12345.yaml")


def test_load_profile_malformed_yaml(tmp_path):
    """Verify loading syntactically invalid YAML raises Exception."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("invalid: yaml: content: [unclosed")
    with pytest.raises(Exception):
        load_profile(str(bad_yaml))


def test_load_profile_invalid_schema(tmp_path):
    """Verify profile with missing required fields raises ValidationError."""
    incomplete_yaml = tmp_path / "incomplete.yaml"
    incomplete_yaml.write_text("schema_version: '2.0.0'\n# missing candidate_background etc.")
    with pytest.raises(Exception):
        load_profile(str(incomplete_yaml))


def test_load_profile_from_json(tmp_path, real_profile):
    """Verify loading profile from a JSON file format."""
    json_path = tmp_path / "profile.json"
    json_path.write_text(real_profile.model_dump_json(indent=2))
    
    loaded = load_profile(str(json_path))
    assert isinstance(loaded, PersonalizationProfile)
    assert loaded.profile_id == real_profile.profile_id
    assert len(loaded.candidate_preferences.target_roles) == len(real_profile.candidate_preferences.target_roles)
