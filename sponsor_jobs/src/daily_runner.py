#!/usr/bin/env python3
"""
daily_runner.py - Orchestrates the daily pipeline for IND sponsor tracking,
scraping open tech jobs, and updating personalized recommendations.
Tracks synchronization runs and new job discovery across daily executions.
"""

import os
import sys
import sqlite3
import asyncio
import logging
from datetime import datetime

# Add package directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ind_fetcher import fetch_and_store_sponsors, init_db, DB_PATH
from src.company_enricher import enrich_curated_sponsors, guess_company_domains
from src.job_scraper import run_scraper
from src.job_aggregator import aggregate_verified_sponsor_jobs
from src.profile_analyzer import analyze_all_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_daily_pipeline(scrape_limit: int = 50, force_ind_refresh: bool = False):
    """Execute complete daily synchronization cycle with run tracking."""
    start_time = datetime.now()
    logging.info("=" * 65)
    logging.info("🚀 STARTING IND SPONSOR JOB SCANNER & ANALYZER DAILY RUN")
    logging.info("=" * 65)

    # Initialize DB schema & record start of sync run
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Check previous completed run
    cur.execute("SELECT started_at FROM sync_runs WHERE completed_at IS NOT NULL ORDER BY id DESC LIMIT 1")
    prev_row = cur.fetchone()
    prev_run_time = prev_row[0] if prev_row else None
    
    # Reset is_new flag on existing jobs so only jobs added in THIS run are tagged as new
    cur.execute("UPDATE jobs SET is_new = 0")
    
    # Record new run in sync_runs
    cur.execute("INSERT INTO sync_runs (run_type, started_at) VALUES ('daily', CURRENT_TIMESTAMP)")
    current_run_id = cur.lastrowid
    conn.commit()
    conn.close()

    # 1. Sync IND Public Register
    logging.info("\n--- Phase 1: IND Public Register Sync ---")
    total_sponsors = fetch_and_store_sponsors(force_refresh=force_ind_refresh)

    # 2. Enrich Target Tech/Automotive/Quant Sponsors
    logging.info("\n--- Phase 2: Target Sponsor Enrichment ---")
    enrich_curated_sponsors()
    guess_company_domains(limit=200)

    # 3. Crawl ATS Endpoints & Career Pages (UK, AU, NL, EU)
    logging.info("\n--- Phase 3: Crawling Sponsor Positions ---")
    asyncio.run(run_scraper(limit=scrape_limit))

    # 4. Ingest & Verify Dutch Tech Feeds
    logging.info("\n--- Phase 4: Ingesting Verified Dutch Tech Feeds ---")
    aggregate_verified_sponsor_jobs()

    # 5. Analyze and Rank against User Profile (Strict Non-Senior, Python Priority)
    logging.info("\n--- Phase 5: Matching & Scoring against Profile ---")
    analyzed_count = analyze_all_jobs()

    # Finalize sync run metadata
    conn = sqlite3.connect(DB_PATH)
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
    logging.info("=" * 65)
    logging.info(f"✅ DAILY RUN COMPLETED IN {elapsed:.1f}s")
    logging.info(f"📊 Monitored Sponsors: {total_sponsors} | Active Non-Senior Jobs: {analyzed_count}")
    logging.info(f"🆕 Newly Discovered Roles This Run: {new_active_jobs}")
    logging.info("📄 Recommendations saved to: sponsor_jobs/data/recommended_jobs.md")
    logging.info("=" * 65)


if __name__ == "__main__":
    run_daily_pipeline(scrape_limit=50)
