#!/usr/bin/env python3
"""
tracker_server.py - Zero-dependency local redirect server and rich web dashboard.
Listens on http://localhost:8765.

Features:
1. Redirect Route: GET /apply/<id>
   - Automatically marks job as 'Applied' in SQLite.
   - Re-analyzes jobs and refreshes recommended_jobs.md.
   - Immediately redirects browser (HTTP 302) to employer's application URL.
2. Web Dashboard: GET / or /dashboard
   - Rich interactive web UI for filtering, searching, and managing applications.
   - Displays newly added jobs since the last daily sync with dedicated 🆕 NEW badges.
   - Multi-country filtering (Netherlands 🇳🇱, United Kingdom 🇬🇧, Australia 🇦🇺, EU 🇪🇺, Remote 🌐).
   - Strict non-senior role presentation (entry/mid/graduate focus).
   - Instant Python skill match tags and cover letter mappings.
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
from socketserver import ThreadingMixIn
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from typing import Dict, Any, Optional

# Ensure package root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.profile_analyzer import mark_job_status, unapply_job, add_custom_job, extract_job_keywords, DB_PATH, OUTPUT_JSON_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Global Tech & IND Sponsor Job Hunter | Pratham Johari</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #070a12;
      --bg-card: rgba(15, 23, 42, 0.75);
      --bg-card-hover: rgba(30, 41, 69, 0.9);
      --border-color: rgba(255, 255, 255, 0.08);
      --border-accent: rgba(56, 189, 248, 0.3);
      --primary: #38bdf8;
      --primary-hover: #0ea5e9;
      --accent: #818cf8;
      --success: #34d399;
      --warning: #fbbf24;
      --danger: #f87171;
      --gold: #f59e0b;
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
                        radial-gradient(at 100% 100%, rgba(129, 140, 248, 0.1) 0px, transparent 50%),
                        radial-gradient(at 50% 50%, rgba(245, 158, 11, 0.04) 0px, transparent 60%);
      background-attachment: fixed;
      color: var(--text-main);
      font-family: var(--font-body);
      min-height: 100vh;
      padding: 32px 24px;
    }

    .container { max-width: 1480px; margin: 0 auto; }

    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border-color);
      flex-wrap: wrap;
      gap: 16px;
    }

    .title-group h1 {
      font-family: var(--font-heading);
      font-size: 28px;
      font-weight: 800;
      background: linear-gradient(135deg, #ffffff 0%, #38bdf8 50%, #818cf8 100%);
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
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .scope-tag {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--border-color);
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 12px;
      color: #e2e8f0;
    }

    .stats-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 14px;
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
      cursor: pointer;
    }
    .stat-card:hover {
      transform: translateY(-2px);
      border-color: var(--border-accent);
    }
    .stat-card.active-card {
      border-color: var(--gold);
      box-shadow: 0 0 15px rgba(245, 158, 11, 0.25);
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
      padding: 14px 16px;
      margin-bottom: 24px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      backdrop-filter: blur(12px);
    }

    .search-input {
      flex: 1;
      min-width: 260px;
      background: rgba(10, 15, 30, 0.85);
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
      background: rgba(10, 15, 30, 0.85);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 10px 14px;
      border-radius: 8px;
      font-family: var(--font-body);
      font-size: 13px;
      outline: none;
      cursor: pointer;
    }
    .filter-select:focus { border-color: var(--primary); }

    .btn-toggle-new {
      background: rgba(245, 158, 11, 0.15);
      border: 1px solid rgba(245, 158, 11, 0.4);
      color: #fbbf24;
      padding: 9px 15px;
      border-radius: 8px;
      font-family: var(--font-body);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
    }
    .btn-toggle-new:hover, .btn-toggle-new.active {
      background: linear-gradient(135deg, #f59e0b, #d97706);
      color: #ffffff;
      box-shadow: 0 0 14px rgba(245, 158, 11, 0.4);
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
      background: rgba(10, 15, 30, 0.92);
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

    .badge-new {
      background: linear-gradient(135deg, #f59e0b, #ef4444);
      color: #ffffff;
      font-family: var(--font-mono);
      font-size: 10px;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
      margin-left: 6px;
      letter-spacing: 0.04em;
      display: inline-flex;
      align-items: center;
      gap: 3px;
      box-shadow: 0 0 10px rgba(245, 158, 11, 0.45);
      animation: pulseNew 2.5s infinite;
      vertical-align: middle;
    }
    @keyframes pulseNew {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.06); }
    }

    .region-badge {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 4px;
      display: inline-block;
      margin-right: 6px;
      letter-spacing: 0.02em;
    }
    .region-nl { background: rgba(249, 115, 22, 0.15); color: #fb923c; border: 1px solid rgba(249, 115, 22, 0.35); }
    .region-uk { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.35); }
    .region-au { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.35); }
    .region-eu { background: rgba(129, 140, 248, 0.15); color: #a5b4fc; border: 1px solid rgba(129, 140, 248, 0.35); }
    .region-remote { background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.35); }

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
      font-weight: 600;
      font-size: 14.5px;
      transition: color 0.15s;
    }
    .job-link:hover { color: #7dd3fc; text-decoration: underline; }

    .skills-tag-list {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 5px;
    }
    .skill-pill {
      font-size: 11px;
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.06);
      color: #cbd5e1;
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .skill-pill.pill-python {
      background: rgba(245, 158, 11, 0.12);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.3);
      font-weight: 600;
    }

    .letter-tag {
      font-family: var(--font-mono);
      font-size: 11.5px;
      background: rgba(129, 140, 248, 0.12);
      color: #a5b4fc;
      border: 1px solid rgba(129, 140, 248, 0.25);
      padding: 4px 8px;
      border-radius: 6px;
      display: inline-block;
      max-width: 250px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .status-select {
      background: rgba(15, 23, 42, 0.85);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 12px;
      outline: none;
      cursor: pointer;
    }

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

    /* Add Custom Role Box Styles */
    .btn-add-role {
      background: linear-gradient(135deg, #059669, #10b981);
      color: #ffffff;
      border: none;
      padding: 8px 16px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      box-shadow: 0 2px 10px rgba(16, 185, 129, 0.3);
      transition: all 0.2s ease;
    }
    .btn-add-role:hover {
      background: linear-gradient(135deg, #047857, #059669);
      transform: translateY(-1px);
      box-shadow: 0 4px 14px rgba(16, 185, 129, 0.45);
    }

    .add-role-panel {
      background: var(--bg-card);
      border: 1px solid rgba(56, 189, 248, 0.35);
      border-radius: 12px;
      padding: 20px 24px;
      margin-bottom: 24px;
      backdrop-filter: blur(16px);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), 0 0 15px rgba(56, 189, 248, 0.08);
      animation: panelSlide 0.2s ease-out;
    }
    @keyframes panelSlide {
      from { opacity: 0; transform: translateY(-8px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .add-role-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--border-color);
    }
    .add-role-title {
      font-family: var(--font-heading);
      font-size: 16px;
      font-weight: 700;
      color: #ffffff;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .add-form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 14px;
    }
    .form-group {
      display: flex;
      flex-direction: column;
      gap: 5px;
    }
    .form-group label {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
    }
    .form-control {
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 9px 12px;
      color: #ffffff;
      font-size: 13px;
      font-family: var(--font-body);
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .form-control:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2);
    }

    .btn-save-role {
      background: linear-gradient(135deg, #2563eb, #38bdf8);
      color: #ffffff;
      border: none;
      padding: 9px 20px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      box-shadow: 0 2px 10px rgba(37, 99, 235, 0.3);
      transition: all 0.2s;
    }
    .btn-save-role:hover {
      background: linear-gradient(135deg, #1d4ed8, #0ea5e9);
      transform: translateY(-1px);
    }
    .btn-cancel-role {
      background: transparent;
      color: var(--text-muted);
      border: 1px solid var(--border-color);
      padding: 9px 16px;
      border-radius: 8px;
      font-size: 13px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-cancel-role:hover {
      background: rgba(255, 255, 255, 0.05);
      color: #ffffff;
    }

    .badge-source {
      background: rgba(14, 165, 233, 0.15);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.3);
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 4px;
      font-weight: 600;
      margin-left: 6px;
      display: inline-flex;
      align-items: center;
      gap: 3px;
    }

    /* ATS Platform Badge Styles */
    .ats-badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 11.5px;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      white-space: nowrap;
      font-family: var(--font-heading);
      letter-spacing: 0.01em;
      transition: all 0.15s ease;
    }
    .ats-badge:hover {
      transform: translateY(-1px);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    }
    .ats-greenhouse {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }
    .ats-lever {
      background: rgba(99, 102, 241, 0.15);
      color: #a5b4fc;
      border: 1px solid rgba(129, 140, 248, 0.4);
    }
    .ats-ashby {
      background: rgba(168, 85, 247, 0.15);
      color: #c084fc;
      border: 1px solid rgba(192, 132, 252, 0.4);
    }
    .ats-workday {
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border: 1px solid rgba(251, 191, 36, 0.4);
    }
    .ats-smartrecruiters {
      background: rgba(14, 165, 233, 0.15);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.4);
    }
    .ats-workable {
      background: rgba(20, 184, 166, 0.15);
      color: #2dd4bf;
      border: 1px solid rgba(45, 212, 191, 0.4);
    }
    .ats-recruitee {
      background: rgba(6, 182, 212, 0.15);
      color: #22d3ee;
      border: 1px solid rgba(34, 211, 238, 0.4);
    }
    .ats-personio {
      background: rgba(244, 63, 94, 0.15);
      color: #fb7185;
      border: 1px solid rgba(251, 113, 133, 0.4);
    }
    .ats-bamboohr {
      background: rgba(132, 204, 22, 0.15);
      color: #a3e635;
      border: 1px solid rgba(163, 230, 53, 0.4);
    }
    .ats-arbeitnow {
      background: rgba(56, 189, 248, 0.15);
      color: #7dd3fc;
      border: 1px solid rgba(125, 211, 252, 0.4);
    }
    .ats-linkedin {
      background: rgba(10, 102, 194, 0.2);
      color: #60a5fa;
      border: 1px solid rgba(59, 130, 246, 0.4);
    }
    .ats-indeed {
      background: rgba(37, 99, 235, 0.15);
      color: #93c5fd;
      border: 1px solid rgba(96, 165, 250, 0.4);
    }
    .ats-direct {
      background: rgba(148, 163, 184, 0.12);
      color: #cbd5e1;
      border: 1px solid rgba(148, 163, 184, 0.25);
    }

    /* Full Job Description & Keyword Extractor Styles */
    .jd-box-container {
      background: rgba(0, 0, 0, 0.32);
      border: 1px solid rgba(56, 189, 248, 0.25);
      border-radius: 10px;
      padding: 16px 18px;
      margin-bottom: 20px;
      box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.3);
    }
    .jd-box-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      flex-wrap: wrap;
      gap: 10px;
    }
    .badge-live-extract {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.35);
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 12px;
      font-weight: 600;
      letter-spacing: 0.03em;
    }
    .btn-tool {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid var(--border-color);
      color: #cbd5e1;
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: all 0.2s;
    }
    .btn-tool:hover {
      background: rgba(255, 255, 255, 0.15);
      color: #ffffff;
      border-color: var(--primary);
    }
    .jd-textarea {
      width: 100%;
      min-height: 130px;
      resize: vertical;
      font-family: var(--font-mono);
      font-size: 12.5px;
      line-height: 1.5;
      padding: 12px;
    }
    .jd-intelligence-panel {
      margin-top: 14px;
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 14px;
    }
    .jd-empty-tip {
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.5;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .jd-summary-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      padding-bottom: 12px;
      margin-bottom: 12px;
      border-bottom: 1px solid var(--border-color);
    }
    .jd-stat-group {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .jd-actions-group {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .btn-copy-kw {
      background: linear-gradient(135deg, #4f46e5, #7c3aed);
      color: #ffffff;
      border: none;
      padding: 6px 14px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 12px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
      box-shadow: 0 2px 8px rgba(79, 70, 229, 0.3);
    }
    .btn-copy-kw:hover {
      opacity: 0.92;
      transform: translateY(-1px);
    }
    .btn-autofill {
      background: linear-gradient(135deg, #0284c7, #0369a1);
      color: #ffffff;
      border: none;
      padding: 6px 14px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 12px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
      box-shadow: 0 2px 8px rgba(2, 132, 199, 0.3);
    }
    .btn-autofill:hover {
      opacity: 0.92;
      transform: translateY(-1px);
    }
    .jd-alert-senior {
      background: rgba(239, 68, 68, 0.12);
      border: 1px solid rgba(239, 68, 68, 0.35);
      color: #fca5a5;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 12px;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .jd-cat-group {
      display: flex;
      flex-direction: column;
      gap: 9px;
    }
    .jd-cat-row {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      font-size: 12px;
    }
    .jd-cat-name {
      width: 145px;
      flex-shrink: 0;
      font-weight: 600;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 6px;
      padding-top: 3px;
    }
    .jd-pills-wrap {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      flex-grow: 1;
    }
    .jd-pill {
      background: rgba(255, 255, 255, 0.07);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #e2e8f0;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 11.5px;
      font-family: var(--font-mono);
      cursor: pointer;
      transition: all 0.15s;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .jd-pill:hover {
      background: rgba(56, 189, 248, 0.2);
      border-color: rgba(56, 189, 248, 0.5);
      color: #38bdf8;
      transform: translateY(-1px);
    }
    .jd-pill.pill-copied {
      background: rgba(16, 185, 129, 0.3) !important;
      border-color: rgba(16, 185, 129, 0.6) !important;
      color: #34d399 !important;
    }
    .pill-lang { border-color: rgba(245, 158, 11, 0.35); color: #fbbf24; }
    .pill-aiml { border-color: rgba(129, 140, 248, 0.35); color: #a5b4fc; }
    .pill-rag { border-color: rgba(236, 72, 153, 0.35); color: #f472b6; }
    .pill-data { border-color: rgba(56, 189, 248, 0.35); color: #38bdf8; }
    .pill-cloud { border-color: rgba(52, 211, 153, 0.35); color: #34d399; }
    .pill-cv { border-color: rgba(168, 85, 247, 0.35); color: #c084fc; }
    .pill-swe { border-color: rgba(148, 163, 184, 0.35); color: #cbd5e1; }
    .pill-qual { border-color: rgba(251, 191, 36, 0.35); color: #fcd34d; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="title-group">
        <h1>🌐 Global Tech & Sponsor Job Hunter</h1>
        <p>
          <span class="scope-tag">🇳🇱 Netherlands (IND Sponsor)</span>
          <span class="scope-tag">🇬🇧 United Kingdom</span>
          <span class="scope-tag">🇦🇺 Australia</span>
          <span class="scope-tag">🇪🇺 EU & Remote</span>
          <span class="scope-tag" style="color: #34d399; border-color: rgba(52, 211, 153, 0.3);">🛡️ Non-Senior Roles Only</span>
          <span class="scope-tag" style="color: #fbbf24; border-color: rgba(245, 158, 11, 0.3);">🐍 Python & AI Priority</span>
          <span class="scope-tag" style="color: #38bdf8; border-color: rgba(56, 189, 248, 0.3);">⚡ Multi-ATS: Greenhouse, Lever, Ashby, Workday</span>
        </p>
      </div>
      <div style="display: flex; gap: 10px; align-items: center;">
        <button id="btn-toggle-add" onclick="toggleAddRoleBox()" class="btn-add-role">
          📋 Paste JD & Add Role
        </button>
        <button onclick="fetchJobs()" class="btn-apply" style="background: rgba(255,255,255,0.1); border: 1px solid var(--border-color); box-shadow: none;">
          🔄 Refresh Data
        </button>
      </div>
    </header>

    <div class="stats-row">
      <div class="stat-card" onclick="filterByStat('all')">
        <div class="stat-label">Active Non-Senior Roles</div>
        <div class="stat-val" id="stat-total">0</div>
      </div>
      <div class="stat-card" id="card-new" onclick="filterByStat('new')">
        <div class="stat-label">🆕 New Since Last Sync</div>
        <div class="stat-val" id="stat-new" style="color: var(--gold)">0</div>
      </div>
      <div class="stat-card" onclick="filterByStat('applied')">
        <div class="stat-label">Submitted Applications</div>
        <div class="stat-val" id="stat-applied" style="color: var(--success)">0</div>
      </div>
      <div class="stat-card" onclick="filterByStat('priority')">
        <div class="stat-label">Priority Matches (75%+)</div>
        <div class="stat-val" id="stat-priority" style="color: var(--accent)">0</div>
      </div>
      <div class="stat-card" onclick="filterByStat('pending')">
        <div class="stat-label">Pending Review</div>
        <div class="stat-val" id="stat-pending" style="color: var(--warning)">0</div>
      </div>
      <div class="stat-card" id="card-rejected" onclick="filterByStat('rejected')">
        <div class="stat-label">❌ Rejected</div>
        <div class="stat-val" id="stat-rejected" style="color: #f87171">0</div>
      </div>
      <div class="stat-card" onclick="filterByStat('uninterested')">
        <div class="stat-label">🚫 Uninterested</div>
        <div class="stat-val" id="stat-uninterested" style="color: #94a3b8">0</div>
      </div>
    </div>

    <!-- ➕ Add Custom External Role Box & JD Keyword Extractor -->
    <div id="add-role-panel" class="add-role-panel" style="display: none;">
      <div class="add-role-header">
        <div class="add-role-title">
          <span>📋</span> Full Job Description Keyword Extractor & Role Ingestion
        </div>
        <button type="button" class="btn-cancel-role" style="padding: 4px 10px; font-size: 12px;" onclick="toggleAddRoleBox()">✕ Close</button>
      </div>
      <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px;">
        Paste any raw job posting from LinkedIn, Indeed, or career portals below. All technical keywords will be extracted automatically, match percentage computed against your profile, and cover letter body recommended.
      </p>

      <!-- 📋 Full Job Description Textarea Section -->
      <div class="jd-box-container">
        <div class="jd-box-header">
          <div style="font-weight: 700; font-size: 13px; color: #fff; display: flex; align-items: center; gap: 8px;">
            <span>📋</span> Paste Full Job Description (LinkedIn / Indeed / Career Page)
            <span class="badge-live-extract">⚡ Auto-Extracts Keywords</span>
          </div>
          <div style="display: flex; gap: 8px;">
            <button type="button" class="btn-tool" onclick="pasteClipboardToJD()">📋 Paste from Clipboard</button>
            <button type="button" class="btn-tool" onclick="clearJDTextarea()">🧹 Clear</button>
          </div>
        </div>
        <textarea id="input-jd" class="form-control jd-textarea" rows="6" 
          placeholder="Paste the full job description here (Ctrl+V / Cmd+V)... Keywords, skills, match score %, and cover letter recommendations will be extracted instantly!"
          oninput="handleJDPasteOrInput()"></textarea>

        <!-- Extracted Keywords & Intelligence Display -->
        <div id="jd-intelligence-panel" class="jd-intelligence-panel">
          <div id="jd-empty-tip" class="jd-empty-tip">
            <span>💡</span>
            <span><strong>Instant Keyword Extraction:</strong> Copy & paste any raw job posting above. All technical skills, frameworks, tools, match percentage, and recommended cover letter body will be detected automatically. You can copy all keywords with 1 click to tailor your CV!</span>
          </div>
          <div id="jd-extracted-content" style="display: none;">
            <div class="jd-summary-bar">
              <div class="jd-stat-group">
                <span id="jd-badge-count" class="badge-live-extract" style="font-size: 12px;">0 Keywords Found</span>
                <span id="jd-badge-score" class="score-badge score-high">0% Match</span>
                <span id="jd-badge-letter" class="letter-tag" style="max-width: 320px;">Letter: 1. GENERIC</span>
              </div>
              <div class="jd-actions-group">
                <button type="button" id="btn-copy-keywords" class="btn-copy-kw" onclick="copyExtractedKeywords()">
                  📋 Copy All Keywords
                </button>
                <button type="button" class="btn-autofill" onclick="autoFillFormFromExtracted()">
                  ⚡ Auto-Fill Form Fields
                </button>
              </div>
            </div>
            
            <div id="jd-senior-warning" class="jd-alert-senior" style="display: none;"></div>

            <div id="jd-categories-container" class="jd-cat-group"></div>
          </div>
        </div>
      </div>
      
      <!-- Role Details & Save Form -->
      <form id="form-add-role" onsubmit="submitCustomJob(event)">
        <div class="add-form-grid">
          <div class="form-group">
            <label>Company Name <span style="color: var(--danger)">*</span></label>
            <input type="text" id="input-company" class="form-control" placeholder="e.g. Stripe, ASML, Booking.com, Databricks..." required>
          </div>
          <div class="form-group">
            <label>Job Title <span style="color: var(--danger)">*</span></label>
            <input type="text" id="input-title" class="form-control" placeholder="e.g. Python AI / Software Engineer" required>
          </div>
          <div class="form-group">
            <label>Job Link / LinkedIn URL</label>
            <input type="url" id="input-url" class="form-control" placeholder="https://www.linkedin.com/jobs/view/...">
          </div>
          <div class="form-group">
            <label>Location</label>
            <input type="text" id="input-location" class="form-control" placeholder="e.g. Amsterdam, Netherlands" value="Amsterdam, Netherlands">
          </div>
          <div class="form-group">
            <label>Initial Status</label>
            <select id="input-status" class="form-control">
              <option value="unapplied">⬜ Unapplied (To Apply Later)</option>
              <option value="applied">✅ Already Applied</option>
              <option value="interviewing">💬 Interviewing</option>
            </select>
          </div>
          <div class="form-group">
            <label>Notes / Key Extracted Requirements</label>
            <input type="text" id="input-notes" class="form-control" placeholder="Extracted keywords will auto-populate here (e.g. Python, PyTorch, Docker...)">
          </div>
        </div>

        <div style="margin-top: 16px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
          <div id="add-role-status"></div>
          <div style="display: flex; gap: 10px; margin-left: auto;">
            <button type="button" class="btn-cancel-role" onclick="toggleAddRoleBox()">Cancel</button>
            <button type="submit" id="btn-submit-role" class="btn-save-role">💾 Save & Add to Tracker</button>
          </div>
        </div>
      </form>
    </div>

    <div class="controls-bar">
      <input type="text" id="search-box" class="search-input" placeholder="🔍 Search company, Python, AI/ML, location, skills..." oninput="filterTable()">
      
      <select id="region-filter" class="filter-select" onchange="filterTable()">
        <option value="all">🌍 All Regions</option>
        <option value="Netherlands">🇳🇱 Netherlands</option>
        <option value="United Kingdom">🇬🇧 United Kingdom</option>
        <option value="Australia">🇦🇺 Australia</option>
        <option value="Europe (Other)">🇪🇺 Other EU</option>
        <option value="Remote">🌐 Remote</option>
      </select>

      <select id="status-filter" class="filter-select" onchange="filterTable()">
        <option value="active">Active Roles (Hide Uninterested & Rejected)</option>
        <option value="all">All Roles (Include Uninterested & Rejected)</option>
        <option value="unapplied">Unapplied (⬜)</option>
        <option value="applied">Applied (✅)</option>
        <option value="interviewing">Interviewing (💬)</option>
        <option value="offered">Offer (🎉)</option>
        <option value="rejected">❌ Rejected (Hidden from Active)</option>
        <option value="uninterested">🚫 Uninterested (Hidden from Active)</option>
      </select>

      <select id="tier-filter" class="filter-select" onchange="filterTable()">
        <option value="all">All Scores</option>
        <option value="priority">Priority Matches (75%+)</option>
        <option value="strong">Strong Matches (60% - 74%)</option>
        <option value="explore">Explore More (40% - 59%)</option>
      </select>

      <select id="ats-filter" class="filter-select" onchange="filterTable()">
        <option value="all">🏢 All ATS Platforms</option>
        <option value="greenhouse">🌱 Greenhouse</option>
        <option value="lever">⚡ Lever</option>
        <option value="ashby">🟣 Ashby</option>
        <option value="workday">💼 Workday</option>
        <option value="smartrecruiters">🎯 SmartRecruiters</option>
        <option value="workable">📋 Workable</option>
        <option value="recruitee">👥 Recruitee</option>
        <option value="personio">🧑‍💼 Personio</option>
        <option value="bamboohr">🎋 BambooHR</option>
        <option value="arbeitnow">📰 Arbeitnow</option>
        <option value="linkedin">👔 LinkedIn</option>
        <option value="direct">🌐 Direct Portal</option>
      </select>

      <button id="btn-new-filter" class="btn-toggle-new" onclick="toggleNewFilter()">
        🆕 Show Only New Roles
      </button>
    </div>

    <div class="jobs-table-container">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Status</th>
            <th>Match Score</th>
            <th>Company</th>
            <th>ATS Platform</th>
            <th>Job Title & Location</th>
            <th>Key Match Tags</th>
            <th>Recommended Letter Body</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="jobs-tbody">
          <tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 40px;">Loading matching positions...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <script>
    let allJobs = [];
    let onlyNew = false;

    async function fetchJobs() {
      const tbody = document.getElementById('jobs-tbody');
      try {
        const resp = await fetch('/api/jobs');
        if (!resp.ok) {
          throw new Error('HTTP ' + resp.status + ': ' + resp.statusText);
        }
        allJobs = await resp.json();
        updateStats();
        filterTable();
      } catch (e) {
        console.error("Error fetching jobs:", e);
        if (tbody) {
          tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: #f87171; padding: 40px;">' +
            '⚠️ Failed to load jobs: ' + escapeHtml(e.message) + '<br>' +
            '<button onclick="fetchJobs()" style="margin-top: 12px; padding: 6px 14px; background: rgba(56,189,248,0.2); border: 1px solid #38bdf8; color: #38bdf8; border-radius: 6px; cursor: pointer;">🔄 Retry</button>' +
            '</td></tr>';
        }
      }
    }

    function updateStats() {
      const total = allJobs.length;
      const newJobs = allJobs.filter(j => j.is_new === 1 && j.status !== 'uninterested' && j.status !== 'unintrested' && j.status !== 'rejected').length;
      const applied = allJobs.filter(j => (j.applied === 1 || (j.status && j.status !== 'unapplied')) && j.status !== 'uninterested' && j.status !== 'unintrested' && j.status !== 'rejected').length;
      const priority = allJobs.filter(j => j.score >= 75 && j.status !== 'uninterested' && j.status !== 'unintrested' && j.status !== 'rejected').length;
      const uninterested = allJobs.filter(j => j.status === 'uninterested' || j.status === 'unintrested').length;
      const rejected = allJobs.filter(j => j.status === 'rejected').length;
      const pending = total - applied - uninterested - rejected;

      document.getElementById('stat-total').textContent = total;
      document.getElementById('stat-new').textContent = newJobs;
      document.getElementById('stat-applied').textContent = applied;
      document.getElementById('stat-priority').textContent = priority;
      document.getElementById('stat-pending').textContent = Math.max(0, pending);
      document.getElementById('stat-rejected').textContent = rejected;
      document.getElementById('stat-uninterested').textContent = uninterested;
    }

    function toggleNewFilter() {
      onlyNew = !onlyNew;
      const btn = document.getElementById('btn-new-filter');
      const card = document.getElementById('card-new');
      if (onlyNew) {
        btn.classList.add('active');
        btn.textContent = '✓ Showing Only New Roles';
        card.classList.add('active-card');
      } else {
        btn.classList.remove('active');
        btn.textContent = '🆕 Show Only New Roles';
        card.classList.remove('active-card');
      }
      filterTable();
    }

    function filterByStat(type) {
      if (type === 'new') {
        toggleNewFilter();
        return;
      }
      // Reset onlyNew if clicked other stat cards
      if (onlyNew) {
        onlyNew = false;
        document.getElementById('btn-new-filter').classList.remove('active');
        document.getElementById('btn-new-filter').textContent = '🆕 Show Only New Roles';
        document.getElementById('card-new').classList.remove('active-card');
      }

      if (type === 'all') {
        document.getElementById('status-filter').value = 'all';
        document.getElementById('tier-filter').value = 'all';
      } else if (type === 'applied') {
        document.getElementById('status-filter').value = 'applied';
      } else if (type === 'priority') {
        document.getElementById('tier-filter').value = 'priority';
      } else if (type === 'pending') {
        document.getElementById('status-filter').value = 'unapplied';
      } else if (type === 'rejected') {
        document.getElementById('status-filter').value = 'rejected';
      } else if (type === 'uninterested') {
        document.getElementById('status-filter').value = 'uninterested';
      }
      filterTable();
    }

    function getRegionClass(region) {
      if (region === 'Netherlands') return 'region-nl';
      if (region === 'United Kingdom') return 'region-uk';
      if (region === 'Australia') return 'region-au';
      if (region === 'Remote') return 'region-remote';
      return 'region-eu';
    }

    function getRegionFlag(region) {
      if (region === 'Netherlands') return '🇳🇱 NL';
      if (region === 'United Kingdom') return '🇬🇧 UK';
      if (region === 'Australia') return '🇦🇺 AU';
      if (region === 'Remote') return '🌐 Remote';
      return '🇪🇺 EU';
    }

    function getAtsInfo(job) {
      const src = (job.source || '').trim();
      const srcLower = src.toLowerCase();
      const url = (job.url || '').toLowerCase();
      const atsType = (job.ats_platform || '').toLowerCase();
      
      let id = 'direct';
      let name = 'Direct Portal';
      let icon = '🌐';
      let badgeClass = 'ats-direct';
      let slug = '';

      // Match slug in parentheses e.g. "Greenhouse (imc)" -> "imc"
      const matchParen = src.match(/\(([^)]+)\)/);
      if (matchParen) {
        slug = matchParen[1];
        if (slug.toLowerCase().startsWith('verified sponsor:')) {
          slug = 'IND Verified Feed';
        }
      }

      if (srcLower.includes('greenhouse') || url.includes('greenhouse.io') || atsType === 'greenhouse') {
        id = 'greenhouse'; name = 'Greenhouse'; icon = '🌱'; badgeClass = 'ats-greenhouse';
      } else if (srcLower.includes('lever') || url.includes('lever.co') || atsType === 'lever') {
        id = 'lever'; name = 'Lever'; icon = '⚡'; badgeClass = 'ats-lever';
      } else if (srcLower.includes('ashby') || url.includes('ashbyhq.com') || atsType === 'ashby') {
        id = 'ashby'; name = 'Ashby'; icon = '🟣'; badgeClass = 'ats-ashby';
      } else if (srcLower.includes('workday') || url.includes('myworkdayjobs.com') || atsType === 'workday') {
        id = 'workday'; name = 'Workday'; icon = '💼'; badgeClass = 'ats-workday';
      } else if (srcLower.includes('smartrecruiters') || url.includes('smartrecruiters.com') || atsType === 'smartrecruiters') {
        id = 'smartrecruiters'; name = 'SmartRecruiters'; icon = '🎯'; badgeClass = 'ats-smartrecruiters';
      } else if (srcLower.includes('workable') || url.includes('workable.com') || atsType === 'workable') {
        id = 'workable'; name = 'Workable'; icon = '📋'; badgeClass = 'ats-workable';
      } else if (srcLower.includes('recruitee') || url.includes('recruitee.com') || atsType === 'recruitee') {
        id = 'recruitee'; name = 'Recruitee'; icon = '👥'; badgeClass = 'ats-recruitee';
      } else if (srcLower.includes('personio') || url.includes('personio.de') || url.includes('personio.com') || atsType === 'personio') {
        id = 'personio'; name = 'Personio'; icon = '🧑‍💼'; badgeClass = 'ats-personio';
      } else if (srcLower.includes('bamboohr') || url.includes('bamboohr.com') || atsType === 'bamboohr') {
        id = 'bamboohr'; name = 'BambooHR'; icon = '🎋'; badgeClass = 'ats-bamboohr';
      } else if (srcLower.includes('arbeitnow') || url.includes('arbeitnow.com') || url.includes('arbeitnow.co.uk') || atsType === 'arbeitnow') {
        id = 'arbeitnow'; name = 'Arbeitnow'; icon = '📰'; badgeClass = 'ats-arbeitnow';
      } else if (srcLower.includes('linkedin') || url.includes('linkedin.com') || atsType === 'linkedin') {
        id = 'linkedin'; name = 'LinkedIn'; icon = '👔'; badgeClass = 'ats-linkedin';
      } else if (srcLower.includes('indeed') || url.includes('indeed.com') || atsType === 'indeed') {
        id = 'indeed'; name = 'Indeed'; icon = '🔍'; badgeClass = 'ats-indeed';
      }

      return { id, name, icon, badgeClass, slug, sourceText: src };
    }

    function filterTable() {
      const query = document.getElementById('search-box').value.toLowerCase();
      const regionFilter = document.getElementById('region-filter').value;
      const statusFilter = document.getElementById('status-filter').value;
      const tierFilter = document.getElementById('tier-filter').value;
      const atsFilter = document.getElementById('ats-filter') ? document.getElementById('ats-filter').value : 'all';

      const filtered = allJobs.filter(j => {
        if (onlyNew && j.is_new !== 1) return false;

        const ats = getAtsInfo(j);
        if (atsFilter !== 'all' && ats.id !== atsFilter) return false;

        const text = `${j.company} ${j.title} ${j.location} ${j.region} ${j.recommended_letter} ${(j.reasons || []).join(' ')} ${j.source || ''} ${ats.name} ${ats.slug}`.toLowerCase();
        if (query && !text.includes(query)) return false;

        if (regionFilter !== 'all' && j.region !== regionFilter) return false;

        const isUninterested = j.status === 'uninterested' || j.status === 'unintrested';
        const isRejected = j.status === 'rejected';
        const isApplied = (j.applied === 1 || (j.status && j.status !== 'unapplied')) && !isUninterested && !isRejected;

        if (statusFilter === 'active' && (isUninterested || isRejected)) return false;
        if (statusFilter === 'uninterested' && !isUninterested) return false;
        if (statusFilter === 'rejected' && !isRejected) return false;
        if (statusFilter === 'applied' && !isApplied) return false;
        if (statusFilter === 'unapplied' && (isApplied || isUninterested || isRejected)) return false;
        if (statusFilter === 'interviewing' && j.status !== 'interviewing') return false;
        if (statusFilter === 'offered' && j.status !== 'offered') return false;

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
        tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 40px;">No matching positions found.</td></tr>';
        return;
      }

      tbody.innerHTML = jobs.map(j => {
        const scoreClass = j.score >= 75 ? 'score-high' : (j.score >= 60 ? 'score-mid' : 'score-low');
        const isUninterested = j.status === 'uninterested' || j.status === 'unintrested';
        const isRejected = j.status === 'rejected';
        const isApplied = (j.applied === 1 || (j.status && j.status !== 'unapplied')) && !isUninterested && !isRejected;
        const regionClass = getRegionClass(j.region);
        const regionFlag = getRegionFlag(j.region);
        const isNewPill = j.is_new === 1 ? '<span class="badge-new">🆕 NEW</span>' : '';
        const ats = getAtsInfo(j);

        // Render skill and reason pills
        const tags = (j.reasons || []).slice(0, 3).map(r => {
          const isPython = r.toLowerCase().includes('python');
          return `<span class="skill-pill ${isPython ? 'pill-python' : ''}">${escapeHtml(r)}</span>`;
        }).join('');

        return `
          <tr style="${isUninterested || isRejected ? 'opacity: 0.6;' : ''}">
            <td style="font-family: var(--font-mono); color: var(--text-muted); font-size: 12px;">#${j.id}</td>
            <td>
              <select class="status-select" onchange="updateStatus(${j.id}, this.value)" style="${isUninterested ? 'border-color: rgba(255,255,255,0.2); color: #94a3b8;' : (isRejected ? 'border-color: rgba(239, 68, 68, 0.4); color: #f87171;' : '')}">
                <option value="unapplied" ${j.status === 'unapplied' ? 'selected' : ''}>⬜ Unapplied</option>
                <option value="applied" ${isApplied && j.status === 'applied' ? 'selected' : ''}>✅ Applied</option>
                <option value="interviewing" ${j.status === 'interviewing' ? 'selected' : ''}>💬 Interviewing</option>
                <option value="offered" ${j.status === 'offered' ? 'selected' : ''}>🎉 Offer</option>
                <option value="rejected" ${isRejected ? 'selected' : ''}>❌ Rejected</option>
                <option value="uninterested" ${isUninterested ? 'selected' : ''}>🚫 Uninterested</option>
              </select>
            </td>
            <td><span class="score-badge ${scoreClass}">${j.score.toFixed(1)}%</span></td>
            <td>
              <div class="company-name">${escapeHtml(j.company)}</div>
              <div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(j.kvk || 'Target Sponsor')}</div>
            </td>
            <td>
              <span class="ats-badge ${ats.badgeClass}" title="${escapeHtml(j.source || ats.name)}">
                <span>${ats.icon}</span> ${escapeHtml(ats.name)}
              </span>
              ${ats.slug ? `<div style="font-size: 10px; color: var(--text-muted); margin-top: 3px; font-family: var(--font-mono);">${escapeHtml(ats.slug)}</div>` : ''}
            </td>
            <td>
              <div>
                <a href="${escapeHtml(j.url)}" target="_blank" class="job-link">${escapeHtml(j.title)}</a>
                ${isNewPill}
              </div>
              <div style="font-size: 12px; color: var(--text-muted); margin-top: 3px; display: flex; align-items: center;">
                <span class="region-badge ${regionClass}">${regionFlag}</span>
                <span>${escapeHtml(j.location)}</span>
              </div>
            </td>
            <td>
              <div class="skills-tag-list">${tags}</div>
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

    // ==========================================
    // LIVE KEYWORD EXTRACTOR & JD INTELLIGENCE
    // ==========================================
    let latestExtracted = {
      allKeywords: [],
      categorized: {},
      detected: {},
      topNotes: '',
      score: 0,
      letter: '1. GENERIC / OPEN APPLICATION'
    };

    let jdDebounceTimer = null;

    const CATEGORY_ICONS = {
      'Languages': { icon: '🐍', cls: 'pill-lang' },
      'AI & Machine Learning': { icon: '🤖', cls: 'pill-aiml' },
      'GenAI, LLMs & RAG': { icon: '🧠', cls: 'pill-rag' },
      'Data Engineering': { icon: '📊', cls: 'pill-data' },
      'Cloud, MLOps & Infra': { icon: '☁️', cls: 'pill-cloud' },
      'Perception & Robotics': { icon: '👁️', cls: 'pill-cv' },
      'Software & Architecture': { icon: '🛠️', cls: 'pill-swe' },
      'Qualifications & Seniority': { icon: '🎓', cls: 'pill-qual' }
    };

    function handleJDPasteOrInput() {
      const text = document.getElementById('input-jd').value;
      const emptyTip = document.getElementById('jd-empty-tip');
      const extractedContent = document.getElementById('jd-extracted-content');

      if (!text || !text.trim()) {
        emptyTip.style.display = 'flex';
        extractedContent.style.display = 'none';
        latestExtracted = { allKeywords: [], categorized: {}, detected: {}, topNotes: '', score: 0, letter: '1. GENERIC / OPEN APPLICATION' };
        return;
      }

      emptyTip.style.display = 'none';
      extractedContent.style.display = 'block';

      clearTimeout(jdDebounceTimer);
      jdDebounceTimer = setTimeout(() => {
        extractKeywordsLive(text);
      }, 100);
    }

    async function extractKeywordsLive(text) {
      try {
        const title = document.getElementById('input-title').value.trim();
        const location = document.getElementById('input-location').value.trim();
        const resp = await fetch('/api/extract-keywords', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, title, location })
        });
        const data = await resp.json();
        if (data.success && data.data) {
          const s = data.data;
          latestExtracted = {
            allKeywords: s.all_keywords || [],
            categorized: s.categorized || {},
            detected: s.detected_metadata || {},
            topNotes: s.top_notes || '',
            score: s.match_score || 0,
            letter: s.recommended_letter || '1. GENERIC / OPEN APPLICATION'
          };
          renderExtractedIntelligence(latestExtracted);
        }
      } catch (err) {
        console.error("Error extracting keywords:", err);
      }
    }

    function renderExtractedIntelligence(info) {
      document.getElementById('jd-badge-count').textContent = `✨ ${info.allKeywords.length} Keywords Found`;

      const scoreBadge = document.getElementById('jd-badge-score');
      scoreBadge.textContent = `${info.score.toFixed(1)}% Match`;
      scoreBadge.className = 'score-badge ' + (info.score >= 75 ? 'score-high' : (info.score >= 60 ? 'score-mid' : 'score-low'));

      const letterBadge = document.getElementById('jd-badge-letter');
      letterBadge.textContent = `Letter: ${info.letter}`;
      letterBadge.title = `Recommended Cover Letter Body: ${info.letter}`;

      const warnBox = document.getElementById('jd-senior-warning');
      const warningText = info.detected && (info.detected.seniority_warning || info.detected.seniorityWarning);
      if (warningText) {
        warnBox.textContent = '⚠️ ' + warningText;
        warnBox.style.display = 'flex';
      } else {
        warnBox.style.display = 'none';
      }

      const catContainer = document.getElementById('jd-categories-container');
      catContainer.innerHTML = '';

      for (const [catName, kws] of Object.entries(info.categorized)) {
        if (!kws || kws.length === 0) continue;
        const meta = CATEGORY_ICONS[catName] || { icon: '🏷️', cls: 'pill-lang' };

        const row = document.createElement('div');
        row.className = 'jd-cat-row';

        const nameCol = document.createElement('div');
        nameCol.className = 'jd-cat-name';
        nameCol.innerHTML = `<span>${meta.icon}</span> <span>${escapeHtml(catName)}</span>`;

        const pillsWrap = document.createElement('div');
        pillsWrap.className = 'jd-pills-wrap';

        for (const kw of kws) {
          const pill = document.createElement('button');
          pill.type = 'button';
          pill.className = `jd-pill ${meta.cls}`;
          pill.textContent = kw;
          pill.title = `Click to copy '${kw}'`;
          pill.onclick = () => copySingleKeyword(kw, pill);
          pillsWrap.appendChild(pill);
        }

        row.appendChild(nameCol);
        row.appendChild(pillsWrap);
        catContainer.appendChild(row);
      }
    }

    async function copyExtractedKeywords() {
      if (!latestExtracted.allKeywords || latestExtracted.allKeywords.length === 0) {
        alert("No keywords extracted yet. Paste a job description first!");
        return;
      }
      const kwText = latestExtracted.allKeywords.join(', ');
      try {
        await navigator.clipboard.writeText(kwText);
        const btn = document.getElementById('btn-copy-keywords');
        const origText = btn.innerHTML;
        btn.innerHTML = `✅ Copied ${latestExtracted.allKeywords.length} Keywords!`;
        btn.style.background = 'linear-gradient(135deg, #059669, #10b981)';
        setTimeout(() => {
          btn.innerHTML = origText;
          btn.style.background = '';
        }, 2200);
      } catch (err) {
        prompt("Copy extracted keywords below:", kwText);
      }
    }

    async function copySingleKeyword(kw, elem) {
      try {
        await navigator.clipboard.writeText(kw);
        elem.classList.add('pill-copied');
        const orig = elem.textContent;
        elem.textContent = `✓ ${kw}`;
        setTimeout(() => {
          elem.classList.remove('pill-copied');
          elem.textContent = orig;
        }, 1200);
      } catch (e) {
        console.warn("Could not copy single keyword:", e);
      }
    }

    function autoFillFormFromExtracted() {
      const d = latestExtracted.detected || {};
      if (d.company) document.getElementById('input-company').value = d.company;
      if (d.title) document.getElementById('input-title').value = d.title;
      if (d.location) document.getElementById('input-location').value = d.location;
      if (latestExtracted.topNotes) document.getElementById('input-notes').value = latestExtracted.topNotes;

      const statusBox = document.getElementById('add-role-status');
      statusBox.innerHTML = `
        <div style="padding: 6px 12px; border-radius: 6px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.35); color: #38bdf8; font-size: 12px;">
          ⚡ Auto-filled fields with extracted Title, Company, Location, and Top Keywords!
        </div>
      `;
      setTimeout(() => { statusBox.innerHTML = ''; }, 4000);
    }

    async function pasteClipboardToJD() {
      try {
        const text = await navigator.clipboard.readText();
        if (text) {
          document.getElementById('input-jd').value = text;
          handleJDPasteOrInput();
        } else {
          alert("Clipboard is empty.");
        }
      } catch (e) {
        alert("Please press Ctrl+V or Cmd+V directly in the box to paste.");
      }
    }

    function clearJDTextarea() {
      document.getElementById('input-jd').value = '';
      handleJDPasteOrInput();
    }

    function toggleAddRoleBox() {
      const panel = document.getElementById('add-role-panel');
      const btn = document.getElementById('btn-toggle-add');
      const isHidden = panel.style.display === 'none';
      if (isHidden) {
        panel.style.display = 'block';
        btn.textContent = '✕ Close JD & Add Box';
        btn.style.background = 'rgba(239, 68, 68, 0.2)';
        btn.style.border = '1px solid rgba(239, 68, 68, 0.4)';
        btn.style.color = '#f87171';
        btn.style.boxShadow = 'none';
        document.getElementById('input-jd').focus();
      } else {
        panel.style.display = 'none';
        btn.textContent = '📋 Paste JD & Add Role';
        btn.style.background = 'linear-gradient(135deg, #059669, #10b981)';
        btn.style.border = 'none';
        btn.style.color = '#ffffff';
        btn.style.boxShadow = '0 2px 10px rgba(16, 185, 129, 0.3)';
        document.getElementById('add-role-status').innerHTML = '';
      }
    }

    async function submitCustomJob(e) {
      e.preventDefault();
      const btn = document.getElementById('btn-submit-role');
      const statusBox = document.getElementById('add-role-status');
      
      const company = document.getElementById('input-company').value.trim();
      const title = document.getElementById('input-title').value.trim();
      const url = document.getElementById('input-url').value.trim();
      const location = document.getElementById('input-location').value.trim() || 'Amsterdam, Netherlands';
      const status = document.getElementById('input-status').value;
      const notes = document.getElementById('input-notes').value.trim();
      const description = document.getElementById('input-jd').value.trim();

      if (!company || !title) {
        statusBox.innerHTML = '<span style="color: var(--danger)">Company Name and Job Title are required.</span>';
        return;
      }

      btn.disabled = true;
      btn.textContent = '⏳ Scoring & Saving...';
      statusBox.innerHTML = '';

      try {
        const resp = await fetch('/api/jobs/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            company,
            title,
            url,
            location,
            status,
            notes,
            description,
            source: url.toLowerCase().includes('linkedin') ? 'LinkedIn' : 'Manual Entry'
          })
        });

        const data = await resp.json();
        if (data.success && data.job) {
          const j = data.job;
          const sponsorTag = j.is_sponsor ? '🏢 IND Recognised Sponsor' : '🌐 External Employer';
          statusBox.innerHTML = `
            <div style="padding: 8px 12px; border-radius: 8px; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); color: #34d399; font-size: 12px;">
              ✅ Added <strong>#${j.id}: ${escapeHtml(j.company)} — ${escapeHtml(j.title)}</strong>! 
              Match Score: <strong>${j.score.toFixed(1)}%</strong> | ${sponsorTag} | Letter: <code>${escapeHtml(j.recommended_letter)}</code>
            </div>
          `;
          
          // Clear form inputs
          document.getElementById('input-company').value = '';
          document.getElementById('input-title').value = '';
          document.getElementById('input-url').value = '';
          document.getElementById('input-notes').value = '';
          clearJDTextarea();
          
          // Refresh list immediately
          await fetchJobs();
        } else {
          statusBox.innerHTML = `<span style="color: var(--danger)">❌ ${escapeHtml(data.error || 'Failed to save')}</span>`;
        }
      } catch (err) {
        console.error("Error adding role:", err);
        statusBox.innerHTML = `<span style="color: var(--danger)">❌ Network error: ${escapeHtml(err.message)}</span>`;
      } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save & Add to Tracker';
      }
    }

    async function updateStatus(jobId, newStatus) {
      try {
        const job = allJobs.find(j => j.id === jobId);
        if (job) {
          job.status = newStatus;
          if (newStatus === 'applied') job.applied = 1;
          else if (newStatus === 'unapplied') job.applied = 0;
          updateStats();
          filterTable();
        }
        await fetch(`/api/status/${jobId}?status=${newStatus}`, { method: 'POST' });
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

    def _send_response_data(self, content_type: str, data_bytes: bytes, status: int = 200, extra_headers: Optional[Dict[str, str]] = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data_bytes)))
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data_bytes)

    def _send_json(self, data: Any, status: int = 200):
        raw = json.dumps(data).encode("utf-8")
        self._send_response_data("application/json; charset=utf-8", raw, status=status)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

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
                    self.send_header("Content-Length", "0")
                    self.send_header("Connection", "close")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    return
                else:
                    self._send_json({"error": f"Job #{job_id} not found in database"}, status=404)
                    return
            else:
                self._send_json({"error": "Invalid Job ID"}, status=400)
                return

        # 2. Revert Application: GET /unapply/<id>
        elif path.startswith("/unapply/"):
            parts = path.split("/")
            if len(parts) >= 3 and parts[2].isdigit():
                job_id = int(parts[2])
                unapply_job(job_id)
                self._send_json({"success": True, "id": job_id, "status": "unapplied"})
                return

        # 3. REST API: GET /api/jobs
        elif path == "/api/jobs":
            if os.path.exists(OUTPUT_JSON_PATH):
                with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
                    data = f.read()
                self._send_response_data("application/json; charset=utf-8", data.encode("utf-8"))
                return
            else:
                self._send_json([])
                return

        # 4. Web Dashboard: GET / or /dashboard
        elif path == "" or path == "/dashboard":
            self._send_response_data("text/html; charset=utf-8", HTML_DASHBOARD.encode("utf-8"))
            return

        # 5. Favicon
        elif path == "/favicon.ico":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            return

        else:
            self._send_json({"error": "Endpoint not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        # 1. Manual / External Role Submission: POST /api/jobs/add
        if path == "/api/jobs/add" or path == "/api/jobs":
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
                source = payload.get("source", "LinkedIn / Manual")

                if not company or not title:
                    self._send_json({"success": False, "error": "Company and Title are required."}, status=400)
                    return

                res = add_custom_job(
                    company_name=company,
                    title=title,
                    url=url,
                    location=location,
                    description=description,
                    status=status,
                    notes=notes,
                    source=source
                )

                self._send_json({"success": True, "job": res})
                return
            except Exception as e:
                logging.exception(f"Error adding custom job: {e}")
                self._send_json({"success": False, "error": str(e)}, status=500)
                return

        # 2. Extract Keywords from JD: POST /api/extract-keywords
        elif path == "/api/extract-keywords":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode("utf-8"))
                except Exception:
                    raw_data = parse_qs(post_data.decode("utf-8"))
                    payload = {k: v[0] for k, v in raw_data.items()}

                text = payload.get("text", "")
                title = payload.get("title", "")
                location = payload.get("location", "")

                res = extract_job_keywords(text=text, title=title, location=location)
                self._send_json({"success": True, "data": res})
                return
            except Exception as e:
                logging.exception(f"Error extracting keywords: {e}")
                self._send_json({"success": False, "error": str(e)}, status=500)
                return

        # 3. Status Update: POST /api/status/<id>?status=applied
        elif path.startswith("/api/status/"):
            parts = path.split("/")
            if len(parts) >= 4 and parts[3].isdigit():
                job_id = int(parts[3])
                status = query.get("status", ["applied"])[0]
                notes = query.get("notes", [None])[0]
                res = mark_job_status(job_id, status=status, notes=notes)
                if res:
                    self._send_json({"success": True, "job": res})
                    return
                else:
                    self._send_json({"success": False, "error": "Job not found"}, status=404)
                    return

        self._send_json({"error": "Endpoint not found"}, status=404)


class ReusableThreadingServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTPServer with address reuse enabled to handle concurrent requests seamlessly."""
    daemon_threads = True
    allow_reuse_address = True


