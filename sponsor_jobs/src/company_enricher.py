#!/usr/bin/env python3
"""
company_enricher.py - Enriches tech/engineering/automotive sponsors with domains,
career portals, and ATS endpoints across all 9 platforms:
Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, Recruitee, Personio, BambooHR.
"""

import os
import re
import sqlite3
import logging
from typing import Dict, Optional, List, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sponsors.db"))

# Format: keyword: (clean_name, domain, careers_url, ats_type, ats_slug)
CURATED_SPONSORS_CONFIG = {
    # --- Greenhouse ---
    "databricks": ("Databricks", "https://www.databricks.com", "https://www.databricks.com/company/careers", "greenhouse", "databricks"),
    "messagebird": ("Bird (MessageBird)", "https://bird.com", "https://bird.com/careers", "greenhouse", "bird"),
    "gitlab": ("GitLab", "https://about.gitlab.com", "https://about.gitlab.com/jobs", "greenhouse", "gitlab"),
    "stripe": ("Stripe", "https://stripe.com", "https://stripe.com/jobs", "greenhouse", "stripe"),
    "datadog": ("Datadog", "https://www.datadoghq.com", "https://careers.datadoghq.com", "greenhouse", "datadog"),
    "cloudflare": ("Cloudflare", "https://www.cloudflare.com", "https://www.cloudflare.com/careers", "greenhouse", "cloudflare"),
    "elastic": ("Elastic", "https://www.elastic.co", "https://www.elastic.co/careers", "greenhouse", "elastic"),
    "reddit": ("Reddit", "https://www.reddit.com", "https://www.redditinc.com/careers", "greenhouse", "reddit"),
    "nebius": ("Nebius AI", "https://nebius.com", "https://nebius.com/careers", "greenhouse", "nebius"),
    "canonical": ("Canonical", "https://canonical.com", "https://canonical.com/careers", "greenhouse", "canonical"),
    "figma": ("Figma", "https://www.figma.com", "https://www.figma.com/careers", "greenhouse", "figma"),
    "imc": ("IMC Trading", "https://www.imc.com", "https://careers.imc.com", "greenhouse", "imc"),
    "adyen": ("Adyen", "https://www.adyen.com", "https://careers.adyen.com/vacancies", "greenhouse", "adyen"),
    "flow traders": ("Flow Traders", "https://www.flowtraders.com", "https://www.flowtraders.com/careers", "greenhouse", "flowtraders"),
    "jetbrains": ("JetBrains", "https://www.jetbrains.com", "https://www.jetbrains.com/careers", "greenhouse", "jetbrains"),
    "braze": ("Braze", "https://www.braze.com", "https://www.braze.com/company/careers", "greenhouse", "braze"),
    "crunchyroll": ("Crunchyroll", "https://www.crunchyroll.com", "https://www.crunchyroll.com/careers", "greenhouse", "crunchyroll"),
    "anthropic": ("Anthropic", "https://www.anthropic.com", "https://www.anthropic.com/careers", "greenhouse", "anthropic"),
    "scaleai": ("Scale AI", "https://scale.com", "https://scale.com/careers", "greenhouse", "scaleai"),

    # --- Lever ---
    "mollie": ("Mollie", "https://www.mollie.com", "https://jobs.mollie.com", "lever", "mollie"),
    "palantir": ("Palantir Technologies", "https://www.palantir.com", "https://www.palantir.com/careers", "lever", "palantir"),
    "spotify": ("Spotify", "https://www.spotify.com", "https://www.lifeatspotify.com", "lever", "spotify"),

    # --- Ashby ---
    "openai": ("OpenAI", "https://openai.com", "https://openai.com/careers", "ashby", "openai"),
    "cohere": ("Cohere", "https://cohere.com", "https://cohere.com/careers", "ashby", "cohere"),
    "perplexity": ("Perplexity AI", "https://www.perplexity.ai", "https://www.perplexity.ai/careers", "ashby", "perplexity"),
    "notion": ("Notion", "https://www.notion.so", "https://www.notion.so/careers", "ashby", "notion"),
    "cursor": ("Cursor / Anysphere", "https://www.cursor.com", "https://www.cursor.com/careers", "ashby", "cursor"),
    "ramp": ("Ramp", "https://ramp.com", "https://ramp.com/careers", "ashby", "ramp"),
    "replit": ("Replit", "https://replit.com", "https://replit.com/careers", "ashby", "replit"),
    "sentry": ("Sentry", "https://sentry.io", "https://sentry.io/careers", "ashby", "sentry"),
    "linear": ("Linear", "https://linear.app", "https://linear.app/careers", "ashby", "linear"),
    "weaviate": ("Weaviate", "https://weaviate.io", "https://weaviate.io/company/careers", "ashby", "weaviate"),

    # --- Recruitee ---
    "bunq": ("bunq", "https://www.bunq.com", "https://www.bunq.com/jobs", "recruitee", "bunq"),
    "channable": ("Channable", "https://www.channable.com", "https://www.channable.com/careers", "recruitee", "channable"),
    "channelengine": ("ChannelEngine", "https://www.channelengine.com", "https://www.channelengine.com/careers", "recruitee", "channelengine"),
    "da vinci": ("Da Vinci Derivatives", "https://davinciderivatives.com", "https://davinciderivatives.com/careers", "recruitee", "davinci-derivatives"),
    "helloprint": ("HelloPrint", "https://www.helloprint.com", "https://jobs.helloprint.com", "recruitee", "helloprint"),

    # --- Personio ---
    "pair finance": ("PAIR Finance", "https://www.pairfinance.com", "https://www.pairfinance.com/careers", "personio", "pair"),
    "lepaya": ("Lepaya", "https://www.lepaya.com", "https://www.lepaya.com/careers", "personio", "lepaya"),
    "personio": ("Personio", "https://www.personio.com", "https://www.personio.com/careers", "personio", "personio"),

    # --- Workable ---
    "huggingface": ("Hugging Face", "https://huggingface.co", "https://apply.workable.com/huggingface", "workable", "huggingface"),

    # --- SmartRecruiters ---
    "backbase": ("Backbase", "https://www.backbase.com", "https://careers.backbase.com", "smartrecruiters", "backbase"),

    # --- Workday ---
    "nxp": ("NXP Semiconductors", "https://www.nxp.com", "https://nxp.wd3.myworkdayjobs.com/careers", "workday", "nxp:wd3:careers"),
    "asml": ("ASML", "https://www.asml.com", "https://asml.wd3.myworkdayjobs.com/careers", "workday", "asml:wd3:careers"),

    # --- Custom / Specialized Portals ---
    "tomtom": ("TomTom", "https://www.tomtom.com", "https://www.tomtom.com/careers", "custom", ""),
    "uber": ("Uber Netherlands", "https://www.uber.com", "https://www.uber.com/careers", "custom", ""),
    "booking": ("Booking.com", "https://www.booking.com", "https://careers.booking.com", "custom", ""),
    "demcon": ("Demcon", "https://demcon.com", "https://werkenbijdemcon.nl", "custom", ""),
    "prodrive": ("Prodrive Technologies", "https://prodrive-technologies.com", "https://careers.prodrive-technologies.com", "custom", ""),
    "sioux": ("Sioux Technologies", "https://www.sioux.eu", "https://jobs.sioux.eu", "custom", ""),
    "vanderlande": ("Vanderlande", "https://www.vanderlande.com", "https://careers.vanderlande.com", "custom", ""),
    "tno": ("TNO", "https://www.tno.nl", "https://www.tno.nl/en/careers", "custom", ""),
    "delft university of technology": ("TU Delft", "https://www.tudelft.nl", "https://www.tudelft.nl/en/about-tu-delft/working-at-tu-delft/vacancies", "custom", ""),
    "tu delft": ("TU Delft", "https://www.tudelft.nl", "https://www.tudelft.nl/en/about-tu-delft/working-at-tu-delft/vacancies", "custom", ""),
    "topdesk": ("TOPdesk", "https://www.topdesk.com", "https://careers.topdesk.com", "custom", ""),
    "coolblue": ("Coolblue", "https://www.coolblue.nl", "https://careersatcoolblue.com", "custom", "")
}


