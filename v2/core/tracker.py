"""
tracker.py - Profile-Driven Application Lifecycle Tracker (v2).

Tracks application statuses ('unapplied', 'applied', 'interviewing', 'offered', 'rejected', 'uninterested')
and persists user notes into SQLite.
"""

from __future__ import annotations

import os
import sqlite3
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ApplicationTracker:
    """
    Manages persistent application tracking states in the jobs database.
    """

    def __init__(self, db_path: str = "v2/data/sponsors.db"):
        self.db_path = os.path.abspath(os.path.expanduser(db_path))

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        return conn

    def mark_status(
        self,
        job_id: int,
        status: str = "applied",
        notes: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update the application status of a job.
        """
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("SELECT id, company_name, title, url FROM jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return None

        is_applied = 1 if status.lower() in ("applied", "interviewing", "offered") else 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if is_applied else None

        if notes is not None:
            cur.execute("""
            UPDATE jobs
            SET applied = ?,
                applied_at = COALESCE(?, applied_at),
                status = ?,
                notes = ?
            WHERE id = ?
            """, (is_applied, now_str, status.lower(), notes, job_id))
        else:
            cur.execute("""
            UPDATE jobs
            SET applied = ?,
                applied_at = COALESCE(?, applied_at),
                status = ?
            WHERE id = ?
            """, (is_applied, now_str, status.lower(), job_id))

        conn.commit()
        conn.close()

        logger.info(f"Updated Job #{job_id} to status '{status}'")
        return {
            "id": row[0],
            "company": row[1],
            "title": row[2],
            "url": row[3],
            "status": status.lower(),
            "applied": is_applied,
            "notes": notes
        }

    def unapply(self, job_id: int) -> bool:
        """Reset a job back to unapplied."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE jobs
        SET applied = 0,
            applied_at = NULL,
            status = 'unapplied'
        WHERE id = ?
        """, (job_id,))
        changed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def get_applications(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List tracked applications."""
        conn = self._get_connection()
        cur = conn.cursor()

        query = """
        SELECT id, company_name, title, location, match_score, recommended_letter,
               applied, applied_at, status, notes, url
        FROM jobs
        WHERE is_active = 1
        """
        params = []
        if status:
            query += " AND status = ?"
            params.append(status.lower())
        else:
            query += " AND status NOT IN ('unapplied', 'uninterested')"

        query += " ORDER BY applied_at DESC, match_score DESC"

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
                "match_score": r[4],
                "recommended_letter": r[5],
                "applied": r[6],
                "applied_at": r[7],
                "status": r[8],
                "notes": r[9],
                "url": r[10]
            })
        return results
