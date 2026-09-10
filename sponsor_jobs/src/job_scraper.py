#!/usr/bin/env python3
"""
job_scraper.py - High-throughput multi-platform ATS scraper supporting all 9 major platforms:
Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, Recruitee, Personio, BambooHR,
plus direct career page crawling.

Based on Conor's ATS Job API Reference (https://conorscode.github.io/ats-api-reference/).
"""

import os
import re
import html
import json
import sqlite3
import logging
import asyncio
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
import aiohttp
from bs4 import BeautifulSoup

try:
    from .profile_analyzer import is_eu_location
except ImportError:
    from profile_analyzer import is_eu_location

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sponsors.db"))

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
    "shanghai", "mumbai", "dubai", "location", "locations", "venues"
]


def is_tech_job(title: str) -> bool:
    """Filter to ensure job is a legitimate engineering/tech/data/AI role."""
    t_lower = title.lower().strip()
    if len(t_lower) < 5 or len(t_lower) > 95:
        return False
    if any(bad in t_lower for bad in EXCLUDE_TITLE_WORDS):
        return False
    return any(re.search(pat, t_lower) for pat in JOB_TITLE_KEYWORDS)


# ==============================================================================
# 1. GREENHOUSE (GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs)
# Quirk: 'content' is double HTML entity-encoded; full open list in 1 call.
# ==============================================================================
async def fetch_greenhouse_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            for r in data.get("jobs", []):
                title = r.get("title", "").strip()
                loc = r.get("location", {}).get("name", "Netherlands")
                job_url = r.get("absolute_url", "")
                
                if is_tech_job(title) and is_eu_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "source": f"Greenhouse ({slug})"
                    })
    except Exception as e:
        logging.debug(f"Greenhouse error ({slug}): {e}")
    return jobs


# ==============================================================================
# 2. LEVER (GET https://api.lever.co/v0/postings/{slug}?mode=json)
# Quirk: MUST pass ?mode=json explicitly; full list in 1 call.
# ==============================================================================
async def fetch_lever_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            if not isinstance(data, list):
                return []
            for r in data:
                title = r.get("text", "").strip()
                loc = r.get("categories", {}).get("location", "Netherlands")
                job_url = r.get("hostedUrl", "")
                workplace = r.get("workplaceType", "")
                if workplace and "remote" in workplace.lower() and "remote" not in loc.lower():
                    loc = f"{loc} (Remote)"
                    
                if is_tech_job(title) and is_eu_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "source": f"Lever ({slug})"
                    })
    except Exception as e:
        logging.debug(f"Lever error ({slug}): {e}")
    return jobs


# ==============================================================================
# 3. ASHBY (GET https://api.ashbyhq.com/posting-api/job-board/{slug})
# Quirk: Trim leading/trailing whitespace in titles; provides secondaryLocations.
# ==============================================================================
async def fetch_ashby_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            for r in data.get("jobs", []):
                title = r.get("title", "").strip()
                primary_loc = r.get("location", "")
                secondary = [s.get("location", "") for s in r.get("secondaryLocations", [])]
                all_locs = [primary_loc] + secondary if primary_loc else secondary
                loc_str = ", ".join(filter(None, all_locs)) or "Netherlands"
                job_url = r.get("jobUrl") or r.get("applyUrl") or ""

                if is_tech_job(title) and is_eu_location(loc_str):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc_str,
                        "url": job_url,
                        "source": f"Ashby ({slug})"
                    })
    except Exception as e:
        logging.debug(f"Ashby error ({slug}): {e}")
    return jobs


# ==============================================================================
# 4. WORKDAY (POST https://{tenant}.{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs)
# Quirk: POST with JSON body {"limit": 20, "offset": 0, "searchText": ""}.
# ==============================================================================
async def fetch_workday_jobs(session: aiohttp.ClientSession, tenant: str, shard: str, site: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    url = f"https://{tenant}.{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    payload = {"limit": 30, "offset": 0, "searchText": ""}
    jobs = []
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            for r in data.get("jobPostings", []):
                title = r.get("title", "").strip()
                loc = r.get("locationsText", "Netherlands")
                ext_path = r.get("externalPath", "").lstrip("/")
                job_url = f"https://{tenant}.{shard}.myworkdayjobs.com/en-US/{site}/job/{ext_path}"

                if is_tech_job(title) and is_eu_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "source": f"Workday ({tenant})"
                    })
    except Exception as e:
        logging.debug(f"Workday error ({tenant}): {e}")
    return jobs


