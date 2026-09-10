#!/usr/bin/env python3
"""
cli.py - Unified Command Line Interface for the IND Sponsor Job Hunter System.
Usage:
    python cli.py update-daily
    python cli.py check "ASML"
    python cli.py top --limit 10
    python cli.py crawl --limit 50
    python cli.py analyze
"""

import sys
import os
import argparse
import sqlite3
import asyncio

# Ensure src is importable
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.ind_fetcher import fetch_and_store_sponsors
from src.company_enricher import enrich_curated_sponsors, guess_company_domains
from src.job_scraper import run_scraper
from src.job_aggregator import aggregate_verified_sponsor_jobs
from src.sponsor_matcher import SponsorMatcher
from src.profile_analyzer import analyze_all_jobs, mark_job_status, unapply_job, format_status_badge, DB_PATH, OUTPUT_MD_PATH
from src.daily_runner import run_daily_pipeline
from src.tracker_server import start_tracker_server
import webbrowser


def cmd_check(args):
    """Check whether a specific company is an IND Recognised Sponsor."""
    company = args.company
    matcher = SponsorMatcher()
    result = matcher.match(company)
    
    print("\n" + "=" * 60)
    if result:
        print(f"✅ VERIFIED IND RECOGNISED SPONSOR")
        print(f"   Official Name : {result['name']}")
        print(f"   Clean Name    : {result['clean_name']}")
        print(f"   KVK Number    : {result['kvk']}")
        print(f"   Target Sector : {'Yes' if result['is_target_sector'] else 'No'}")
        print(f"   Sector Tags   : {result['sector_tags'] or 'None'}")
        
        # Check if we have open jobs recorded for this sponsor
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
        SELECT id, title, location, url, match_score, recommended_letter, applied, status
        FROM jobs
        WHERE sponsor_id = ? AND is_active = 1
        ORDER BY match_score DESC
        """, (result["id"],))
        jobs = cur.fetchall()
        conn.close()
        
        if jobs:
            print(f"\n   📋 {len(jobs)} Active Job(s) Found in Database:")
            for jid, title, loc, url, score, rec_letter, applied, st in jobs[:5]:
                status_txt = " [✅ Applied]" if (applied == 1 or st == "applied") else ""
                print(f"   • [#{jid} | {score:.0f}% Match{status_txt}] {title} ({loc})")
                print(f"     Recommended Letter: {rec_letter}")
                print(f"     URL: {url}\n")
        else:
            print("\n   ℹ️ No active jobs currently indexed for this specific sponsor.")
    else:
        print(f"❌ NOT FOUND in IND Public Register: '{company}'")
        print("   This employer might not be an official Recognised Sponsor for the Highly Skilled Migrant visa.")
    print("=" * 60 + "\n")


def cmd_top(args):
    """Display the top matching jobs directly in the console."""
    limit = args.limit or 10
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    SELECT id, company_name, title, location, match_score, recommended_letter, url, applied, status
    FROM jobs
    WHERE is_active = 1 AND match_score > 0
    ORDER BY match_score DESC
    LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("\nNo jobs in database. Run 'python cli.py update-daily' or 'python cli.py crawl' first.")
        return

    print("\n" + "=" * 80)
    print(f"🎯 TOP {len(rows)} IND SPONSOR JOBS FOR PRATHAM JOHARI")
    print("=" * 80)
    for i, (jid, company, title, loc, score, letter, url, applied, st) in enumerate(rows, 1):
        status_txt = " [✅ APPLIED]" if (applied == 1 or st == "applied") else ""
        print(f"{i:2d}. [#{jid} | {score:.0f}% Match{status_txt}] {company} — {title}")
        print(f"    Location   : {loc}")
        print(f"    Letter Body: {letter}")
        print(f"    Apply Link : {url}")
        print("-" * 80)
    print(f"\nFull report available at: {OUTPUT_MD_PATH}\n")


def cmd_apply(args):
    """Mark a job as applied by ID or company search query."""
    target = args.target
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if target is None:
        # Interactive mode: show top unapplied jobs
        cur.execute("""
        SELECT id, company_name, title, location, match_score, recommended_letter
        FROM jobs
        WHERE is_active = 1 AND applied = 0 AND status = 'unapplied'
        ORDER BY match_score DESC
        LIMIT 15
        """)
        top_unapplied = cur.fetchall()
        conn.close()

        if not top_unapplied:
            print("\n🎉 All top matching jobs are already marked as applied!")
            return

        print("\n" + "=" * 75)
        print("🎯 SELECT A JOB TO MARK AS APPLIED:")
        print("=" * 75)
        for idx, (jid, company, title, loc, score, letter) in enumerate(top_unapplied, 1):
            print(f"{idx:2d}. [#{jid}] {company} — {title} ({score:.0f}%)")
        print("=" * 75)
        try:
            choice = input("\nEnter number (1-15) or Job ID (e.g. 7) to mark applied (or 'q' to quit): ").strip()
            if choice.lower() == 'q' or not choice:
                return
            if choice.isdigit():
                val = int(choice)
                if 1 <= val <= len(top_unapplied):
                    job_id = top_unapplied[val - 1][0]
                else:
                    job_id = val
            else:
                print("Invalid input.")
                return
        except KeyboardInterrupt:
            print("\nCancelled.")
            return
    elif target.isdigit():
        job_id = int(target)
        conn.close()
    else:
        # Search by company name or title
        cur.execute("""
        SELECT id, company_name, title, match_score
        FROM jobs
        WHERE (company_name LIKE ? OR title LIKE ?) AND is_active = 1
        ORDER BY match_score DESC
        LIMIT 10
        """, (f"%{target}%", f"%{target}%"))
        matches = cur.fetchall()
        conn.close()

        if not matches:
            print(f"\n❌ No jobs found matching '{target}'.")
            return
        elif len(matches) == 1:
            job_id = matches[0][0]
        else:
            print(f"\nFound {len(matches)} matching positions:")
            for idx, (mid, comp, tit, sc) in enumerate(matches, 1):
                print(f" {idx}. [#{mid}] {comp} — {tit} ({sc:.0f}%)")
            try:
                ch = input(f"Select 1-{len(matches)} (or 'q' to cancel): ").strip()
                if ch.lower() == 'q' or not ch.isdigit() or not (1 <= int(ch) <= len(matches)):
                    return
                job_id = matches[int(ch) - 1][0]
            except KeyboardInterrupt:
                return

    status = args.status or "applied"
    notes = args.notes
    res = mark_job_status(job_id, status=status, notes=notes)
    if res:
        print("\n" + "=" * 65)
        print(f"✅ MARKED AS APPLIED: Job #{res['id']}")
        print(f"   Company : {res['company']}")
        print(f"   Title   : {res['title']}")
        print(f"   Status  : {res['status'].upper()}")
        if notes:
            print(f"   Notes   : {notes}")
        print(f"   Report  : Updated {OUTPUT_MD_PATH}")
        print("=" * 65 + "\n")
    else:
        print(f"\n❌ Error: Job #{job_id} not found in database.")


def cmd_unapply(args):
    """Revert a job's status back to unapplied."""
    job_id = args.job_id
    success = unapply_job(job_id)
    if success:
        print(f"\n🔄 Job #{job_id} has been reset to UNAPPLIED. Reports updated.\n")
    else:
        print(f"\n❌ Job #{job_id} not found.\n")


