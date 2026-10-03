"""
test_scorer.py - Comprehensive unit tests for Scorer evaluation, seniority, and matching.
"""

import pytest
from v2.core.scorer import Scorer, JobScoreResult


def test_disallowed_seniority_exclusion_intern(scorer):
    """Verify that all intern/internship variants are strictly excluded with 0.0 score."""
    intern_titles = [
        "Machine Learning Engineer Intern",
        "Campus ML Research Engineer (Intern)",
        "Internship - Search Machine Learning Engineer",
        "Software Engineer Intern",
        "Associate Data Scientist - Intern",
        "2027 Summer Intern, MS/PhD, Machine Learning Engineer",
        "Intern Software Developer - London - 2027",
        "Software Engineering Internship (C++ or Python) – Summer 2027",
    ]
    for title in intern_titles:
        res = scorer.score_job(
            title=title,
            location="Amsterdam, Netherlands",
            description="Python PyTorch machine learning algorithms",
            company_name="Adyen"
        )
        assert res.score == 0.0, f"Expected 0.0 for '{title}', got {res.score}"
        assert res.is_senior is True
        assert res.is_active is False
        assert res.recommended_letter == "EXCLUDED (Seniority)"
        assert any("strictly excluded" in r for r in res.reasons)


def test_disallowed_seniority_exclusion_leadership(scorer):
    """Verify that senior, lead, staff, principal, director, manager roles are strictly excluded."""
    leadership_titles = [
        "Senior Machine Learning Engineer",
        "Sr. Software Engineer",
        "Lead Backend Developer",
        "Principal AI Scientist",
        "Staff Infrastructure Engineer",
        "Director of Machine Learning",
        "Head of AI Research",
        "VP of Engineering",
        "Engineering Manager",
        "Distinguished Engineer",
        "Founding Engineer",
    ]
    for title in leadership_titles:
        res = scorer.score_job(
            title=title,
            location="Amsterdam, Netherlands",
            description="Leading team, python backend",
            company_name="Adyen"
        )
        assert res.score == 0.0, f"Expected 0.0 for '{title}', got {res.score}"
        assert res.is_senior is True
        assert res.is_active is False
        assert any("strictly excluded" in r for r in res.reasons)


def test_word_boundary_safety(scorer):
    """Verify word boundaries prevent false positive exclusions on 'internal' or 'international'."""
    safe_titles = [
        "Internal Tools Engineer",
        "Software Engineer - Internal Compute Frameworks",
        "Applied AI Engineer, Government, International",
        "Software Engineer, International Systems",
    ]
    for title in safe_titles:
        assert scorer.is_senior_role(title) is False, f"'{title}' should NOT be flagged as senior"
        res = scorer.score_job(
            title=title,
            location="Amsterdam, Netherlands",
            description="Python FastAPI backend engineering",
            company_name="Adyen"
        )
        assert res.score > 50.0, f"Expected active score for '{title}', got {res.score}"
        assert res.is_senior is False
        assert res.is_active is True


def test_allowed_seniority_levels_accepted(scorer):
    """Verify junior, graduate, associate, and mid roles are scored favorably."""
    accepted_titles = [
        "Junior Machine Learning Engineer",
        "Graduate Software Engineer",
        "Associate Data Scientist",
        "Working Student AI Research",
        "Machine Learning Engineer",
    ]
    for title in accepted_titles:
        res = scorer.score_job(
            title=title,
            location="Amsterdam, Netherlands",
            description="Python PyTorch data modeling",
            company_name="Adyen"
        )
        assert res.score >= 70.0, f"Expected >= 70.0 for '{title}', got {res.score}"
        assert res.is_senior is False
        assert res.is_active is True


def test_allow_senior_bypass(scorer):
    """Verify allow_senior=True bypasses strict exclusion for manually added jobs."""
    res = scorer.score_job(
        title="Senior Machine Learning Engineer",
        location="Amsterdam, Netherlands",
        description="Python PyTorch distributed training",
        company_name="Adyen",
        allow_senior=True
    )
    assert res.score > 50.0
    assert res.is_senior is True  # Flag preserved for badge, but not excluded
    assert res.is_active is True


def test_entry_level_bonus_never_awarded_to_disallowed_level(scorer):
    """Verify entry-level bonus is not awarded to roles with disallowed terms even if allow_senior=True."""
    res = scorer.score_job(
        title="Machine Learning Intern",
        location="Amsterdam, Netherlands",
        description="Intern project with python",
        company_name="Adyen",
        allow_senior=True
    )
    # Entry level bonus reason should NOT be in reasons because 'Intern' is disallowed
    assert not any("Graduate/Entry friendly" in r for r in res.reasons)


def test_target_roles_matching(scorer):
    """Verify target roles award their configured weights."""
    res_ml = scorer.score_job(
        title="Machine Learning Engineer",
        location="Amsterdam, Netherlands",
        description="Machine learning model deployment",
        company_name="Adyen"
    )
    assert any("Target role: Machine Learning Engineer" in r for r in res_ml.reasons)

    res_cv = scorer.score_job(
        title="Computer Vision Engineer",
        location="Amsterdam, Netherlands",
        description="Perception point cloud processing",
        company_name="Adyen"
    )
    assert any("Target role: Computer Vision Engineer" in r for r in res_cv.reasons)