# ==============================================================================
# 5. SMARTRECRUITERS (GET https://api.smartrecruiters.com/v1/companies/{id}/postings)
# Quirk: Pagination via totalFound, offset/limit. Explicit location booleans.
# ==============================================================================
async def fetch_smartrecruiters_jobs(session: aiohttp.ClientSession, identifier: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    url = f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings?limit=100&offset=0"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            for r in data.get("content", []):
                title = r.get("name", "").strip()
                loc_obj = r.get("location", {})
                loc = loc_obj.get("fullLocation") or f"{loc_obj.get('city', '')}, {loc_obj.get('country', '')}".strip() or "Netherlands"
                ref = r.get("id", "")
                job_url = f"https://jobs.smartrecruiters.com/{identifier}/{ref}"

                if is_tech_job(title) and is_eu_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "source": f"SmartRecruiters ({identifier})"
                    })
    except Exception as e:
        logging.debug(f"SmartRecruiters error ({identifier}): {e}")
    return jobs


# ==============================================================================
# 6. WORKABLE (GET https://apply.workable.com/api/v1/widget/accounts/{slug})
# Quirk: Separated city, state, country fields; telecommuting boolean.
# ==============================================================================
async def fetch_workable_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=false"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            for r in data.get("jobs", []):
                title = r.get("title", "").strip()
                city = r.get("city", "")
                country = r.get("country", "")
                is_remote = r.get("telecommuting", False)
                loc_parts = [p for p in [city, country] if p]
                if is_remote:
                    loc_parts.append("Remote")
                loc = ", ".join(loc_parts) or "Netherlands"
                job_url = r.get("application_url", f"https://apply.workable.com/j/{r.get('shortcode', '')}")

                if is_tech_job(title) and is_eu_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "source": f"Workable ({slug})"
                    })
    except Exception as e:
        logging.debug(f"Workable error ({slug}): {e}")
    return jobs


# ==============================================================================
# 7. RECRUITEE (GET https://{slug}.recruitee.com/api/offers/)
# Quirk: Keep trailing slash! Check structured locations array.
# ==============================================================================
async def fetch_recruitee_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    url = f"https://{slug}.recruitee.com/api/offers/"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            offers = data.get("offers", []) if isinstance(data, dict) else data
            for r in offers:
                title = r.get("title", "").strip()
                loc_objs = r.get("locations", [])
                if loc_objs and isinstance(loc_objs, list):
                    loc = ", ".join(f"{o.get('city', '')} {o.get('country', '')}".strip() for o in loc_objs)
                else:
                    loc = f"{r.get('city', '')} {r.get('country', '')}".strip() or "Netherlands"
                job_url = r.get("careers_url", "")

                if is_tech_job(title) and is_eu_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "source": f"Recruitee ({slug})"
                    })
    except Exception as e:
        logging.debug(f"Recruitee error ({slug}): {e}")
    return jobs


# ==============================================================================
# 8. PERSONIO (GET https://{slug}.jobs.personio.de/xml)
# Quirk: XML workzag-jobs schema! Do NOT follow 307 redirects to marketing site.
# ==============================================================================
async def fetch_personio_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    url = f"https://{slug}.jobs.personio.de/xml"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8), allow_redirects=False) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()
            root = ET.fromstring(text)
            for pos in root.findall(".//position"):
                title = (pos.findtext("name") or "").strip()
                pos_id = pos.findtext("id") or ""
                primary_office = pos.findtext("office") or ""
                additional = [off.text for off in pos.findall(".//additionalOffices/office") if off.text]
                all_offices = [primary_office] + additional if primary_office else additional
                loc = ", ".join(filter(None, all_offices)) or "Netherlands"
                job_url = f"https://{slug}.jobs.personio.de/job/{pos_id}"

                if is_tech_job(title) and is_eu_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "source": f"Personio ({slug})"
                    })
    except Exception as e:
        logging.debug(f"Personio error ({slug}): {e}")
    return jobs


