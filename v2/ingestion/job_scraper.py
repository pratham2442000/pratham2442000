#!/usr/bin/env python3
"""
job_scraper.py - High-throughput multi-platform ATS scraper (v2).
Supports 9 major platforms: Greenhouse, Lever, Ashby, Workday, SmartRecruiters,
Workable, Recruitee, Personio, BambooHR, plus direct career page crawling.

Based on Conor's ATS Job API Reference (https://conorscode.github.io/ats-api-reference/).
Standalone v2 implementation operating strictly on v2/data/sponsors.db.
"""

from __future__ import annotations

import os
import re
import json
import sqlite3
import logging
import asyncio
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sponsors.db"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/xml, text/html, */*"
}

JOB_TITLE_KEYWORDS = [
    r"\bengineer\b", r"\bdeveloper\b", r"\bsoftware\b", r"\bmachine\s+learning\b",
    r"\bdata\b", r"\bai\b", r"\bvision\b", r"\bautonomous\b", r"\brobotics\b",
    r"\bresearch\b", r"\bplatform\b", r"\bbackend\b", r"\bfrontend\b",
    r"\bfullstack\b", r"\bperception\b", r"\blidar\b", r"\bdeep\s+learning\b",
    r"\bembedded\b", r"\barchitect\b", r"\balgorithm\b", r"\bmlops\b"
]

EXCLUDE_TITLE_WORDS = [
    "email", "contact", "privacy", "disclaimer", "cookie", "terms", "policy",
    "accountant", "recruiter", "sales", "hr", "legal", "marketing", "office manager"
]

TARGET_LOCATION_PATTERNS = [
    r"\bnetherlands\b", r"\bamsterdam\b", r"\bdelft\b", r"\beindhoven\b", r"\brotterdam\b",
    r"\butrecht\b", r"\bthe\s+hague\b", r"\bden\s+haag\b", r"\bholland\b",
    r"\bunited\s+kingdom\b", r"\buk\b", r"\blondon\b", r"\bcambridge\b", r"\boxford\b",
    r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b", r"\bbrisbane\b",
    r"\bnew\s+york\b", r"\bnyc\b", r"\bmanhattan\b",
    r"\bsan\s+francisco\b", r"\bsf\b", r"\bbay\s+area\b", r"\bsilicon\s+valley\b",
    r"\bmountain\s+view\b", r"\bpalo\s+alto\b", r"\bsunnyvale\b", r"\bsan\s+jose\b",
    r"\blos\s+angeles\b", r"\bla\b", r"\bsanta\s+monica\b", r"\bculver\s+city\b",
    r"\bunited\s+states\b", r"\busa\b", r"\bu\.s\.", r"\bcalifornia\b",
    r"\beurope\b", r"\beu\b", r"\bemea\b", r"\bgermany\b", r"\bberlin\b", r"\bmunich\b",
    r"\bfrance\b", r"\bparis\b", r"\bswitzerland\b", r"\bzurich\b", r"\bgeneva\b",
    r"\bireland\b", r"\bdublin\b", r"\bsweden\b", r"\bstockholm\b", r"\bbelgium\b",
    r"\bbrussels\b", r"\bghent\b", r"\bdenmark\b", r"\bcopenhagen\b",
    r"\bremote\b", r"\bworldwide\b", r"\banywhere\b", r"\bhybrid\b"
]

NON_TARGET_PATTERNS = [
    r"\bindia\b", r"\bbangalore\b", r"\bhyderabad\b", r"\bpune\b", r"\bmumbai\b",
    r"\bdelhi\b", r"\bgurgaon\b", r"\bnoida\b", r"\bchennai\b",
    r"\bsingapore\b", r"\bbrazil\b", r"\bchina\b", r"\bjapan\b", r"\btokyo\b"
]


def is_tech_job(title: str) -> bool:
    """Check if job title matches tech, engineering, AI, or research domains."""
    t = title.lower()
    if any(ex in t for ex in EXCLUDE_TITLE_WORDS):
        return False
    return any(re.search(pat, t) for pat in JOB_TITLE_KEYWORDS)


def is_target_location(location: str) -> bool:
    """Check if location matches candidate target geographies."""
    if not location or location.strip() == "":
        return True
    loc = location.lower().strip()
    if any(re.search(pat, loc) for pat in [r"\bnew\s+york\b", r"\bsan\s+francisco\b", r"\blos\s+angeles\b"]):
        return True
    has_non_target = any(re.search(pat, loc) for pat in NON_TARGET_PATTERNS)
    has_target = any(re.search(pat, loc) for pat in TARGET_LOCATION_PATTERNS)
    if has_non_target:
        is_explicit_target = any(re.search(pat, loc) for pat in [
            r"\bnetherlands\b", r"\bamsterdam\b", r"\bdelft\b", r"\beindhoven\b",
            r"\bunited\s+kingdom\b", r"\buk\b", r"\blondon\b",
            r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b",
            r"\beurope\b", r"\beu\b", r"\bemea\b", r"\bworldwide\b"
        ])
        return is_explicit_target
    return has_target


