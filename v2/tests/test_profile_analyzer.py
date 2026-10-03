"""
test_profile_analyzer.py - Unit tests for ProfileAnalyzer and reporting facilities.
"""

import os
import json
import pytest
from v2.core.profile_analyzer import ProfileAnalyzer, detect_ats_platform, format_status_badge


def test_detect_ats_platform():
    """Verify ATS platform detection from source string, URL, and metadata."""
    assert detect_ats_platform(source="Greenhouse") == "Greenhouse"
    assert detect_ats_platform(url="https://boards.greenhouse.io/databricks/jobs/1") == "Greenhouse"
    assert detect_ats_platform(url="https://jobs.ashbyhq.com/axelera-ai/123") == "Ashby"
    assert detect_ats_platform(source="Lever Scraper") == "Lever"
    assert detect_ats_platform(url="https://company.myworkdayjobs.com/en-US/careers/job/1") == "Workday"
    assert detect_ats_platform(source="LinkedIn Job") == "LinkedIn"
    assert detect_ats_platform(source="custom", url="https://example.com", ats_type=None) == "Direct Portal"


def test_format_status_badge():
    """Verify application status formatting badges."""
    assert format_status_badge(applied=1, status="applied", applied_at="2026-09-30 12:00:00") == "✅ Applied (2026-09-30)"
    assert format_status_badge(applied=0, status="interviewing") == "💬 Interviewing"
    assert format_status_badge(applied=0, status="offered") == "🎉 Offer"
    assert format_status_badge(applied=0, status="uninterested") == "🚫 Uninterested"
    assert format_status_badge(applied=0, status="rejected") == "❌ Rejected"
    assert format_status_badge(applied=0, status="unapplied") == "⬜ Not Applied"


def test_extract_keywords(real_profile, temp_db_path):
    """Verify JD parsing, keyword extraction, and score evaluation."""
    analyzer = ProfileAnalyzer(real_profile, db_path=temp_db_path)
    jd_text = """
    We are looking for a Machine Learning Engineer to build autonomous perception pipelines.
    Required:
    - Python mastery and PyTorch or JAX experience
    - Experience with Docker, Kubernetes, Linux, Git
    - Knowledge of Point Cloud, LiDAR, and Sensor Fusion is a plus
    - 2 years of experience
    """

    res = analyzer.extract_keywords(
        text=jd_text,
        title="Machine Learning Engineer",
        location="Amsterdam, Netherlands",
        company="Adyen"
    )

    assert res["match_score"] > 80.0
    assert "Python" in res["all_keywords"]
    assert "PyTorch" in res["all_keywords"]
    assert "Docker" in res["all_keywords"]
    assert "categorized" in res
    assert res["detected_metadata"]["experience_years"] is not None
    assert res["detected_metadata"]["seniority_warning"] is None


def test_extract_keywords_seniority_warning(real_profile, temp_db_path):
    """Verify seniority warning when experience years exceed candidate cap."""
    analyzer = ProfileAnalyzer(real_profile, db_path=temp_db_path)
    jd_text = "Requires 8+ years of experience leading engineering teams."

    res = analyzer.extract_keywords(
        text=jd_text,
        title="Staff ML Engineer",
        location="Amsterdam, Netherlands"
    )

    warning = res["detected_metadata"]["seniority_warning"]
    assert warning is not None
    assert "Exceeds candidate preferred cap" in warning or "disallowed seniority" in warning


def test_analyze_all_jobs_and_report_generation(real_profile, temp_db_path, tmp_path):
    """Verify end-to-end SQLite job re-scoring, database updates, and Markdown/JSON generation."""
    # Direct reports to tmp_path
    reports_dir = str(tmp_path / "reports")
    custom_profile = real_profile.model_copy(deep=True)
    custom_profile.output_settings.reports_dir = reports_dir
    custom_profile.output_settings.markdown_filename = "test_jobs.md"
    custom_profile.output_settings.json_filename = "test_jobs.json"

    analyzer = ProfileAnalyzer(custom_profile, db_path=temp_db_path)
    analyzed = analyzer.analyze_all_jobs()

    assert len(analyzed) > 0
    # Verify report files were created
    md_file = os.path.join(reports_dir, "test_jobs.md")
    json_file = os.path.join(reports_dir, "test_jobs.json")
    assert os.path.exists(md_file)
    assert os.path.exists(json_file)

    # Check JSON content
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) == len(analyzed)

    # Check Markdown content
    with open(md_file, "r", encoding="utf-8") as f:
        md_content = f.read()
    candidate_name = custom_profile.candidate_background.personal_info.name
    assert candidate_name in md_content or "Job Search" in md_content
    assert "Databricks" in md_content


def test_refresh_reports(real_profile, temp_db_path, tmp_path):
    """Verify lightweight refresh_reports generates valid reports from current DB state."""
    reports_dir = str(tmp_path / "reports_refresh")
    custom_profile = real_profile.model_copy(deep=True)
    custom_profile.output_settings.reports_dir = reports_dir

    analyzer = ProfileAnalyzer(custom_profile, db_path=temp_db_path)
    analyzer.refresh_reports()

    md_file = os.path.join(reports_dir, custom_profile.output_settings.markdown_filename)
    json_file = os.path.join(reports_dir, custom_profile.output_settings.json_filename)
    assert os.path.exists(md_file)
    assert os.path.exists(json_file)
