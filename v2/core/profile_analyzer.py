"""
profile_analyzer.py - Dynamic Profile-Driven Job Analyzer & Report Generator (v2).

Coordinates scoring, keyword extraction, seniority classification, and report generation
completely customized to the active PersonalizationProfile.
Zero hardcoded candidate names, rules, or schemas.
"""

from __future__ import annotations

import os
import re
import json
import sqlite3
import logging
from typing import Dict, Any, List, Optional, Tuple

from v2.profile_schema import PersonalizationProfile
from v2.core.scorer import Scorer, JobScoreResult
from v2.core.company_matcher import CompanyMatcher

logger = logging.getLogger(__name__)


def detect_ats_platform(source: str = "", url: str = "", ats_type: Optional[str] = None) -> str:
    """Classify ATS platform name from source, url, and sponsor metadata."""
    src = (source or "").lower()
    u = (url or "").lower()
    at = (ats_type or "").lower()

    if "greenhouse" in src or "greenhouse.io" in u or at == "greenhouse":
        return "Greenhouse"
    if "lever" in src or "lever.co" in u or at == "lever":
        return "Lever"
    if "ashby" in src or "ashbyhq.com" in u or at == "ashby":
        return "Ashby"
    if "workday" in src or "myworkdayjobs.com" in u or at == "workday":
        return "Workday"
    if "smartrecruiters" in src or "smartrecruiters.com" in u or at == "smartrecruiters":
        return "SmartRecruiters"
    if "workable" in src or "workable.com" in u or at == "workable":
        return "Workable"
    if "recruitee" in src or "recruitee.com" in u or at == "recruitee":
        return "Recruitee"
    if "personio" in src or "personio.de" in u or "personio.com" in u or at == "personio":
        return "Personio"
    if "bamboohr" in src or "bamboohr.com" in u or at == "bamboohr":
        return "BambooHR"
    if "teamtailor" in src or "teamtailor.com" in u or at == "teamtailor":
        return "Teamtailor"
    if "linkedin" in src or "linkedin.com" in u:
        return "LinkedIn"
    if "indeed" in src or "indeed.com" in u:
        return "Indeed"
    return "Direct Portal"


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
    elif st == "uninterested":
        return "🚫 Uninterested"
    elif st == "rejected":
        return "❌ Rejected"
    return "⬜ Not Applied"