# ============================================================================
# ATS HANDLERS
# ============================================================================

async def fetch_greenhouse_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    """Greenhouse API: GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            for j in data.get("jobs", []):
                title = j.get("title", "")
                loc = j.get("location", {}).get("name", "")
                if is_tech_job(title) and is_target_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": j.get("absolute_url", ""),
                        "description": "",
                        "source": "Greenhouse API"
                    })
    except Exception:
        pass
    return jobs


async def fetch_lever_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    """Lever API: GET https://api.lever.co/v0/postings/{slug}?mode=json"""
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            for j in data:
                title = j.get("text", "")
                cats = j.get("categories", {})
                loc = cats.get("location", "") or cats.get("allLocations", [""])[0] if isinstance(cats.get("allLocations"), list) and cats.get("allLocations") else ""
                desc = j.get("descriptionPlain", "") or ""
                if is_tech_job(title) and is_target_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": j.get("hostedUrl", ""),
                        "description": desc[:1000],
                        "source": "Lever API"
                    })
    except Exception:
        pass
    return jobs


async def fetch_ashby_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    """Ashby API: POST https://api.ashbyhq.com/posting-api/job-board/{slug}"""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    jobs = []
    try:
        async with session.post(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            for j in data.get("jobs", []):
                title = j.get("title", "")
                loc = j.get("location", "")
                secondary = j.get("secondaryLocations", [])
                loc_str = loc
                if secondary:
                    loc_str += ", " + ", ".join(secondary)
                if is_tech_job(title) and is_target_location(loc_str):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc_str,
                        "url": j.get("jobUrl", ""),
                        "description": "",
                        "source": "Ashby API"
                    })
    except Exception:
        pass
    return jobs


async def fetch_smartrecruiters_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    """SmartRecruiters API: GET https://api.smartrecruiters.com/v1/companies/{slug}/postings"""
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            for j in data.get("content", []):
                title = j.get("name", "")
                loc_obj = j.get("location", {})
                loc = f"{loc_obj.get('city', '')}, {loc_obj.get('country', '')}".strip(", ")
                job_id = j.get("id", "")
                job_url = f"https://jobs.smartrecruiters.com/{slug}/{job_id}"
                if is_tech_job(title) and is_target_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "description": "",
                        "source": "SmartRecruiters API"
                    })
    except Exception:
        pass
    return jobs


async def fetch_workable_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    """Workable API: GET https://apply.workable.com/api/v1/widget/accounts/{slug}"""
    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            for j in data.get("jobs", []):
                title = j.get("title", "")
                loc = f"{j.get('city', '')}, {j.get('country', '')}".strip(", ")
                if is_tech_job(title) and is_target_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": j.get("url", ""),
                        "description": "",
                        "source": "Workable API"
                    })
    except Exception:
        pass
    return jobs


async def fetch_recruitee_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    """Recruitee API: GET https://{slug}.recruitee.com/api/offers/"""
    url = f"https://{slug}.recruitee.com/api/offers/"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            for j in data.get("offers", []):
                title = j.get("title", "")
                loc = f"{j.get('city', '')}, {j.get('country', '')}".strip(", ")
                if is_tech_job(title) and is_target_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": j.get("careers_url", ""),
                        "description": BeautifulSoup(j.get("description", ""), "html.parser").get_text()[:1000],
                        "source": "Recruitee API"
                    })
    except Exception:
        pass
    return jobs


async def fetch_personio_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    """Personio XML API: GET https://{slug}.jobs.personio.de/xml"""
    url = f"https://{slug}.jobs.personio.de/xml"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            xml_text = await resp.text()
            root = ET.fromstring(xml_text)
            for pos in root.findall(".//position"):
                title = pos.findtext("name", "")
                job_id = pos.findtext("id", "")
                loc = pos.findtext("office", "")
                job_url = f"https://{slug}.jobs.personio.de/job/{job_id}"
                if is_tech_job(title) and is_target_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "description": "",
                        "source": "Personio XML API"
                    })
    except Exception:
        pass
    return jobs