def enrich_curated_sponsors(db_path: str = DB_PATH) -> int:
    """Enrich known tech/automotive/engineering sponsors with direct career & ATS configurations."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    cur = conn.cursor()
    
    updated = 0
    for keyword, (clean_name, domain, careers_url, ats_type, ats_slug) in CURATED_SPONSORS_CONFIG.items():
        cur.execute("""
        SELECT id, name FROM sponsors
        WHERE LOWER(name) LIKE ? OR LOWER(clean_name) LIKE ?
        """, (f"%{keyword}%", f"%{keyword}%"))
        
        matches = cur.fetchall()
        if matches:
            for sponsor_id, full_name in matches:
                cur.execute("""
                UPDATE sponsors
                SET clean_name = COALESCE(?, clean_name),
                    website = ?,
                    careers_url = ?,
                    ats_type = ?,
                    ats_slug = ?,
                    is_target_sector = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """, (clean_name, domain, careers_url, ats_type, ats_slug, sponsor_id))
                updated += 1
        else:
            cur.execute("""
            INSERT OR IGNORE INTO sponsors (name, clean_name, website, careers_url, ats_type, ats_slug, is_target_sector)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (clean_name, clean_name, domain, careers_url, ats_type, ats_slug))
            updated += 1
            
    conn.commit()
    conn.close()
    logging.info(f"Enriched {updated} curated target sponsor records across 9 ATS types.")
    return updated


def guess_company_domains(db_path: str = DB_PATH, limit: int = 500) -> int:
    """For target tech sponsors without a website, generate standard domain heuristics."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    cur = conn.cursor()
    
    cur.execute("""
    SELECT id, clean_name FROM sponsors
    WHERE is_target_sector = 1 AND (website IS NULL OR website = '')
    ORDER BY id ASC
    LIMIT ?
    """, (limit,))
    
    rows = cur.fetchall()
    updated = 0
    
    for sponsor_id, clean_name in rows:
        slug = re.sub(r'[^a-zA-Z0-9]', '', clean_name.lower())
        if not slug or len(slug) < 3:
            continue
            
        website = f"https://www.{slug}.nl"
        careers_url = f"{website}/careers"
        
        cur.execute("""
        UPDATE sponsors
        SET website = ?,
            careers_url = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (website, careers_url, sponsor_id))
        updated += 1
        
    conn.commit()
    conn.close()
    return updated


if __name__ == "__main__":
    import time
    t0 = time.time()
    print("=" * 60)
    print("🚀 Company Enricher: Populating Target Sponsors & ATS Slugs")
    print("=" * 60)
    
    enriched = enrich_curated_sponsors()
    guessed = guess_company_domains()
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    SELECT ats_type, count(*) 
    FROM sponsors 
    WHERE ats_slug IS NOT NULL AND ats_slug != '' 
    GROUP BY ats_type 
    ORDER BY count(*) DESC
    """)
    ats_stats = cur.fetchall()
    conn.close()
    
    print("\n📊 Configured ATS breakdown in database:")
    for ats, count in ats_stats:
        print(f"   • {ats.capitalize():16}: {count} sponsors")
        
    print(f"\n✅ Finished in {time.time() - t0:.2f}s (Enriched {enriched} curated sponsors, generated {guessed} domains).")
    print("=" * 60)