class ProfileAnalyzer:
    """
    Profile-driven job analyzer and report generator.
    Evaluates jobs from SQLite databases or raw JD texts against a PersonalizationProfile.
    """

    def __init__(self, profile: PersonalizationProfile, db_path: Optional[str] = None):
        self.profile = profile
        self.db_path = db_path or profile.output_settings.sqlite_db_path or "v2/data/sponsors.db"
        self.scorer = Scorer(profile)
        self.matcher = CompanyMatcher(profile, db_path=self.db_path)

    def extract_keywords(
        self,
        text: str,
        title: Optional[str] = None,
        location: Optional[str] = None,
        company: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parse raw job description text, extract technical keywords against candidate's
        skill categories, check seniority indicators, and score the job match.
        """
        raw_text = (text or "").strip()
        detected_title = title or ""
        detected_company = company or ""
        detected_location = location or ""
        seniority_warning = None
        exp_years = None

        # Fallback Title extraction from text header
        if not detected_title and raw_text:
            first_line = raw_text.split("\n")[0][:100].strip()
            if any(k in first_line.lower() for k in ("engineer", "developer", "scientist", "specialist")):
                detected_title = first_line

        # Detect Seniority / Experience indicators
        m_exp = re.search(
            r"\b(\d+\s*[-+to]+\s*\d+|\d+\+?)\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp)?\b",
            raw_text,
            re.IGNORECASE
        )
        if m_exp:
            exp_years = m_exp.group(0).strip()
            max_allowed = self.profile.candidate_preferences.seniority.max_experience_years or 3
            m_num = re.search(r"\b(\d+)\b", exp_years)
            if m_num and int(m_num.group(1)) > max_allowed:
                seniority_warning = f"Notice: Mentions '{exp_years}'. Exceeds candidate preferred cap ({max_allowed} yrs)."

        if not seniority_warning and self.scorer.is_senior_role(detected_title or raw_text[:300]):
            disallowed_token = self.scorer.get_disallowed_seniority_match(detected_title or raw_text[:300])
            seniority_warning = f"Notice: Mentions disallowed seniority designation ('{disallowed_token}')." if disallowed_token else "Notice: Mentions disallowed seniority designation."

        # Keyword extraction grouped by candidate's verified skill categories
        categorized: Dict[str, List[str]] = {}
        all_matched_skills: List[str] = []
        seen = set()

        for skill_cat in self.profile.candidate_background.verified_technical_skills:
            matched_in_cat = []
            for skill_name in skill_cat.skills:
                # Check skill name directly or aliases
                patterns_to_check = [rf"\b{re.escape(skill_name)}\b"]
                if skill_cat.aliases and skill_name in skill_cat.aliases:
                    for alias in skill_cat.aliases[skill_name]:
                        patterns_to_check.append(rf"\b{re.escape(alias)}\b")

                for pat in patterns_to_check:
                    if re.search(pat, raw_text, re.IGNORECASE):
                        if skill_name not in matched_in_cat:
                            matched_in_cat.append(skill_name)
                        if skill_name not in seen:
                            seen.add(skill_name)
                            all_matched_skills.append(skill_name)
                        break

            if matched_in_cat:
                categorized[skill_cat.category] = matched_in_cat

        # Score job using Scorer
        eval_title = detected_title or "Software / Machine Learning Engineer"
        eval_loc = detected_location or "Target Location"
        score_res = self.scorer.score_job(
            title=eval_title,
            location=eval_loc,
            description=raw_text,
            company_name=detected_company,
            allow_senior=True
        )

        return {
            "total_count": len(all_matched_skills),
            "all_keywords": all_matched_skills,
            "categorized": categorized,
            "detected_metadata": {
                "title": detected_title,
                "company": detected_company,
                "location": detected_location,
                "seniority_warning": seniority_warning,
                "experience_years": exp_years
            },
            "match_score": score_res.score,
            "match_reasons": score_res.reasons,
            "recommended_letter": score_res.recommended_letter,
            "talking_points": score_res.talking_points,
            "top_notes": ", ".join(all_matched_skills[:10])
        }

    def analyze_all_jobs(self, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Score all jobs in SQLite database dynamically according to the profile
        and generate Markdown & JSON recommendation reports.
        """
        target_db = db_path or self.db_path
        if not target_db or not os.path.exists(target_db):
            logger.warning(f"Database not found at '{target_db}'. Returning empty job list.")
            return []

        conn = sqlite3.connect(target_db, timeout=30)
        conn.execute("PRAGMA journal_mode = WAL;")
        cur = conn.cursor()

        # Check if table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
        if not cur.fetchone():
            conn.close()
            return []

        cur.execute("""
        SELECT j.id, j.company_name, j.title, j.location, j.url, j.description, s.kvk,
               j.applied, j.applied_at, j.status, j.notes, j.is_new, j.first_seen, j.source,
               s.ats_type
        FROM jobs j
        LEFT JOIN sponsors s ON j.sponsor_id = s.id
        """)
        rows = cur.fetchall()

        analyzed_jobs: List[Dict[str, Any]] = []

        for row in rows:
            job_id, company, title, loc, url, desc, kvk, applied, applied_at, status, notes, is_new, first_seen, source, ats_type = row
            location_str = loc or "Target Location"
            is_manual = bool(source and any(k in source.lower() for k in ("manual", "linkedin", "custom", "external")))

            # Filter location if candidate excludes it and not manual
            if not is_manual and not self.scorer.is_target_location(location_str):
                cur.execute("UPDATE jobs SET match_score = 0, is_active = 0 WHERE id = ?", (job_id,))
                continue

            # Check senior exclusion
            if not is_manual and self.scorer.is_senior_role(title):
                cur.execute("UPDATE jobs SET match_score = 0, is_active = 0, is_senior = 1 WHERE id = ?", (job_id,))
                continue

            score_res = self.scorer.score_job(
                title=title,
                location=location_str,
                description=desc or "",
                company_name=company,
                allow_senior=is_manual
            )

            reason_str = " | ".join(score_res.reasons)
            ats_platform = detect_ats_platform(source, url, ats_type)

            cur.execute("""
            UPDATE jobs
            SET match_score = ?,
                match_reason = ?,
                recommended_letter = ?,
                is_active = ?,
                is_senior = ?
            WHERE id = ?
            """, (score_res.score, reason_str, score_res.recommended_letter,
                  1 if score_res.is_active else 0, 1 if score_res.is_senior else 0, job_id))

            analyzed_jobs.append({
                "id": job_id,
                "company": company,
                "kvk": kvk or ("IND Recognised Sponsor" if is_manual else "Target Sponsor"),
                "title": title,
                "location": location_str,
                "region": score_res.location_category,
                "url": url,
                "score": score_res.score,
                "reasons": score_res.reasons,
                "recommended_letter": score_res.recommended_letter,
                "applied": applied or 0,
                "applied_at": applied_at,
                "status": status or "unapplied",
                "notes": notes or "",
                "is_new": 1 if is_new else 0,
                "first_seen": first_seen or "",
                "source": source or "Scraper",
                "ats_platform": ats_platform,
                "talking_points": score_res.talking_points
            })

        conn.commit()
        conn.close()

        analyzed_jobs.sort(key=lambda x: x["score"], reverse=True)

        # Resolve output paths
        reports_dir = os.path.abspath(self.profile.output_settings.reports_dir or "v2/reports")
        os.makedirs(reports_dir, exist_ok=True)

        md_path = os.path.join(reports_dir, self.profile.output_settings.markdown_filename)
        json_path = os.path.join(reports_dir, self.profile.output_settings.json_filename)

        self.generate_markdown_report(analyzed_jobs, md_path)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(analyzed_jobs, f, indent=2)

        logger.info(f"Analyzed {len(analyzed_jobs)} jobs for profile '{self.profile.profile_id}'. Saved to {md_path}")
        return analyzed_jobs

    def refresh_reports(self, db_path: Optional[str] = None) -> None:
        """
        Lightweight report regeneration: reads existing scores from DB
        without re-scoring. Use after status-only changes (apply/unapply/reject).
        """
        target_db = db_path or self.db_path
        if not target_db or not os.path.exists(target_db):
            return

        conn = sqlite3.connect(target_db, timeout=30)
        conn.execute("PRAGMA journal_mode = WAL;")
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
        if not cur.fetchone():
            conn.close()
            return

        cur.execute("""
        SELECT j.id, j.company_name, j.title, j.location, j.url, j.description, s.kvk,
               j.applied, j.applied_at, j.status, j.notes, j.is_new, j.first_seen, j.source,
               s.ats_type, j.match_score, j.match_reason, j.recommended_letter, j.is_active, j.is_senior
        FROM jobs j
        LEFT JOIN sponsors s ON j.sponsor_id = s.id
        WHERE j.is_active = 1 AND j.match_score > 0
        """)
        rows = cur.fetchall()
        conn.close()

        jobs = []
        for row in rows:
            (job_id, company, title, loc, url, desc, kvk, applied, applied_at,
             status, notes, is_new, first_seen, source, ats_type,
             score, reason_str, rec_letter, is_active, is_senior) = row

            ats_platform = detect_ats_platform(source, url, ats_type)
            loc_category = self.scorer.get_location_category(loc or "")

            jobs.append({
                "id": job_id, "company": company, "kvk": kvk or "Target Sponsor",
                "title": title, "location": loc or "", "region": loc_category,
                "url": url, "score": score or 0.0,
                "reasons": (reason_str or "").split(" | "),
                "recommended_letter": rec_letter or "",
                "applied": applied or 0, "applied_at": applied_at,
                "status": status or "unapplied", "notes": notes or "",
                "is_new": 1 if is_new else 0, "first_seen": first_seen or "",
                "source": source or "Scraper", "ats_platform": ats_platform,
                "talking_points": []
            })

        jobs.sort(key=lambda x: x["score"], reverse=True)

        reports_dir = os.path.abspath(self.profile.output_settings.reports_dir or "v2/reports")
        os.makedirs(reports_dir, exist_ok=True)
        md_path = os.path.join(reports_dir, self.profile.output_settings.markdown_filename)
        json_path = os.path.join(reports_dir, self.profile.output_settings.json_filename)

        self.generate_markdown_report(jobs, md_path)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2)

    def generate_markdown_report(self, jobs: List[Dict[str, Any]], output_path: str) -> None:
        """
        Render a clean, formatted Markdown report dynamically customized with
        candidate name, target roles, location tiers, and application badges.
        """
        hidden_statuses = ("uninterested", "rejected")

        tier_top = [j for j in jobs if j["score"] >= 75 and j.get("status") not in hidden_statuses]
        tier_mid = [j for j in jobs if 60 <= j["score"] < 75 and j.get("status") not in hidden_statuses]
        tier_low = [j for j in jobs if 40 <= j["score"] < 60 and j.get("status") not in hidden_statuses]

        applied_jobs = [
            j for j in jobs
            if (j.get("applied") == 1 or (j.get("status") and j.get("status") not in ("unapplied", *hidden_statuses)))
            and j.get("status") != "rejected"
        ]
        new_jobs = [j for j in jobs if j.get("is_new") == 1 and j.get("status") not in hidden_statuses]
        uninterested_jobs = [j for j in jobs if j.get("status") == "uninterested"]
        rejected_jobs = [j for j in jobs if j.get("status") == "rejected"]

        candidate_name = self.profile.candidate_background.personal_info.name
        primary_roles = [r.title for r in self.profile.candidate_preferences.target_roles[:4]]
        target_locations = [t.name for t in self.profile.candidate_preferences.locations.tiers]

        lines = [
            f"# 🎯 Top Job Recommendations for {candidate_name}",
            "",
            f"**Candidate:** {candidate_name} ({self.profile.candidate_background.personal_info.tagline or 'AI & Software Engineer'})",
            f"**Profile ID:** `{self.profile.profile_id}` (Schema v{self.profile.schema_version})",
            f"**Active Roles Evaluated:** {len(jobs)} positions across verified sponsors & tech leaders.",
            f"**Application Pipeline:** 🎯 **{len(applied_jobs)} Active Applied** | ❌ **{len(rejected_jobs)} Rejected** | 🚫 **{len(uninterested_jobs)} Uninterested**",
            f"**Newly Discovered:** 🆕 **{len(new_jobs)} New Roles**.",
            f"**Target Roles:** {', '.join(primary_roles)}",
            f"**Geographical Scope:** {' • '.join(target_locations)} • 🌐 Remote",
            f"**Seniority Policy:** {'🛡️ Disallowed Seniority Excluded (' + ', '.join(self.profile.candidate_preferences.seniority.disallowed_levels[:5]) + '...)' if self.profile.candidate_preferences.seniority.strict_exclusion else 'All Seniority Levels Accepted'}",
            ""
        ]

        # 1. Dedicated Applied Jobs Tracker section
        if applied_jobs:
            lines.append("## 📌 Active Submitted Applications & Interviews")
            lines.append("")
            lines.append("| ID | Company | Role | Location | Match | Status | Letter Body | ATS / Portal |")
            lines.append("|:---|:---|:---|:---|:---:|:---:|:---|:---|")
            for j in applied_jobs:
                badge = format_status_badge(j.get("applied", 0), j.get("status", "applied"), j.get("applied_at"))
                lines.append(
                    f"| `#{j['id']}` | **{j['company']}** | [{j['title']}]({j['url']}) | {j['location']} | "
                    f"**{j['score']:.0f}%** | {badge} | `{j['recommended_letter']}` | {j.get('ats_platform', 'Direct')} |"
                )
            lines.append("")

        # 2. Tier 1: Prime Matches (Score >= 75%)
        lines.append(f"## 🌟 Prime Recommendations (Score ≥ 75%) — {len(tier_top)} Roles")
        lines.append("")
        if tier_top:
            lines.append("| ID | Score | Company | Job Title | Location | Recommended Letter | Apply Link |")
            lines.append("|:---:|:---:|:---|:---|:---|:---|:---:|")
            for j in tier_top:
                new_tag = "🆕 " if j.get("is_new") else ""
                lines.append(
                    f"| `#{j['id']}` | **{j['score']:.0f}%** | **{j['company']}** | {new_tag}[{j['title']}]({j['url']}) | "
                    f"{j['location']} | `{j['recommended_letter']}` | [Apply ⚡]({j['url']}) |"
                )
        else:
            lines.append("*(No unapplied jobs currently in this tier)*")
        lines.append("")

        # 3. Tier 2: Strong Matches (60% <= Score < 75%)
        lines.append(f"## ⚡ Strong Matches (60% ≤ Score < 75%) — {len(tier_mid)} Roles")
        lines.append("")
        if tier_mid:
            lines.append("| ID | Score | Company | Job Title | Location | Recommended Letter | Apply Link |")
            lines.append("|:---:|:---:|:---|:---|:---|:---|:---:|")
            for j in tier_mid:
                new_tag = "🆕 " if j.get("is_new") else ""
                lines.append(
                    f"| `#{j['id']}` | **{j['score']:.0f}%** | **{j['company']}** | {new_tag}[{j['title']}]({j['url']}) | "
                    f"{j['location']} | `{j['recommended_letter']}` | [Apply ⚡]({j['url']}) |"
                )
        else:
            lines.append("*(No unapplied jobs currently in this tier)*")
        lines.append("")

        # 4. Tier 3: Viable Matches (40% <= Score < 60%)
        lines.append(f"## 📋 Viable Matches (40% ≤ Score < 60%) — {len(tier_low)} Roles")
        lines.append("")
        if tier_low:
            lines.append("| ID | Score | Company | Job Title | Location | Recommended Letter | Apply Link |")
            lines.append("|:---:|:---:|:---|:---|:---|:---|:---:|")
            for j in tier_low[:30]:  # limit lower tier for readability
                lines.append(
                    f"| `#{j['id']}` | {j['score']:.0f}% | {j['company']} | [{j['title']}]({j['url']}) | "
                    f"{j['location']} | `{j['recommended_letter']}` | [Apply ⚡]({j['url']}) |"
                )
        lines.append("")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
