# 🇳🇱 Dutch IND Recognised Sponsor Job Hunter & Analyzer

An automated, intelligent job discovery and matching system specifically engineered for **Pratham Johari** (MSc Data Science & AI @ TU Delft).

It monitors all **12,927+ Dutch Recognised Sponsors** from the official [IND Public Register for Work](https://ind.nl/en/public-register-recognised-sponsors/public-register-work), tracks tech/engineering/automotive employers, crawls open positions via direct ATS APIs & career portals, and scores jobs against your profile with tailored cover letter recommendations.

---

## 🚀 Key Features

1. **Official IND Sponsor Registry Database (`sponsors.db`)**:
   - Ingests and maintains all 12,927+ recognised sponsors with KVK numbers.
   - Automatically filters and tags companies in **Tech, Software, AI, Engineering, Robotics, Semiconductor, Automotive, and Mobility** (~1,770 high-target sponsors).
2. **High-Speed Dual Discovery Engine**:
   - **Direct ATS API Scrapers**: Greenhouse, Lever, Recruitee, SmartRecruiters (fetches hundreds of clean structured listings in seconds with 0 rate limits).
   - **Reverse Sponsor Verification**: Aggregates Dutch tech job feeds and instantly verifies employers against the IND registry.
3. **Profile-Driven Application Matching**:
   - Analyzes jobs against your background in `aboutme.md` and `cv.tex` (AI/ML, RAG, PyTorch, LIDAR/ROS, Autonomous Driving, C++, MLOps).
   - Generates a **0–100% Match Score** with priority given to Dutch & Remote positions.
   - Recommends the exact **Cover Letter Body** from `letter_bodies.tex` to use (e.g. `11. FORMULA 1 / MOTORSPORT`, `8. PROSUS AI ENGINEER`, `3. ML ENGINEER`, `4. SOFTWARE ENGINEER`).
4. **Automated Application Tracking**:
   - **Persistent Tracking**: Stores `applied`, `applied_at`, `status`, and `notes` in SQLite (never lost during daily scrapes).
   - **1-Click Auto-Tracking (`[Apply ⚡]`)**: Clicking the apply link in `recommended_jobs.md` automatically marks the job as applied in the database and redirects directly to the company application portal.
   - **Interactive Web Dashboard (`python cli.py web`)**: Real-time filtering, 1-click apply, custom application notes, and status transitions (`Applied`, `Interviewing`, `Offered`, `Rejected`).
5. **Automated Daily Updates**:
   - Runs a single pipeline that checks for IND changes, discovers new jobs, archives stale postings, and updates `data/recommended_jobs.md`.

---

## 📦 Quick Start

Always activate your conda environment first:
```bash
conda activate mt
```

### 1. View Top Recommended Jobs
```bash
python sponsor_jobs/cli.py top --limit 10
```

### 2. Launch Interactive Web Dashboard & Tracker
```bash
python sponsor_jobs/cli.py web
# or start the background 1-click tracking server:
python sponsor_jobs/cli.py tracker
```

### 3. Track Applications via CLI
```bash
# Mark as applied by Job ID (e.g. #7)
python sponsor_jobs/cli.py apply 7

# Search by company name to mark applied
python sponsor_jobs/cli.py apply "Databricks"

# Interactive selector for top unapplied jobs
python sponsor_jobs/cli.py apply

# Open in browser and auto-track
python sponsor_jobs/cli.py open 7

# View all submitted applications
python sponsor_jobs/cli.py applied

# Update status (e.g. interviewing, offered, rejected)
python sponsor_jobs/cli.py status 7 interviewing --notes "Round 1 scheduled"

# Revert back to unapplied
python sponsor_jobs/cli.py unapply 7
```

### 4. Verify If Any Company Sponsors Visas
```bash
python sponsor_jobs/cli.py check "ASML"
python sponsor_jobs/cli.py check "Databricks"
python sponsor_jobs/cli.py check "TomTom"
```

### 5. Run the Complete Daily Update
```bash
python sponsor_jobs/cli.py update-daily
```

---

## ⏰ Daily Cron Job Setup

To run the job scanner automatically every morning at 08:00 AM, add this to your crontab (`crontab -e`):

```bash
0 8 * * * bash -c "source /home/prat/miniconda3/etc/profile.d/conda.sh && conda activate mt && python /mnt/c/Users/prats/Documents/Uni\(Tudelft\)/job_hunt/pratham2442000/sponsor_jobs/cli.py update-daily" >> /mnt/c/Users/prats/Documents/Uni\(Tudelft\)/job_hunt/pratham2442000/sponsor_jobs/data/cron.log 2>&1
```

---

## 📂 Project Structure

```
sponsor_jobs/
├── cli.py                     # Unified CLI (daily sync, checking, tracking, web UI)
├── README.md                  # System documentation
├── data/
│   ├── sponsors.db            # SQLite database (sponsors & indexed jobs with tracking)
│   ├── recommended_jobs.md    # Formatted priority recommendation report with Status column
│   └── recommended_jobs.json  # Structured JSON export
└── src/
    ├── ind_fetcher.py         # IND public register downloader, classifier & schema migrations
    ├── company_enricher.py    # Target company registry & ATS slug mapping
    ├── job_scraper.py         # Async ATS board & career page crawler
    ├── job_aggregator.py      # Tech feed aggregator with IND verification
    ├── sponsor_matcher.py     # Inverted-index sponsor lookup & fuzzy matcher
    ├── profile_analyzer.py    # Match scoring, status badges & markdown report generator
    ├── tracker_server.py      # Zero-dependency 1-click redirect server & web dashboard
    └── daily_runner.py        # Complete daily pipeline orchestrator
```

---

## 🎯 Instant Cover Letter Generation Workflow

When you find a high-match job in `data/recommended_jobs.md` or the Web Dashboard:
1. Click **`[Apply ⚡]`** to open the listing and automatically track it.
2. Note the **Recommended Letter Body** (e.g. `11. FORMULA 1 / MOTORSPORT`, `8. PROSUS AI ENGINEER`, `3. ML ENGINEER`).
3. Open `cover_letter.tex` and adjust:
   ```latex
   \recipient{Hiring Team}{Company Name\\Address}
   \jobTitle{Job Title}
   \companyName{Company Name}
   ```
4. Compile with pdflatex:
   ```bash
   pdflatex cover_letter.tex
   ```
5. You instantly have a perfectly tailored, one-page application PDF ready to submit!