async def fetch_bamboohr_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    """BambooHR API: GET https://{slug}.bamboohr.com/jobs/embed2.php"""
    url = f"https://{slug}.bamboohr.com/jobs/embed2.php"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()
            soup = BeautifulSoup(text, "html.parser")
            for a in soup.find_all("a", href=True):
                if "/jobs/view.php" in a["href"]:
                    title = a.get_text().strip()
                    loc = "Netherlands / Remote"
                    parent = a.find_parent("li") or a.find_parent("div")
                    if parent:
                        loc_elem = parent.find(class_=re.compile(r"location|city", re.I))
                        if loc_elem:
                            loc = loc_elem.get_text().strip()
                    job_url = a["href"]
                    if not job_url.startswith("http"):
                        job_url = f"https://{slug}.bamboohr.com" + job_url
                    if is_tech_job(title) and is_target_location(loc):
                        jobs.append({
                            "sponsor_id": sponsor_id,
                            "company_name": company_name,
                            "title": title,
                            "location": loc,
                            "url": job_url,
                            "description": "",
                            "source": "BambooHR Embed API"
                        })
    except Exception:
        pass
    return jobs


async def fetch_workday_jobs(session: aiohttp.ClientSession, tenant: str, shard: str, site: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    """Workday API: POST https://{tenant}.{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"""
    url = f"https://{tenant}.{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    jobs = []
    payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "Engineer"}
    try:
        async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            for j in data.get("jobPostings", []):
                title = j.get("title", "")
                loc = j.get("locationsText", "")
                ext_path = j.get("externalPath", "")
                job_url = f"https://{tenant}.{shard}.myworkdayjobs.com/en-US/{site}{ext_path}"
                if is_tech_job(title) and is_target_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "description": "",
                        "source": "Workday CXS API"
                    })
    except Exception:
        pass
    return jobs


REJECT_URL_PATTERNS = [
    r"/blog", r"/product", r"/solution", r"/service", r"/feature", r"/topic",
    r"/technolog", r"/event", r"/investor", r"/insight", r"/success-stori",
    r"/resource", r"/oplossing", r"/assessment", r"/market", r"/competence",
    r"/job-area", r"/why-", r"/engage", r"/category", r"/partner", r"/customer",
    r"/whitepaper", r"/pricing", r"/contact", r"/about", r"/news", r"/press",
    r"/docs", r"/community", r"/privacy", r"/terms", r"/cookie", r"/legal",
    r"linkedin\.com/company", r"/division", r"/tools", r"\.pdf$", r"\.png$", r"\.jpg$", r"#"
]

JOB_URL_HINTS = [
    r"/job[s]?", r"/career", r"/position", r"/opening", r"/vacatur",
    r"/work-at", r"/join", r"boards\.", r"greenhouse", r"lever\.co"
]

ROLE_TITLE_PATTERNS = [
    r"\bengineer\b", r"\bdeveloper\b", r"\barchitect\b", r"\bscientist\b",
    r"\bspecialist\b", r"\blead\b", r"\bmanager\b", r"\bintern\b",
    r"\bresearcher\b", r"\bconsultant\b", r"\boperator\b", r"\banalyst\b",
    r"\bdesigner\b", r"\btechnician\b", r"\bprogrammer\b"
]

NON_JOB_TITLE_WORDS = [
    "resources", "tools", "platform", "solutions", "whitepaper", "data sheets", 
    "ai topics", "overview", "ecosystem", "program", "services"
]


