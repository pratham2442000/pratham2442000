#!/usr/bin/env python3
"""
job_aggregator.py - Aggregates open positions from Dutch tech boards & developer job feeds,
automatically cross-referencing each employer with the IND Recognised Sponsors database.
"""

import os
import re
import sqlite3
import logging
from typing import List, Dict, Any
import requests

try:
    from .sponsor_matcher import SponsorMatcher
    from .job_scraper import save_jobs_to_db, is_tech_job
except ImportError:
    from sponsor_matcher import SponsorMatcher
    from job_scraper import save_jobs_to_db, is_tech_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sponsors.db"))


def fetch_arbeitnow_jobs(matcher: SponsorMatcher) -> List[Dict[str, Any]]:
    """Fetch tech jobs from Arbeitnow and cross-reference with IND sponsors."""
    url = "https://www.arbeitnow.com/api/job-board-api"
    jobs = []
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", [])
        for item in data:
            title = item.get("title", "")
            company = item.get("company_name", "")
            loc = item.get("location", "")
            job_url = item.get("url", "")
            
            # Check tech relevance
            if not is_tech_job(title):
                continue
                
            # Cross-reference with IND Sponsors
            sponsor = matcher.match(company)
            if sponsor:
                jobs.append({
                    "sponsor_id": sponsor["id"],
                    "company_name": company,
                    "title": title,
                    "location": loc or "Netherlands / Remote",
                    "url": job_url,
                    "description": item.get("description", "")[:1000],
                    "source": f"Arbeitnow (Verified Sponsor: {sponsor['clean_name']})"
                })
    except Exception as e:
        logging.warning(f"Error fetching Arbeitnow jobs: {e}")
    return jobs


def fetch_remotive_jobs(matcher: SponsorMatcher) -> List[Dict[str, Any]]:
    """Fetch developer/AI jobs from Remotive and cross-reference with IND sponsors."""
    url = "https://remotive.com/api/remote-jobs?category=software-dev&limit=60"
    jobs = []
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json().get("jobs", [])
        for item in data:
            title = item.get("title", "")
            company = item.get("company_name", "")
            loc = item.get("candidate_required_location", "")
            job_url = item.get("url", "")
            
            if not is_tech_job(title):
                continue
                
            sponsor = matcher.match(company)
            if sponsor:
                jobs.append({
                    "sponsor_id": sponsor["id"],
                    "company_name": company,
                    "title": title,
                    "location": loc or "Europe / Remote",
                    "url": job_url,
                    "description": item.get("description", "")[:1000],
                    "source": f"Remotive (Verified Sponsor: {sponsor['clean_name']})"
                })
    except Exception as e:
        logging.warning(f"Error fetching Remotive jobs: {e}")
    return jobs


def aggregate_verified_sponsor_jobs(db_path: str = DB_PATH) -> int:
    """Run all feed aggregators and store verified IND sponsor jobs."""
    matcher = SponsorMatcher(db_path)
    all_jobs = []
    
    logging.info("Aggregating tech feeds and cross-referencing against IND Sponsors...")
    all_jobs.extend(fetch_arbeitnow_jobs(matcher))
    all_jobs.extend(fetch_remotive_jobs(matcher))
    
    saved = save_jobs_to_db(all_jobs, db_path)
    logging.info(f"Verified & saved {saved} positions from external tech feeds.")
    return saved


if __name__ == "__main__":
    aggregate_verified_sponsor_jobs()