def cmd_status(args):
    """Update lifecycle status and notes for an application."""
    job_id = args.job_id
    new_status = args.status
    notes = args.notes
    res = mark_job_status(job_id, status=new_status, notes=notes)
    if res:
        print(f"\n✅ Updated Job #{job_id} status to '{new_status.upper()}'.\n")
    else:
        print(f"\n❌ Job #{job_id} not found.\n")


def cmd_applied(args):
    """List all tracked job applications in the console."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    SELECT id, company_name, title, location, recommended_letter, applied_at, status, notes, url
    FROM jobs
    WHERE applied = 1 OR status != 'unapplied'
    ORDER BY applied_at DESC, id DESC
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("\nℹ️ No applications recorded yet. Run 'python cli.py apply <id>' or use the 1-click apply links!")
        return

    print("\n" + "=" * 85)
    print(f"📌 PRATHAM JOHARI'S SUBMITTED APPLICATIONS ({len(rows)} Tracked)")
    print("=" * 85)
    for jid, comp, tit, loc, rec_letter, app_date, st, notes, url in rows:
        badge = format_status_badge(1, st, app_date)
        dt = app_date[:10] if app_date else "Tracked"
        print(f"[#{jid}] {comp} — {tit}")
        print(f"  Status       : {badge} on {dt}")
        print(f"  Location     : {loc}")
        print(f"  Cover Letter : {rec_letter}")
        if notes:
            print(f"  Notes        : {notes}")
        print(f"  URL          : {url}")
        print("-" * 85)
    print(f"\nView & manage in Web UI: run 'python cli.py web'\n")


def cmd_open(args):
    """Open job application in browser and mark it applied."""
    job_id = args.job_id
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, company_name, title, url FROM jobs WHERE id = ?", (job_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        print(f"\n❌ Job #{job_id} not found.")
        return

    jid, company, title, url = row
    print(f"\n🌐 Opening Job #{jid} in browser: '{title}' at '{company}'...")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Could not open browser: {e}")

    mark_job_status(jid, status="applied")
    print(f"✅ Automatically marked Job #{jid} as APPLIED in database & markdown report!\n")


def main():
    parser = argparse.ArgumentParser(description="IND Sponsor Job Automation & Application Matcher CLI")
    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # Command: update-daily
    sub_daily = subparsers.add_parser("update-daily", help="Run full daily sync: IND + Crawl + Match")
    sub_daily.add_argument("--limit", type=int, default=50, help="Number of sponsor career pages to crawl")
    sub_daily.add_argument("--refresh-ind", action="store_true", help="Force redownload IND register from ind.nl")

    # Command: fetch-sponsors
    sub_fetch = subparsers.add_parser("fetch-sponsors", help="Ingest all 12,927+ IND recognised sponsors")
    sub_fetch.add_argument("--refresh", action="store_true", help="Force live download from ind.nl")

    # Command: crawl
    sub_crawl = subparsers.add_parser("crawl", help="Crawl open positions from tech/engineering sponsors")
    sub_crawl.add_argument("--limit", type=int, default=50, help="Crawl limit for company pages")

    # Command: analyze
    subparsers.add_parser("analyze", help="Re-score jobs and update recommended_jobs.md")

    # Command: check
    sub_check = subparsers.add_parser("check", help="Check if a company is a recognised IND sponsor")
    sub_check.add_argument("company", type=str, help="Company name to search")

    # Command: top
    sub_top = subparsers.add_parser("top", help="Print top matching jobs in console")
    sub_top.add_argument("--limit", type=int, default=10, help="Number of jobs to show")

    # Command: apply
    sub_apply = subparsers.add_parser("apply", help="Mark a job as applied")
    sub_apply.add_argument("target", type=str, nargs="?", default=None, help="Job ID or company name")
    sub_apply.add_argument("--status", type=str, default="applied", help="Status (applied, interviewing, offered, rejected)")
    sub_apply.add_argument("--notes", type=str, default=None, help="Custom notes for this application")

    # Command: unapply
    sub_unapply = subparsers.add_parser("unapply", help="Reset a job back to unapplied")
    sub_unapply.add_argument("job_id", type=int, help="Numeric Job ID")

    # Command: status
    sub_status = subparsers.add_parser("status", help="Update application status (interviewing, offered, rejected)")
    sub_status.add_argument("job_id", type=int, help="Numeric Job ID")
    sub_status.add_argument("status", type=str, help="New status string")
    sub_status.add_argument("--notes", type=str, default=None, help="Optional application notes")

    # Command: applied
    subparsers.add_parser("applied", help="Display all submitted/tracked job applications")

    # Command: open
    sub_open = subparsers.add_parser("open", help="Open job in browser and automatically mark as applied")
    sub_open.add_argument("job_id", type=int, help="Numeric Job ID")

    # Command: tracker / web
    sub_tracker = subparsers.add_parser("tracker", help="Start background 1-click redirect tracking server")
    sub_tracker.add_argument("--port", type=int, default=8765, help="Port to run tracker server on")

    sub_web = subparsers.add_parser("web", help="Launch interactive Web Dashboard in browser")
    sub_web.add_argument("--port", type=int, default=8765, help="Port for web dashboard")

    args = parser.parse_args()

    if args.subcommand == "update-daily":
        run_daily_pipeline(scrape_limit=args.limit, force_ind_refresh=args.refresh_ind)
    elif args.subcommand == "fetch-sponsors":
        fetch_and_store_sponsors(force_refresh=args.refresh)
    elif args.subcommand == "crawl":
        enrich_curated_sponsors()
        asyncio.run(run_scraper(limit=args.limit))
        aggregate_verified_sponsor_jobs()
        analyze_all_jobs()
    elif args.subcommand == "analyze":
        analyze_all_jobs()
    elif args.subcommand == "check":
        cmd_check(args)
    elif args.subcommand == "top":
        cmd_top(args)
    elif args.subcommand == "apply":
        cmd_apply(args)
    elif args.subcommand == "unapply":
        cmd_unapply(args)
    elif args.subcommand == "status":
        cmd_status(args)
    elif args.subcommand == "applied":
        cmd_applied(args)
    elif args.subcommand == "open":
        cmd_open(args)
    elif args.subcommand == "tracker":
        start_tracker_server(port=args.port, open_browser=False)
    elif args.subcommand == "web":
        start_tracker_server(port=args.port, open_browser=True)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