def open_in_browser(url: str):
    """Open URL in default browser, cleanly supporting WSL2 Windows host as well as native Linux/macOS."""
    import subprocess
    import shutil
    
    # 1. WSL2 check: if running under WSL, open via Windows host
    try:
        if os.path.exists("/proc/version"):
            with open("/proc/version", "r") as f:
                version_info = f.read().lower()
            if "microsoft" in version_info or "wsl" in version_info:
                for opener in ["explorer.exe", "cmd.exe", "wslview"]:
                    if shutil.which(opener):
                        if opener == "cmd.exe":
                            subprocess.Popen(["cmd.exe", "/c", "start", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        else:
                            subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        return
    except Exception:
        pass

    # 2. Standard browser fallback
    try:
        webbrowser.open(url)
    except Exception:
        pass


def start_tracker_server(port: int = 8765, open_browser: bool = False):
    """Start local click-tracking and application server on 127.0.0.1."""
    server_address = ("127.0.0.1", port)
    httpd = ReusableThreadingServer(server_address, JobTrackerHandler)
    logging.info("=" * 65)
    logging.info(f"🚀 GLOBAL SPONSOR CLICK-TRACKER & WEB DASHBOARD RUNNING")
    logging.info(f"🌐 Dashboard URL: http://localhost:{port}")
    logging.info(f"⚡ Click-to-Apply Tracker Active on port {port}")
    logging.info("=" * 65)
    
    if open_browser:
        open_in_browser(f"http://localhost:{port}")
        
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("\nStopping Tracker Server...")
        httpd.server_close()


if __name__ == "__main__":
    start_tracker_server(8765, open_browser=True)
