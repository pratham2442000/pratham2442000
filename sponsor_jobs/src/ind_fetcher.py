#!/usr/bin/env python3
"""
ind_fetcher.py - Ingest and categorize recognised sponsors from the Dutch IND Public Register.
URL: https://ind.nl/en/public-register-recognised-sponsors/public-register-work
"""

import os
import re
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

IND_URL = "https://ind.nl/en/public-register-recognised-sponsors/public-register-work"
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sponsors.db"))

# Sector keywords for categorizing companies into target sectors (Tech, AI, Engineering, Automotive, Robotics, etc.)
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

# Curated known high-profile tech / engineering / automotive sponsors in Netherlands
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


def init_db(db_path: str = DB_PATH) -> None:
    """Initialize the SQLite database schema."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sponsors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        clean_name TEXT NOT NULL,
        kvk TEXT,
        is_target_sector INTEGER DEFAULT 0,
        sector_tags TEXT,
        website TEXT,
        careers_url TEXT,
        ats_type TEXT,
        ats_slug TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sponsor_id INTEGER,
        company_name TEXT NOT NULL,
        title TEXT NOT NULL,
        location TEXT,
        url TEXT UNIQUE NOT NULL,
        description TEXT,
        source TEXT,
        match_score REAL DEFAULT 0,
        match_reason TEXT,
        recommended_letter TEXT,
        applied INTEGER DEFAULT 0,
        applied_at TIMESTAMP,
        status TEXT DEFAULT 'unapplied',
        notes TEXT,
        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY (sponsor_id) REFERENCES sponsors(id)
    )
    """)
    
    # Safe migration for existing databases
    cur.execute("PRAGMA table_info(jobs)")
    existing_cols = {row[1] for row in cur.fetchall()}
    if "applied" not in existing_cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN applied INTEGER DEFAULT 0")
    if "applied_at" not in existing_cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN applied_at TIMESTAMP")
    if "status" not in existing_cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN status TEXT DEFAULT 'unapplied'")
    if "notes" not in existing_cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN notes TEXT")
    
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sponsor_clean ON sponsors(clean_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sponsor_target ON sponsors(is_target_sector)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(match_score DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(is_active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_applied ON jobs(applied)")
    
    conn.commit()
    conn.close()
    logging.info(f"Initialized database schema at {db_path}")


def clean_company_name(raw_name: str) -> str:
    """Clean legal artifacts and punctuation from Dutch corporate names."""
    name = raw_name.strip()
    # Strip enclosing quotes
    name = re.sub(r'^["\']+|["\']+$', '', name)
    name = re.sub(r'""+', '', name)
    # Remove standard Dutch legal suffixes for cleaner matching
    name_clean = re.sub(r'\b(B\.?V\.?|N\.?V\.?|Holding|Holdings|Nederland|Netherlands|Group|Europe|International)\b', '', name, flags=re.IGNORECASE)
    name_clean = re.sub(r'[^\w\s\-\.\&]', ' ', name_clean)
    name_clean = re.sub(r'\s+', ' ', name_clean).strip()
    return name_clean if name_clean else name.strip()


def classify_sector(name: str) -> Tuple[bool, List[str]]:
    """Determine if a company belongs to target sectors (Tech, AI, Engineering, Automotive, Robotics)."""
    name_lower = name.lower()
    tags = []
    
    # Check known curated tech sponsors
    for known in KNOWN_TECH_SPONSORS:
        if known in name_lower:
            tags.append("CuratedTech")
            break
            
    # Check automotive & mobility
    if any(re.search(pat, name_lower) for pat in AUTOMOTIVE_KEYWORDS):
        tags.append("Automotive/Mobility")
        
    # Check tech & software & AI
    if any(re.search(pat, name_lower) for pat in TECH_KEYWORDS):
        tags.append("Tech/Software/AI")
        
    # Check engineering & semiconductor & robotics
    if any(re.search(pat, name_lower) for pat in ENGINEERING_KEYWORDS):
        tags.append("Engineering/Robotics")
        
    # Check research & academia & sciences
    if any(re.search(pat, name_lower) for pat in SCIENCE_RESEARCH_KEYWORDS):
        tags.append("Research/Science")
        
    is_target = len(tags) > 0
    return is_target, tags


def parse_ind_html(html_content: str) -> List[Dict[str, str]]:
    """Parse table rows from IND HTML content."""
    soup = BeautifulSoup(html_content, "html.parser")
    rows = []
    
    table = soup.find("table")
    if not table:
        logging.warning("No <table> found in HTML, falling back to regex extraction.")
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


def fetch_and_store_sponsors(force_refresh: bool = False, db_path: str = DB_PATH) -> int:
    """Download the IND public register, parse all entries, and update SQLite."""
    init_db(db_path)
    
    html_content = ""
    cached_file = "/home/prat/.gemini/antigravity-ide/brain/6a29f66a-34aa-4a24-af03-6d68544ac4da/.system_generated/steps/58/content.md"
    
    if not force_refresh and os.path.exists(cached_file) and os.path.getsize(cached_file) > 100000:
        logging.info("Using cached IND public register file...")
        with open(cached_file, "r", encoding="utf-8", errors="ignore") as f:
            html_content = f.read()
    else:
        logging.info(f"Fetching live IND public register from {IND_URL}...")
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(IND_URL, headers=headers, timeout=30)
        resp.raise_for_status()
        html_content = resp.text

    sponsors_raw = parse_ind_html(html_content)
    logging.info(f"Parsed {len(sponsors_raw)} raw sponsor entries from IND register.")
    
    conn = sqlite3.connect(db_path)
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
    
    # Get total counts
    cur.execute("SELECT COUNT(*) FROM sponsors")
    total_in_db = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM sponsors WHERE is_target_sector=1")
    targets_in_db = cur.fetchone()[0]
    
    conn.close()
    logging.info(f"Sync complete! Total sponsors in DB: {total_in_db} | Target Tech/Eng/Auto sponsors: {targets_in_db}")
    return total_in_db


if __name__ == "__main__":
    fetch_and_store_sponsors()
