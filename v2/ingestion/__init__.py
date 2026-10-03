"""
v2/ingestion - Standalone Data Ingestion & Crawling Engines.
Independent of legacy packages; operates directly on v2 database and schemas.
"""

from v2.ingestion.ind_fetcher import fetch_and_store_sponsors, init_db
from v2.ingestion.job_scraper import run_scraper, save_jobs_to_db, is_tech_job
from v2.ingestion.company_enricher import enrich_curated_sponsors, guess_company_domains
from v2.ingestion.job_aggregator import aggregate_verified_sponsor_jobs

__all__ = [
    "fetch_and_store_sponsors",
    "init_db",
    "run_scraper",
    "save_jobs_to_db",
    "is_tech_job",
    "enrich_curated_sponsors",
    "guess_company_domains",
    "aggregate_verified_sponsor_jobs",
]
