"""
test_storage_db.py - Unit tests for DatabaseManager and SQLite schema provisioning.
"""

import os
import sqlite3
import pytest
from v2.storage.db import DatabaseManager


def test_db_manager_initialization_and_schema(tmp_path):
    """Verify that DatabaseManager provisions all tables and indexes in a clean directory."""
    db_file = str(tmp_path / "sub" / "fresh.db")
    mgr = DatabaseManager(db_file)
    assert os.path.exists(db_file)

    conn = mgr.get_connection()
    cur = conn.cursor()

    # Verify tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}
    assert "sponsors" in tables
    assert "jobs" in tables

    # Verify indexes
    cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {row[0] for row in cur.fetchall()}
    assert "idx_jobs_score" in indexes
    assert "idx_jobs_status" in indexes
    assert "idx_jobs_url" in indexes

    conn.close()


def test_db_manager_wal_mode(tmp_path):
    """Verify connection executes WAL mode pragma."""
    db_file = str(tmp_path / "wal_test.db")
    mgr = DatabaseManager(db_file)
    conn = mgr.get_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode")
    mode = cur.fetchone()[0]
    assert mode.lower() == "wal"
    conn.close()


def test_legacy_typo_migration(tmp_path):
    """Verify legacy 'unintrested' typo is automatically corrected to 'uninterested'."""
    db_file = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE jobs (
        id INTEGER PRIMARY KEY,
        company_name TEXT,
        title TEXT,
        url TEXT UNIQUE,
        status TEXT,
        match_score REAL DEFAULT 0.0
    )
    """)
    cur.execute("INSERT INTO jobs (id, company_name, title, url, status, match_score) VALUES (1, 'Acme', 'Dev', 'http://a', 'unintrested', 50.0)")
    conn.commit()
    conn.close()

    # Initializing DatabaseManager runs ensure_schema and migrates legacy rows
    mgr = DatabaseManager(db_file)
    conn = mgr.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT status FROM jobs WHERE id = 1")
    row = cur.fetchone()
    assert row[0] == "uninterested"
    conn.close()


def test_get_top_jobs(mock_db_mgr):
    """Verify get_top_jobs retrieves active jobs ordered by score."""
    top_jobs = mock_db_mgr.get_top_jobs(limit=5)
    assert len(top_jobs) <= 5
    assert len(top_jobs) > 0

    scores = [j["score"] for j in top_jobs]
    assert scores == sorted(scores, reverse=True)

    # Excluded statuses shouldn't be returned
    for j in top_jobs:
        assert j["status"] not in ("uninterested", "rejected")
        assert j["score"] > 0


def test_get_top_jobs_only_new(mock_db_mgr):
    """Verify get_top_jobs filters by is_new when requested."""
    top_new = mock_db_mgr.get_top_jobs(limit=10, only_new=True)
    for j in top_new:
        assert j["is_new"] == 1
