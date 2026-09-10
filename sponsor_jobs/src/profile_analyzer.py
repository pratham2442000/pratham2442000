#!/usr/bin/env python3
"""
profile_analyzer.py - Analyzes scraped jobs and scores match quality against
Pratham Johari's profile (aboutme.md, cv.tex), generating tailored rationale and
cover letter recommendations with strict EU/Netherlands location filtering.
"""

import os
import re
import json
import sqlite3
import logging
from typing import Dict, Any, List, Tuple, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sponsors.db"))
OUTPUT_MD_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "recommended_jobs.md"))
OUTPUT_JSON_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "recommended_jobs.json"))

# Explicit NON-EU locations that MUST be filtered out
NON_EU_PATTERNS = [
    r"\b(united\s+states|usa|u\.s\.|us)\b", r"\bindia\b", r"\bjapan\b", r"\bkorea\b",
    r"\bcanada\b", r"\baustralia\b", r"\bmexico\b", r"\bbrazil\b", r"\bsingapore\b",
    r"\bchina\b", r"\bcalifornia\b", r"\bwashington\b", r"\bnew\s+york\b", r"\btexas\b",
    r"\bvirginia\b", r"\bmaryland\b", r"\bcolorado\b", r"\boregon\b", r"\bbengaluru\b",
    r"\bdelaware\b", r"\bpennsylvania\b", r"\bsan\s+francisco\b", r"\bmountain\s+view\b",
    r"\bbellevue\b", r"\bseattle\b", r"\baustin\b", r"\btokyo\b", r"\bseoul\b",
    r"\blondon\b", r"\bunited\s+kingdom\b", r"\buk\b", r"\bserbia\b", r"\bbelgrade\b"
]

# Accepted EU / Netherlands / Remote keywords
EU_KEYWORDS = [
    r"\bnetherlands\b", r"\bamsterdam\b", r"\bdelft\b", r"\beindhoven\b",
    r"\brotterdam\b", r"\butrecht\b", r"\bthe\s+hague\b", r"\bden\s+haag\b",
    r"\bleiden\b", r"\bgroningen\b", r"\benschede\b", r"\bbrabant\b",
    r"\beurope\b", r"\beu\b", r"\bemea\b", r"\bgermany\b", r"\bberlin\b", r"\bmunich\b",
    r"\bfrance\b", r"\bparis\b", r"\bspain\b", r"\bmadrid\b", r"\bbarcelona\b",
    r"\bireland\b", r"\bdublin\b", r"\bsweden\b", r"\bstockholm\b", r"\bdenmark\b",
    r"\bcopenhagen\b", r"\bbelgium\b", r"\bbrussels\b", r"\bitaly\b", r"\bmilan\b",
    r"\baustria\b", r"\bvienna\b", r"\bswitzerland\b", r"\bzurich\b",
    r"\bpoland\b", r"\bwarsaw\b", r"\bportugal\b", r"\blisbon\b", r"\bfinland\b",
    r"\bnorway\b", r"\bremote\b"
]

ROLE_WEIGHTS = {
    r"\b(machine learning|ml)\s+engineer\b": 45,
    r"\bai\s+engineer\b": 45,
    r"\bai\s+platform\s+engineer\b": 45,
    r"\bperception\s+engineer\b": 45,
    r"\bcomputer\s+vision\b": 42,
    r"\bautonomous\s+(driving|systems|vehicle|navigation)\b": 45,
    r"\bmlops\b": 42,
    r"\bdeep\s+learning\b": 40,
    r"\brobotics\s+(software|engineer)\b": 42,
    r"\bdata\s+scientist\b": 35,
    r"\bapplied\s+(ai|ml)\b": 42,
    r"\bresearch\s+engineer\b": 40,
    r"\balgorithm\s+engineer\b": 40,
    r"\bsoftware\s+engineer\b": 30,
    r"\bbackend\s+engineer\b": 30,
    r"\bpython\s+developer\b": 30
}

PENALTY_PATTERNS = {
    r"\b(senior\s+director|director|vp|head\s+of|vice\s+president)\b": -35,
    r"\b(staff|principal)\b": -10,
    r"\b(frontend|front-end|react\s+native|ios|android|swift|flutter)\b": -25,
    r"\b(sales|marketing|recruiter|hr|talent|accountant|legal|counsel)\b": -50,
    r"\b(intern|internship|trainee|working\s+student|junior|graduate)\b": 15
}