def test_location_scoring_tiers(scorer):
    """Verify Netherlands and UK location tier bonuses."""
    res_nl = scorer.score_job(
        title="Machine Learning Engineer",
        location="Amsterdam, Netherlands",
        description="Python",
        company_name="Adyen"
    )
    assert any("Netherlands (+25 pts)" in r for r in res_nl.reasons)
    assert res_nl.location_category == "Netherlands"

    res_uk = scorer.score_job(
        title="Machine Learning Engineer",
        location="London, United Kingdom",
        description="Python",
        company_name="Adyen"
    )
    assert any("United Kingdom (+20 pts)" in r for r in res_uk.reasons)
    assert res_uk.location_category == "United Kingdom"


def test_remote_location_handling(scorer):
    """Verify remote locations are accepted and scored with bonus points."""
    res_remote = scorer.score_job(
        title="Machine Learning Engineer",
        location="Remote, EU",
        description="Python",
        company_name="Adyen"
    )
    assert scorer.is_target_location("Remote") is True
    assert res_remote.is_target_location is True


def test_excluded_location_filtering(scorer):
    """Verify excluded geographic regions return False from is_target_location."""
    assert scorer.is_target_location("Bengaluru, India") is False
    assert scorer.is_target_location("Tokyo, Japan") is False
    assert scorer.is_target_location("Sao Paulo, Brazil") is False


def test_technical_skills_matching(scorer):
    """Verify skills categories (Python, PyTorch, C++, etc.) award configured weights."""
    res = scorer.score_job(
        title="Machine Learning Engineer",
        location="Amsterdam",
        description="Strong Python and PyTorch experience with Docker and Linux.",
        company_name="Adyen"
    )
    assert "🐍 Python Mastery" in res.matched_skills or "Python Mastery" in res.matched_skills
    assert any("Skills:" in r for r in res.reasons)


def test_company_tier_1_dream_matching(scorer):
    """Verify Tier 1 Dream employers apply correct multipliers and bonuses."""
    tier1_companies = ["Anthropic", "Google DeepMind", "OpenAI", "Helsing", "Together AI", "Hudson River Trading", "Databricks", "Wayve", "ASML"]
    for company in tier1_companies:
        res = scorer.score_job(
            title="Machine Learning Engineer",
            location="Amsterdam, Netherlands",
            description="Python PyTorch",
            company_name=company
        )
        assert res.company_tier == "Tier 1 Dream"
        assert res.company_multiplier == 1.25


def test_company_tier_2_high_priority_matching(scorer):
    """Verify Tier 2 High Priority employers apply correct multipliers and bonuses."""
    tier2_companies = ["Fizyr", "Rocsys", "bol.com", "Qualcomm AI Research", "Radix Trading", "Nearfield Instruments", "Axelera AI", "Glean", "G-Research", "XTX Markets"]
    for company in tier2_companies:
        res = scorer.score_job(
            title="Machine Learning Engineer",
            location="Amsterdam, Netherlands",
            description="Python PyTorch",
            company_name=company
        )
        assert res.company_tier == "Tier 2 High Priority"
        assert res.company_multiplier == 1.15


def test_company_tier_3_neutral_matching(scorer):
    """Verify Tier 3 Neutral employers apply correct multipliers and bonuses."""
    tier3_companies = ["Lely", "ASM International", "Bitvavo", "Thermo Fisher Scientific", "Modal Labs", "Weaviate", "Qdrant", "deepset", "Voyage AI", "Braintrust"]
    for company in tier3_companies:
        res = scorer.score_job(
            title="Machine Learning Engineer",
            location="Amsterdam, Netherlands",
            description="Python PyTorch",
            company_name=company
        )
        assert res.company_tier == "Tier 3 Neutral"
        assert res.company_multiplier == 1.05


def test_excluded_company_blacklist(scorer):
    """Verify blacklisted companies receive 0.0 score and EXCLUDED status."""
    res = scorer.score_job(
        title="Machine Learning Engineer",
        location="Amsterdam, Netherlands",
        description="Python",
        company_name="NonTechConsultingB.V."
    )
    assert res.score == 0.0
    assert res.recommended_letter == "EXCLUDED (Company)"
    assert res.company_tier == "Excluded"
    assert res.is_active is False


def test_penalties_application(scorer):
    """Verify non-technical or frontend anti-patterns deduct points with schema reason."""
    res = scorer.score_job(
        title="Frontend React Developer",
        location="Amsterdam, Netherlands",
        description="React Native iOS Swift frontend UI developer",
        company_name="Adyen"
    )
    assert any("Frontend/Mobile focus deducted" in r for r in res.reasons)


def test_cover_letter_template_selection(scorer):
    """Verify specialized cover letter templates trigger on relevant technical keywords."""
    res_f1 = scorer.score_job(
        title="Autonomous Driving Engineer",
        location="Amsterdam",
        description="Formula 1 motorsport telemetry and LiDAR perception pipeline",
        company_name="Adyen"
    )
    assert "FORMULA 1" in res_f1.recommended_letter

    res_cv = scorer.score_job(
        title="Perception Engineer",
        location="Amsterdam",
        description="LiDAR perception, point cloud clustering, YOLO inference",
        company_name="Adyen"
    )
    assert "COMPUTER VISION & PERCEPTION" in res_cv.recommended_letter

    res_ai = scorer.score_job(
        title="AI Engineer",
        location="Amsterdam",
        description="Forward deployed compound AI, LLM and RAG pipelines",
        company_name="Adyen"
    )
    assert "AI ENGINEER" in res_ai.recommended_letter
