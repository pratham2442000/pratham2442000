"""
web_server.py - Profile-Driven Web Dashboard & 1-Click Apply Tracker (v2).

Provides a local web server (http://localhost:8765) with:
1. Dynamic Dashboard personalized to the active PersonalizationProfile.
2. 1-Click Apply redirection (/apply/<id>) with automatic SQLite tracking.
3. REST APIs for application status updates, live JD keyword extraction, and custom job additions.
"""

from __future__ import annotations

import os
import sys
import json
import sqlite3
import logging
import webbrowser
from socketserver import ThreadingMixIn
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional

from v2.profile_schema import PersonalizationProfile
from v2.core.profile_analyzer import ProfileAnalyzer
from v2.core.tracker import ApplicationTracker

from v2.core.dashboard_template import HTML_DASHBOARD

logger = logging.getLogger(__name__)


def get_dashboard_html(profile: PersonalizationProfile) -> str:
    """Customize HTML dashboard with active candidate profile parameters."""
    cand_name = profile.candidate_background.personal_info.name
    cand_tagline = profile.candidate_background.personal_info.tagline or "AI & Software Engineer"
    custom_html = HTML_DASHBOARD.replace("Pratham Johari", cand_name)
    custom_html = custom_html.replace("MSc Data Science & AI @ TU Delft", cand_tagline)
    return custom_html


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP Server handling simultaneous browser requests."""
    daemon_threads = True
    allow_reuse_address = True


def make_handler(profile: PersonalizationProfile, db_path: str, json_path: str):
    """Factory to create request handler bound to active profile and database paths."""
    analyzer = ProfileAnalyzer(profile, db_path=db_path)
    tracker = ApplicationTracker(db_path=db_path)
    dashboard_html = get_dashboard_html(profile)

    class DynamicTrackerHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            logger.info(f"[{self.command}] {self.path} - {format % args}")

        def _send_response_data(self, content_type: str, data: bytes, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: Any, status: int = 200):
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self._send_response_data("application/json; charset=utf-8", data, status=status)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")

            # 1. 1-Click Apply & Redirect: GET /apply/<id>
            if path.startswith("/apply/"):
                parts = path.split("/")
                if len(parts) >= 3 and parts[2].isdigit():
                    job_id = int(parts[2])
                    conn = sqlite3.connect(db_path, timeout=30)
                    cur = conn.cursor()
                    cur.execute("SELECT url, company_name, title FROM jobs WHERE id = ?", (job_id,))
                    row = cur.fetchone()
                    conn.close()

                    if row:
                        job_url, company, title = row[0], row[1], row[2]
                        logger.info(f"🎯 [TRACKER] 1-Click Apply for Job #{job_id}: '{title}' at '{company}'")
                        tracker.mark_status(job_id, status="applied")
                        analyzer.refresh_reports(db_path)

                        self.send_response(302)
                        self.send_header("Location", job_url)
                        self.send_header("Content-Length", "0")
                        self.send_header("Connection", "close")
                        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                        self.end_headers()
                        return
                    else:
                        self._send_json({"error": f"Job #{job_id} not found"}, status=404)
                        return
                else:
                    self._send_json({"error": "Invalid Job ID"}, status=400)
                    return

            # 2. Revert Application: GET /unapply/<id>
            elif path.startswith("/unapply/"):
                parts = path.split("/")
                if len(parts) >= 3 and parts[2].isdigit():
                    job_id = int(parts[2])
                    tracker.unapply(job_id)
                    analyzer.refresh_reports(db_path)
                    self._send_json({"success": True, "id": job_id, "status": "unapplied"})
                    return

            # 3. REST API: GET /api/jobs
            elif path == "/api/jobs":
                if os.path.exists(json_path):
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = f.read()
                    self._send_response_data("application/json; charset=utf-8", data.encode("utf-8"))
                    return
                else:
                    jobs = analyzer.analyze_all_jobs(db_path)
                    self._send_json(jobs)
                    return

            # 4. Web Dashboard: GET / or /dashboard
            elif path == "" or path == "/dashboard":
                self._send_response_data("text/html; charset=utf-8", dashboard_html.encode("utf-8"))
                return

            elif path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return

            else:
                self._send_json({"error": "Endpoint not found"}, status=404)

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            query = parse_qs(parsed.query)

            # 1. Manual / External Role Submission: POST /api/jobs/add
            if path in ("/api/jobs/add", "/api/jobs"):
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    post_data = self.rfile.read(content_length)
                    try:
                        payload = json.loads(post_data.decode("utf-8"))
                    except Exception:
                        raw_data = parse_qs(post_data.decode("utf-8"))
                        payload = {k: v[0] for k, v in raw_data.items()}

                    company = payload.get("company") or payload.get("company_name")
                    title = payload.get("title")
                    url = payload.get("url")
                    location = payload.get("location") or "Amsterdam, Netherlands"
                    description = payload.get("description", "")
                    status = payload.get("status", "unapplied")
                    notes = payload.get("notes")

                    if not company or not title:
                        self._send_json({"success": False, "error": "Company and Title are required."}, status=400)
                        return

                    # Score job
                    score_res = analyzer.scorer.score_job(title, location, description, company, allow_senior=True)
                    reason_str = " | ".join(score_res.reasons)

                    conn = sqlite3.connect(db_path, timeout=30)
                    cur = conn.cursor()
                    cur.execute("""
                    INSERT INTO jobs (
                        company_name, title, location, url, description, source,
                        match_score, match_reason, recommended_letter, is_active,
                        status, notes, is_new
                    ) VALUES (?, ?, ?, ?, ?, 'Manual Entry', ?, ?, ?, 1, ?, ?, 1)
                    """, (company, title, location, url or f"https://manual/{int(os.times()[4])}",
                          description, score_res.score, reason_str, score_res.recommended_letter,
                          status, notes))
                    conn.commit()
                    job_id = cur.lastrowid
                    conn.close()

                    analyzer.analyze_all_jobs(db_path)
                    self._send_json({"success": True, "id": job_id, "score": score_res.score})
                    return
                except Exception as e:
                    logger.exception(f"Error adding manual job: {e}")
                    self._send_json({"success": False, "error": str(e)}, status=500)
                    return

            # 2. Extract Keywords from JD: POST /api/extract-keywords
            elif path == "/api/extract-keywords":
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    post_data = self.rfile.read(content_length)
                    payload = json.loads(post_data.decode("utf-8"))

                    text = payload.get("text", "")
                    title = payload.get("title", "")
                    location = payload.get("location", "")
                    company = payload.get("company", "")

                    res = analyzer.extract_keywords(text, title=title, location=location, company=company)
                    self._send_json({"success": True, "data": res})
                    return
                except Exception as e:
                    logger.exception(f"Error extracting keywords: {e}")
                    self._send_json({"success": False, "error": str(e)}, status=500)
                    return

            # 3. Status Update: POST /api/status/<id>?status=applied
            elif path.startswith("/api/status/"):
                parts = path.split("/")
                if len(parts) >= 4 and parts[3].isdigit():
                    job_id = int(parts[3])
                    status = query.get("status", ["applied"])[0].lower()
                    notes = query.get("notes", [None])[0]

                    res = tracker.mark_status(job_id, status=status, notes=notes)
                    analyzer.refresh_reports(db_path)
                    if res:
                        self._send_json({"success": True, "job": res})
                    else:
                        self._send_json({"error": f"Job #{job_id} not found"}, status=404)
                    return
                else:
                    self._send_json({"error": "Invalid Job ID"}, status=400)
                    return

            else:
                self._send_json({"error": "Endpoint not found"}, status=404)

    return DynamicTrackerHandler


def start_web_server(
    profile: PersonalizationProfile,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True
):
    """Launch the profile-driven web server and application dashboard."""
    db_path = profile.output_settings.sqlite_db_path or "v2/data/sponsors.db"
    reports_dir = profile.output_settings.reports_dir or "v2/reports"
    json_path = os.path.join(reports_dir, profile.output_settings.json_filename)

    # Initial analysis to ensure JSON report is fresh
    analyzer = ProfileAnalyzer(profile, db_path=db_path)
    analyzer.analyze_all_jobs(db_path)

    handler_cls = make_handler(profile, db_path, json_path)
    server = ThreadedHTTPServer((host, port), handler_cls)

    cand_name = profile.candidate_background.personal_info.name
    url = f"http://{host}:{port}"
    print("=" * 65)
    print(f"🚀 V2 WEB DASHBOARD & 1-CLICK TRACKER FOR: {cand_name.upper()}")
    print(f"🌐 Dashboard URL: {url}")
    print(f"⚡ Click-to-Apply Tracker Active on port {port}")
    print("=" * 65)

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web dashboard server...")
        server.shutdown()
        server.server_close()