SKILL_PATTERNS = {
    "RAG / GenAI / LLM": (r"\b(rag|retrieval|llm|generative\s+ai|langchain|transformers|colbert|colpali|context\s+retrieval)\b", 15),
    "PyTorch / Deep Learning": (r"\b(pytorch|tensorflow|deep\s+learning|model\s+training|deep\s+neural)\b", 12),
    "Perception / LIDAR / ROS": (r"\b(ros|ros2|lidar|point\s+cloud|yolo|sensor\s+fusion|opencv|perception)\b", 16),
    "C++ / High Performance": (r"\b(c\+\+|embedded|low\s+latency|concurrency)\b", 12),
    "MLOps / Kubernetes": (r"\b(docker|kubernetes|k8s|ci/cd|onnx|vllm|prometheus|helm|observability)\b", 12),
    "Python / Systems": (r"\b(python|distributed\s+systems|runtime)\b", 10)
}


def is_eu_location(location: str) -> bool:
    """Check whether a location is strictly within the European Union / Netherlands / Remote EU."""
    if not location or location.strip() == "":
        return True
        
    loc = location.lower().strip()
    if any(re.search(pat, loc) for pat in NON_EU_PATTERNS):
        return False
        
    return any(re.search(pat, loc) for pat in EU_KEYWORDS)


def score_job(title: str, location: str, description: str = "") -> Tuple[float, List[str], str]:
    """Calculate match score (0-100), reasoning tags, and recommended letter body."""
    text = f"{title} {description}".lower()
    loc_lower = location.lower()
    score = 15.0
    reasons = []

    is_nl = any(re.search(pat, loc_lower) for pat in [r"\bnetherlands\b", r"\bamsterdam\b", r"\bdelft\b", r"\beindhoven\b", r"\brotterdam\b", r"\butrecht\b", r"\bthe\s+hague\b"])
    if is_nl:
        score += 25
        reasons.append("Netherlands Priority (+25 pts)")
    elif "remote" in loc_lower or "europe" in loc_lower:
        score += 15
        reasons.append("EU / Remote (+15 pts)")

    matched_role = False
    for pat, weight in ROLE_WEIGHTS.items():
        if re.search(pat, text):
            score += weight
            matched_role = True
            reasons.append(f"Target role match ({weight} pts)")
            break
            
    if not matched_role:
        if "engineer" in text or "developer" in text:
            score += 15
            reasons.append("Engineering role (+15 pts)")

    for pat, penalty in PENALTY_PATTERNS.items():
        if re.search(pat, text):
            score += penalty
            if penalty > 0:
                reasons.append(f"Graduate/Entry friendly (+{penalty} pts)")
            else:
                reasons.append(f"Seniority mismatch ({penalty} pts)")

    skills_found = []
    for skill_name, (pat, weight) in SKILL_PATTERNS.items():
        if re.search(pat, text):
            score += weight
            skills_found.append(skill_name)
            
    if skills_found:
        reasons.append(f"Skills: {', '.join(skills_found)}")

    score = max(5.0, min(99.0, score))

    recommended_letter = "1. GENERIC / OPEN APPLICATION"
    if re.search(r"\b(f1|formula\s+1|motorsport|racing|race\s+car)\b", text):
        recommended_letter = "10. FORMULA 1 & MOTORSPORT"
    elif re.search(r"\b(embedded|semiconductor|firmware|hardware|c\+\+|mechatronics)\b", text):
        recommended_letter = "9. HIGH-TECH & EMBEDDED SYSTEMS"
    elif re.search(r"\b(perception|lidar|autonomous|computer\s+vision|robotics|sensor\s+fusion)\b", text):
        recommended_letter = "8. COMPUTER VISION & PERCEPTION"
    elif re.search(r"\b(ai\s+engineer|forward\s+deployed|applied\s+ai|compound\s+ai|genai|llm\s+engineer)\b", text):
        recommended_letter = "7. AI ENGINEER (0-to-1 Builder)"
    elif re.search(r"\b(mlops|devops|platform|kubernetes|docker|infrastructure|observability)\b", text):
        recommended_letter = "6. MLOPS & PLATFORM ENGINEER"
    elif re.search(r"\b(software\s+engineer|backend|core|systems\s+engineer)\b", text):
        recommended_letter = "5. SOFTWARE ENGINEER (Backend/Core)"
    elif re.search(r"\b(data\s+scientist|analytics|data\s+analyst)\b", text):
        recommended_letter = "4. DATA SCIENTIST"
    elif re.search(r"\b(machine\s+learning|ml\s+engineer|deep\s+learning)\b", text):
        recommended_letter = "3. MACHINE LEARNING ENGINEER"
    elif re.search(r"\b(research|phd|scientist|nlp|rag|colbert|colpali|retrieval)\b", text):
        recommended_letter = "2. AI & ML RESEARCHER"

    return round(score, 1), reasons, recommended_letter


