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
    # --- Greenhouse: Global & EU Tech / AI / Infrastructure ---
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
    "adyen": ("Adyen", "https://www.adyen.com", "https://careers.adyen.com/vacancies", "greenhouse", "adyen"),
    "jetbrains": ("JetBrains", "https://www.jetbrains.com", "https://www.jetbrains.com/careers", "greenhouse", "jetbrains"),
    "braze": ("Braze", "https://www.braze.com", "https://www.braze.com/company/careers", "greenhouse", "braze"),
    "crunchyroll": ("Crunchyroll", "https://www.crunchyroll.com", "https://www.crunchyroll.com/careers", "greenhouse", "crunchyroll"),
    "anthropic": ("Anthropic", "https://www.anthropic.com", "https://www.anthropic.com/careers", "greenhouse", "anthropic"),
    "scaleai": ("Scale AI", "https://scale.com", "https://scale.com/careers", "greenhouse", "scaleai"),
    "wandb": ("Weights & Biases", "https://wandb.ai", "https://boards.greenhouse.io/wandb", "greenhouse", "wandb"),
    "pinecone": ("Pinecone", "https://www.pinecone.io", "https://boards.greenhouse.io/pinecone", "greenhouse", "pinecone"),
    "snowflake": ("Snowflake", "https://www.snowflake.com", "https://boards.greenhouse.io/snowflake", "greenhouse", "snowflake"),
    "clickhouse": ("ClickHouse", "https://clickhouse.com", "https://boards.greenhouse.io/clickhouse", "greenhouse", "clickhouse"),
    "docker": ("Docker", "https://www.docker.com", "https://boards.greenhouse.io/docker", "greenhouse", "docker"),
    "hashicorp": ("HashiCorp", "https://www.hashicorp.com", "https://boards.greenhouse.io/hashicorp", "greenhouse", "hashicorp"),
    "grafanalabs": ("Grafana Labs", "https://grafana.com", "https://boards.greenhouse.io/grafanalabs", "greenhouse", "grafanalabs"),
    "temporal": ("Temporal", "https://temporal.io", "https://boards.greenhouse.io/temporal", "greenhouse", "temporal"),
    "redis": ("Redis", "https://redis.io", "https://boards.greenhouse.io/redis", "greenhouse", "redis"),
    "neo4j": ("Neo4j", "https://neo4j.com", "https://boards.greenhouse.io/neo4j", "greenhouse", "neo4j"),
    "github": ("GitHub", "https://github.com", "https://boards.greenhouse.io/github", "greenhouse", "github"),
    "miro": ("Miro", "https://miro.com", "https://boards.greenhouse.io/miro", "greenhouse", "miro"),
    "picnic": ("Picnic Technologies", "https://picnic.app", "https://boards.greenhouse.io/picnic", "greenhouse", "picnic"),

    # --- Greenhouse: Australia Tech Leaders ---
    "canva": ("Canva", "https://www.canva.com", "https://boards.greenhouse.io/canva", "greenhouse", "canva"),
    "safetyculture": ("SafetyCulture", "https://safetyculture.com", "https://boards.greenhouse.io/safetyculture", "greenhouse", "safetyculture"),
    "cultureamp": ("Culture Amp", "https://www.cultureamp.com", "https://boards.greenhouse.io/cultureamp", "greenhouse", "cultureamp"),
    "employmenthero": ("Employment Hero", "https://employmenthero.com", "https://boards.greenhouse.io/employmenthero", "greenhouse", "employmenthero"),

    # --- Greenhouse: United Kingdom Scaleups & Tech ---
    "wayve": ("Wayve (Autonomous AI)", "https://wayve.ai", "https://boards.greenhouse.io/wayve", "greenhouse", "wayve"),
    "oxa": ("Oxa Autonomy", "https://oxa.tech", "https://boards.greenhouse.io/oxa", "greenhouse", "oxa"),
    "revolut": ("Revolut", "https://www.revolut.com", "https://boards.greenhouse.io/revolut", "greenhouse", "revolut"),
    "monzo": ("Monzo", "https://monzo.com", "https://boards.greenhouse.io/monzo", "greenhouse", "monzo"),
    "wise": ("Wise", "https://wise.com", "https://boards.greenhouse.io/wise", "greenhouse", "wise"),
    "deliveroo": ("Deliveroo", "https://deliveroo.co.uk", "https://boards.greenhouse.io/deliveroo", "greenhouse", "deliveroo"),
    "starling": ("Starling Bank", "https://www.starlingbank.com", "https://boards.greenhouse.io/starlingbank", "greenhouse", "starlingbank"),
    "checkout": ("Checkout.com", "https://www.checkout.com", "https://boards.greenhouse.io/checkout", "greenhouse", "checkout"),
    "gocardless": ("GoCardless", "https://gocardless.com", "https://boards.greenhouse.io/gocardless", "greenhouse", "gocardless"),
    "deepmind": ("Google DeepMind", "https://deepmind.google", "https://boards.greenhouse.io/deepmind", "greenhouse", "deepmind"),
    "improbable": ("Improbable", "https://improbable.io", "https://boards.greenhouse.io/improbable", "greenhouse", "improbable"),

    # --- Greenhouse: Quant, HFT & Market Making (Amsterdam, London, Sydney) ---
    "imc": ("IMC Trading", "https://www.imc.com", "https://careers.imc.com", "greenhouse", "imc"),
    "flow traders": ("Flow Traders", "https://www.flowtraders.com", "https://www.flowtraders.com/careers", "greenhouse", "flowtraders"),
    "optiver": ("Optiver", "https://www.optiver.com", "https://boards.greenhouse.io/optiver", "greenhouse", "optiver"),
    "jumptrading": ("Jump Trading", "https://www.jumptrading.com", "https://boards.greenhouse.io/jumptrading", "greenhouse", "jumptrading"),
    "janestreet": ("Jane Street", "https://www.janestreet.com", "https://boards.greenhouse.io/janestreet", "greenhouse", "janestreet"),
    "citadel": ("Citadel", "https://www.citadel.com", "https://boards.greenhouse.io/citadel", "greenhouse", "citadel"),
    "mavensecurities": ("Maven Securities", "https://www.mavensecurities.com", "https://boards.greenhouse.io/mavensecurities", "greenhouse", "mavensecurities"),
    "sig": ("Susquehanna (SIG)", "https://sig.com", "https://boards.greenhouse.io/sig", "greenhouse", "sig"),
    "squarepoint": ("Squarepoint Capital", "https://www.squarepoint-capital.com", "https://boards.greenhouse.io/squarepointcapital", "greenhouse", "squarepointcapital"),
    "drw": ("DRW", "https://drw.com", "https://boards.greenhouse.io/drw", "greenhouse", "drw"),

    # --- Greenhouse: Autonomous Vehicles, Robotics & Motorsport ---
    "rimac": ("Rimac Technology", "https://www.rimac-technology.com", "https://boards.greenhouse.io/rimacautomobili", "greenhouse", "rimacautomobili"),
    "appliedintuition": ("Applied Intuition", "https://www.appliedintuition.com", "https://boards.greenhouse.io/appliedintuition", "greenhouse", "appliedintuition"),
    "skydio": ("Skydio", "https://www.skydio.com", "https://boards.greenhouse.io/skydio", "greenhouse", "skydio"),
    "torc": ("Torc Robotics", "https://torc.ai", "https://boards.greenhouse.io/torcrobotics", "greenhouse", "torcrobotics"),
    "redbullracing": ("Red Bull Technology / Racing", "https://www.redbullracing.com", "https://boards.greenhouse.io/redbullracing", "greenhouse", "redbullracing"),
    "mercedesf1": ("Mercedes-AMG Petronas F1 Team", "https://www.mercedesamgf1.com", "https://boards.greenhouse.io/mercedesamgpetronasf1", "greenhouse", "mercedesamgpetronasf1"),
    "mclaren": ("McLaren Racing", "https://www.mclaren.com", "https://boards.greenhouse.io/mclaren", "greenhouse", "mclaren"),
    "williamsf1": ("Williams Racing", "https://www.williamsf1.com", "https://boards.greenhouse.io/williamsracing", "greenhouse", "williamsracing"),

    # --- Lever: Global, UK & EU ---
    "mollie": ("Mollie", "https://www.mollie.com", "https://jobs.mollie.com", "lever", "mollie"),
    "palantir": ("Palantir Technologies", "https://www.palantir.com", "https://www.palantir.com/careers", "lever", "palantir"),
    "spotify": ("Spotify", "https://www.spotify.com", "https://www.lifeatspotify.com", "lever", "spotify"),
    "atlassian": ("Atlassian", "https://www.atlassian.com", "https://jobs.lever.co/atlassian", "lever", "atlassian"),
    "deepl": ("DeepL", "https://www.deepl.com", "https://jobs.lever.co/deepl", "lever", "deepl"),
    "mistral": ("Mistral AI", "https://mistral.ai", "https://jobs.lever.co/mistral", "lever", "mistral"),
    "einride": ("Einride", "https://www.einride.tech", "https://jobs.lever.co/einride", "lever", "einride"),
    "wintermute": ("Wintermute", "https://www.wintermute.com", "https://jobs.lever.co/wintermute-trading", "lever", "wintermute-trading"),
    "wetransfer": ("WeTransfer", "https://wetransfer.com", "https://jobs.lever.co/wetransfer", "lever", "wetransfer"),
    "swapfiets": ("Swapfiets", "https://swapfiets.com", "https://jobs.lever.co/swapfiets", "lever", "swapfiets"),
    "vandebron": ("Vandebron", "https://vandebron.nl", "https://jobs.lever.co/vandebron", "lever", "vandebron"),

    # --- Ashby: AI, DevTools & Modern SaaS ---
    "openai": ("OpenAI", "https://openai.com", "https://openai.com/careers", "ashby", "openai"),
    "cohere": ("Cohere", "https://cohere.com", "https://cohere.com/careers", "ashby", "cohere"),
    "perplexity": ("Perplexity AI", "https://www.perplexity.ai", "https://www.perplexity.ai/careers", "ashby", "perplexity"),
    "elevenlabs": ("ElevenLabs", "https://elevenlabs.io", "https://jobs.ashbyhq.com/elevenlabs", "ashby", "elevenlabs"),
    "notion": ("Notion", "https://www.notion.so", "https://www.notion.so/careers", "ashby", "notion"),
    "cursor": ("Cursor / Anysphere", "https://www.cursor.com", "https://www.cursor.com/careers", "ashby", "cursor"),
    "ramp": ("Ramp", "https://ramp.com", "https://ramp.com/careers", "ashby", "ramp"),
    "replit": ("Replit", "https://replit.com", "https://replit.com/careers", "ashby", "replit"),
    "sentry": ("Sentry", "https://sentry.io", "https://sentry.io/careers", "ashby", "sentry"),
    "linear": ("Linear", "https://linear.app", "https://linear.app/careers", "ashby", "linear"),
    "weaviate": ("Weaviate", "https://weaviate.io", "https://weaviate.io/company/careers", "ashby", "weaviate"),
    "qdrant": ("Qdrant", "https://qdrant.tech", "https://jobs.ashbyhq.com/qdrant", "ashby", "qdrant"),
    "langchain": ("LangChain", "https://www.langchain.com", "https://jobs.ashbyhq.com/langchain", "ashby", "langchain"),
    "posthog": ("PostHog", "https://posthog.com", "https://jobs.ashbyhq.com/posthog", "ashby", "posthog"),
    "vercel": ("Vercel", "https://vercel.com", "https://jobs.ashbyhq.com/vercel", "ashby", "vercel"),
    "supabase": ("Supabase", "https://supabase.com", "https://jobs.ashbyhq.com/supabase", "ashby", "supabase"),
    "runway": ("Runway", "https://runwayml.com", "https://jobs.ashbyhq.com/runwayml", "ashby", "runwayml"),
    "synthesia": ("Synthesia", "https://www.synthesia.io", "https://jobs.ashbyhq.com/synthesia", "ashby", "synthesia"),

    # --- Greenhouse & Lever: San Francisco & Silicon Valley Tech Leaders ---
    "waymo": ("Waymo", "https://waymo.com", "https://boards.greenhouse.io/waymo", "greenhouse", "waymo"),
    "zoox": ("Zoox (Autonomous Vehicles)", "https://zoox.com", "https://jobs.lever.co/zoox", "lever", "zoox"),
    "verkada": ("Verkada", "https://www.verkada.com", "https://boards.greenhouse.io/verkada", "greenhouse", "verkada"),
    "samsara": ("Samsara", "https://www.samsara.com", "https://boards.greenhouse.io/samsara", "greenhouse", "samsara"),
    "airbnb": ("Airbnb", "https://www.airbnb.com", "https://boards.greenhouse.io/airbnb", "greenhouse", "airbnb"),
    "pinterest": ("Pinterest", "https://www.pinterest.com", "https://boards.greenhouse.io/pinterest", "greenhouse", "pinterest"),
    "discord": ("Discord", "https://discord.com", "https://boards.greenhouse.io/discord", "greenhouse", "discord"),
    "coinbase": ("Coinbase", "https://www.coinbase.com", "https://boards.greenhouse.io/coinbase", "greenhouse", "coinbase"),
    "robinhood": ("Robinhood", "https://robinhood.com", "https://boards.greenhouse.io/robinhood", "greenhouse", "robinhood"),
    "instacart": ("Instacart", "https://www.instacart.com", "https://boards.greenhouse.io/instacart", "greenhouse", "instacart"),
    "lyft": ("Lyft", "https://www.lyft.com", "https://boards.greenhouse.io/lyft", "greenhouse", "lyft"),
    "character": ("Character.ai", "https://character.ai", "https://jobs.ashbyhq.com/character", "ashby", "character"),

    # --- Greenhouse: New York City Tech, Data & Fintech ---
    "mongodb": ("MongoDB", "https://www.mongodb.com", "https://boards.greenhouse.io/mongodb", "greenhouse", "mongodb"),
    "cockroachlabs": ("Cockroach Labs", "https://www.cockroachlabs.com", "https://boards.greenhouse.io/cockroachlabs", "greenhouse", "cockroachlabs"),
    "squarespace": ("Squarespace", "https://www.squarespace.com", "https://boards.greenhouse.io/squarespace", "greenhouse", "squarespace"),
    "flatironhealth": ("Flatiron Health", "https://flatiron.com", "https://boards.greenhouse.io/flatironhealth", "greenhouse", "flatironhealth"),
    "celonis": ("Celonis", "https://www.celonis.com", "https://boards.greenhouse.io/celonis", "greenhouse", "celonis"),
    "betterment": ("Betterment", "https://www.betterment.com", "https://boards.greenhouse.io/betterment", "greenhouse", "betterment"),
    "oscar": ("Oscar Health", "https://www.hioscar.com", "https://boards.greenhouse.io/oscar", "greenhouse", "oscar"),

    # --- Greenhouse: Los Angeles & Southern California (Aerospace, Defense AI, Gaming, AV) ---
    "spacex": ("SpaceX", "https://www.spacex.com", "https://boards.greenhouse.io/spacex", "greenhouse", "spacex"),
    "anduril": ("Anduril Industries", "https://www.anduril.com", "https://boards.greenhouse.io/andurilindustries", "greenhouse", "andurilindustries"),
    "riotgames": ("Riot Games", "https://www.riotgames.com", "https://boards.greenhouse.io/riotgames", "greenhouse", "riotgames"),
    "relativity": ("Relativity Space", "https://www.relativityspace.com", "https://boards.greenhouse.io/relativity", "greenhouse", "relativity"),
    "scopely": ("Scopely", "https://www.scopely.com", "https://boards.greenhouse.io/scopely", "greenhouse", "scopely"),
    "motional": ("Motional (Autonomous Vehicles)", "https://motional.com", "https://boards.greenhouse.io/motional", "greenhouse", "motional"),

    # --- Recruitee ---
    "bunq": ("bunq", "https://www.bunq.com", "https://www.bunq.com/jobs", "recruitee", "bunq"),
    "channable": ("Channable", "https://www.channable.com", "https://www.channable.com/careers", "recruitee", "channable"),
    "channelengine": ("ChannelEngine", "https://www.channelengine.com", "https://www.channelengine.com/careers", "recruitee", "channelengine"),
    "da vinci": ("Da Vinci Derivatives", "https://davinciderivatives.com", "https://davinciderivatives.com/careers", "recruitee", "davinci-derivatives"),
    "helloprint": ("HelloPrint", "https://www.helloprint.com", "https://jobs.helloprint.com", "recruitee", "helloprint"),
    "fairphone": ("Fairphone", "https://www.fairphone.com", "https://fairphone.recruitee.com", "recruitee", "fairphone"),

    # --- Personio ---
    "pair finance": ("PAIR Finance", "https://www.pairfinance.com", "https://www.pairfinance.com/careers", "personio", "pair"),
    "lepaya": ("Lepaya", "https://www.lepaya.com", "https://www.lepaya.com/careers", "personio", "lepaya"),
    "personio": ("Personio", "https://www.personio.com", "https://www.personio.com/careers", "personio", "personio"),
    "embotech": ("Embotech", "https://www.embotech.com", "https://embotech.jobs.personio.de", "personio", "embotech"),

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

