#!/usr/bin/env python3
"""
cli.py - Standardized Command Line Interface for Personalization Profile System (v2).

Supports full feature parity with legacy tooling, all dynamically driven by a
single Personalization Profile (user_profile.yaml).

Usage:
    python v2/cli.py --profile v2/schemas/pratham.example.yaml validate
    python v2/cli.py --profile v2/schemas/pratham.example.yaml top --limit 10
    python v2/cli.py --profile v2/schemas/pratham.example.yaml web
    python v2/cli.py --profile v2/schemas/pratham.example.yaml update-daily
    python v2/cli.py --profile v2/schemas/pratham.example.yaml check "Databricks"
    python v2/cli.py --profile v2/schemas/pratham.example.yaml extract --file sample_jd.txt
    python v2/cli.py --profile v2/schemas/pratham.example.yaml crawl --limit 50
    python v2/cli.py --profile v2/schemas/pratham.example.yaml apply 123
"""

from __future__ import annotations

import os
import sys
import argparse
import json
import sqlite3
import asyncio
import logging
import webbrowser

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from v2.profile_schema import PersonalizationProfile
from v2.core.config_loader import load_profile, DEFAULT_PROFILE_PATH
from v2.core.company_matcher import CompanyMatcher
from v2.core.profile_analyzer import ProfileAnalyzer, format_status_badge
from v2.core.tracker import ApplicationTracker
from v2.storage.db import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def resolve_db_path(args, profile: PersonalizationProfile) -> str:
    """Resolve database path from CLI args or profile settings (single source of truth)."""
    return getattr(args, "db", None) or profile.output_settings.sqlite_db_path or "v2/data/sponsors.db"


def cmd_validate(args, profile: PersonalizationProfile):
    """Validate profile schema and show high-level summary."""
    target_path = args.target_file or getattr(args, "profile_path", DEFAULT_PROFILE_PATH)
    print("\n" + "=" * 70)
    print(f"🔍 VALIDATING PERSONALIZATION PROFILE: {target_path}")
    print("=" * 70)
    try:
        prof = load_profile(target_path) if args.target_file else profile
        print(f"✅ Schema Validation Passed (Schema v{prof.schema_version})")
        print(f"   Profile ID        : {prof.profile_id}")
        print(f"   Candidate Name    : {prof.candidate_background.personal_info.name}")
        print(f"   Email             : {prof.candidate_background.personal_info.email or 'N/A'}")
        print(f"   Location          : {prof.candidate_background.personal_info.location or 'N/A'}")
        print(f"   Education Degrees : {len(prof.candidate_background.education)}")
        print(f"   Skill Categories  : {len(prof.candidate_background.verified_technical_skills)}")
        print(f"   Target Roles      : {len(prof.candidate_preferences.target_roles)}")
        print(f"   Location Tiers    : {len(prof.candidate_preferences.locations.tiers)}")
        print(f"   Tier 1 Employers  : {len(prof.target_companies_and_domains.company_tiers.tier_1_dream)}")
        print(f"   Curated Sponsors  : {len(prof.target_companies_and_domains.company_tiers.curated_sponsors)}")
        print(f"   Letter Templates  : {len(prof.evaluation_and_scoring_rubric.cover_letter_templates)}")
        print(f"   Strict Senior Excl: {prof.candidate_preferences.seniority.strict_exclusion}")
        print(f"   Disallowed Levels : {len(prof.candidate_preferences.seniority.disallowed_levels)} ({', '.join(prof.candidate_preferences.seniority.disallowed_levels[:4])}...)")
        print("=" * 70 + "\n")
    except Exception as e:
        print(f"\n❌ Validation Failed: {e}\n" + "=" * 70 + "\n")
        sys.exit(1)


