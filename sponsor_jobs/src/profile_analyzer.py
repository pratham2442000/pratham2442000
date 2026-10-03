#!/usr/bin/env python3
"""
profile_analyzer.py - Analyzes scraped jobs and scores match quality against
Pratham Johari's profile (aboutme.md, cv.tex), generating tailored rationale and
cover letter recommendations with Netherlands, UK, Australia, EU, and Remote target locations.
Strictly excludes senior/staff/principal/lead/management roles and strongly prioritizes
Python, AI/ML, Compound AI/RAG, Computer Vision/Perception, and MLOps.
"""

import os
import re
import json
import time
import sqlite3
import logging
from typing import Dict, Any, List, Tuple, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sponsors.db"))
OUTPUT_MD_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "recommended_jobs.md"))
OUTPUT_JSON_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "recommended_jobs.json"))

# Explicit Non-Target locations (filtered out unless remote or in accepted US target hubs)
NON_TARGET_PATTERNS = [
    r"\b(united\s+states|usa)\b", r"\b(u\.s\b|us\b|u\.s\.)",
    r"\bindia\b", r"\bjapan\b", r"\bkorea\b",
    r"\bcanada\b", r"\bmexico\b", r"\bbrazil\b", r"\bsingapore\b",
    r"\bchina\b", r"\bwashington\b", r"\btexas\b",
    r"\bvirginia\b", r"\bmaryland\b", r"\bcolorado\b", r"\boregon\b",
    r"\b(bengaluru|bangalore|hyderabad|pune|delhi|noida|gurgaon|gurugram|chennai|mumbai)\b",
    r"\b(ann\s+arbor|chicago|blacksburg|fort\s+worth|austin|seattle)\b",
    r"\bdelaware\b", r"\bpennsylvania\b", r"\btokyo\b", r"\bseoul\b",
    r"\bserbia\b", r"\bbelgrade\b"
]

# High-priority US tech hubs: New York, San Francisco (Bay Area), Los Angeles
US_TARGET_PATTERNS = [
    # New York City & Metro
    r"\bnew\s+york\b", r"\bnyc\b", r"\bny\b", r"\bmanhattan\b", r"\bbrooklyn\b", r"\bnew\s+york\s+city\b",
    # San Francisco & Bay Area / Silicon Valley
    r"\bsan\s+francisco\b", r"\bsf\b", r"\bbay\s+area\b", r"\bsilicon\s+valley\b",
    r"\bmountain\s+view\b", r"\bpalo\s+alto\b", r"\bsunnyvale\b", r"\bsan\s+jose\b",
    r"\bmenlo\s+park\b", r"\boakland\b", r"\bberkeley\b", r"\bsan\s+mateo\b", r"\bredwood\s+city\b",
    r"\bsanta\s+clara\b", r"\bfoster\s+city\b",
    # Los Angeles & Southern California
    r"\blos\s+angeles\b", r"\bla\b", r"\bsanta\s+monica\b", r"\bculver\s+city\b",
    r"\bpasadena\b", r"\birvine\b", r"\blong\s+beach\b", r"\bel\s+segundo\b",
    r"\bhawthorne\b", r"\bcosta\s+mesa\b"
]

# Accepted target locations: Netherlands, UK, Australia, US (NYC, SF, LA), European Union, and Remote
TARGET_LOCATION_KEYWORDS = [
    # Netherlands
    r"\bnetherlands\b", r"\bamsterdam\b", r"\bdelft\b", r"\beindhoven\b",
    r"\brotterdam\b", r"\butrecht\b", r"\bthe\s+hague\b", r"\bden\s+haag\b",
    r"\bleiden\b", r"\bgroningen\b", r"\benschede\b", r"\bbrabant\b", r"\bholland\b",
    # United Kingdom
    r"\bunited\s+kingdom\b", r"\buk\b", r"\blondon\b", r"\bcambridge\b", r"\boxford\b",
    r"\bmanchester\b", r"\bedinburgh\b", r"\bbristol\b", r"\bbirmingham\b", r"\bleeds\b",
    r"\bglasgow\b", r"\bengland\b", r"\bscotland\b", r"\bwales\b",
    # Australia
    r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b", r"\bbrisbane\b", r"\bperth\b",
    r"\badelaide\b", r"\bcanberra\b", r"\bnsw\b", r"\bvictoria\b", r"\bqueensland\b",
    # United States: New York, San Francisco (Bay Area), Los Angeles
    *US_TARGET_PATTERNS,
    r"\bcalifornia\b", r"\bca\b",
    # Europe & Remote
    r"\beurope\b", r"\beu\b", r"\bemea\b", r"\bgermany\b", r"\bberlin\b", r"\bmunich\b",
    r"\bfrance\b", r"\bparis\b", r"\bspain\b", r"\bmadrid\b", r"\bbarcelona\b",
    r"\bireland\b", r"\bdublin\b", r"\bsweden\b", r"\bstockholm\b", r"\bdenmark\b",
    r"\bcopenhagen\b", r"\bbelgium\b", r"\bbrussels\b", r"\bitaly\b", r"\bmilan\b",
    r"\baustria\b", r"\bvienna\b", r"\bswitzerland\b", r"\bzurich\b",
    r"\bpoland\b", r"\bwarsaw\b", r"\bportugal\b", r"\blisbon\b", r"\bfinland\b",
    r"\bnorway\b", r"\bremote\b"
]

# Strict senior role filter pattern - user requested strictly NO senior roles
SENIOR_ROLE_PATTERN = re.compile(
    r"\b(senior|sr\.?|sr\s+|lead|principal|staff|director|head\s+of|vp|vice\s+president|chief|manager|management|architect|distinguished|founding\s+engineer)\b",
    re.IGNORECASE
)

