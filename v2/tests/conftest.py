"""
conftest.py - Shared pytest fixtures for v2 test suite.
"""

import os
import sys
import tempfile
import sqlite3
import pytest

from v2.core.config_loader import load_profile, DEFAULT_PROFILE_PATH
from v2.profile_schema import PersonalizationProfile
from v2.storage.db import DatabaseManager
from v2.core.tracker import ApplicationTracker
from v2.core.scorer import Scorer
from v2.core.company_matcher import CompanyMatcher


@pytest.fixture(scope="session")
def real_profile() -> PersonalizationProfile:
    """Load the real profile from DEFAULT_PROFILE_PATH."""
    return load_profile(DEFAULT_PROFILE_PATH)


@pytest.fixture
def temp_db_path(tmp_path) -> str:
    """Create a temporary SQLite database initialized with v2 schema and fixture data."""
    db_file = str(tmp_path / "test_sponsors.db")
    db_mgr = DatabaseManager(db_file)
    conn = db_mgr.get_connection()
    cur = conn.cursor()

    # Insert sample sponsors
    cur.executemany("""
    INSERT INTO sponsors (name, clean_name, kvk, is_target_sector, sector_tags, ats_type, ats_slug, careers_url, website)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        ("Databricks B.V.", "Databricks", "12345678", 1, "AI, Cloud", "greenhouse", "databricks", "https://databricks.com/careers", "https://databricks.com"),
        ("Adyen N.V.", "Adyen", "87654321", 1, "Fintech", "greenhouse", "adyen", "https://adyen.com/careers", "https://adyen.com"),
        ("Axelera AI B.V.", "Axelera AI", "82483027", 1, "Edge AI, Hardware", "ashby", "axelera-ai", "https://jobs.ashbyhq.com/axelera-ai", "https://axelera.ai"),
        ("ASM International N.V.", "ASM International", "30037466", 1, "Semiconductor", "greenhouse", "asminternational", "https://asm.com/careers", "https://asm.com"),
        ("Lely Industries N.V.", "Lely", "24441878", 1, "Robotics, Agritech", "custom", "lely", "https://lely.com/careers", "https://lely.com"),
        ("NonTechConsulting B.V.", "NonTechConsulting", "99999999", 0, "Consulting", None, None, None, "https://example.com"),
    ])

    # Insert sample jobs (variety of roles: graduate, intern, senior, non-tech)
    cur.executemany("""
    INSERT INTO jobs (id, company_name, title, location, url, description, source, match_score, is_active, is_senior, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (1, "Databricks", "Machine Learning Engineer", "Amsterdam, Netherlands", "https://databricks.com/job/1", "Python PyTorch distributed systems", "Greenhouse", 95.0, 1, 0, "unapplied"),
        (2, "Databricks", "Machine Learning Engineer Intern", "Amsterdam, Netherlands", "https://databricks.com/job/2", "Python PyTorch intern project", "Greenhouse", 0.0, 0, 1, "unapplied"),
        (3, "Adyen", "Python Software Engineer", "Amsterdam, Netherlands", "https://adyen.com/job/3", "FastAPI SQL backend APIs", "Greenhouse", 90.0, 1, 0, "unapplied"),
        (4, "Adyen", "Senior Backend Engineer", "Amsterdam, Netherlands", "https://adyen.com/job/4", "Senior lead python architect", "Greenhouse", 0.0, 0, 1, "unapplied"),
        (5, "Axelera AI", "AI Inference Compiler Engineer", "Eindhoven, Netherlands", "https://axelera.ai/job/5", "C++ ML compilers ONNX Titania", "Ashby", 92.0, 1, 0, "unapplied"),
        (6, "Unknown Startup", "Junior Machine Learning Engineer", "Delft, Netherlands", "https://example.com/job/6", "Python PyTorch CV", "External", 75.0, 1, 0, "unapplied"),
        (7, "NonTechConsulting", "Software Engineer", "Amsterdam, Netherlands", "https://nontech.com/job/7", "Java spring", "Manual", 0.0, 0, 0, "unapplied"),
        (8, "OpenAI", "Research Engineer, Multimodal", "San Francisco, CA, USA", "https://openai.com/job/8", "Vision-language scaling laws", "Ashby", 96.0, 1, 0, "unapplied"),
        (9, "Keyrus", "Python Developer", "Amsterdam, Netherlands", "https://keyrus.pt/job/9", "Python microservices", "Greenhouse", 99.0, 1, 0, "applied"),
    ])

    conn.commit()
    conn.close()
    return db_file


@pytest.fixture
def mock_db_mgr(temp_db_path) -> DatabaseManager:
    return DatabaseManager(temp_db_path)


@pytest.fixture
def mock_tracker(temp_db_path) -> ApplicationTracker:
    return ApplicationTracker(temp_db_path)


@pytest.fixture
def scorer(real_profile) -> Scorer:
    return Scorer(real_profile)


@pytest.fixture
def matcher(real_profile, temp_db_path) -> CompanyMatcher:
    return CompanyMatcher(real_profile, db_path=temp_db_path)
