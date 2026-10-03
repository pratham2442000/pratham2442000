"""
db.py - SQLite Database Management & Schema Provisioning (v2).

Handles database initialization, connections, and table provisioning for
user-agnostic job discovery and application tracking.
"""

from __future__ import annotations

import os
import sqlite3
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages SQLite connections and table schemas for v2.
    Can operate against an existing sponsors.db or initialize a clean database.
    """

    def __init__(self, db_path: str = "v2/data/sponsors.db"):
        self.db_path = os.path.abspath(os.path.expanduser(db_path))
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.ensure_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Create a resilient SQLite connection with WAL mode and generous busy timeout."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        return conn

    def ensure_schema(self) -> None:
        """Provision tables if they do not exist."""
        conn = self.get_connection()
        cur = conn.cursor()

        # 1. Sponsors table (optional if importing from registers)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS sponsors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            clean_name TEXT,
            kvk TEXT,
            is_target_sector INTEGER DEFAULT 0,
            sector_tags TEXT,
            ats_type TEXT,
            ats_slug TEXT,
            careers_url TEXT,
            website TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 2. Jobs table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sponsor_id INTEGER,
            company_name TEXT NOT NULL,
            title TEXT NOT NULL,
            location TEXT,
            url TEXT UNIQUE NOT NULL,
            description TEXT,
            source TEXT DEFAULT 'Manual / API',
            match_score REAL DEFAULT 0.0,
            match_reason TEXT,
            recommended_letter TEXT,
            is_active INTEGER DEFAULT 1,
            applied INTEGER DEFAULT 0,
            applied_at TIMESTAMP,
            status TEXT DEFAULT 'unapplied',
            notes TEXT,
            is_new INTEGER DEFAULT 1,
            is_senior INTEGER DEFAULT 0,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sponsor_id) REFERENCES sponsors (id)
        );
        """)

        # Indexes for fast lookup
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs (match_score DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs (url);")

        # One-time migration: normalize legacy 'unintrested' typo
        cur.execute("UPDATE jobs SET status = 'uninterested' WHERE status = 'unintrested'")

        conn.commit()
        conn.close()

    def get_top_jobs(self, limit: int = 10, only_new: bool = False) -> List[Dict[str, Any]]:
        """Retrieve top ranked active jobs."""
        conn = self.get_connection()
        cur = conn.cursor()

        query = """
        SELECT id, company_name, title, location, match_score, recommended_letter,
               url, applied, status, is_new, source
        FROM jobs
        WHERE is_active = 1 AND match_score > 0 AND status NOT IN ('uninterested', 'rejected')
        """
        params = []
        if only_new:
            query += " AND is_new = 1"

        query += " ORDER BY match_score DESC LIMIT ?"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "company": r[1],
                "title": r[2],
                "location": r[3],
                "score": r[4],
                "recommended_letter": r[5],
                "url": r[6],
                "applied": r[7],
                "status": r[8],
                "is_new": r[9],
                "source": r[10]
            })
        return results