async def crawl_html_career_page(session: aiohttp.ClientSession, url: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    """Generic career page HTML crawler."""
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()
            soup = BeautifulSoup(text, "html.parser")
            for a in soup.find_all("a", href=True):
                raw_href = a["href"].strip()
                if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue

                job_url = raw_href if raw_href.startswith("http") else urljoin(url, raw_href)

                # Skip obvious non-job URLs (products, blogs, solutions, marketing landing pages)
                lower_url = job_url.lower().strip()
                if any(re.search(pat, lower_url) for pat in REJECT_URL_PATTERNS):
                    continue

                if "zoekterm=" in lower_url or "search=" in lower_url or lower_url.rstrip("/").endswith(("/careers", "/jobs", "/vacatures")):
                    continue

                raw_title = a.get_text()
                # Ignore multi-line marketing cards / navigation menus
                if "\n\n" in raw_title or len(raw_title.splitlines()) > 2:
                    continue

                title = " ".join(raw_title.split()).strip()
                lower_title = title.lower()

                if not (8 < len(title) < 100 and is_tech_job(title)):
                    continue

                if any(bw in lower_title for bw in NON_JOB_TITLE_WORDS) and not any(re.search(p, lower_title) for p in ROLE_TITLE_PATTERNS):
                    continue

                # Ensure title contains concrete role words or specific vacancy pattern in URL
                has_role_title_hint = any(re.search(pat, lower_title) for pat in ROLE_TITLE_PATTERNS)
                has_specific_job_url = any(re.search(pat, lower_url) for pat in [
                    r"/vacanc", r"/vacatur", r"/o/[a-z0-9\-]+", r"gh_jid=", r"/all-jobs/[a-z0-9\-]+",
                    r"/position/[a-z0-9\-]+", r"/careers/[a-z0-9\-]+-(engineer|developer|scientist|specialist|lead|architect|manager)"
                ])

                if not (has_role_title_hint or has_specific_job_url):
                    continue

                # Exclude non-target geographies mentioned in job titles
                if any(loc in lower_title for loc in ["pune", "india", "bangalore", "chennai", "mumbai"]):
                    continue

                jobs.append({
                    "sponsor_id": sponsor_id,
                    "company_name": company_name,
                    "title": title,
                    "location": "Netherlands",
                    "url": job_url,
                    "description": "",
                    "source": "HTML Career Crawler"
                })
    except Exception:
        pass
    return jobs


def save_jobs_to_db(jobs: List[Dict[str, Any]], db_path: str = DEFAULT_DB_PATH) -> int:
    """Insert or update scraped positions into SQLite jobs table."""
    if not jobs:
        return 0

    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL;")
    cur = conn.cursor()
    saved = 0

    for j in jobs:
        cur.execute("""
        INSERT INTO jobs (sponsor_id, company_name, title, location, url, description, source, is_active, is_new, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(url) DO UPDATE SET
            title = excluded.title,
            location = excluded.location,
            is_active = 1,
            last_seen = CURRENT_TIMESTAMP
        """, (
            j.get("sponsor_id"),
            j["company_name"],
            j["title"],
            j.get("location", ""),
            j["url"],
            j.get("description", ""),
            j.get("source", "Scraper")
        ))
        saved += 1

    conn.commit()
    conn.close()
    return saved


async def run_scraper(limit: int = 50, db_path: str = DEFAULT_DB_PATH) -> int:
    """Orchestrate async scraping across ATS platforms and web pages."""
    conn = sqlite3.connect(db_path, timeout=30)
    cur = conn.cursor()

    cur.execute("""
    SELECT id, clean_name, ats_type, ats_slug, careers_url
    FROM sponsors
    WHERE ats_type IS NOT NULL AND ats_type != '' AND ats_slug IS NOT NULL AND ats_slug != ''
    """)
    ats_sponsors = cur.fetchall()

    cur.execute("""
    SELECT id, clean_name, careers_url
    FROM sponsors
    WHERE is_target_sector = 1 AND careers_url IS NOT NULL AND careers_url != ''
    LIMIT ?
    """, (limit,))
    web_sponsors = cur.fetchall()
    conn.close()

    all_jobs: List[Dict[str, Any]] = []

    connector = aiohttp.TCPConnector(limit=30, ssl=False)
    async with aiohttp.ClientSession(connector=connector, headers=HEADERS) as session:
        tasks = []

        for sp_id, name, ats_type, slug, _ in ats_sponsors:
            t = (ats_type or "").lower()
            if t == "greenhouse":
                tasks.append(fetch_greenhouse_jobs(session, slug, name, sp_id))
            elif t == "lever":
                tasks.append(fetch_lever_jobs(session, slug, name, sp_id))
            elif t == "ashby":
                tasks.append(fetch_ashby_jobs(session, slug, name, sp_id))
            elif t == "smartrecruiters":
                tasks.append(fetch_smartrecruiters_jobs(session, slug, name, sp_id))
            elif t == "workable":
                tasks.append(fetch_workable_jobs(session, slug, name, sp_id))
            elif t == "recruitee":
                tasks.append(fetch_recruitee_jobs(session, slug, name, sp_id))
            elif t == "personio":
                tasks.append(fetch_personio_jobs(session, slug, name, sp_id))
            elif t == "bamboohr":
                tasks.append(fetch_bamboohr_jobs(session, slug, name, sp_id))
            elif t == "workday" and ":" in slug:
                parts = slug.split(":")
                if len(parts) == 3:
                    tasks.append(fetch_workday_jobs(session, parts[0], parts[1], parts[2], name, sp_id))

        for sp_id, name, careers_url in web_sponsors[:limit]:
            tasks.append(crawl_html_career_page(session, careers_url, name, sp_id))

        logger.info(f"Executing {len(tasks)} asynchronous job scraping tasks across 9 ATS platforms & web portals...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, list):
                all_jobs.extend(res)

    saved_count = save_jobs_to_db(all_jobs, db_path)
    logger.info(f"Discovered {len(all_jobs)} tech/engineering positions. Saved/Updated {saved_count} in DB.")
    return saved_count
