"""
test_profile_schema.py - Unit tests for PersonalizationProfile models and validation.
"""

import pytest
from pydantic import ValidationError

from v2.profile_schema import (
    PersonalizationProfile,
    SeniorityPreferences,
    LocationTier,
    TargetRole,
    CompanyTierItem,
    CompanyTiers,
    CoverLetterTemplate,
    DomainItem,
    PenaltyItem,
    EvaluationAndScoringRubric,
    CandidatePreferences,
    CandidateBackground,
    PersonalInfo,
    TargetCompaniesAndDomains,
)


def test_seniority_preferences_effective_pattern():
    """Verify get_effective_exclusion_pattern unifies disallowed_levels and senior_exclusion_pattern."""
    sen = SeniorityPreferences(
        disallowed_levels=["intern", "internship", "senior", "lead"],
        senior_exclusion_pattern=r"\b(principal|staff|director)\b"
    )
    pattern = sen.get_effective_exclusion_pattern()
    assert pattern is not None
    assert r"\b(principal|staff|director)\b" in pattern
    assert r"\bintern\b" in pattern
    assert r"\binternship\b" in pattern
    assert r"\bsenior\b" in pattern
    assert r"\blead\b" in pattern


def test_seniority_preferences_empty_levels():
    """Verify handling when disallowed_levels is empty."""
    sen = SeniorityPreferences(
        disallowed_levels=[],
        senior_exclusion_pattern=r"\b(senior)\b"
    )
    pattern = sen.get_effective_exclusion_pattern()
    assert pattern == r"(?:\b(senior)\b)"


def test_target_role_invalid_regex_raises():
    """Verify TargetRole regex validator catches malformed regex syntax."""
    with pytest.raises(ValueError, match="Invalid regex"):
        TargetRole(title="Broken Role", patterns=[r"(unclosed group"])


def test_location_tier_invalid_regex_raises():
    """Verify LocationTier regex validator catches malformed regex syntax."""
    with pytest.raises(ValueError, match="Invalid regex"):
        LocationTier(name="Bad Tier", patterns=[r"[unclosed bracket"])


def test_domain_item_invalid_regex_raises():
    """Verify DomainItem regex validator catches malformed regex syntax."""
    with pytest.raises(ValueError, match="Invalid regex"):
        DomainItem(name="Bad Domain", patterns=[r"*invalid star quantifier"])


def test_company_tier_item_defaults():
    """Verify CompanyTierItem default field values."""
    item = CompanyTierItem(name="TestCorp")
    assert item.name == "TestCorp"
    assert item.multiplier == 1.0
    assert item.bonus_points == 0.0
    assert item.tier == "Curated Sponsor"


def test_personalization_profile_json_schema():
    """Verify JSON schema export produces valid schema structure."""
    schema = PersonalizationProfile.get_json_schema()
    assert isinstance(schema, dict)
    assert schema.get("type") == "object" or "$defs" in schema
    assert "properties" in schema or "$defs" in schema


def test_real_profile_validates_successfully(real_profile):
    """Verify real profile loads and adheres to all schema constraints."""
    assert real_profile.schema_version == "2.0.0"
    assert real_profile.profile_id == "pratham_johari"
    assert len(real_profile.candidate_background.verified_technical_skills) > 0
    assert len(real_profile.candidate_preferences.target_roles) > 0
    assert len(real_profile.candidate_preferences.locations.tiers) > 0
    assert len(real_profile.target_companies_and_domains.company_tiers.tier_1_dream) == 11
    assert len(real_profile.target_companies_and_domains.company_tiers.tier_2_high_priority) >= 10
    assert len(real_profile.target_companies_and_domains.company_tiers.tier_3_neutral) == 10