# ==============================================================================
# 9. BAMBOOHR (GET https://{slug}.bamboohr.com/careers/list)
# Quirk: JSON response; do NOT follow 302 redirects to marketing site.
# ==============================================================================
async def fetch_bamboohr_jobs(session: aiohttp.ClientSession, slug: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    url = f"https://{slug}.bamboohr.com/careers/list"
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8), allow_redirects=False) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            for r in data.get("result", []):
                title = r.get("jobOpeningName", "").strip()
                job_id = r.get("id", "")
                ats_loc = r.get("atsLocation", {}) or {}
                loc = f"{ats_loc.get('city', '')} {ats_loc.get('country', '')}".strip() or "Netherlands"
                job_url = f"https://{slug}.bamboohr.com/careers/{job_id}"

                if is_tech_job(title) and is_eu_location(loc):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "source": f"BambooHR ({slug})"
                    })
    except Exception as e:
        logging.debug(f"BambooHR error ({slug}): {e}")
    return jobs


# ==============================================================================
# 10. DIRECT CAREER WEB PAGE CRAWLER (HTML fallback)
# ==============================================================================
async def crawl_html_career_page(session: aiohttp.ClientSession, url: str, company_name: str, sponsor_id: int) -> List[Dict[str, Any]]:
    jobs = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=6), headers=HEADERS) as resp:
            if resp.status != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
                return []
            html_text = await resp.text()
            soup = BeautifulSoup(html_text, "html.parser")
            
            for a in soup.find_all("a", href=True):
                text = a.get_text().strip()
                href = a["href"].strip()
                
                if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue
                if not text or not is_tech_job(text):
                    continue
                    
                full_url = href if href.startswith("http") else f"{url.rstrip('/')}/{href.lstrip('/')}"
                if is_eu_location("Netherlands"):
                    jobs.append({
                        "sponsor_id": sponsor_id,
                        "company_name": company_name,
                        "title": text,
                        "location": "Netherlands",
                        "url": full_url,
                        "source": "Web Career Page"
                    })
    except Exception as e:
        logging.debug(f"HTML crawl error ({url}): {e}")
    return jobs


def save_jobs_to_db(jobs: List[Dict[str, Any]], db_path: str = DB_PATH) -> int:
    """Upsert discovered jobs into the SQLite database."""
    if not jobs:
        return 0
        
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    saved = 0
    
    for j in jobs:
        try:
            cur.execute("""
            INSERT INTO jobs (sponsor_id, company_name, title, location, url, source, is_active, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                location = excluded.location,
                is_active = 1,
                last_seen = CURRENT_TIMESTAMP
            """, (j.get("sponsor_id"), j["company_name"], j["title"], j.get("location", "Netherlands"), j["url"], j.get("source", "Scraper")))
            saved += 1
        except Exception as e:
            logging.debug(f"Error saving job {j.get('url')}: {e}")
            
    conn.commit()
    conn.close()
    return saved


async def run_scraper(limit: int = 50, db_path: str = DB_PATH) -> int:
    """Orchestrate async scraping across all 9 ATS platforms and web pages."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # 1. Fetch sponsors with known ATS configs
    cur.execute("""
    SELECT id, clean_name, ats_type, ats_slug, careers_url
    FROM sponsors
    WHERE ats_type IS NOT NULL AND ats_type != '' AND ats_slug IS NOT NULL AND ats_slug != ''
    """)
    ats_sponsors = cur.fetchall()
    
    # 2. Fetch candidate tech sponsors with careers URLs
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
        
        # Dispatch to appropriate ATS handler based on ats_type
        for sp_id, name, ats_type, slug, _ in ats_sponsors:
            t = ats_type.lower()
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
                # slug format: tenant:shard:site (e.g. nxp:wd3:careers)
                parts = slug.split(":")
                if len(parts) == 3:
                    tasks.append(fetch_workday_jobs(session, parts[0], parts[1], parts[2], name, sp_id))
                
        # Dispatch HTML crawler tasks
        for sp_id, name, careers_url in web_sponsors[:limit]:
            tasks.append(crawl_html_career_page(session, careers_url, name, sp_id))
            
        logging.info(f"Executing {len(tasks)} asynchronous job scraping tasks across 9 ATS platforms & web portals...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in results:
            if isinstance(res, list):
                all_jobs.extend(res)
                
    saved_count = save_jobs_to_db(all_jobs, db_path)
    logging.info(f"Discovered {len(all_jobs)} tech/engineering EU positions. Saved/Updated {saved_count} in DB.")
    return saved_count


if __name__ == "__main__":
    asyncio.run(run_scraper(limit=30))