ROLE_WEIGHTS = {
    r"\b(python\s+(engineer|developer|specialist|backend|programmer))\b": 46,
    r"\b(machine\s+learning|ml)\s+engineer\b": 45,
    r"\bai\s+engineer\b": 45,
    r"\bai\s+platform\s+engineer\b": 45,
    r"\bperception\s+engineer\b": 45,
    r"\bcomputer\s+vision\b": 42,
    r"\bautonomous\s+(driving|systems|vehicle|navigation)\b": 45,
    r"\bmlops\b": 42,
    r"\bdeep\s+learning\b": 42,
    r"\brobotics\s+(software|engineer)\b": 42,
    r"\bresearch\s+engineer\b": 40,
    r"\bapplied\s+(ai|ml)\b": 42,
    r"\bdata\s+scientist\b": 35,
    r"\bbackend\s+(engineer|developer)\b": 32,
    r"\bsoftware\s+engineer\b": 30,
    r"\bsoftware\s+developer\b": 30
}

PENALTY_PATTERNS = {
    r"\b(frontend|front-end|react\s+native|ios|android|swift|flutter)\b": -25,
    r"\b(sales|marketing|recruiter|hr|talent|accountant|legal|counsel)\b": -50,
    r"\b(intern|internship|trainee|working\s+student|junior|graduate|entry\s+level|associate)\b": 20
}

SKILL_PATTERNS = {
    "Python Mastery": (r"\b(python|python3|fastapi|flask|django|asyncio|pydantic|pytest|celery)\b", 18),
    "RAG / Compound AI / LLM": (r"\b(rag|retrieval|llm|generative\s+ai|langchain|langgraph|transformers|colbert|colpali|vllm|faiss|context\s+retrieval|bm25)\b", 16),
    "Perception / LIDAR / ROS": (r"\b(ros|ros2|lidar|point\s+cloud|yolo|sensor\s+fusion|opencv|perception|pointcloud)\b", 16),
    "PyTorch / Deep Learning": (r"\b(pytorch|tensorflow|deep\s+learning|model\s+training|deep\s+neural|weights\s*&\s*biases|w&b|onnx)\b", 14),
    "MLOps / Kubernetes / Infra": (r"\b(docker|kubernetes|k8s|helm|ci/cd|slurm|hpc|prometheus|grafana|observability)\b", 14),
    "C++ / High Performance": (r"\b(c\+\+|embedded|low\s+latency|concurrency)\b", 10),
    "Linux / Homelab / Systems": (r"\b(linux|bash|tailscale|networking|cloud\s+sql|microservices)\b", 10)
}


def is_senior_role(title: str) -> bool:
    """Determine whether a job title denotes a senior, staff, lead, or leadership position."""
    if not title:
        return False
    return bool(SENIOR_ROLE_PATTERN.search(title))


def is_target_location(location: str) -> bool:
    """Check whether a location is within Netherlands, UK, Australia, EU, Target US hubs (NYC, SF, LA), or Remote."""
    if not location or location.strip() == "":
        return True
        
    loc = location.lower().strip()
    
    # Check if explicitly in one of our US target hubs (NYC, SF, LA)
    if any(re.search(pat, loc) for pat in US_TARGET_PATTERNS):
        return True

    has_non_target = any(re.search(pat, loc) for pat in NON_TARGET_PATTERNS)
    has_target = any(re.search(pat, loc) for pat in TARGET_LOCATION_KEYWORDS)
    
    if has_non_target:
        # If a non-target token (e.g. India, USA generic, Singapore) is present, only accept if
        # a primary target region (NL, UK, Australia, EU, EMEA, Worldwide, or our US hubs) is explicitly named.
        is_explicit_target = any(re.search(pat, loc) for pat in [
            r"\bnetherlands\b", r"\bamsterdam\b", r"\bdelft\b", r"\beindhoven\b",
            r"\bunited\s+kingdom\b", r"\buk\b", r"\blondon\b",
            r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b",
            r"\beurope\b", r"\beu\b", r"\bemea\b", r"\bworldwide\b"
        ] + US_TARGET_PATTERNS)
        return is_explicit_target
        
    return has_target


# Alias for backward compatibility
is_eu_location = is_target_location


