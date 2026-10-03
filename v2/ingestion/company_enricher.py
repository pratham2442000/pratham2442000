#!/usr/bin/env python3
"""
company_enricher.py - Enriches sponsors with domains, career portals, and ATS endpoints (v2).
Standalone v2 implementation operating strictly on v2/data/sponsors.db.
"""

from __future__ import annotations

import os
import re
import logging
from typing import Optional

from v2.profile_schema import PersonalizationProfile

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sponsors.db"))


def enrich_curated_sponsors(
    profile: Optional[PersonalizationProfile] = None,
    db_path: str = DEFAULT_DB_PATH
) -> int:
    """
    Enrich sponsors in SQLite using curated sponsors from the active profile.
    Delegates to the canonical implementation in daily_runner.
    """
    if profile is None:
        from v2.core.config_loader import load_profile
        profile = load_profile("v2/schemas/pratham.example.yaml")

    from v2.core.daily_runner import enrich_profile_sponsors
    enrich_profile_sponsors(profile, db_path=db_path)
    return len(profile.target_companies_and_domains.company_tiers.curated_sponsors or [])


def guess_company_domains(db_path: str = DEFAULT_DB_PATH, limit: int = 500) -> int:
    """For target tech sponsors without a website, generate standard domain heuristics."""
    from v2.storage.db import DatabaseManager
    db = DatabaseManager(db_path)
    conn = db.get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT id, clean_name FROM sponsors
    WHERE is_target_sector = 1 AND (website IS NULL OR website = '')
    ORDER BY id ASC
    LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    updated = 0

    for sponsor_id, clean_name in rows:
        slug = re.sub(r'[^a-zA-Z0-9]', '', clean_name.lower())
        if not slug or len(slug) < 3:
            continue

        website = f"https://www.{slug}.nl"
        careers_url = f"{website}/careers"

        cur.execute("""
        UPDATE sponsors
        SET website = ?,
            careers_url = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (website, careers_url, sponsor_id))
        updated += 1

    conn.commit()
    conn.close()
    return updated