def cmd_check(args, profile: PersonalizationProfile):
    """Check an employer against candidate preference tiers and sponsor registers."""
    company = args.company
    db_path = resolve_db_path(args, profile)
    matcher = CompanyMatcher(profile, db_path=db_path)
    res = matcher.match(company)

    print("\n" + "=" * 65)
    print(f"🏢 EMPLOYER EVALUATION FOR: {company}")
    print("=" * 65)
    print(f"   Matched Name       : {res.matched_name}")
    print(f"   Candidate Tier     : {res.tier}")
    print(f"   Score Multiplier   : {res.multiplier}x")
    print(f"   Bonus Points       : +{res.bonus_points:.0f} pts" if res.bonus_points > 0 else "   Bonus Points       : None")
    print(f"   Verified Sponsor   : {'✅ Yes' if res.is_verified_sponsor else '❌ Not in Registry'}")
    if res.kvk:
        print(f"   KVK Number         : {res.kvk}")
    if res.ats_type:
        print(f"   ATS Platform       : {res.ats_type.capitalize()}")
    if res.reason:
        print(f"   Rationale          : {res.reason}")

    # Check active jobs in database
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
        SELECT id, title, location, url, match_score, recommended_letter, status
        FROM jobs
        WHERE company_name LIKE ? AND is_active = 1
        ORDER BY match_score DESC LIMIT 5
        """, (f"%{res.matched_name}%",))
        jobs = cur.fetchall()
        conn.close()

        if jobs:
            print(f"\n   📋 {len(jobs)} Active Indexed Roles Found:")
            for jid, tit, loc, u, sc, let, st in jobs:
                status_txt = f" [{st.upper()}]" if st != "unapplied" else ""
                print(f"   • [#{jid} | {sc:.0f}% Match{status_txt}] {tit} ({loc})")
                print(f"     Letter: {let} | Apply: {u}\n")
    except Exception:
        pass

    print("=" * 65 + "\n")


def cmd_extract(args, profile: PersonalizationProfile):
    """Extract keywords and score a job description text against the profile."""
    text = ""
    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: File not found '{args.file}'")
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        print("Please provide job text either via argument or --file.")
        sys.exit(1)

    analyzer = ProfileAnalyzer(profile)
    res = analyzer.extract_keywords(text, title=args.title, location=args.location, company=args.company)

    print("\n" + "=" * 75)
    print(f"📋 JOB DESCRIPTION EVALUATION FOR: {profile.candidate_background.personal_info.name}")
    print("=" * 75)
    print(f"🎯 Match Score        : {res['match_score']:.1f}%")
    print(f"✉️  Recommended Letter : {res['recommended_letter']}")
    if res['detected_metadata']['seniority_warning']:
        print(f"⚠️  Seniority Warning  : {res['detected_metadata']['seniority_warning']}")
    print(f"\n🔑 Technical Keywords Matched ({res['total_count']} found):")
    for cat, kws in res['categorized'].items():
        print(f"   • {cat:<24}: {', '.join(kws)}")

    if res['talking_points']:
        print(f"\n💡 Suggested Pitch / Letter Highlights:")
        for tp in res['talking_points']:
            print(f"   - {tp}")

    print("\n📊 Scoring Breakdown:")
    for r in res['match_reasons']:
        print(f"   + {r}")
    print("=" * 75 + "\n")


def cmd_top(args, profile: PersonalizationProfile):
    """Display top recommended jobs directly in console."""
    db_path = resolve_db_path(args, profile)
    limit = args.limit or 10
    db = DatabaseManager(db_path)
    rows = db.get_top_jobs(limit=limit, only_new=args.new)

    if not rows:
        print("\nℹ️ No active jobs found. Run 'python v2/cli.py analyze' or 'python v2/cli.py update-daily' first.\n")
        return

    cand_name = profile.candidate_background.personal_info.name
    print("\n" + "=" * 80)
    print(f"🎯 TOP {len(rows)} RECOMMENDED JOBS FOR {cand_name.upper()}")
    print("=" * 80)
    for i, j in enumerate(rows, 1):
        status_txt = f" [✅ {j['status'].upper()}]" if j['applied'] or j['status'] != 'unapplied' else ""
        new_txt = " [🆕 NEW]" if j['is_new'] else ""
        print(f"{i:2d}. [#{j['id']} | {j['score']:.0f}% Match{status_txt}{new_txt}] {j['company']} — {j['title']}")
        print(f"    Location    : {j['location']}")
        print(f"    Letter Body : {j['recommended_letter']}")
        print(f"    Apply Link  : {j['url']}")
        print("-" * 80)
    print()


def cmd_analyze(args, profile: PersonalizationProfile):
    """Run full evaluation on database jobs using profile."""
    db_path = resolve_db_path(args, profile)
    analyzer = ProfileAnalyzer(profile, db_path=db_path)
    print(f"\nEvaluating active jobs against profile '{profile.profile_id}'...")
    jobs = analyzer.analyze_all_jobs()
    reports_dir = profile.output_settings.reports_dir or "v2/reports"
    md_file = os.path.join(reports_dir, profile.output_settings.markdown_filename)
    print(f"✅ Successfully evaluated {len(jobs)} jobs.")
    print(f"📄 Generated Personalized Report: {md_file}\n")


def cmd_web(args, profile: PersonalizationProfile):
    """Launch rich interactive web dashboard & 1-click tracker."""
    from v2.core.web_server import start_web_server
    host = getattr(args, "host", "127.0.0.1") or "127.0.0.1"
    port = getattr(args, "port", 8765) or 8765
    no_open = getattr(args, "no_open", False)
    start_web_server(profile, host=host, port=port, open_browser=not no_open)


def cmd_tracker(args, profile: PersonalizationProfile):
    """Start background 1-click apply redirect tracker server."""
    from v2.core.web_server import start_web_server
    host = getattr(args, "host", "127.0.0.1") or "127.0.0.1"
    port = getattr(args, "port", 8765) or 8765
    start_web_server(profile, host=host, port=port, open_browser=False)


def cmd_update_daily(args, profile: PersonalizationProfile):
    """Run the complete daily pipeline (IND sync, enrich, crawl, aggregate, profile score)."""
    from v2.core.daily_runner import run_daily_pipeline
    limit = getattr(args, "limit", 50) or 50
    force = getattr(args, "force", False)
    run_daily_pipeline(profile, scrape_limit=limit, force_ind_refresh=force)


def cmd_crawl(args, profile: PersonalizationProfile):
    """Run ATS scrapers directly."""
    from v2.ingestion.job_scraper import run_scraper
    db_path = resolve_db_path(args, profile)
    limit = getattr(args, "limit", 50) or 50
    platform = getattr(args, "platform", None)
    slug = getattr(args, "slug", None)
    print(f"🚀 Launching ATS Scraper (Limit: {limit})...")
    asyncio.run(run_scraper(limit=limit, db_path=db_path))
    # Re-score with profile
    analyzer = ProfileAnalyzer(profile, db_path=db_path)
    analyzer.analyze_all_jobs(db_path)


def cmd_sync_ind(args, profile: PersonalizationProfile):
    """Download and synchronize IND recognised sponsor public register."""
    from v2.ingestion.ind_fetcher import fetch_and_store_sponsors
    db_path = resolve_db_path(args, profile)
    force = getattr(args, "force", False)
    print(f"🔄 Syncing official IND Recognised Sponsors Register...")
    total = fetch_and_store_sponsors(db_path=db_path, force_refresh=force)
    print(f"✅ Sync complete: {total} sponsors registered.")


def cmd_enrich(args, profile: PersonalizationProfile):
    """Enrich curated sponsors from profile and discover domains."""
    from v2.core.daily_runner import enrich_profile_sponsors
    from v2.ingestion.company_enricher import guess_company_domains
    db_path = resolve_db_path(args, profile)
    print("✨ Enriching target sponsors from profile catalog...")
    enrich_profile_sponsors(profile, db_path=db_path)
    guess_company_domains(db_path=db_path, limit=getattr(args, "limit", 200) or 200)
    print("✅ Enrichment complete.")


def cmd_aggregate(args, profile: PersonalizationProfile):
    """Ingest Dutch tech feeds with IND sponsor verification."""
    from v2.ingestion.job_aggregator import aggregate_verified_sponsor_jobs
    db_path = resolve_db_path(args, profile)
    print("📡 Aggregating verified sponsor jobs from feeds...")
    count = aggregate_verified_sponsor_jobs(db_path=db_path)
    print(f"✅ Aggregated {count} verified postings.")
    analyzer = ProfileAnalyzer(profile, db_path=db_path)
    analyzer.analyze_all_jobs(db_path)


def cmd_open(args, profile: PersonalizationProfile):
    """Open job application portal in browser and record as applied."""
    db_path = resolve_db_path(args, profile)
    conn = sqlite3.connect(db_path, timeout=30)
    cur = conn.cursor()
    cur.execute("SELECT url, company_name, title FROM jobs WHERE id = ?", (args.job_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        print(f"❌ Job #{args.job_id} not found in database.")
        return

    url, company, title = row
    tracker = ApplicationTracker(db_path)
    tracker.mark_status(args.job_id, status="applied")
    analyzer = ProfileAnalyzer(profile, db_path=db_path)
    analyzer.refresh_reports(db_path)

    print(f"🌐 Opening Job #{args.job_id} ({company} — {title}) in browser...")
    print(f"✅ Marked as APPLIED.")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Please open manually: {url}")


def cmd_apply(args, profile: PersonalizationProfile):
    """Mark job as applied (supports interactive selection or search)."""
    db_path = resolve_db_path(args, profile)
    tracker = ApplicationTracker(db_path)
    target = getattr(args, "target", None)

    if target is None:
        # Interactive selector
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
        SELECT id, company_name, title, location, match_score, recommended_letter
        FROM jobs
        WHERE is_active = 1 AND applied = 0 AND status = 'unapplied'
        ORDER BY match_score DESC LIMIT 15
        """)
        unapplied = cur.fetchall()
        conn.close()

        if not unapplied:
            print("\n🎉 All top matching jobs are already marked as applied!")
            return

        print("\n" + "=" * 75)
        print(f"🎯 TOP UNAPPLIED JOBS FOR {profile.candidate_background.personal_info.name.upper()}:")
        print("=" * 75)
        for idx, (jid, comp, tit, loc, sc, let) in enumerate(unapplied, 1):
            print(f"{idx:2d}. [#{jid}] {comp} — {tit} ({sc:.0f}% Match)")
        print("=" * 75)

        try:
            choice = input("\nEnter Job # to mark as applied (or press Enter to cancel): ").strip()
            if not choice:
                return
            job_id = int(choice.lstrip("#"))
        except (ValueError, KeyboardInterrupt):
            print("\nCancelled.")
            return
    else:
        try:
            job_id = int(target.lstrip("#"))
        except ValueError:
            # Search by company name
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT id FROM jobs WHERE company_name LIKE ? AND is_active = 1 ORDER BY match_score DESC LIMIT 1", (f"%{target}%",))
            row = cur.fetchone()
            conn.close()
            if row:
                job_id = row[0]
            else:
                print(f"❌ No active job found matching company '{target}'")
                return

    res = tracker.mark_status(job_id, status="applied", notes=getattr(args, "notes", None))
    if res:
        analyzer = ProfileAnalyzer(profile, db_path=db_path)
        analyzer.refresh_reports(db_path)
        print(f"\n✅ Job #{job_id} ({res['company']} - {res['title']}) marked as APPLIED.")
    else:
        print(f"❌ Job #{job_id} not found.")


