#!/usr/bin/env python3
"""
daily_runner.py - Orchestrates the daily pipeline for IND sponsor tracking,
scraping open tech jobs, and updating personalized recommendations.
Can be executed directly or scheduled as a cron job.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime

# Add package directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ind_fetcher import fetch_and_store_sponsors, init_db
from src.company_enricher import enrich_curated_sponsors, guess_company_domains
from src.job_scraper import run_scraper
from src.job_aggregator import aggregate_verified_sponsor_jobs
from src.profile_analyzer import analyze_all_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_daily_pipeline(scrape_limit: int = 50, force_ind_refresh: bool = False):
    """Execute complete daily synchronization cycle."""
    start_time = datetime.now()
    logging.info("=" * 65)
    logging.info("🚀 STARTING IND SPONSOR JOB SCANNER & ANALYZER DAILY RUN")
    logging.info("=" * 65)

    # 1. Sync IND Public Register
    logging.info("\n--- Phase 1: IND Public Register Sync ---")
    total_sponsors = fetch_and_store_sponsors(force_refresh=force_ind_refresh)

    # 2. Enrich Target Tech/Automotive Sponsors
    logging.info("\n--- Phase 2: Target Sponsor Enrichment ---")
    enrich_curated_sponsors()
    guess_company_domains(limit=200)

    # 3. Crawl ATS Endpoints & Career Pages
    logging.info("\n--- Phase 3: Crawling Sponsor Positions ---")
    asyncio.run(run_scraper(limit=scrape_limit))

    # 4. Ingest & Verify Dutch Tech Feeds
    logging.info("\n--- Phase 4: Ingesting Verified Dutch Tech Feeds ---")
    aggregate_verified_sponsor_jobs()

    # 5. Analyze and Rank against User Profile
    logging.info("\n--- Phase 5: Matching & Scoring against Profile ---")
    analyzed_count = analyze_all_jobs()

    elapsed = (datetime.now() - start_time).total_seconds()
    logging.info("=" * 65)
    logging.info(f"✅ DAILY RUN COMPLETED IN {elapsed:.1f}s")
    logging.info(f"📊 Monitored Sponsors: {total_sponsors} | Active Analyzed Jobs: {analyzed_count}")
    logging.info("📄 Recommendations saved to: sponsor_jobs/data/recommended_jobs.md")
    logging.info("=" * 65)


if __name__ == "__main__":
    run_daily_pipeline(scrape_limit=50)
