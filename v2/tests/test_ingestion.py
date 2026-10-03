"""
test_ingestion.py - Unit tests for ingestion pipeline (IND fetcher, scrapers, enrichers, aggregator).
"""

import sqlite3
import pytest
from unittest.mock import patch, MagicMock

from v2.ingestion.ind_fetcher import clean_company_name, classify_sector, parse_ind_html
from v2.ingestion.job_scraper import is_tech_job, is_target_location, save_jobs_to_db
from v2.ingestion.company_enricher import guess_company_domains, enrich_curated_sponsors
from v2.ingestion.job_aggregator import fetch_arbeitnow_jobs, fetch_remotive_jobs


def test_clean_company_name():
    """Verify legal entity suffix removal from company names."""
    assert clean_company_name("Databricks B.V.") == "Databricks"
    assert clean_company_name("Adyen N.V.") == "Adyen"
    assert clean_company_name("Booking.com Holding B.V.") == "Booking.com"
    assert clean_company_name("ASML Netherlands B.V.") == "ASML"
    assert clean_company_name("Uber Europe B.V.") == "Uber"
    assert clean_company_name("Standard Tech Ltd.") == "Standard Tech"


def test_classify_sector():
    """Verify tech / engineering / automotive sector tagging."""
    is_target_asml, tags_asml = classify_sector("ASML Netherlands B.V.")
    assert is_target_asml is True
    assert "Known Target Tech" in tags_asml

    is_target_ai, tags_ai = classify_sector("Acme Artificial Intelligence Solutions")
    assert is_target_ai is True
    assert "Tech/IT" in tags_ai

    is_target_robotics, tags_robot = classify_sector("Precision Robotics & Sensor B.V.")
    assert is_target_robotics is True
    assert "Engineering/Semiconductors" in tags_robot or "Automotive/Robotics" in tags_robot

    is_target_bakery, tags_bakery = classify_sector("De Bakkerij Van Amsterdam")
    assert is_target_bakery is False
    assert len(tags_bakery) == 0


def test_parse_ind_html():
    """Verify parsing tabular IND HTML register."""
    sample_html = """
    <table>
        <thead>
            <tr><th>Organisation</th><th>KvK number</th></tr>
        </thead>
        <tbody>
            <tr><td>Databricks B.V.</td><td>12345678</td></tr>
            <tr><td>Adyen N.V.</td><td>87654321</td></tr>
        </tbody>
    </table>
    """
    rows = parse_ind_html(sample_html)
    assert len(rows) == 2
    assert rows[0]["name"] == "Databricks B.V."
    assert rows[0]["kvk"] == "12345678"
    assert rows[1]["name"] == "Adyen N.V."
    assert rows[1]["kvk"] == "87654321"


def test_is_tech_job():
    """Verify filtering of engineering/ML roles and exclusion of non-tech roles."""
    assert is_tech_job("Machine Learning Engineer") is True
    assert is_tech_job("Senior Fullstack Developer") is True
    assert is_tech_job("Autonomous Driving Perception Researcher") is True
    assert is_tech_job("Computer Vision / LiDAR Specialist") is True

    # Excluded keywords
    assert is_tech_job("HR Recruiter") is False
    assert is_tech_job("Accountant & Financial Auditor") is False
    assert is_tech_job("Sales & Marketing Manager") is False
    assert is_tech_job("Legal Counsel and Privacy Officer") is False


def test_is_target_location():
    """Verify target geography filtering and non-target exclusion."""
    assert is_target_location("Amsterdam, Netherlands") is True
    assert is_target_location("London, United Kingdom") is True
    assert is_target_location("San Francisco, CA, USA") is True
    assert is_target_location("Remote - Europe") is True
    assert is_target_location("Worldwide") is True

    # Explicitly non-target
    assert is_target_location("Bangalore, India") is False
    assert is_target_location("Pune, India") is False
    assert is_target_location("Singapore") is False


def test_save_jobs_to_db(temp_db_path):
    """Verify saving jobs to database with URL deduplication."""
    jobs = [
        {
            "company_name": "TestCorp",
            "title": "Robotics Engineer",
            "location": "Delft, Netherlands",
            "url": "https://testcorp.com/jobs/101",
            "description": "Robotics perception ROS C++",
            "source": "Scraper"
        },
        {
            "company_name": "TestCorp",
            "title": "Robotics Engineer",
            "location": "Delft, Netherlands",
            "url": "https://testcorp.com/jobs/101",  # duplicate URL
            "description": "Robotics perception ROS C++",
            "source": "Scraper"
        },
        {
            "company_name": "TestCorp",
            "title": "ML Platform Engineer",
            "location": "Delft, Netherlands",
            "url": "https://testcorp.com/jobs/102",
            "description": "Kubernetes ML pipelines",
            "source": "Scraper"
        }
    ]

    saved = save_jobs_to_db(jobs, temp_db_path)
    assert saved == 3  # 3 items processed / upserted

    # Query DB
    conn = sqlite3.connect(temp_db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM jobs WHERE company_name = 'TestCorp'")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 2


def test_guess_company_domains(temp_db_path):
    """Verify generating website/careers URL heuristics for target tech sponsors."""
    conn = sqlite3.connect(temp_db_path)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO sponsors (name, clean_name, is_target_sector, website, careers_url)
    VALUES ('Novel AI Labs B.V.', 'Novel AI Labs', 1, NULL, NULL)
    """)
    conn.commit()
    conn.close()

    updated = guess_company_domains(temp_db_path, limit=10)
    assert updated >= 1

    conn = sqlite3.connect(temp_db_path)
    cur = conn.cursor()
    cur.execute("SELECT website, careers_url FROM sponsors WHERE clean_name = 'Novel AI Labs'")
    row = cur.fetchone()
    conn.close()

    assert row[0] is not None
    assert "novelailabs.nl" in row[0]
    assert "careers" in row[1]


def test_fetch_arbeitnow_jobs_mock(matcher):
    """Verify Arbeitnow feed fetching and IND sponsor cross-referencing."""
    mock_payload = {
        "data": [
            {
                "title": "Python Software Engineer",
                "company_name": "Adyen",  # verified sponsor
                "location": "Amsterdam",
                "url": "https://arbeitnow.com/job/adyen-python",
                "description": "Python, SQL, APIs"
            },
            {
                "title": "Lead Accountant",  # non-tech job
                "company_name": "Adyen",
                "location": "Amsterdam",
                "url": "https://arbeitnow.com/job/adyen-acc",
                "description": "Accounting"
            },
            {
                "title": "Machine Learning Engineer",
                "company_name": "UnknownNonSponsorCo",  # not verified sponsor
                "location": "Amsterdam",
                "url": "https://arbeitnow.com/job/unknown-ml",
                "description": "Machine learning"
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("requests.get", return_value=mock_resp):
        jobs = fetch_arbeitnow_jobs(matcher)
        assert len(jobs) == 1
        assert jobs[0]["company_name"] == "Adyen"
        assert jobs[0]["title"] == "Python Software Engineer"
        assert "Verified Sponsor" in jobs[0]["source"]