def cmd_unapply(args, profile: PersonalizationProfile):
    """Reset a job back to unapplied."""
    db_path = resolve_db_path(args, profile)
    tracker = ApplicationTracker(db_path)
    res = tracker.unapply(args.job_id)
    if res:
        analyzer = ProfileAnalyzer(profile, db_path=db_path)
        analyzer.refresh_reports(db_path)
        print(f"✅ Job #{args.job_id} reverted back to UNAPPLIED.")
    else:
        print(f"❌ Job #{args.job_id} not found.")


def cmd_reject(args, profile: PersonalizationProfile):
    """Mark a job or company as rejected."""
    db_path = resolve_db_path(args, profile)
    tracker = ApplicationTracker(db_path)

    if getattr(args, "list", False):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, company_name, title, location, notes FROM jobs WHERE status = 'rejected' ORDER BY last_seen DESC")
        rows = cur.fetchall()
        conn.close()
        print("\n" + "=" * 75)
        print(f"❌ REJECTED / DISQUALIFIED ROLES ({len(rows)} Total):")
        print("=" * 75)
        for jid, comp, tit, loc, n in rows:
            print(f"• [#{jid}] {comp} — {tit} ({loc})")
            if n:
                print(f"  Notes: {n}")
        print("=" * 75 + "\n")
        return

    target = getattr(args, "target", None)
    if not target:
        print("Please provide a Job ID or company name to reject.")
        return

    try:
        job_id = int(target.lstrip("#"))
        res = tracker.mark_status(job_id, status="rejected", notes=getattr(args, "notes", "Position closed/rejected"))
        if res:
            analyzer = ProfileAnalyzer(profile, db_path=db_path)
            analyzer.refresh_reports(db_path)
            print(f"❌ Job #{job_id} ({res['company']} - {res['title']}) marked as REJECTED.")
        else:
            print(f"Job #{job_id} not found.")
    except ValueError:
        # Match company
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("UPDATE jobs SET status = 'rejected', applied = 0 WHERE company_name LIKE ?", (f"%{target}%",))
        cnt = cur.rowcount
        conn.commit()
        conn.close()
        analyzer = ProfileAnalyzer(profile, db_path=db_path)
        analyzer.refresh_reports(db_path)
        print(f"❌ Marked {cnt} roles for company matching '{target}' as REJECTED.")


