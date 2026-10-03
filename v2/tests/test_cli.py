"""
test_cli.py - Unit tests for CLI subcommands, parser aliases, and execution flows.
"""

import sys
import io
import json
import pytest
from unittest.mock import patch, MagicMock

from v2.cli import (
    cmd_validate,
    cmd_check,
    cmd_extract,
    cmd_top,
    cmd_new,
    cmd_status,
    cmd_apply,
    cmd_unapply,
    cmd_uninterested,
    cmd_add,
    cmd_export_schema,
    CleanCLIParser
)
from v2.core.config_loader import DEFAULT_PROFILE_PATH


def test_clean_cli_parser_help():
    """Verify CleanCLIParser groups commands cleanly on root --help."""
    parser = CleanCLIParser(prog="job-hunt", description="Test CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("validate", help="Validate profile")
    subparsers.add_parser("top", help="Display top jobs")

    help_text = parser.format_help()
    assert "Job Search & Recommendations" in help_text
    assert "Application Tracking" in help_text
    assert "validate" in help_text
    assert "top" in help_text


def test_cmd_validate(real_profile, capsys):
    """Verify cmd_validate outputs formatted validation summary."""
    args = MagicMock()
    args.target_file = None
    args.profile_path = DEFAULT_PROFILE_PATH

    cmd_validate(args, real_profile)
    captured = capsys.readouterr().out
    assert "VALIDATING PERSONALIZATION PROFILE" in captured
    assert "Schema Validation Passed" in captured
    assert real_profile.candidate_background.personal_info.name in captured


def test_cmd_check(real_profile, temp_db_path, capsys):
    """Verify cmd_check inspects an employer and outputs tier and sponsorship status."""
    args = MagicMock()
    args.company = "Databricks"
    args.db = temp_db_path

    cmd_check(args, real_profile)
    captured = capsys.readouterr().out
    assert "EMPLOYER EVALUATION FOR: Databricks" in captured
    assert "Tier 1 Dream" in captured
    assert "Score Multiplier" in captured


def test_cmd_extract(real_profile, capsys):
    """Verify cmd_extract evaluates text passed via CLI."""
    args = MagicMock()
    args.text = "Seeking Machine Learning Engineer with Python and PyTorch experience."
    args.file = None
    args.title = "Machine Learning Engineer"
    args.location = "Amsterdam, Netherlands"
    args.company = "Adyen"

    cmd_extract(args, real_profile)
    captured = capsys.readouterr().out
    assert "JOB DESCRIPTION EVALUATION FOR:" in captured
    assert "Match Score" in captured
    assert "Python" in captured or "PyTorch" in captured


def test_cmd_top(real_profile, temp_db_path, capsys):
    """Verify cmd_top retrieves top matches from SQLite."""
    args = MagicMock()
    args.limit = 5
    args.letter = None
    args.region = None
    args.new = False
    args.db = temp_db_path

    cmd_top(args, real_profile)
    captured = capsys.readouterr().out
    assert "RECOMMENDED JOBS FOR" in captured
    assert "Databricks" in captured or "Adyen" in captured


def test_cmd_new(real_profile, temp_db_path, capsys):
    """Verify cmd_new retrieves newly indexed jobs."""
    args = MagicMock()
    args.limit = 5
    args.db = temp_db_path

    cmd_new(args, real_profile)
    captured = capsys.readouterr().out
    assert "RECOMMENDED JOBS FOR" in captured
    assert "[🆕 NEW]" in captured


def test_cmd_status_apply_unapply(real_profile, temp_db_path, capsys):
    """Verify applying, changing status, and unapplying via CLI commands."""
    # 1. Apply
    args_apply = MagicMock()
    args_apply.target = "1"
    args_apply.notes = "CLI applied"
    args_apply.db = temp_db_path
    cmd_apply(args_apply, real_profile)
    out1 = capsys.readouterr().out
    assert "marked as APPLIED" in out1

    # 2. Update status to interviewing
    args_st = MagicMock()
    args_st.job_id = 1
    args_st.status = "interviewing"
    args_st.notes = "Round 1 scheduled"
    args_st.db = temp_db_path
    cmd_status(args_st, real_profile)
    out2 = capsys.readouterr().out
    assert "status updated to 'INTERVIEWING'" in out2

    # 3. Unapply
    args_un = MagicMock()
    args_un.job_id = 1
    args_un.db = temp_db_path
    cmd_unapply(args_un, real_profile)
    out3 = capsys.readouterr().out
    assert "reverted back to UNAPPLIED" in out3


def test_cmd_uninterested(real_profile, temp_db_path, capsys):
    """Verify marking a job as uninterested via CLI."""
    args = MagicMock()
    args.job_id = 1
    args.db = temp_db_path
    cmd_uninterested(args, real_profile)
    captured = capsys.readouterr().out
    assert "marked as UNINTERESTED" in captured


def test_cmd_add(real_profile, temp_db_path, capsys):
    """Verify manually adding an external role via CLI."""
    args = MagicMock()
    args.company = "Helsing"
    args.title = "Autonomous Systems Engineer"
    args.location = "Munich, Germany"
    args.url = "https://helsing.ai/jobs/999"
    args.description = "C++, Python, AI sensor fusion"
    args.notes = "Referral from teammate"
    args.status = "unapplied"
    args.db = temp_db_path

    cmd_add(args, real_profile)
    captured = capsys.readouterr().out
    assert "Added Custom Role" in captured
    assert "Helsing" in captured
    assert "Autonomous Systems Engineer" in captured


def test_cmd_export_schema(real_profile, tmp_path, capsys):
    """Verify cmd_export_schema generates valid JSON Schema file."""
    out_file = str(tmp_path / "schema.json")
    args = MagicMock()
    args.out = out_file

    cmd_export_schema(args, real_profile)
    captured = capsys.readouterr().out
    assert "Exported JSON Schema to" in captured

    with open(out_file, "r", encoding="utf-8") as f:
        schema = json.load(f)
    assert schema.get("title") == "PersonalizationProfile"
    assert "properties" in schema
