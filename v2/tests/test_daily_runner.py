"""
test_daily_runner.py - Unit tests for daily scanning, sponsor enrichment, and pipeline orchestration.
"""

import sqlite3
import pytest
from unittest.mock import patch, MagicMock

from v2.core.daily_runner import enrich_profile_sponsors, run_daily_pipeline


def test_enrich_profile_sponsors(real_profile, temp_db_path):
    """Verify that curated sponsors from profile enrich existing sponsors and insert missing ones."""
    # Ensure database has a partial sponsor row
    conn = sqlite3.connect(temp_db_path)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO sponsors (name, clean_name, ats_type, ats_slug, is_target_sector)
    VALUES ('Nearfield Instruments B.V.', 'Nearfield Instruments', NULL, NULL, 0)
    """)
    conn.commit()
    conn.close()

    enrich_profile_sponsors(real_profile, temp_db_path)

    conn = sqlite3.connect(temp_db_path)
    cur = conn.cursor()

    # Check updated sponsor
    cur.execute("SELECT ats_type, ats_slug, is_target_sector FROM sponsors WHERE clean_name LIKE '%Nearfield Instruments%'")
    row = cur.fetchone()
    assert row is not None
    assert row[2] == 1  # is_target_sector updated to 1

    # Check newly inserted sponsor from profile catalog (e.g. Axelera AI or Helsing)
    cur.execute("SELECT count(*) FROM sponsors WHERE clean_name LIKE '%Axelera AI%' OR clean_name LIKE '%Helsing%'")
    count = cur.fetchone()[0]
    assert count >= 1
    conn.close()


def test_run_daily_pipeline_orchestration(real_profile, temp_db_path, tmp_path):
    """Verify complete daily pipeline execution and sync_runs logging."""
    custom_profile = real_profile.model_copy(deep=True)
    custom_profile.output_settings.sqlite_db_path = temp_db_path
    custom_profile.output_settings.reports_dir = str(tmp_path / "reports")

    with patch("v2.core.daily_runner.fetch_and_store_sponsors", return_value=100), \
         patch("v2.core.daily_runner.run_scraper", return_value=15), \
         patch("v2.core.daily_runner.aggregate_verified_sponsor_jobs", return_value=5):

        run_daily_pipeline(custom_profile, scrape_limit=10, force_ind_refresh=False)

    conn = sqlite3.connect(temp_db_path)
    cur = conn.cursor()
    cur.execute("SELECT run_type, started_at, completed_at FROM sync_runs WHERE run_type = 'daily_v2'")
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "daily_v2"
    assert row[1] is not None
    assert row[2] is not None