def cmd_uninterested(args, profile: PersonalizationProfile):
    """Mark a job as uninterested or list uninterested jobs."""
    db_path = resolve_db_path(args, profile)
    tracker = ApplicationTracker(db_path)
    job_id = getattr(args, "job_id", None)

    if job_id is None:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
        SELECT id, company_name, title, location, match_score, url
        FROM jobs
        WHERE status = 'uninterested'
        ORDER BY id DESC
        """)
        rows = cur.fetchall()
        conn.close()

        if not rows:
            print("\nℹ️ No jobs currently marked as uninterested.\n")
            return

        print("\n" + "=" * 80)
        print(f"🚫 UNINTERESTED JOBS ({len(rows)} Hidden from Active Recommendations)")
        print("=" * 80)
        for jid, comp, tit, loc, sc, url in rows:
            print(f"• [#{jid}] {comp} — {tit} ({sc:.0f}% match)")
            print(f"  Location: {loc} | URL: {url}")
            print(f"  To revert: python v2/cli.py unapply {jid}")
            print("-" * 80)
        print()
        return

    res = tracker.mark_status(job_id, status="uninterested")
    if res:
        analyzer = ProfileAnalyzer(profile, db_path=db_path)
        analyzer.refresh_reports(db_path)
        print(f"\n🚫 Job #{job_id} marked as UNINTERESTED. It is now hidden from active recommendations.\n")
    else:
        print(f"\n❌ Job #{job_id} not found.\n")


def cmd_new(args, profile: PersonalizationProfile):
    """Display newly discovered jobs."""
    setattr(args, "new", True)
    if not getattr(args, "limit", None):
        setattr(args, "limit", 20)
    cmd_top(args, profile)


def cmd_status(args, profile: PersonalizationProfile):
    """Update application status of a job."""
    db_path = resolve_db_path(args, profile)
    tracker = ApplicationTracker(db_path)
    res = tracker.mark_status(args.job_id, status=args.status, notes=args.notes)
    if res:
        analyzer = ProfileAnalyzer(profile, db_path=db_path)
        analyzer.refresh_reports(db_path)
        print(f"✅ Job #{args.job_id} ({res['company']} - {res['title']}) status updated to '{args.status.upper()}'.")
    else:
        print(f"❌ Job #{args.job_id} not found.")


def cmd_applied(args, profile: PersonalizationProfile):
    """List all currently submitted applications and status."""
    db_path = resolve_db_path(args, profile)
    tracker = ApplicationTracker(db_path)
    apps = tracker.get_applications()

    print("\n" + "=" * 80)
    print(f"📌 ACTIVE APPLICATIONS TRACKER FOR: {profile.candidate_background.personal_info.name.upper()} ({len(apps)} Total)")
    print("=" * 80)
    if not apps:
        print("No active submitted applications recorded.")
    for a in apps:
        badge = format_status_badge(a['applied'], a['status'], a['applied_at'])
        print(f"• [#{a['id']} | {a['match_score']:.0f}%] {a['company']} — {a['title']}")
        print(f"  Status   : {badge}")
        print(f"  Location : {a['location']}")
        print(f"  Letter   : {a['recommended_letter']}")
        print(f"  Portal   : {a['url']}")
        if a['notes']:
            print(f"  Notes    : {a['notes']}")
        print("-" * 80)
    print()


def cmd_add(args, profile: PersonalizationProfile):
    """Manually insert an external or LinkedIn role and score it."""
    db_path = resolve_db_path(args, profile)
    company = args.company
    title = args.title
    url = args.url or f"https://custom-entry.local/{company.lower()}-{int(os.times()[4])}"
    loc = args.location or "Amsterdam, Netherlands"
    desc = args.description or args.notes or ""

    analyzer = ProfileAnalyzer(profile, db_path=db_path)
    score_res = analyzer.scorer.score_job(title, loc, desc, company, allow_senior=True)
    reason_str = " | ".join(score_res.reasons)

    conn = sqlite3.connect(db_path, timeout=30)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO jobs (
        company_name, title, location, url, description, source,
        match_score, match_reason, recommended_letter, is_active,
        status, notes, is_new
    ) VALUES (?, ?, ?, ?, ?, 'Manual Entry', ?, ?, ?, 1, ?, ?, 1)
    """, (company, title, loc, url, desc, score_res.score, reason_str,
          score_res.recommended_letter, args.status or 'unapplied', args.notes))
    conn.commit()
    job_id = cur.lastrowid
    conn.close()

    analyzer.analyze_all_jobs(db_path)
    print(f"\n✅ Added Custom Role [#{job_id} | {score_res.score:.0f}% Match] {company} — {title}")
    print(f"   Recommended Letter : {score_res.recommended_letter}")
    print(f"   Location           : {loc}")
    print(f"   Saved to database and refreshed recommendation reports.\n")


