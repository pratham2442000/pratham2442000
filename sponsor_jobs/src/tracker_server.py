#!/usr/bin/env python3
"""
tracker_server.py - Zero-dependency local redirect server and web dashboard.
Listens on http://localhost:8765.

Features:
1. Redirect Route: GET /apply/<id>
   - Automatically marks job as 'Applied' in SQLite.
   - Re-analyzes jobs and refreshes recommended_jobs.md.
   - Immediately redirects browser (HTTP 302) to employer's application URL.
2. Web Dashboard: GET /
   - Rich interactive web UI for filtering, searching, and managing applications.
   - One-click apply & track, status transitions, notes, and cover letter mappings.
3. REST APIs:
   - POST /api/apply/<id>
   - POST /api/unapply/<id>
   - POST /api/status/<id>
   - GET /api/jobs
"""

import os
import sys
import json
import sqlite3
import logging
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from typing import Dict, Any, Optional

# Ensure package root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.profile_analyzer import mark_job_status, unapply_job, DB_PATH, OUTPUT_JSON_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>IND Sponsor Job Hunter & Application Tracker | Pratham Johari</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #090d16;
      --bg-card: rgba(18, 26, 44, 0.75);
      --bg-card-hover: rgba(26, 38, 64, 0.9);
      --border-color: rgba(255, 255, 255, 0.08);
      --border-accent: rgba(56, 189, 248, 0.3);
      --primary: #38bdf8;
      --primary-hover: #0ea5e9;
      --accent: #818cf8;
      --success: #34d399;
      --warning: #fbbf24;
      --danger: #f87171;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --badge-bg: rgba(56, 189, 248, 0.12);
      --font-heading: 'Outfit', sans-serif;
      --font-body: 'Inter', sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-dark);
      background-image: radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.12) 0px, transparent 50%),
                        radial-gradient(at 100% 100%, rgba(129, 140, 248, 0.1) 0px, transparent 50%);
      background-attachment: fixed;
      color: var(--text-main);
      font-family: var(--font-body);
      min-height: 100vh;
      padding: 32px 24px;
    }

    .container { max-width: 1400px; margin: 0 auto; }

    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 28px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border-color);
      flex-wrap: wrap;
      gap: 16px;
    }

    .title-group h1 {
      font-family: var(--font-heading);
      font-size: 28px;
      font-weight: 800;
      background: linear-gradient(135deg, #ffffff 0%, #38bdf8 60%, #818cf8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .title-group p {
      color: var(--text-muted);
      font-size: 14px;
      margin-top: 4px;
    }

    .stats-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }

    .stat-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 16px 20px;
      backdrop-filter: blur(12px);
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
      transition: transform 0.2s, border-color 0.2s;
    }
    .stat-card:hover {
      transform: translateY(-2px);
      border-color: var(--border-accent);
    }
    .stat-val {
      font-family: var(--font-heading);
      font-size: 32px;
      font-weight: 700;
      color: var(--primary);
      margin-top: 4px;
    }
    .stat-label {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
    }

    .controls-bar {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 24px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      backdrop-filter: blur(12px);
    }

    .search-input {
      flex: 1;
      min-width: 250px;
      background: rgba(10, 15, 30, 0.8);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 10px 16px;
      border-radius: 8px;
      font-family: var(--font-body);
      font-size: 14px;
      outline: none;
      transition: border-color 0.2s;
    }
    .search-input:focus { border-color: var(--primary); }

    .filter-select {
      background: rgba(10, 15, 30, 0.8);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 10px 14px;
      border-radius: 8px;
      font-family: var(--font-body);
      font-size: 14px;
      outline: none;
      cursor: pointer;
    }

    .jobs-table-container {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      overflow-x: auto;
      backdrop-filter: blur(12px);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 14px;
    }

    th {
      background: rgba(10, 15, 30, 0.9);
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: 0.06em;
      padding: 14px 16px;
      border-bottom: 1px solid var(--border-color);
    }

    td {
      padding: 14px 16px;
      border-bottom: 1px solid var(--border-color);
      vertical-align: middle;
    }

    tr:last-child td { border-bottom: none; }
    tr:hover td { background: var(--bg-card-hover); }

    .score-badge {
      font-family: var(--font-mono);
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 6px;
      display: inline-block;
      font-size: 13px;
    }
    .score-high { background: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.3); }
    .score-mid { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); }
    .score-low { background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.2); }

    .company-name {
      font-weight: 700;
      font-family: var(--font-heading);
      font-size: 15px;
      color: #fff;
    }

    .job-link {
      color: #38bdf8;
      text-decoration: none;
      font-weight: 500;
      transition: color 0.15s;
    }
    .job-link:hover { color: #7dd3fc; text-decoration: underline; }

    .letter-tag {
      font-family: var(--font-mono);
      font-size: 12px;
      background: rgba(129, 140, 248, 0.12);
      color: #a5b4fc;
      border: 1px solid rgba(129, 140, 248, 0.25);
      padding: 4px 8px;
      border-radius: 6px;
      display: inline-block;
      max-width: 260px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .status-badge {
      font-size: 12px;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 20px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .status-applied { background: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.3); }
    .status-unapplied { background: rgba(148, 163, 184, 0.1); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.2); }
    .status-interviewing { background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3); }

    .btn-apply {
      background: linear-gradient(135deg, #0284c7, #2563eb);
      color: #ffffff;
      border: none;
      padding: 8px 14px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      text-decoration: none;
      box-shadow: 0 2px 10px rgba(37, 99, 235, 0.3);
      transition: all 0.2s;
    }
    .btn-apply:hover {
      background: linear-gradient(135deg, #0369a1, #1d4ed8);
      transform: translateY(-1px);
      box-shadow: 0 4px 14px rgba(37, 99, 235, 0.45);
    }
    .btn-applied {
      background: rgba(52, 211, 153, 0.2);
      color: #34d399;
      border: 1px solid rgba(52, 211, 153, 0.4);
      box-shadow: none;
    }

    .status-select {
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 12px;
      outline: none;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="title-group">
        <h1>🇳🇱 IND Sponsor Job Tracker</h1>
        <p>Verified Dutch Recognised Sponsors • Highly Skilled Migrant Visa Eligible • Real-Time Tracking</p>
      </div>
      <div>
        <button onclick="fetchJobs()" class="btn-apply" style="background: rgba(255,255,255,0.1); border: 1px solid var(--border-color);">🔄 Refresh</button>
      </div>
    </header>

    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">Total EU Jobs</div>
        <div class="stat-val" id="stat-total">0</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Submitted Applications</div>
        <div class="stat-val" id="stat-applied" style="color: var(--success)">0</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Priority Roles (75%+)</div>
        <div class="stat-val" id="stat-priority" style="color: var(--accent)">0</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Pending Review</div>
        <div class="stat-val" id="stat-pending" style="color: var(--warning)">0</div>
      </div>
    </div>

    <div class="controls-bar">
      <input type="text" id="search-box" class="search-input" placeholder="🔍 Search company, role, skills, or location..." oninput="filterTable()">
      <select id="status-filter" class="filter-select" onchange="filterTable()">
        <option value="all">All Statuses</option>
        <option value="applied">Applied (✅)</option>
        <option value="unapplied">Unapplied (⬜)</option>
        <option value="interviewing">Interviewing (💬)</option>
      </select>
      <select id="tier-filter" class="filter-select" onchange="filterTable()">
        <option value="all">All Scores</option>
        <option value="priority">Priority Matches (75%+)</option>
        <option value="strong">Strong Matches (60% - 74%)</option>
        <option value="explore">Explore More (40% - 59%)</option>
      </select>
    </div>

    <div class="jobs-table-container">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Status</th>
            <th>Match Score</th>
            <th>Company</th>
            <th>Job Title & Location</th>
            <th>Recommended Letter Body</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="jobs-tbody">
          <tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">Loading sponsor jobs...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <script>
    let allJobs = [];

    async function fetchJobs() {
      try {
        const resp = await fetch('/api/jobs');
        allJobs = await resp.json();
        updateStats();
        filterTable();
      } catch (e) {
        console.error("Error fetching jobs:", e);
      }
    }

    function updateStats() {
      const total = allJobs.length;
      const applied = allJobs.filter(j => j.applied === 1 || (j.status && j.status !== 'unapplied')).length;
      const priority = allJobs.filter(j => j.score >= 75).length;
      const pending = total - applied;

      document.getElementById('stat-total').textContent = total;
      document.getElementById('stat-applied').textContent = applied;
      document.getElementById('stat-priority').textContent = priority;
      document.getElementById('stat-pending').textContent = pending;
    }

    function filterTable() {
      const query = document.getElementById('search-box').value.toLowerCase();
      const statusFilter = document.getElementById('status-filter').value;
      const tierFilter = document.getElementById('tier-filter').value;

      const filtered = allJobs.filter(j => {
        const text = `${j.company} ${j.title} ${j.location} ${j.recommended_letter} ${(j.reasons || []).join(' ')}`.toLowerCase();
        if (query && !text.includes(query)) return false;

        const isApplied = j.applied === 1 || (j.status && j.status !== 'unapplied');
        if (statusFilter === 'applied' && !isApplied) return false;
        if (statusFilter === 'unapplied' && isApplied) return false;
        if (statusFilter === 'interviewing' && j.status !== 'interviewing') return false;

        if (tierFilter === 'priority' && j.score < 75) return false;
        if (tierFilter === 'strong' && (j.score < 60 || j.score >= 75)) return false;
        if (tierFilter === 'explore' && (j.score < 40 || j.score >= 60)) return false;

        return true;
      });

      renderTable(filtered);
    }

    function renderTable(jobs) {
      const tbody = document.getElementById('jobs-tbody');
      if (jobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 40px;">No matching sponsor jobs found.</td></tr>';
        return;
      }

      tbody.innerHTML = jobs.map(j => {
        const scoreClass = j.score >= 75 ? 'score-high' : (j.score >= 60 ? 'score-mid' : 'score-low');
        const isApplied = j.applied === 1 || (j.status && j.status !== 'unapplied');
        const badgeClass = isApplied ? 'status-applied' : 'status-unapplied';
        const badgeText = isApplied ? `✅ Applied ${j.applied_at ? '(' + j.applied_at.substring(0,10) + ')' : ''}` : '⬜ Not Applied';

        return `
          <tr>
            <td style="font-family: var(--font-mono); color: var(--text-muted); font-size: 12px;">#${j.id}</td>
            <td>
              <select class="status-select" onchange="updateStatus(${j.id}, this.value)">
                <option value="unapplied" ${j.status === 'unapplied' ? 'selected' : ''}>⬜ Unapplied</option>
                <option value="applied" ${isApplied && j.status === 'applied' ? 'selected' : ''}>✅ Applied</option>
                <option value="interviewing" ${j.status === 'interviewing' ? 'selected' : ''}>💬 Interviewing</option>
                <option value="offered" ${j.status === 'offered' ? 'selected' : ''}>🎉 Offer</option>
                <option value="rejected" ${j.status === 'rejected' ? 'selected' : ''}>❌ Rejected</option>
              </select>
            </td>
            <td><span class="score-badge ${scoreClass}">${j.score.toFixed(1)}%</span></td>
            <td>
              <div class="company-name">${escapeHtml(j.company)}</div>
              <div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(j.kvk || 'IND Sponsor')}</div>
            </td>
            <td>
              <div><a href="${escapeHtml(j.url)}" target="_blank" class="job-link">${escapeHtml(j.title)}</a></div>
              <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">📍 ${escapeHtml(j.location)}</div>
            </td>
            <td><span class="letter-tag" title="${escapeHtml(j.recommended_letter)}">${escapeHtml(j.recommended_letter)}</span></td>
            <td>
              <div style="display: flex; gap: 8px;">
                <a href="/apply/${j.id}" target="_blank" class="btn-apply ${isApplied ? 'btn-applied' : ''}" onclick="setTimeout(fetchJobs, 1000)">
                  ${isApplied ? '✓ Applied ↗' : '⚡ Apply & Track'}
                </a>
              </div>
            </td>
          </tr>
        `;
      }).join('');
    }

    async function updateStatus(jobId, newStatus) {
      try {
        await fetch(`/api/status/${jobId}?status=${newStatus}`, { method: 'POST' });
        await fetchJobs();
      } catch (e) {
        console.error("Error updating status:", e);
      }
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    window.onload = fetchJobs;
  </script>
</body>
</html>
"""


class JobTrackerHandler(BaseHTTPRequestHandler):
    """HTTP request handler for 1-click tracking redirects and web UI."""
    
    def log_message(self, format, *args):
        # Clean logging
        logging.info(f"[{self.command}] {self.path} - {args[0] if args else ''}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        
        # 1. Automatic 1-Click Apply & Redirect: GET /apply/<id>
        if path.startswith("/apply/"):
            parts = path.split("/")
            if len(parts) >= 3 and parts[2].isdigit():
                job_id = int(parts[2])
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("SELECT url, company_name, title FROM jobs WHERE id = ?", (job_id,))
                row = cur.fetchone()
                conn.close()
                
                if row:
                    job_url, company, title = row[0], row[1], row[2]
                    logging.info(f"🎯 [TRACKER] 1-Click Apply detected for Job #{job_id}: '{title}' at '{company}'")
                    # Mark applied in database and update markdown report
                    mark_job_status(job_id, status="applied")
                    
                    # Redirect browser directly to original job posting
                    self.send_response(302)
                    self.send_header("Location", job_url)
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    return
                else:
                    self.send_error(404, f"Job #{job_id} not found in database")
                    return
            else:
                self.send_error(400, "Invalid Job ID")
                return

        # 2. Revert Application: GET /unapply/<id>
        elif path.startswith("/unapply/"):
            parts = path.split("/")
            if len(parts) >= 3 and parts[2].isdigit():
                job_id = int(parts[2])
                unapply_job(job_id)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "id": job_id, "status": "unapplied"}).encode("utf-8"))
                return

        # 3. REST API: GET /api/jobs
        elif path == "/api/jobs":
            if os.path.exists(OUTPUT_JSON_PATH):
                with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(data.encode("utf-8"))
                return
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"[]")
                return

        # 4. Web Dashboard: GET / or /dashboard
        elif path == "" or path == "/dashboard":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_DASHBOARD.encode("utf-8"))
            return

        else:
            self.send_error(404, "Endpoint not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        # POST /api/status/<id>?status=applied
        if path.startswith("/api/status/"):
            parts = path.split("/")
            if len(parts) >= 4 and parts[3].isdigit():
                job_id = int(parts[3])
                status = query.get("status", ["applied"])[0]
                notes = query.get("notes", [None])[0]
                res = mark_job_status(job_id, status=status, notes=notes)
                if res:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": True, "job": res}).encode("utf-8"))
                    return
                else:
                    self.send_error(404, "Job not found")
                    return

        self.send_error(404, "Endpoint not found")


def start_tracker_server(port: int = 8765, open_browser: bool = False):
    """Start local click-tracking and application server on 127.0.0.1."""
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, JobTrackerHandler)
    logging.info("=" * 65)
    logging.info(f"🚀 IND SPONSOR CLICK-TRACKER & WEB DASHBOARD RUNNING")
    logging.info(f"🌐 Dashboard URL: http://localhost:{port}")
    logging.info(f"⚡ Click-to-Apply Tracker Active on port {port}")
    logging.info("=" * 65)
    
    if open_browser:
        try:
            webbrowser.open(f"http://localhost:{port}")
        except Exception:
            pass
        
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("\nStopping Tracker Server...")
        httpd.server_close()


if __name__ == "__main__":
    start_tracker_server(8765, open_browser=True)
