"""
test_tracker.py - Unit tests for ApplicationTracker state management.
"""

import pytest
from v2.core.tracker import ApplicationTracker


def test_mark_status_applied(mock_tracker):
    """Verify marking job as applied sets applied=1, timestamp, and notes."""
    res = mock_tracker.mark_status(job_id=1, status="applied", notes="Applied via referral")
    assert res is not None
    assert res["id"] == 1
    assert res["status"] == "applied"
    assert res["applied"] == 1
    assert res["notes"] == "Applied via referral"

    apps = mock_tracker.get_applications(status="applied")
    match = next((a for a in apps if a["id"] == 1), None)
    assert match is not None
    assert match["applied"] == 1
    assert match["applied_at"] is not None
    assert match["notes"] == "Applied via referral"


def test_mark_status_interviewing_and_offered(mock_tracker):
    """Verify interviewing and offered statuses maintain applied flag."""
    res_int = mock_tracker.mark_status(job_id=3, status="interviewing")
    assert res_int["status"] == "interviewing"
    assert res_int["applied"] == 1

    res_off = mock_tracker.mark_status(job_id=3, status="offered")
    assert res_off["status"] == "offered"
    assert res_off["applied"] == 1


def test_mark_status_uninterested_and_rejected(mock_tracker):
    """Verify uninterested and rejected statuses set applied=0."""
    res_un = mock_tracker.mark_status(job_id=5, status="uninterested")
    assert res_un["status"] == "uninterested"
    assert res_un["applied"] == 0

    res_rej = mock_tracker.mark_status(job_id=6, status="rejected", notes="Position closed")
    assert res_rej["status"] == "rejected"
    assert res_rej["applied"] == 0
    assert res_rej["notes"] == "Position closed"


def test_unapply(mock_tracker):
    """Verify unapplying resets applied flag, timestamp, and sets status to unapplied."""
    mock_tracker.mark_status(job_id=1, status="applied")
    changed = mock_tracker.unapply(job_id=1)
    assert changed is True

    apps = mock_tracker.get_applications()
    match = next((a for a in apps if a["id"] == 1), None)
    # Default get_applications filters out 'unapplied'
    assert match is None

    # Status explicitly queried
    unapplied_apps = mock_tracker.get_applications(status="unapplied")
    match_un = next((a for a in unapplied_apps if a["id"] == 1), None)
    assert match_un is not None
    assert match_un["applied"] == 0
    assert match_un["applied_at"] is None


def test_mark_status_non_existent_job(mock_tracker):
    """Verify non-existent job ID returns None safely."""
    res = mock_tracker.mark_status(job_id=99999, status="applied")
    assert res is None