def cmd_export_schema(args, profile: PersonalizationProfile):
    """Export standard JSON Schema to file or stdout."""
    schema = PersonalizationProfile.get_json_schema()
    out_path = args.out or "v2/schemas/profile.schema.json"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    print(f"✅ Exported JSON Schema to {out_path}")


class CleanCLIParser(argparse.ArgumentParser):
    """Refined CLI parser with grouped, beautiful command formatting."""

    def format_help(self) -> str:
        if " " in self.prog.strip():
            return super().format_help()
        return """v2 Unified Personalization Engine & Profile-Driven Matcher

Usage:
  python v2/cli.py [--profile PATH] <command> [options]

Job Search & Recommendations:
  top                 Display top matching jobs in console
  new                 Display newly added jobs since the last daily sync
  applied             List all active job applications and interview statuses
  check               Check employer tier, sponsorship status, and active roles
  extract             Extract keywords and score a job description

Application Tracking:
  open                Open job link in browser and mark as applied
  apply               Mark job as applied
  unapply             Revert job status back to unapplied
  status              Update job application status (applied, interviewing, offered, etc.)
  reject              Mark job or company as rejected
  uninterested        Mark a job as uninterested or list uninterested jobs
  add                 Manually add an external role to the database

Sync & Data Ingestion:
  update-daily        Run complete daily sync pipeline (aliases: update_daily, daily)
  crawl               Run ATS scrapers for target employers
  sync-ind            Download official IND Recognised Sponsors register (alias: fetch-sponsors)
  enrich              Enrich sponsors from profile catalog
  aggregate           Ingest verified tech feeds

Profile, System & Dashboard:
  analyze             Re-score all database jobs and generate reports (alias: rescore)
  validate            Validate personalization profile against schema
  export-schema       Export profile JSON Schema
  web                 Launch interactive web dashboard & 1-click tracker
  tracker             Start background 1-click tracker server

Options:
  -h, --help          Show this help message and exit
  --profile, -p PATH  Path to Personalization Profile YAML or JSON
                      (default: v2/schemas/pratham.example.yaml)
"""

    def error(self, message: str):
        sys.stderr.write(f"\n❌ Error: {message}\n\nRun 'python v2/cli.py --help' to view available commands and usage.\n\n")
        sys.exit(2)