def format_status_badge(applied: int, status: str, applied_at: Optional[str] = None) -> str:
    """Return a clean formatted badge for the application status."""
    st = (status or "unapplied").lower().strip()
    if st == "applied" or applied == 1:
        date_str = f" ({applied_at[:10]})" if applied_at else ""
        return f"✅ Applied{date_str}"
    elif st == "interviewing":
        return "💬 Interviewing"
    elif st == "offered":
        return "🎉 Offer"
    elif st == "rejected":
        return "❌ Rejected"
    return "⬜ Not Applied"


def mark_job_status(job_id: int, status: str = "applied", notes: Optional[str] = None, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Update application status of a job in SQLite and refresh markdown reports."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("SELECT id, company_name, title, url FROM jobs WHERE id = ?", (job_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
        
    is_applied = 1 if status.lower() in ("applied", "interviewing", "offered") else 0
    now_str = None
    if is_applied:
        cur.execute("SELECT datetime('now', 'localtime')")
        now_str = cur.fetchone()[0]
        
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
    
    analyze_all_jobs(db_path)
    return {"id": row[0], "company": row[1], "title": row[2], "url": row[3], "status": status}


def unapply_job(job_id: int, db_path: str = DB_PATH) -> bool:
    """Reset a job's status back to unapplied."""
    conn = sqlite3.connect(db_path)
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
    if changed:
        analyze_all_jobs(db_path)
    return changed


def analyze_all_jobs(db_path: str = DB_PATH) -> int:
    """Score all active jobs in SQLite and generate EU-filtered recommendation reports."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("""
    SELECT j.id, j.company_name, j.title, j.location, j.url, j.description, s.kvk,
           j.applied, j.applied_at, j.status, j.notes
    FROM jobs j
    LEFT JOIN sponsors s ON j.sponsor_id = s.id
    """)
    rows = cur.fetchall()
    
    analyzed_jobs = []
    
    for job_id, company, title, loc, url, desc, kvk, applied, applied_at, status, notes in rows:
        location_str = loc or "Netherlands"
        
        # If NOT EU location, deactivate and set score 0
        if not is_eu_location(location_str):
            cur.execute("UPDATE jobs SET match_score = 0, is_active = 0 WHERE id = ?", (job_id,))
            continue
            
        score, reasons, rec_letter = score_job(title, location_str, desc or "")
        reason_str = " | ".join(reasons)
        
        cur.execute("""
        UPDATE jobs
        SET match_score = ?,
            match_reason = ?,
            recommended_letter = ?,
            is_active = 1
        WHERE id = ?
        """, (score, reason_str, rec_letter, job_id))
        
        analyzed_jobs.append({
            "id": job_id,
            "company": company,
            "kvk": kvk or "Recognised Sponsor",
            "title": title,
            "location": location_str,
            "url": url,
            "score": score,
            "reasons": reasons,
            "recommended_letter": rec_letter,
            "applied": applied or 0,
            "applied_at": applied_at,
            "status": status or "unapplied",
            "notes": notes or ""
        })
        
    conn.commit()
    conn.close()
    
    analyzed_jobs.sort(key=lambda x: x["score"], reverse=True)
    generate_markdown_report(analyzed_jobs, OUTPUT_MD_PATH)
    
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(analyzed_jobs, f, indent=2)
        
    logging.info(f"Analyzed {len(analyzed_jobs)} EU jobs. Saved reports to {OUTPUT_MD_PATH} and {OUTPUT_JSON_PATH}")
    return len(analyzed_jobs)


def generate_markdown_report(jobs: List[Dict[str, Any]], output_path: str):
    """Render a clean, formatted Markdown report of EU-only recommended jobs with application tracking."""
    tier_top = [j for j in jobs if j["score"] >= 75]
    tier_mid = [j for j in jobs if 60 <= j["score"] < 75]
    tier_low = [j for j in jobs if 40 <= j["score"] < 60]
    applied_jobs = [j for j in jobs if j.get("applied") == 1 or (j.get("status") and j.get("status") != "unapplied")]
    
    lines = [
        "# 🎯 IND Recognised Sponsor Job Recommendations for Pratham Johari",
        "",
        f"**Active EU Jobs Evaluated:** {len(jobs)} positions across verified Dutch IND Recognised Sponsors.",
        f"**Applications Status:** 🎯 **{len(applied_jobs)} Applied** | ⏳ **{len(jobs) - len(applied_jobs)} Remaining** to Review",
        f"**Location Scope:** 🇪🇺 Strictly EU / Netherlands / Remote within EU/EMEA (Non-EU roles filtered out).",
        f"**Target Focus:** AI / ML Engineer, Autonomous Driving / Perception, Computer Vision, Compound AI / RAG.",
        f"**Visa Sponsorship:** Every company listed below is confirmed in the Dutch IND Public Register.",
        f"**Automatic Tracking:** Click **`[Apply ⚡]`** to automatically record application and open the listing.",
        ""
    ]
    
    # 1. Dedicated Applied Jobs Tracker section (if any applied)
    if applied_jobs:
        lines.extend([
            "---",
            "",
            f"## 📌 Applied Jobs Tracker ({len(applied_jobs)} Submitted)",
            "",
            "| ID | Status | Applied Date | Company | Job Title | Location | Recommended Letter Body | Notes | Direct Link |",
            "| :---: | :---: | :---: | :--- | :--- | :--- | :--- | :--- | :---: |"
        ])
        for j in applied_jobs:
            badge = format_status_badge(j.get("applied", 1), j.get("status", "applied"), j.get("applied_at"))
            app_date = j.get("applied_at", "")[:10] if j.get("applied_at") else "Tracked"
            note_str = j.get("notes") or "—"
            lines.append(
                f"| `#{j['id']}` | **{badge}** | {app_date} | **{j['company']}** | [{j['title']}]({j['url']}) | {j['location']} | `{j['recommended_letter']}` | {note_str} | [Open ↗]({j['url']}) |"
            )
        lines.append("")
        
    # 2. Priority Recommendations
    lines.extend([
        "---",
        "",
        f"## 🌟 Priority Recommendations (Score 75%+) — {len(tier_top)} Positions",
        "",
        "| ID | Status | Score | Company | Job Title | Location | Recommended Letter Body | Action |",
        "| :---: | :---: | :---: | :--- | :--- | :--- | :--- | :---: |"
    ])
    
    for j in tier_top:
        badge = format_status_badge(j.get("applied", 0), j.get("status", "unapplied"), j.get("applied_at"))
        lines.append(
            f"| `#{j['id']}` | {badge} | **{j['score']}%** | **{j['company']}** | [{j['title']}]({j['url']}) | {j['location']} | `{j['recommended_letter']}` | [Apply ⚡](http://localhost:8765/apply/{j['id']}) \\| [Direct ↗]({j['url']}) |"
        )
        
    # 3. Strong Matches
    lines.extend([
        "",
        "---",
        "",
        f"## ⚡ Strong Matches (Score 60% - 74%) — {len(tier_mid)} Positions",
        "",
        "| ID | Status | Score | Company | Job Title | Location | Recommended Letter Body | Action |",
        "| :---: | :---: | :---: | :--- | :--- | :--- | :--- | :---: |"
    ])
    
    for j in tier_mid:
        badge = format_status_badge(j.get("applied", 0), j.get("status", "unapplied"), j.get("applied_at"))
        lines.append(
            f"| `#{j['id']}` | {badge} | **{j['score']}%** | {j['company']} | [{j['title']}]({j['url']}) | {j['location']} | `{j['recommended_letter']}` | [Apply ⚡](http://localhost:8765/apply/{j['id']}) \\| [Direct ↗]({j['url']}) |"
        )
        
    # 4. Explore More
    lines.extend([
        "",
        "---",
        "",
        f"## 🔍 Explore More EU Positions (Score 40% - 59%) — {len(tier_low)} Positions",
        "",
        "| ID | Status | Score | Company | Job Title | Location | Action |",
        "| :---: | :---: | :---: | :--- | :--- | :--- | :---: |"
    ])
    
    for j in tier_low:
        badge = format_status_badge(j.get("applied", 0), j.get("status", "unapplied"), j.get("applied_at"))
        lines.append(
            f"| `#{j['id']}` | {badge} | {j['score']}% | {j['company']} | [{j['title']}]({j['url']}) | {j['location']} | [Apply ⚡](http://localhost:8765/apply/{j['id']}) \\| [Direct ↗]({j['url']}) |"
        )
        
    lines.extend([
        "",
        "---",
        "### 💡 Instant Application Workflow",
        "1. Click **[Apply ⚡]** to automatically record application in SQLite & redirect straight to the employer's page.",
        "2. Note the **Recommended Letter Body** (e.g. `11. FORMULA 1 / MOTORSPORT`, `8. PROSUS AI ENGINEER`, `3. ML ENGINEER`).",
        "3. Set `\\jobTitle{...}` and `\\companyName{...}` in `cover_letter.tex` and compile with `pdflatex cover_letter.tex` for a 1-page custom PDF!",
        "4. Use `python sponsor_jobs/cli.py applied` or `python sponsor_jobs/cli.py web` to inspect your application pipeline anytime."
    ])
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    analyze_all_jobs()
