# 🚀 Configurable Personalization & Job Matching Engine (`/v2`)

A user-agnostic, modular, and dynamic job discovery, evaluation, and application matching architecture.

In `/v2`, all downstream evaluation, scoring heuristics, company targeting, and tailored cover letter selections derive their parameters **solely from one standardized Personalization Profile** (`user_profile.yaml` or `profile.json`).

---

## 🔒 Architectural Principles

1. **Strict Legacy Isolation**: Built entirely in `/v2/`. Does not modify, refactor, or delete any legacy `/sponsor_jobs` code.
2. **Single Source of Truth**: All candidate criteria—education, skills, target roles, seniority limits, geographic tiers, visa sponsorship needs, employer tiers, and scoring weights—are defined in the profile.
3. **Dynamic Evaluation**: The core modules ([Scorer](file:///mnt/c/Users/prats/Documents/Uni(Tudelft)/job_hunt/pratham2442000/v2/core/scorer.py), [CompanyMatcher](file:///mnt/c/Users/prats/Documents/Uni(Tudelft)/job_hunt/pratham2442000/v2/core/company_matcher.py), [ProfileAnalyzer](file:///mnt/c/Users/prats/Documents/Uni(Tudelft)/job_hunt/pratham2442000/v2/core/profile_analyzer.py)) ingest the profile object at runtime with zero hardcoded candidate assumptions.

---

## 📂 Project Structure

```
v2/
├── README.md                              # System documentation & usage guide
├── AGENT_PROFILE_GENERATION_GUIDE.md      # AI Agent SOP for generating profiles from CVs
├── cli.py                                 # Unified command line interface
├── profile_schema.py                      # Pydantic v2 data models & validation rules
├── data/
│   └── sponsors.db                        # Independent SQLite database for v2
├── schemas/
│   ├── profile.schema.json                # Standard JSON Schema for IDE validation
│   ├── pratham.example.yaml               # Fully populated mock profile for Pratham Johari
│   └── template.yaml                      # Clean starter template for any new candidate
├── ingestion/                             # Self-contained scrapers and data ingestion
│   ├── __init__.py
│   ├── ind_fetcher.py                     # IND recognised sponsor register fetcher & sector classifier
│   ├── job_scraper.py                     # Multi-ATS async scrapers (Greenhouse, Lever, Ashby, Workday, etc.)
│   ├── company_enricher.py                # Profile-driven curated sponsors enricher & domain guesser
│   └── job_aggregator.py                  # Verified Dutch tech job feed aggregator
├── core/
│   ├── __init__.py
│   ├── config_loader.py                   # Profile loading, parsing, and serialization
│   ├── scorer.py                          # Profile-driven dynamic match scoring engine
│   ├── company_matcher.py                 # Profile-driven company tier & sponsor matching
│   ├── profile_analyzer.py                # Job batch evaluation, JD text parsing & report rendering
│   ├── daily_runner.py                    # Complete daily sync pipeline orchestrator
│   ├── dashboard_template.py              # Standalone rich interactive HTML/CSS/JS dashboard template
│   ├── web_server.py                      # Local HTTP server, 1-click apply tracker & REST API
│   └── tracker.py                         # Application lifecycle state management
├── storage/
│   ├── __init__.py
│   └── db.py                              # SQLite manager with schema provisioning
└── reports/
    ├── recommended_jobs.md                # Dynamically generated personalized markdown report
    └── recommended_jobs.json              # Structured JSON export
```

---

## 🛠️ Quick Start

Always activate your conda environment:
```bash
source /home/prat/miniconda3/etc/profile.d/conda.sh && conda activate mt
```

### 1. Validate a Personalization Profile
```bash
python v2/cli.py --profile v2/schemas/pratham.example.yaml validate
```

### 2. View Top Job Recommendations for Candidate
```bash
python v2/cli.py --profile v2/schemas/pratham.example.yaml top --limit 10
```

### 3. Check an Employer's Sponsorship & Candidate Tier
```bash
python v2/cli.py --profile v2/schemas/pratham.example.yaml check "Databricks"
python v2/cli.py --profile v2/schemas/pratham.example.yaml check "ASML"
```

### 4. Evaluate Any Job Description Text
```bash
python v2/cli.py --profile v2/schemas/pratham.example.yaml extract \
  "Looking for an AI Engineer with Python, PyTorch, FAISS, and LangChain in Amsterdam." \
  --title "AI Engineer" --company "Databricks" --location "Amsterdam, Netherlands"
```
Or evaluate from a text file:
```bash
python v2/cli.py --profile v2/schemas/pratham.example.yaml extract --file sample_jd.txt
```

### 5. Run Full Database Analysis & Generate Reports
```bash
python v2/cli.py --profile v2/schemas/pratham.example.yaml analyze
```
Outputs personalized reports to `v2/reports/recommended_jobs.md` and `v2/reports/recommended_jobs.json`.

### 6. Track Applications
```bash
# Mark as applied
python v2/cli.py --profile v2/schemas/pratham.example.yaml apply 1268 --notes "Applied on company portal"

# Update status
python v2/cli.py --profile v2/schemas/pratham.example.yaml status 1268 interviewing --notes "Round 1 scheduled"
```

### 7. Export Standard JSON Schema for IDE Autocompletion
```bash
python v2/cli.py export-schema --out v2/schemas/profile.schema.json
```

---

## 🤖 Generating a Profile for a New User

To configure this system for any new candidate:
1. Refer to the comprehensive Standard Operating Procedure: [AGENT_PROFILE_GENERATION_GUIDE.md](file:///mnt/c/Users/prats/Documents/Uni(Tudelft)/job_hunt/pratham2442000/v2/AGENT_PROFILE_GENERATION_GUIDE.md).
2. Copy [v2/schemas/template.yaml](file:///mnt/c/Users/prats/Documents/Uni(Tudelft)/job_hunt/pratham2442000/v2/schemas/template.yaml) to `v2/schemas/<candidate_id>.yaml`.
3. Populate the fields following the extraction rules without hallucinating details.
4. Validate with `python v2/cli.py --profile v2/schemas/<candidate_id>.yaml validate`.
5. Run evaluations seamlessly!
