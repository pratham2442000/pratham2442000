#!/usr/bin/env python3
"""
ind_fetcher.py - Ingest and categorize recognised sponsors from Dutch IND Public Register (v2).
URL: https://ind.nl/en/public-register-recognised-sponsors/public-register-work

Standalone v2 implementation operating strictly on v2/data/sponsors.db.
"""

from __future__ import annotations

import os
import re
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

IND_URL = "https://ind.nl/en/public-register-recognised-sponsors/public-register-work"
DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sponsors.db"))

# Sector classification taxonomies
TECH_KEYWORDS = [
    r"\btech\b", r"\btechnology\b", r"\btechnologies\b", r"\bsoftware\b", r"\bdata\b",
    r"\bai\b", r"\bartificial intelligence\b", r"\bmachine learning\b", r"\bdeep learning\b",
    r"\bcloud\b", r"\bcyber\b", r"\bsecurity\b", r"\bit\b", r"\binformatics\b", r"\bdigital\b",
    r"\binfotech\b", r"\bcomput\b", r"\bsystems\b", r"\binternet\b", r"\bweb\b", r"\bplatform\b",
    r"\blabs?\b", r"\binteractive\b", r"\bmedia\b", r"\btelecom\b", r"\bnetwork\b"
]

ENGINEERING_KEYWORDS = [
    r"\bengineer\b", r"\bengineering\b", r"\bingenieur\b", r"\bsemiconductor\b", r"\bsemi\b",
    r"\belectron\b", r"\belectronic\b", r"\belectronics\b", r"\bhardware\b", r"\bphotonics\b",
    r"\boptics\b", r"\blaser\b", r"\bnanotech\b", r"\bmechanic\b", r"\bmechanical\b",
    r"\bmechatron\b", r"\bprecision\b", r"\baerospace\b", r"\baviation\b", r"\bspace\b",
    r"\binstruments\b", r"\bmanufacturing\b", r"\bautomation\b", r"\bautomated\b", r"\brobot\b",
    r"\brobotics\b", r"\bsensor\b", r"\bmicro\b", r"\benergy\b", r"\bpower\b"
]

AUTOMOTIVE_KEYWORDS = [
    r"\bauto\b", r"\bautomotive\b", r"\bmotors?\b", r"\bmobility\b", r"\bvehicle\b",
    r"\bdriving\b", r"\bautonomous\b", r"\bracing\b", r"\bmotorsport\b", r"\btransport\b",
    r"\belectric vehicle\b", r"\bev\b", r"\btrucks?\b", r"\bcar\b", r"\bcars\b", r"\bfleet\b"
]

SCIENCE_RESEARCH_KEYWORDS = [
    r"\bresearch\b", r"\binstitute\b", r"\blaborator\b", r"\buniversity\b", r"\buniv\b",
    r"\bdelft\b", r"\beindhoven\b", r"\btwente\b", r"\btno\b", r"\bscience\b", r"\bsciences\b",
    r"\bbiotech\b", r"\bpharma\b", r"\bbiosciences\b", r"\bgenomics\b", r"\bquantum\b"
]

KNOWN_TECH_SPONSORS = {
    "asml", "nxp", "adyen", "booking", "uber", "tomtom", "picnic", "elsevier",
    "philips", "tno", "esa", "european space agency", "qualcomm", "asmi", "asm international",
    "thermo fisher", "synopsys", "cadence", "siemens", "daf trucks", "scania",
    "stellantis", "bmw", "mercedes", "tesla", "rivian", "lightyear", "embotech",
    "palantir", "optiver", "flow traders", "imc", "da vinci", "jane street",
    "databricks", "snowflake", "elastic", "miro", "messagebird", "bird", "mollie",
    "bunq", "backbase", "infor", "red hat", "canonical", "aws", "amazon", "google",
    "meta", "apple", "microsoft", "cisco", "nvidia", "intel", "amd", "broadcom",
    "delft university of technology", "tu delft", "eindhoven university of technology",
    "stmicroelectronics", "vanderlande", "demcon", "vdnl", "prodrive", "sioux",
    "topic", "tessenderlo", "bdr thermea", "nedap", "chipsoft", "topdesk",
    "gorillas", "just eat", "takeaway", "coolblue", "bol.com", "vandebron"
}


def clean_company_name(name: str) -> str:
    """Normalize legal business suffixes for accurate entity matching."""
    s = name.strip()
    patterns = [
        r"\s+Holding\s+B\.V\.?$", r"\s+Holdings\s+B\.V\.?$",
        r"\s+Nederland\s+B\.V\.?$", r"\s+Netherlands\s+B\.V\.?$",
        r"\s+International\s+B\.V\.?$", r"\s+Europe\s+B\.V\.?$",
        r"\s+Services\s+B\.V\.?$", r"\s+Group\s+B\.V\.?$",
        r"\s+Coöperatief\s+U\.A\.?$", r"\s+U\.A\.?$", r"\s+C\.V\.?$",
        r"\s+B\.V\.?$", r"\s+BV$", r"\s+N\.V\.?$", r"\s+NV$",
        r"\s+Holding$", r"\s+Holdings$",
        r"\s+GmbH$", r"\s+Ltd\.?$", r"\s+Limited$", r"\s+Inc\.?$", r"\s+LLC$"
    ]
    for p in patterns:
        s = re.sub(p, "", s, flags=re.IGNORECASE).strip()
    return s


