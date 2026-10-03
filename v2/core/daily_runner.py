"""
daily_runner.py - Orchestrates the Daily Job Scanning, Crawling, and Dynamic Evaluation Pipeline (v2).

Executes:
1. IND Public Register synchronization.
2. Target sponsor enrichment using profile-defined curated sponsors.
3. High-speed ATS scraping across Greenhouse, Lever, Ashby, etc.
4. Dutch tech feed aggregation and verification.
5. Dynamic scoring and personalized markdown report generation for the active profile.
"""

from __future__ import annotations

import os
import sys
import sqlite3
import asyncio
import logging
from datetime import datetime
from typing import Optional

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from v2.profile_schema import PersonalizationProfile
from v2.core.profile_analyzer import ProfileAnalyzer
from v2.ingestion.ind_fetcher import fetch_and_store_sponsors, init_db
from v2.ingestion.company_enricher import guess_company_domains
from v2.ingestion.job_scraper import run_scraper
from v2.ingestion.job_aggregator import aggregate_verified_sponsor_jobs

logger = logging.getLogger(__name__)


def enrich_profile_sponsors(profile: PersonalizationProfile, db_path: str):
    """Enrich sponsors in SQLite using the profile's curated sponsor catalog."""
    curated = profile.target_companies_and_domains.company_tiers.curated_sponsors
    if not curated:
        return

    conn = sqlite3.connect(db_path, timeout=30)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL;")

    updated = 0
    inserted = 0

    for item in curated:
        ats_type = item.ats_type
        ats_slug = item.ats_slug
        domain = item.domain
        careers_url = item.careers_url or (f"https://boards.greenhouse.io/{ats_slug}" if ats_type == "greenhouse" and ats_slug else None)
        cname = item.name

        # Look up in sponsors table
        cur.execute("SELECT id FROM sponsors WHERE clean_name LIKE ? OR name LIKE ?", (f"%{cname}%", f"%{cname}%"))
        rows = cur.fetchall()

        if rows:
            for (sid,) in rows:
                cur.execute("""
                UPDATE sponsors
                SET ats_type = COALESCE(?, ats_type),
                    ats_slug = COALESCE(?, ats_slug),
                    website = COALESCE(?, website),
                    careers_url = COALESCE(?, careers_url),
                    is_target_sector = 1
                WHERE id = ?
                """, (ats_type, ats_slug, domain, careers_url, sid))
                updated += 1
        else:
            # Insert new target sponsor if not already in IND register
            cur.execute("""
            INSERT INTO sponsors (name, clean_name, kvk, is_target_sector, sector_tags, ats_type, ats_slug, careers_url, website)
            VALUES (?, ?, 'Global / ATS', 1, 'Tech & AI', ?, ?, ?, ?)
            """, (cname, cname, ats_type, ats_slug, careers_url, domain))
            inserted += 1

    conn.commit()
    conn.close()
    logger.info(f"Enriched {updated} existing and {inserted} new sponsors from profile catalog.")


def run_daily_pipeline(
    profile: PersonalizationProfile,
    scrape_limit: int = 50,
    force_ind_refresh: bool = False
):
    """Execute complete daily synchronization cycle driven by active profile."""
    start_time = datetime.now()
    cand_name = profile.candidate_background.personal_info.name
    db_path = profile.output_settings.sqlite_db_path or "v2/data/sponsors.db"

    print("=" * 65)
    print(f"🚀 STARTING DAILY JOB DISCOVERY & MATCHING FOR: {cand_name.upper()}")
    print("=" * 65)

    # Initialize DB & track run
    init_db(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    cur = conn.cursor()

    cur.execute("CREATE TABLE IF NOT EXISTS sync_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_type TEXT, started_at TIMESTAMP, completed_at TIMESTAMP, new_jobs_count INTEGER, total_jobs_count INTEGER);")
    cur.execute("UPDATE jobs SET is_new = 0")
    cur.execute("INSERT INTO sync_runs (run_type, started_at) VALUES ('daily_v2', CURRENT_TIMESTAMP)")
    current_run_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Phase 1: IND Public Register Sync
    print("\n--- Phase 1: IND Public Register Sync ---")
    total_sponsors = fetch_and_store_sponsors(db_path=db_path, force_refresh=force_ind_refresh)

    # Phase 2: Target Sponsor Enrichment from Profile
    print("\n--- Phase 2: Target Sponsor Enrichment from Profile ---")
    enrich_profile_sponsors(profile, db_path=db_path)
    guess_company_domains(db_path=db_path, limit=200)

    # Phase 3: Crawl Sponsor Positions across ATS
    print(f"\n--- Phase 3: Crawling Sponsor Positions (Limit: {scrape_limit}) ---")
    asyncio.run(run_scraper(db_path=db_path, limit=scrape_limit))

    # Phase 4: Ingest & Verify Dutch Tech Feeds
    print("\n--- Phase 4: Ingesting Verified Dutch Tech Feeds ---")
    aggregate_verified_sponsor_jobs(db_path=db_path)

    # Phase 5: Dynamic Profile Matching & Scoring
    print("\n--- Phase 5: Dynamic Profile Matching & Scoring ---")
    analyzer = ProfileAnalyzer(profile, db_path=db_path)
    analyzed_jobs = analyzer.analyze_all_jobs(db_path)
    analyzed_count = len(analyzed_jobs)

    # Finalize sync run metadata
    conn = sqlite3.connect(db_path, timeout=30)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM jobs WHERE is_new = 1 AND is_active = 1")
    new_active_jobs = cur.fetchone()[0]

    cur.execute("""
    UPDATE sync_runs
    SET completed_at = CURRENT_TIMESTAMP,
        new_jobs_count = ?,
        total_jobs_count = ?
    WHERE id = ?
    """, (new_active_jobs, analyzed_count, current_run_id))
    conn.commit()
    conn.close()

    elapsed = (datetime.now() - start_time).total_seconds()
    reports_dir = profile.output_settings.reports_dir or "v2/reports"
    md_report = os.path.join(reports_dir, profile.output_settings.markdown_filename)

    print("=" * 65)
    print(f"✅ DAILY RUN COMPLETED IN {elapsed:.1f}s")
    print(f"📊 Monitored Sponsors: {total_sponsors} | Active Matching Roles: {analyzed_count}")
    print(f"🆕 Newly Discovered Roles This Run: {new_active_jobs}")
    print(f"📄 Personalized Report: {md_report}")
    print("=" * 65)