def main():
    parser = CleanCLIParser(
        description="v2 Unified Personalization Engine & Profile-Driven Matcher."
    )
    parser.add_argument(
        "--profile", "-p",
        default=DEFAULT_PROFILE_PATH,
        help="Path to user Personalization Profile YAML or JSON (default: v2/schemas/pratham.example.yaml)"
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # validate
    sub_val = subparsers.add_parser("validate", help="Validate a personalization profile against schema")
    sub_val.add_argument("target_file", nargs="?", help="Optional file path to validate")

    # check
    sub_check = subparsers.add_parser("check", help="Check employer tier and visa sponsorship")
    sub_check.add_argument("company", help="Company name to evaluate")
    sub_check.add_argument("--db", help="Custom database path")

    # extract
    sub_ext = subparsers.add_parser("extract", help="Extract keywords and score job description")
    sub_ext.add_argument("text", nargs="?", help="Raw job description text")
    sub_ext.add_argument("--file", "-f", help="Path to text file containing job description")
    sub_ext.add_argument("--title", "-t", help="Job title override")
    sub_ext.add_argument("--company", "-c", help="Company name override")
    sub_ext.add_argument("--location", "-l", help="Location override")

    # top
    sub_top = subparsers.add_parser("top", help="Display top matching jobs in console")
    sub_top.add_argument("--limit", "-n", type=int, default=10, help="Number of jobs to display")
    sub_top.add_argument("--new", action="store_true", help="Only show newly discovered jobs")
    sub_top.add_argument("--db", help="Custom database path")

    # new
    sub_new = subparsers.add_parser("new", help="Display newly added jobs since the last daily sync")
    sub_new.add_argument("--limit", "-n", type=int, default=20, help="Number of jobs to display")
    sub_new.add_argument("--db", help="Custom database path")

    # analyze (alias: rescore)
    sub_an = subparsers.add_parser("analyze", aliases=["rescore"], help="Re-score all database jobs and generate reports")
    sub_an.add_argument("--db", help="Custom database path")

    # update-daily (aliases: update_daily, daily)
    sub_ud = subparsers.add_parser("update-daily", aliases=["update_daily", "daily"], help="Run complete daily sync pipeline")
    sub_ud.add_argument("--limit", type=int, default=50, help="Scraper limit")
    sub_ud.add_argument("--force", action="store_true", help="Force IND register re-download")

    # web & tracker
    sub_web = subparsers.add_parser("web", help="Launch interactive web dashboard")
    sub_web.add_argument("--port", type=int, default=8765, help="Port to listen on (default 8765)")
    sub_web.add_argument("--host", default="127.0.0.1", help="Host interface")
    sub_web.add_argument("--no-open", action="store_true", help="Do not auto-open browser")

    sub_tr = subparsers.add_parser("tracker", help="Start background 1-click tracker server")
    sub_tr.add_argument("--port", type=int, default=8765, help="Port to listen on (default 8765)")
    sub_tr.add_argument("--host", default="127.0.0.1", help="Host interface")

    # crawl
    sub_cr = subparsers.add_parser("crawl", help="Run ATS scrapers")
    sub_cr.add_argument("--limit", type=int, default=50, help="Scraper limit per ATS")
    sub_cr.add_argument("--platform", help="Filter by ATS platform (greenhouse, lever, ashby, etc.)")
    sub_cr.add_argument("--slug", help="Filter by specific company slug")
    sub_cr.add_argument("--db", help="Custom database path")

    # sync-ind (aliases: fetch-sponsors, sync_ind)
    sub_si = subparsers.add_parser("sync-ind", aliases=["fetch-sponsors", "sync_ind"], help="Download official IND Recognised Sponsors register")
    sub_si.add_argument("--force", action="store_true", help="Force re-download")
    sub_si.add_argument("--db", help="Custom database path")

    # enrich
    sub_en = subparsers.add_parser("enrich", help="Enrich sponsors from profile catalog")
    sub_en.add_argument("--limit", type=int, default=200, help="Domain guessing limit")
    sub_en.add_argument("--db", help="Custom database path")

    # aggregate
    sub_ag = subparsers.add_parser("aggregate", help="Ingest verified tech feeds")
    sub_ag.add_argument("--db", help="Custom database path")

    # open
    sub_op = subparsers.add_parser("open", help="Open job in browser and mark as applied")
    sub_op.add_argument("job_id", type=int, help="Numeric Job ID")
    sub_op.add_argument("--db", help="Custom database path")

    # apply
    sub_app = subparsers.add_parser("apply", help="Mark job as applied")
    sub_app.add_argument("target", nargs="?", help="Job ID or company name")
    sub_app.add_argument("--notes", help="Application notes")
    sub_app.add_argument("--db", help="Custom database path")

    # unapply
    sub_un = subparsers.add_parser("unapply", help="Revert job status back to unapplied")
    sub_un.add_argument("job_id", type=int, help="Numeric Job ID")
    sub_un.add_argument("--db", help="Custom database path")

    # uninterested
    sub_unint = subparsers.add_parser("uninterested", help="Mark a job as uninterested or list uninterested jobs")
    sub_unint.add_argument("job_id", nargs="?", type=int, help="Job ID to mark as uninterested")
    sub_unint.add_argument("--db", help="Custom database path")

    # reject
    sub_rej = subparsers.add_parser("reject", help="Mark job or company as rejected")
    sub_rej.add_argument("target", nargs="?", help="Job ID or company query")
    sub_rej.add_argument("--notes", help="Rejection rationale")
    sub_rej.add_argument("--list", action="store_true", help="List all rejected jobs")
    sub_rej.add_argument("--db", help="Custom database path")

    # status
    sub_st = subparsers.add_parser("status", help="Update job application status")
    sub_st.add_argument("job_id", type=int, help="Numeric Job ID")
    sub_st.add_argument("status", choices=["applied", "interviewing", "offered", "rejected", "uninterested", "unapplied"])
    sub_st.add_argument("--notes", help="Application notes")
    sub_st.add_argument("--db", help="Custom database path")

    # applied
    sub_apd = subparsers.add_parser("applied", help="List all active applications")
    sub_apd.add_argument("--db", help="Custom database path")

    # add
    sub_add = subparsers.add_parser("add", help="Manually add an external role")
    sub_add.add_argument("company", help="Company name")
    sub_add.add_argument("title", help="Job title")
    sub_add.add_argument("--url", help="Job posting URL")
    sub_add.add_argument("--location", default="Amsterdam, Netherlands", help="Location")
    sub_add.add_argument("--description", help="Job description text")
    sub_add.add_argument("--notes", help="Application notes")
    sub_add.add_argument("--status", default="unapplied", help="Initial status")
    sub_add.add_argument("--db", help="Custom database path")

    # export-schema
    sub_sch = subparsers.add_parser("export-schema", help="Export profile JSON Schema")
    sub_sch.add_argument("--out", help="Output file path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Ingest profile
    try:
        profile_path = os.path.abspath(args.profile)
        profile = load_profile(profile_path)
        setattr(args, "profile_path", profile_path)
    except Exception as e:
        print(f"Error loading personalization profile '{args.profile}': {e}")
        sys.exit(1)

    cmd_map = {
        "validate": cmd_validate,
        "check": cmd_check,
        "extract": cmd_extract,
        "top": cmd_top,
        "new": cmd_new,
        "analyze": cmd_analyze,
        "rescore": cmd_analyze,
        "update-daily": cmd_update_daily,
        "update_daily": cmd_update_daily,
        "daily": cmd_update_daily,
        "web": cmd_web,
        "tracker": cmd_tracker,
        "crawl": cmd_crawl,
        "sync-ind": cmd_sync_ind,
        "sync_ind": cmd_sync_ind,
        "fetch-sponsors": cmd_sync_ind,
        "enrich": cmd_enrich,
        "aggregate": cmd_aggregate,
        "open": cmd_open,
        "apply": cmd_apply,
        "unapply": cmd_unapply,
        "uninterested": cmd_uninterested,
        "reject": cmd_reject,
        "status": cmd_status,
        "applied": cmd_applied,
        "add": cmd_add,
        "export-schema": cmd_export_schema
    }

    cmd_map[args.command](args, profile)


if __name__ == "__main__":
    main()