def classify_sector(name: str) -> Tuple[bool, List[str]]:
    """Determine if company operates in Tech/AI/Engineering/Research target sectors."""
    lower_name = name.lower()
    clean_lower = clean_company_name(name).lower()
    tags = []

    # Check known sponsor registry
    if any(ts in lower_name or ts == clean_lower for ts in KNOWN_TECH_SPONSORS):
        tags.append("Known Target Tech")

    # Keyword regex scanning
    for p in TECH_KEYWORDS:
        if re.search(p, lower_name):
            tags.append("Tech/IT")
            break
    for p in ENGINEERING_KEYWORDS:
        if re.search(p, lower_name):
            tags.append("Engineering/Semiconductors")
            break
    for p in AUTOMOTIVE_KEYWORDS:
        if re.search(p, lower_name):
            tags.append("Automotive/Robotics")
            break
    for p in SCIENCE_RESEARCH_KEYWORDS:
        if re.search(p, lower_name):
            tags.append("Science/Research")
            break

    is_target = len(tags) > 0
    return is_target, list(set(tags))


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Provision schema for sponsors and jobs via central DatabaseManager."""
    from v2.storage.db import DatabaseManager
    DatabaseManager(db_path)


def parse_ind_html(html_content: str) -> List[Dict[str, str]]:
    """Parse table rows from IND HTML content."""
    soup = BeautifulSoup(html_content, "html.parser")
    rows = []

    table = soup.find("table")
    if not table:
        pattern = re.compile(r'<th[^>]*scope="row"[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>', re.DOTALL | re.IGNORECASE)
        for m in pattern.finditer(html_content):
            name = BeautifulSoup(m.group(1), "html.parser").get_text().strip()
            kvk = BeautifulSoup(m.group(2), "html.parser").get_text().strip()
            if name:
                rows.append({"name": name, "kvk": kvk})
        return rows

    tbody = table.find("tbody") or table
    for tr in tbody.find_all("tr"):
        th = tr.find(["th", "td"])
        if not th:
            continue
        cols = tr.find_all(["th", "td"])
        name = cols[0].get_text().strip()
        kvk = cols[1].get_text().strip() if len(cols) > 1 else ""
        if name and name.lower() != "organisation":
            rows.append({"name": name, "kvk": kvk})

    return rows


def fetch_and_store_sponsors(force_refresh: bool = False, db_path: str = DEFAULT_DB_PATH) -> int:
    """Download the official IND public register, parse all entries, and update SQLite."""
    init_db(db_path)

    html_content = ""
    # Check for local cached copy
    cached_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "ind_register_cache.html"))

    if not force_refresh and os.path.exists(cached_file) and os.path.getsize(cached_file) > 100000:
        logger.info("Using cached IND public register file...")
        with open(cached_file, "r", encoding="utf-8", errors="ignore") as f:
            html_content = f.read()
    else:
        logger.info(f"Fetching live IND public register from {IND_URL}...")
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        try:
            resp = requests.get(IND_URL, headers=headers, timeout=30)
            resp.raise_for_status()
            html_content = resp.text
            # Cache locally in v2/data
            os.makedirs(os.path.dirname(cached_file), exist_ok=True)
            with open(cached_file, "w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception as e:
            logger.warning(f"Could not download live IND register: {e}")
            if os.path.exists(cached_file):
                with open(cached_file, "r", encoding="utf-8", errors="ignore") as f:
                    html_content = f.read()
            else:
                raise

    sponsors_raw = parse_ind_html(html_content)
    logger.info(f"Parsed {len(sponsors_raw)} raw sponsor entries from IND register.")

    conn = sqlite3.connect(db_path, timeout=30)
    cur = conn.cursor()

    target_count = 0
    now = datetime.utcnow().isoformat()

    for item in sponsors_raw:
        raw_name = item["name"]
        clean_name = clean_company_name(raw_name)
        kvk = item["kvk"]
        is_target, tags = classify_sector(raw_name)
        if is_target:
            target_count += 1

        tags_str = ",".join(tags)

        cur.execute("""
        INSERT INTO sponsors (name, clean_name, kvk, is_target_sector, sector_tags, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            clean_name=excluded.clean_name,
            kvk=excluded.kvk,
            is_target_sector=excluded.is_target_sector,
            sector_tags=excluded.sector_tags,
            updated_at=excluded.updated_at
        """, (raw_name, clean_name, kvk, 1 if is_target else 0, tags_str, now))

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM sponsors")
    total_in_db = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM sponsors WHERE is_target_sector=1")
    targets_in_db = cur.fetchone()[0]

    conn.close()
    logger.info(f"Sync complete! Total sponsors in DB: {total_in_db} | Target Tech/Eng/Auto sponsors: {targets_in_db}")
    return total_in_db
