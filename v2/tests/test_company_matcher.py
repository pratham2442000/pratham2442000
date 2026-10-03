"""
test_company_matcher.py - Unit tests for profile-driven CompanyMatcher.
"""

import pytest
from v2.core.company_matcher import CompanyMatcher, CompanyMatchResult


def test_normalize_company_name(matcher):
    """Test legal suffix and punctuation normalization."""
    assert matcher._normalize("Databricks B.V.") == "databricks"
    assert matcher._normalize("Adyen N.V.") == "adyen"
    assert matcher._normalize("Axelera AI Nederland B.V.") == "axelera ai"
    assert matcher._normalize("  ASML   Holding  ") == "asml"
    assert matcher._normalize("Lely Industries International") == "lely industries"


def test_tokenize_and_stop_words(matcher):
    """Test tokenization filtering of common stop words."""
    tokens = matcher._tokenize("Adyen Nederland B.V. Technologies Services")
    assert "adyen" in tokens
    assert "nederland" not in tokens
    assert "services" not in tokens
    assert "technologies" not in tokens
    # Short words (<3 chars) filtered
    assert "bv" not in tokens


def test_tier_1_dream_matching(matcher):
    """Verify Tier 1 Dream employers match accurately."""
    tier1_names = ["Anthropic", "Google DeepMind", "OpenAI", "Helsing", "Together AI", "Databricks", "Wayve", "ASML"]
    for name in tier1_names:
        res = matcher.match(name)
        assert isinstance(res, CompanyMatchResult)
        assert res.tier == "Tier 1 Dream"
        assert res.multiplier >= 1.2
        assert not res.is_excluded


def test_tier_2_high_priority_matching(matcher):
    """Verify Tier 2 High Priority employers match accurately."""
    tier2_names = ["Fizyr", "Rocsys", "bol.com", "Qualcomm AI Research", "Radix Trading", "Axelera AI", "G-Research", "XTX Markets"]
    for name in tier2_names:
        res = matcher.match(name)
        assert isinstance(res, CompanyMatchResult)
        assert res.tier == "Tier 2 High Priority"
        assert res.multiplier >= 1.1
        assert not res.is_excluded


def test_tier_3_neutral_matching(matcher):
    """Verify Tier 3 Neutral employers match accurately."""
    tier3_names = ["Lely", "ASM International", "Bitvavo", "Thermo Fisher Scientific", "Modal Labs", "Weaviate", "Qdrant", "deepset", "Voyage AI", "Braintrust"]
    for name in tier3_names:
        res = matcher.match(name)
        assert isinstance(res, CompanyMatchResult)
        assert res.tier == "Tier 3 Neutral"
        assert res.multiplier >= 1.0
        assert not res.is_excluded


def test_excluded_company_blacklist(matcher, real_profile):
    """Verify blacklisted companies return excluded results."""
    # Test configured excluded company from real_profile
    res = matcher.match("NonTechConsultingB.V.")
    assert isinstance(res, CompanyMatchResult)
    assert res.is_excluded is True
    assert res.tier == "Excluded"
    assert res.multiplier == 0.0

    # Also test with a profile configured with multiple excluded companies
    custom_profile = real_profile.model_copy(deep=True)
    custom_profile.target_companies_and_domains.company_tiers.excluded_companies = [
        "BadCorp", "ScamConsultancy", "LegacyShop"
    ]
    custom_matcher = CompanyMatcher(custom_profile)
    for bad in ["BadCorp", "ScamConsultancy BV", "LegacyShop"]:
        res_bad = custom_matcher.match(bad)
        assert res_bad.is_excluded is True
        assert res_bad.tier == "Excluded"
        assert res_bad.multiplier == 0.0


def test_verified_sponsor_db_lookup(matcher):
    """Verify sponsor lookup correctly extracts KVK, sector tags, and ATS information."""
    res = matcher.match("Adyen N.V.")
    assert res.is_verified_sponsor is True
    assert res.kvk == "87654321"
    assert res.ats_type == "greenhouse"
    assert "Fintech" in (res.sector_tags or "")


def test_standard_unrecognized_company(matcher):
    """Verify unknown companies default to standard non-sponsor."""
    res = matcher.match("Completely Unknown Robotics Inc")
    assert res.tier == "Standard"
    assert res.is_verified_sponsor is False
    assert res.multiplier == 1.0
    assert not res.is_excluded


def test_evaluate_employer_alias(matcher):
    """Verify evaluate_employer is an exact alias for match."""
    res1 = matcher.match("Axelera AI")
    res2 = matcher.evaluate_employer("Axelera AI")
    assert res1.tier == res2.tier
    assert res1.multiplier == res2.multiplier