def get_location_category(location: str) -> str:
    """Classify location into primary display regions."""
    loc = (location or "").lower().strip()
    if any(re.search(pat, loc) for pat in [r"\bnetherlands\b", r"\bamsterdam\b", r"\bdelft\b", r"\beindhoven\b", r"\brotterdam\b", r"\butrecht\b", r"\bthe\s+hague\b", r"\bden\s+haag\b", r"\bholland\b"]):
        return "Netherlands"
    if any(re.search(pat, loc) for pat in [r"\bunited\s+kingdom\b", r"\buk\b", r"\blondon\b", r"\bcambridge\b", r"\boxford\b", r"\bmanchester\b", r"\bedinburgh\b", r"\bbristol\b", r"\bengland\b", r"\bscotland\b"]):
        return "United Kingdom"
    if any(re.search(pat, loc) for pat in [r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b", r"\bbrisbane\b", r"\bperth\b", r"\badelaide\b", r"\bcanberra\b"]):
        return "Australia"
    if any(re.search(pat, loc) for pat in [r"\bnew\s+york\b", r"\bnyc\b", r"\bmanhattan\b", r"\bbrooklyn\b", r"\bnew\s+york\s+city\b"]):
        return "New York"
    if any(re.search(pat, loc) for pat in [r"\bsan\s+francisco\b", r"\bsf\b", r"\bbay\s+area\b", r"\bsilicon\s+valley\b", r"\bmountain\s+view\b", r"\bpalo\s+alto\b", r"\bsunnyvale\b", r"\bsan\s+jose\b", r"\bmenlo\s+park\b", r"\boakland\b", r"\bberkeley\b", r"\bsan\s+mateo\b", r"\bredwood\s+city\b", r"\bsanta\s+clara\b", r"\bfoster\s+city\b"]):
        return "San Francisco"
    if any(re.search(pat, loc) for pat in [r"\blos\s+angeles\b", r"\bla\b", r"\bsanta\s+monica\b", r"\bculver\s+city\b", r"\bpasadena\b", r"\birvine\b", r"\blong\s+beach\b", r"\bel\s+segundo\b", r"\bhawthorne\b", r"\bcosta\s+mesa\b"]):
        return "Los Angeles"
    if any(re.search(pat, loc) for pat in [r"\bunited\s+states\b", r"\busa\b", r"\bu\.s\.", r"\bcalifornia\b"]):
        return "United States"
    if "remote" in loc:
        return "Remote"
    return "Europe (Other)"


def score_job(title: str, location: str, description: str = "", allow_senior: bool = False) -> Tuple[float, List[str], str]:
    """Calculate match score (0-100), reasoning tags, and recommended letter body."""
    # Strict exclusion: Senior roles receive score 0 unless allowed for manual entries
    if not allow_senior and is_senior_role(title):
        return 0.0, ["Senior/Leadership role excluded"], "EXCLUDED (Senior)"

    text = f"{title} {description}".lower()
    loc_lower = location.lower()
    score = 15.0
    reasons = []

    # Location scoring
    region = get_location_category(location)
    if region == "Netherlands":
        score += 25
        reasons.append("Netherlands Priority (+25 pts)")
    elif region == "United Kingdom":
        score += 20
        reasons.append("United Kingdom Target (+20 pts)")
    elif region == "Australia":
        score += 20
        reasons.append("Australia Target (+20 pts)")
    elif region == "New York":
        score += 20
        reasons.append("New York Target (+20 pts)")
    elif region == "San Francisco":
        score += 20
        reasons.append("San Francisco Target (+20 pts)")
    elif region == "Los Angeles":
        score += 20
        reasons.append("Los Angeles Target (+20 pts)")
    elif region == "United States":
        score += 18
        reasons.append("United States Target (+18 pts)")
    elif "remote" in loc_lower or "europe" in loc_lower:
        score += 15
        reasons.append("EU / Remote (+15 pts)")

    # Python role bonus
    if re.search(r"\b(python\s+(engineer|developer|specialist|backend|programmer))\b", text):
        score += 46
        reasons.append("Python Specialist Target (+46 pts)")
    else:
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

    # Penalties and bonuses
    for pat, penalty in PENALTY_PATTERNS.items():
        if re.search(pat, text):
            score += penalty
            if penalty > 0:
                reasons.append(f"Graduate/Entry friendly (+{penalty} pts)")
            else:
                reasons.append(f"Domain mismatch ({penalty} pts)")

    # Technical Skills matching (CV highlights)
    skills_found = []
    for skill_name, (pat, weight) in SKILL_PATTERNS.items():
        if re.search(pat, text):
            score += weight
            if skill_name == "Python Mastery":
                skills_found.append("🐍 Python Mastery")
            else:
                skills_found.append(skill_name)
                
    if skills_found:
        reasons.append(f"Skills: {', '.join(skills_found)}")

    score = max(5.0, min(99.0, score))

    # Determine recommended cover letter body
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
    elif re.search(r"\b(software\s+engineer|backend|core|systems\s+engineer|python\s+developer|python\s+engineer)\b", text):
        recommended_letter = "5. SOFTWARE ENGINEER (Backend/Core)"
    elif re.search(r"\b(data\s+scientist|analytics|data\s+analyst)\b", text):
        recommended_letter = "4. DATA SCIENTIST"
    elif re.search(r"\b(machine\s+learning|ml\s+engineer|deep\s+learning)\b", text):
        recommended_letter = "3. MACHINE LEARNING ENGINEER"
    elif re.search(r"\b(research|phd|scientist|nlp|rag|colbert|colpali|retrieval)\b", text):
        recommended_letter = "2. AI & ML RESEARCHER"

    return round(score, 1), reasons, recommended_letter


# ============================================================
# COMPREHENSIVE KEYWORD TAXONOMY & EXTRACTION ENGINE
# ============================================================

KEYWORD_TAXONOMY: Dict[str, List[Tuple[str, str]]] = {
    "Languages": [
        ("Python", r"\b(python|python3)\b"),
        ("SQL", r"\b(sql|postgresql|postgres|mysql|sqlite|t-sql|pl/sql)\b"),
        ("C++", r"(?:\bc\+\+(?!\+)|\bcpp\b)"),
        ("C", r"(?<!\w)[Cc](?!\w|\+|\#)"),
        ("Java", r"\bjava\b"),
        ("Go / Golang", r"\b(golang|(?<!\w)go(?!\w))\b"),
        ("Rust", r"\brust\b"),
        ("TypeScript", r"\b(typescript|ts)\b"),
        ("JavaScript", r"\b(javascript|js|node\.?js)\b"),
        ("Bash / Shell", r"\b(bash|shell|sh|zsh)\b"),
        ("R", r"(?<!\w)[Rr](?!\w)"),
        ("Scala", r"\bscala\b"),
    ],
    "AI & Machine Learning": [
        ("PyTorch", r"\bpytorch\b"),
        ("TensorFlow", r"\b(tensorflow|tf)\b"),
        ("Scikit-learn", r"\b(scikit-learn|sklearn)\b"),
        ("Pandas", r"\bpandas\b"),
        ("NumPy", r"\bnumpy\b"),
        ("SciPy", r"\bscipy\b"),
        ("Keras", r"\bkeras\b"),
        ("JAX", r"\bjax\b"),
        ("ONNX", r"\bonnx\b"),
        ("XGBoost", r"\bxgboost\b"),
        ("LightGBM", r"\blightgbm\b"),
        ("Weights & Biases", r"\b(weights\s*&\s*biases|w&b|wandb)\b"),
        ("Deep Learning", r"\bdeep\s+learning\b"),
        ("Neural Networks", r"\b(neural\s+networks?|deep\s+neural)\b"),
        ("Model Training & Evaluation", r"\b(model\s+training|model\s+evaluation|ablation|cross-validation)\b"),
        ("NLP", r"\b(nlp|natural\s+language\s+processing)\b"),
    ],
    "GenAI, LLMs & RAG": [
        ("RAG", r"\b(rag|retrieval-augmented|retrieval\s+augmented)\b"),
        ("LLMs", r"\b(llms?|large\s+language\s+models?)\b"),
        ("LangChain", r"\blangchain\b"),
        ("LangGraph", r"\blanggraph\b"),
        ("LlamaIndex", r"\bllamaindex\b"),
        ("Transformers", r"\b(transformers|hugging\s*face|huggingface)\b"),
        ("Vector Databases", r"\b(vector\s*dbs?|vector\s*databases?|vector\s*search)\b"),
        ("FAISS", r"\bfaiss\b"),
        ("Qdrant / Chroma", r"\b(qdrant|chroma|chromadb|milvus|pinecone|weaviate)\b"),
        ("ColPali / ColBERT", r"\b(colpali|colbert|pyterrier)\b"),
        ("BM25 / Sparse Retrieval", r"\b(bm25|sparse\s+retrieval|lexical\s+search)\b"),
        ("vLLM", r"\bvllm\b"),
        ("Embeddings", r"\b(embeddings?|sentence-transformers?|cross-encoders?|reranking|reranker)\b"),
        ("Fine-tuning", r"\b(fine-tuning|finetuning|lora|qlora|peft)\b"),
        ("Prompt Engineering", r"\bprompt\s+engineering\b"),
        ("Semantic Search", r"\bsemantic\s+search\b"),
        ("Compound AI", r"\bcompound\s+ai\b"),
    ],
    "Data Engineering": [
        ("PostgreSQL", r"\b(postgresql|postgres)\b"),
        ("Snowflake", r"\bsnowflake\b"),
        ("BigQuery", r"\bbigquery\b"),
        ("ClickHouse", r"\bclickhouse\b"),
        ("Apache Spark / PySpark", r"\b(spark|pyspark|apache\s+spark)\b"),
        ("Databricks", r"\bdatabricks\b"),
        ("Apache Kafka", r"\b(kafka|apache\s+kafka)\b"),
        ("Apache Airflow", r"\b(airflow|apache\s+airflow)\b"),
        ("dbt", r"\b(?<!\w)dbt(?!\w)\b"),
        ("ETL / ELT", r"\b(etl|elt|data\s+pipeline|data\s+ingestion)\b"),
        ("Redis", r"\bredis\b"),
        ("NoSQL / MongoDB", r"\b(nosql|mongodb)\b"),
        ("Data Warehousing", r"\b(data\s+warehous\w+|data\s+lake|lakehouse)\b"),
    ],
    "Cloud, MLOps & Infra": [
        ("Docker", r"\b(docker|containerization|containers?)\b"),
        ("Kubernetes", r"\b(kubernetes|k8s)\b"),
        ("Helm", r"\bhelm\b"),
        ("CI/CD", r"(?:\bci/cd\b|\bci\s*-\s*cd\b|\bgithub\s+actions\b|\bgitlab\s+ci\b)"),
        ("AWS", r"\b(aws|amazon\s+web\s+services|s3|ec2|ecs|eks|sagemaker)\b"),
        ("GCP", r"\b(gcp|google\s+cloud|vertex\s+ai|cloud\s+run|gke)\b"),
        ("Azure", r"\b(azure|azure\s+ml|aks)\b"),
        ("Linux", r"\b(linux|unix|ubuntu|debian|homelab)\b"),
        ("Terraform", r"\bterraform\b"),
        ("Prometheus & Grafana", r"\b(prometheus|grafana|observability|monitoring)\b"),
        ("SLURM / HPC", r"\b(slurm|hpc|cluster\s+computing)\b"),
        ("DVC", r"\bdvc\b"),
        ("MLflow", r"\bmlflow\b"),
        ("Ray", r"(?<!\w)ray(?!\w)"),
        ("Triton", r"\btriton\b"),
    ],
    "Perception & Robotics": [
        ("OpenCV", r"\bopencv\b"),
        ("YOLO", r"\b(yolo|yolov\w*)\b"),
        ("ROS / ROS2", r"\b(ros|ros2|robot\s+operating\s+system)\b"),
        ("LIDAR & Point Clouds", r"\b(lidar|point\s*clouds?|pointcloud)\b"),
        ("Computer Vision", r"\b(computer\s+vision|object\s+detection|segmentation|pose\s+estimation)\b"),
        ("Sensor Fusion", r"\b(sensor\s+fusion|kalman\s+filter)\b"),
        ("Autonomous Systems", r"\b(autonomous\s+(driving|vehicles?|navigation|systems?)|slam)\b"),
        ("MMPose / MMAction", r"\b(mmpose|mmaction\w*|mmdetection)\b"),
    ],
    "Software & Architecture": [
        ("FastAPI", r"\bfastapi\b"),
        ("Flask / Django", r"\b(flask|django)\b"),
        ("REST APIs", r"\b(rest|restful|apis?|endpoints?)\b"),
        ("Microservices", r"\bmicroservices\b"),
        ("AsyncIO", r"\b(asyncio|asynchronous|async/await|concurrency)\b"),
        ("Git", r"\b(git|github|gitlab)\b"),
        ("Unit Testing", r"\b(unit\s+testing|pytest|tdd|test-driven)\b"),
        ("Agile / Scrum", r"\b(agile|scrum|kanban)\b"),
        ("Distributed Systems", r"\b(distributed\s+systems?|high\s+throughput|low\s+latency|scalab\w+)\b"),
    ],
    "Qualifications & Seniority": [
        ("Master's / MSc", r"\b(master'?s?|msc|m\.sc)\b"),
        ("Bachelor's / BSc", r"\b(bachelor'?s?|bsc|b\.sc)\b"),
        ("PhD", r"\b(phd|doctorate)\b"),
        ("0-2 / 1-3 Years Exp", r"\b(0-2\s+years?|1-3\s+years?|entry\s+level|junior|graduate|intern\w*)\b"),
        ("English", r"\b(fluent\s+in\s+english|english\s+proficiency|working\s+language\s+is\s+english|english)\b"),
        ("Hybrid / Remote", r"\b(hybrid|remote|work\s+from\s+home)\b"),
        ("Visa / Sponsorship", r"\b(visa\s+sponsorship|relocation|sponsor\w*|kennismigrant|ind)\b"),
    ]
}


def extract_job_keywords(text: str, title: str = "", location: str = "") -> Dict[str, Any]:
    """Extract categorized keywords, skills, metadata, match score, and recommended letter from full JD text."""
    if not text:
        text = ""

    # Metadata extraction
    detected_title = title or ""
    detected_company = ""
    detected_location = location or ""
    seniority_warning = None
    exp_years = None

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # 1. Detect explicit labels
    m_title = re.search(r"(?:job\s+title|role|position)\s*:\s*([^\n\r]+)", text, re.I)
    if m_title and not detected_title:
        detected_title = m_title.group(1).strip()

    m_comp = re.search(r"(?:company|employer|organisation|organization)\s*:\s*([^\n\r]+)", text, re.I)
    if m_comp:
        detected_company = m_comp.group(1).strip()

    m_loc = re.search(r"(?:location|city|office)\s*:\s*([^\n\r]+)", text, re.I)
    if m_loc and not detected_location:
        detected_location = m_loc.group(1).strip()

    # 2. Detect LinkedIn or header formats if lines exist
    if lines:
        # Check LinkedIn "Company · Location · time" format on line 1
        if len(lines) > 1 and ("·" in lines[1] or "•" in lines[1]):
            if not detected_title:
                detected_title = lines[0]
            parts = [p.strip() for p in re.split(r"[·•]", lines[1])]
            if parts and not detected_company:
                detected_company = parts[0]
            if len(parts) > 1 and not detected_location:
                detected_location = parts[1]
        elif not detected_title and any(w in lines[0].lower() for w in ["engineer", "developer", "scientist", "specialist", "intern", "researcher", "analyst"]):
            detected_title = lines[0]

    # Fallback company extraction (e.g. "At Booking.com, we..." or "About Uber")
    if not detected_company:
        m_at = re.search(r"(?:about|at)\s+([A-Z][A-Za-z0-9\s&]{2,25})[,.\s]+(?:we|is|are)", text)
        if m_at:
            detected_company = m_at.group(1).strip()

    # Fallback location detection
    if not detected_location:
        for pat in [
            r"\bamsterdam\b", r"\bdelft\b", r"\beindhoven\b", r"\brotterdam\b", r"\butrecht\b",
            r"\bthe\s+hague\b", r"\bnetherlands\b", r"\blondon\b", r"\bunited\s+kingdom\b",
            r"\bsydney\b", r"\bmelbourne\b", r"\baustralia\b",
            r"\bnew\s+york\b", r"\bsan\s+francisco\b", r"\blos\s+angeles\b", r"\bcalifornia\b",
            r"\bremote\b"
        ]:
            if re.search(pat, text, re.I):
                detected_location = pat.replace(r"\b", "").replace(r"\s+", " ").title()
                break

    # 3. Detect Seniority / Experience indicators
    m_exp = re.search(r"\b(\d+\s*[-+to]+\s*\d+|\d+\+?)\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp)?\b", text, re.I)
    if m_exp:
        exp_years = m_exp.group(0).strip()
        if re.search(r"\b([4-9]|1\d)\+?\s*(?:years?|yrs?)\b", exp_years, re.I):
            seniority_warning = f"Notice: Mentions '{exp_years}'. May require senior experience."

    if not seniority_warning and re.search(r"\b(senior|lead|principal|staff|director|head of)\b", detected_title or text[:300], re.I):
        seniority_warning = "Notice: Mentions Senior/Lead designation."

    # 4. Keyword extraction by category
    categorized = {}
    all_keywords = []
    seen = set()

    for category, pattern_list in KEYWORD_TAXONOMY.items():
        matched = []
        for name, pattern in pattern_list:
            if re.search(pattern, text, re.I):
                matched.append(name)
                if name not in seen:
                    seen.add(name)
                    all_keywords.append(name)
        if matched:
            categorized[category] = matched

    # 5. Profile Match Scoring & Recommended Letter
    eval_title = detected_title or "Software / Machine Learning Engineer"
    eval_loc = detected_location or "Amsterdam, Netherlands"
    score, reasons, rec_letter = score_job(eval_title, eval_loc, text, allow_senior=True)

    # Top technical notes string (exclude soft qualifications)
    tech_keywords = [
        kw for kw in all_keywords
        if kw not in ["English", "Hybrid / Remote", "Visa / Sponsorship", "0-2 / 1-3 Years Exp", "Bachelor's / BSc", "Master's / MSc", "PhD"]
    ]
    top_notes = ", ".join(tech_keywords[:10])

    return {
        "total_count": len(all_keywords),
        "all_keywords": all_keywords,
        "categorized": categorized,
        "detected_metadata": {
            "title": detected_title,
            "company": detected_company,
            "location": detected_location,
            "seniority_warning": seniority_warning,
            "experience_years": exp_years
        },
        "match_score": score,
        "match_reasons": reasons,
        "recommended_letter": rec_letter,
        "top_notes": top_notes
    }


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
    elif st in ("uninterested", "unintrested"):
        return "🚫 Uninterested"
    elif st == "rejected":
        return "❌ Rejected"
    return "⬜ Not Applied"


def mark_job_status(job_id: int, status: str = "applied", notes: Optional[str] = None, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Update application status of a job in SQLite and refresh markdown reports."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
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
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
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


def detect_ats_platform(source: str = "", url: str = "", ats_type: Optional[str] = None) -> str:
    """Classify ATS platform (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, etc.) from source, url, and sponsor metadata."""
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
    if "arbeitnow" in src or "arbeitnow.com" in u or "arbeitnow.co.uk" in u:
        return "Arbeitnow"
    if "linkedin" in src or "linkedin.com" in u:
        return "LinkedIn"
    if "indeed" in src or "indeed.com" in u:
        return "Indeed"
    return "Direct Portal"


def add_custom_job(
    company_name: str,
    title: str,
    url: Optional[str] = None,
    location: Optional[str] = "Amsterdam, Netherlands",
    description: Optional[str] = "",
    status: str = "unapplied",
    notes: Optional[str] = None,
    source: str = "LinkedIn / Manual",
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """Manually insert an external or LinkedIn job into SQLite, score it, and update recommendation lists."""
    company_name = (company_name or "").strip()
    title = (title or "").strip()
    if not company_name or not title:
        raise ValueError("Company name and Job Title are required.")

    location_str = (location or "Amsterdam, Netherlands").strip()
    url_str = (url or "").strip()
    if not url_str:
        clean_comp = re.sub(r"[^a-zA-Z0-9]+", "-", company_name.lower()).strip("-")
        clean_tit = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
        url_str = f"https://linkedin.com/jobs/custom/{clean_comp}-{clean_tit}-{int(time.time())}"

    # 1. Sponsor Matching against IND register
    sponsor_id = None
    kvk = "External / Manual"
    ats_type = None
    try:
        from src.sponsor_matcher import SponsorMatcher
        matcher = SponsorMatcher(db_path)
        m = matcher.match(company_name)
        if m:
            sponsor_id = m["id"]
            kvk = m.get("kvk") or "IND Recognised Sponsor"
            ats_type = m.get("ats_type")
    except Exception as e:
        logging.warning(f"Could not check sponsor matcher: {e}")

    # 2. Extract keywords from description if provided and auto-populate notes
    desc_clean = (description or "").strip()
    if desc_clean and not notes:
        try:
            kw_data = extract_job_keywords(desc_clean, title, location_str)
            if kw_data.get("top_notes"):
                notes = kw_data["top_notes"]
        except Exception as e:
            logging.warning(f"Error auto-extracting keywords for custom job: {e}")

    # 3. Score job against profile (allow_senior=True for manual inputs)
    score, reasons, rec_letter = score_job(title, location_str, desc_clean or notes or "", allow_senior=True)
    reason_str = " | ".join(reasons)

    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    cur = conn.cursor()

    is_applied = 1 if status.lower() in ("applied", "interviewing", "offered") else 0
    now_str = None
    if is_applied:
        cur.execute("SELECT datetime('now', 'localtime')")
        now_str = cur.fetchone()[0]

    # Check if URL already exists
    cur.execute("SELECT id, sponsor_id FROM jobs WHERE url = ?", (url_str,))
    existing = cur.fetchone()

    if existing:
        job_id = existing[0]
        if not sponsor_id and existing[1]:
            sponsor_id = existing[1]
    if sponsor_id and not ats_type:
        try:
            cur.execute("SELECT ats_type FROM sponsors WHERE id = ?", (sponsor_id,))
            s_row = cur.fetchone()
            if s_row and s_row[0]:
                ats_type = s_row[0]
        except Exception:
            pass

    if existing:
        job_id = existing[0]
        cur.execute("""
        UPDATE jobs
        SET company_name = ?,
            title = ?,
            location = ?,
            description = CASE WHEN ? != '' THEN ? ELSE description END,
            sponsor_id = COALESCE(?, sponsor_id),
            source = ?,
            match_score = ?,
            match_reason = ?,
            recommended_letter = ?,
            status = ?,
            applied = ?,
            applied_at = COALESCE(?, applied_at),
            notes = COALESCE(?, notes),
            is_active = 1,
            is_new = 1,
            last_seen = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (company_name, title, location_str, desc_clean, desc_clean,
              sponsor_id, source, score, reason_str, rec_letter,
              status.lower(), is_applied, now_str, notes, job_id))
    else:
        cur.execute("""
        INSERT INTO jobs (
            sponsor_id, company_name, title, location, url, description,
            source, match_score, match_reason, recommended_letter,
            is_active, applied, applied_at, status, notes, is_new, is_senior,
            first_seen, last_seen
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            1, ?, ?, ?, ?, 1, 0,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        """, (
            sponsor_id, company_name, title, location_str, url_str, desc_clean,
            source, score, reason_str, rec_letter,
            is_applied, now_str, status.lower(), notes
        ))
        job_id = cur.lastrowid

    conn.commit()
    conn.close()

    # Re-analyze all jobs and update reports/json
    analyze_all_jobs(db_path)

    ats_platform = detect_ats_platform(source, url_str, ats_type)
    return {
        "id": job_id,
        "company": company_name,
        "title": title,
        "location": location_str,
        "url": url_str,
        "score": score,
        "reasons": reasons,
        "recommended_letter": rec_letter,
        "status": status.lower(),
        "applied": is_applied,
        "is_sponsor": bool(sponsor_id),
        "kvk": kvk,
        "source": source,
        "ats_platform": ats_platform
    }


def analyze_all_jobs(db_path: str = DB_PATH) -> int:
    """Score all active non-senior jobs in SQLite and generate recommendation reports."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    cur = conn.cursor()
    
    cur.execute("""
    SELECT j.id, j.company_name, j.title, j.location, j.url, j.description, s.kvk,
           j.applied, j.applied_at, j.status, j.notes, j.is_new, j.first_seen, j.source,
           s.ats_type
    FROM jobs j
    LEFT JOIN sponsors s ON j.sponsor_id = s.id
    """)
    rows = cur.fetchall()
    
    analyzed_jobs = []
    
    for job_id, company, title, loc, url, desc, kvk, applied, applied_at, status, notes, is_new, first_seen, source, ats_type in rows:
        location_str = loc or "Netherlands"
        is_manual = bool(source and any(k in source.lower() for k in ("manual", "linkedin", "custom", "external")))
        
        # 1. Filter out non-target locations for scraper jobs
        if not is_manual and not is_target_location(location_str):
            cur.execute("UPDATE jobs SET match_score = 0, is_active = 0 WHERE id = ?", (job_id,))
            continue
            
        # 2. Strict Filter: Exclude Senior / Leadership / Principal / Staff roles for scraper jobs
        if not is_manual and is_senior_role(title):
            cur.execute("UPDATE jobs SET match_score = 0, is_active = 0, is_senior = 1 WHERE id = ?", (job_id,))
            continue
            
        score, reasons, rec_letter = score_job(title, location_str, desc or "", allow_senior=is_manual)
        reason_str = " | ".join(reasons)
        region = get_location_category(location_str)
        ats_platform = detect_ats_platform(source, url, ats_type)
        
        cur.execute("""
        UPDATE jobs
        SET match_score = ?,
            match_reason = ?,
            recommended_letter = ?,
            is_active = 1,
            is_senior = ?
        WHERE id = ?
        """, (score, reason_str, rec_letter, 1 if is_senior_role(title) else 0, job_id))
        
        analyzed_jobs.append({
            "id": job_id,
            "company": company,
            "kvk": kvk or ("IND Recognised Sponsor" if is_manual else "Target Sponsor"),
            "title": title,
            "location": location_str,
            "region": region,
            "url": url,
            "score": score,
            "reasons": reasons,
            "recommended_letter": rec_letter,
            "applied": applied or 0,
            "applied_at": applied_at,
            "status": status or "unapplied",
            "notes": notes or "",
            "is_new": 1 if is_new else 0,
            "first_seen": first_seen or "",
            "source": source or "Scraper",
            "ats_platform": ats_platform
        })
        
    conn.commit()
    conn.close()
    
    analyzed_jobs.sort(key=lambda x: x["score"], reverse=True)
    generate_markdown_report(analyzed_jobs, OUTPUT_MD_PATH)
    
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(analyzed_jobs, f, indent=2)
        
    logging.info(f"Analyzed {len(analyzed_jobs)} active non-senior jobs across NL, UK, AU, US (NYC/SF/LA), and EU. Saved to {OUTPUT_MD_PATH}")
    return len(analyzed_jobs)


def generate_markdown_report(jobs: List[Dict[str, Any]], output_path: str):
    """Render a clean, formatted Markdown report of non-senior recommended jobs with application tracking."""
    hidden_statuses = ("uninterested", "unintrested", "rejected")
    
    tier_top = [j for j in jobs if j["score"] >= 75 and j.get("status") not in hidden_statuses]
    tier_mid = [j for j in jobs if 60 <= j["score"] < 75 and j.get("status") not in hidden_statuses]
    tier_low = [j for j in jobs if 40 <= j["score"] < 60 and j.get("status") not in hidden_statuses]
    
    # Active applications: applied, interviewing, offered (excluding rejected & uninterested)
    applied_jobs = [j for j in jobs if (j.get("applied") == 1 or (j.get("status") and j.get("status") not in ("unapplied", *hidden_statuses))) and j.get("status") != "rejected"]
    new_jobs = [j for j in jobs if j.get("is_new") == 1 and j.get("status") not in hidden_statuses]
    uninterested_jobs = [j for j in jobs if j.get("status") in ("uninterested", "unintrested")]
    rejected_jobs = [j for j in jobs if j.get("status") == "rejected"]
    
    remaining = len(jobs) - len(applied_jobs) - len(uninterested_jobs) - len(rejected_jobs)
    
    lines = [
        "# 🎯 Top Job Recommendations for Pratham Johari",
        "",
        f"**Active Non-Senior Roles Evaluated:** {len(jobs)} positions across verified sponsors & tech leaders.",
        f"**Applications Status:** 🎯 **{len(applied_jobs)} Active Applied** | ❌ **{len(rejected_jobs)} Rejected** | 🚫 **{len(uninterested_jobs)} Uninterested** | ⏳ **{max(0, remaining)} Remaining** to Review",
        f"**Newly Discovered:** 🆕 **{len(new_jobs)} New Roles** since last daily sync.",
        f"**Geographical Scope:** 🇳🇱 Netherlands • 🇬🇧 United Kingdom • 🇦🇺 Australia • 🇺🇸 United States (New York • San Francisco • Los Angeles) • 🇪🇺 European Union • 🌐 Remote",
        f"**Seniority Policy:** 🛡️ **Non-Senior Only** (Senior, Staff, Principal, Lead, and Director roles filtered out).",
        f"**Core Technology Focus:** 🐍 Python Specialist, AI / ML Engineering, Compound AI / RAG, Computer Vision & Perception, MLOps.",
        f"**Automatic Tracking:** Click **`[Apply ⚡]`** to automatically record application and open the employer's page.",
        ""
    ]
    
    # 1. Dedicated Applied Jobs Tracker section (if any applied)
    if applied_jobs:
        lines.extend([
            "---",
            "",
            f"## 📌 Applied Jobs Tracker ({len(applied_jobs)} Submitted)",
            "",
            "| ID | Status | Applied Date | Company | ATS | Job Title | Location | Recommended Letter Body | Notes | Direct Link |",
            "| :---: | :---: | :---: | :--- | :---: | :--- | :--- | :--- | :--- | :---: |"
        ])
        for j in applied_jobs:
            badge = format_status_badge(j.get("applied", 1), j.get("status", "applied"), j.get("applied_at"))
            app_date = j.get("applied_at", "")[:10] if j.get("applied_at") else "Tracked"
            note_str = j.get("notes") or "—"
            ats_val = j.get("ats_platform") or detect_ats_platform(j.get("source"), j.get("url"))
            lines.append(
                f"| `#{j['id']}` | **{badge}** | {app_date} | **{j['company']}** | `{ats_val}` | [{j['title']}]({j['url']}) | {j['location']} | `{j['recommended_letter']}` | {note_str} | [Open ↗]({j['url']}) |"
            )
        lines.append("")

    # 2. Newly Discovered Jobs Section (if any new jobs exist)
    if new_jobs:
        lines.extend([
            "---",
            "",
            f"## 🆕 Newly Added Positions (Since Last Daily Sync) — {len(new_jobs)} Roles",
            "",
            "| ID | Score | Company | ATS | Job Title | Location | Recommended Letter Body | Action |",
            "| :---: | :---: | :--- | :---: | :--- | :--- | :--- | :---: |"
        ])
        for j in new_jobs[:20]:
            badge = "🆕 "
            ats_val = j.get("ats_platform") or detect_ats_platform(j.get("source"), j.get("url"))
            lines.append(
                f"| `#{j['id']}` | **{j['score']}%** | **{j['company']}** | `{ats_val}` | {badge}[{j['title']}]({j['url']}) | {j['location']} | `{j['recommended_letter']}` | [Apply ⚡](http://localhost:8765/apply/{j['id']}) \\| [Direct ↗]({j['url']}) |"
            )
        lines.append("")
        
    # 3. Priority Recommendations (75%+)
    lines.extend([
        "---",
        "",
        f"## 🌟 Priority Recommendations (Score 75%+) — {len(tier_top)} Positions",
        "",
        "| ID | Status | Score | Company | ATS | Job Title | Location | Recommended Letter Body | Action |",
        "| :---: | :---: | :---: | :--- | :---: | :--- | :--- | :--- | :---: |"
    ])
    
    for j in tier_top:
        badge = format_status_badge(j.get("applied", 0), j.get("status", "unapplied"), j.get("applied_at"))
        new_tag = "🆕 " if j.get("is_new") == 1 else ""
        ats_val = j.get("ats_platform") or detect_ats_platform(j.get("source"), j.get("url"))
        lines.append(
            f"| `#{j['id']}` | {badge} | **{j['score']}%** | **{j['company']}** | `{ats_val}` | {new_tag}[{j['title']}]({j['url']}) | {j['location']} | `{j['recommended_letter']}` | [Apply ⚡](http://localhost:8765/apply/{j['id']}) \\| [Direct ↗]({j['url']}) |"
        )
        
    # 4. Strong Matches (60% - 74%)
    lines.extend([
        "",
        "---",
        "",
        f"## ⚡ Strong Matches (Score 60% - 74%) — {len(tier_mid)} Positions",
        "",
        "| ID | Status | Score | Company | ATS | Job Title | Location | Recommended Letter Body | Action |",
        "| :---: | :---: | :---: | :--- | :---: | :--- | :--- | :--- | :---: |"
    ])
    
    for j in tier_mid:
        badge = format_status_badge(j.get("applied", 0), j.get("status", "unapplied"), j.get("applied_at"))
        new_tag = "🆕 " if j.get("is_new") == 1 else ""
        ats_val = j.get("ats_platform") or detect_ats_platform(j.get("source"), j.get("url"))
        lines.append(
            f"| `#{j['id']}` | {badge} | **{j['score']}%** | {j['company']} | `{ats_val}` | {new_tag}[{j['title']}]({j['url']}) | {j['location']} | `{j['recommended_letter']}` | [Apply ⚡](http://localhost:8765/apply/{j['id']}) \\| [Direct ↗]({j['url']}) |"
        )
        
    # 5. Explore More (40% - 59%)
    lines.extend([
        "",
        "---",
        "",
        f"## 🔍 Explore More Positions (Score 40% - 59%) — {len(tier_low)} Positions",
        "",
        "| ID | Status | Score | Company | ATS | Job Title | Location | Action |",
        "| :---: | :---: | :---: | :--- | :---: | :--- | :--- | :---: |"
    ])
    
    for j in tier_low:
        badge = format_status_badge(j.get("applied", 0), j.get("status", "unapplied"), j.get("applied_at"))
        new_tag = "🆕 " if j.get("is_new") == 1 else ""
        ats_val = j.get("ats_platform") or detect_ats_platform(j.get("source"), j.get("url"))
        lines.append(
            f"| `#{j['id']}` | {badge} | {j['score']}% | {j['company']} | `{ats_val}` | {new_tag}[{j['title']}]({j['url']}) | {j['location']} | [Apply ⚡](http://localhost:8765/apply/{j['id']}) \\| [Direct ↗]({j['url']}) |"
        )

    # 6. Rejected Positions (Hidden from active recommendations)
    if rejected_jobs:
        lines.extend([
            "",
            "---",
            "",
            f"## ❌ Rejected Roles ({len(rejected_jobs)} Hidden from Recommendations)",
            "",
            "| ID | Status | Company | Job Title | Location | Recommended Letter Body | Action |",
            "| :---: | :---: | :--- | :--- | :--- | :--- | :---: |"
        ])
        for j in rejected_jobs:
            lines.append(
                f"| `#{j['id']}` | ❌ Rejected | **{j['company']}** | [{j['title']}]({j['url']}) | {j['location']} | `{j['recommended_letter']}` | [Open ↗]({j['url']}) |"
            )

    # 7. Uninterested Positions (Hidden from active recommendations)
    if uninterested_jobs:
        lines.extend([
            "",
            "---",
            "",
            f"## 🚫 Uninterested Roles ({len(uninterested_jobs)} Hidden from Recommendations)",
            "",
            "| ID | Status | Company | Job Title | Location | Action |",
            "| :---: | :---: | :--- | :--- | :--- | :---: |"
        ])
        for j in uninterested_jobs:
            lines.append(
                f"| `#{j['id']}` | 🚫 Uninterested | **{j['company']}** | [{j['title']}]({j['url']}) | {j['location']} | [Reconsider ↗]({j['url']}) |"
            )

    lines.extend([
        "",
        "---",
        "### 💡 Instant Application Workflow",
        "1. Click **[Apply ⚡]** to automatically record application in SQLite & redirect straight to the employer's page.",
        "2. Note the **Recommended Letter Body** (e.g. `5. SOFTWARE ENGINEER (Backend/Core)`, `7. AI ENGINEER`, `8. COMPUTER VISION`).",
        "3. Set `\\jobTitle{...}` and `\\companyName{...}` in `cover_letter.tex` and compile with `pdflatex cover_letter.tex` for a 1-page custom PDF!",
        "4. Use `python sponsor_jobs/cli.py applied` or `python sponsor_jobs/cli.py web` to inspect your application pipeline anytime."
    ])
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    analyze_all_jobs()
