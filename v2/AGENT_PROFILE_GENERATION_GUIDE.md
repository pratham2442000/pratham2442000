# Standard Operating Procedure (SOP): AI Agent Personalization Profile Generation

**Document Version:** `2.0.0`  
**Target System:** `/v2` Personalization Engine (`PersonalizationProfile` Schema v2.0.0)  
**Audience:** Autonomous AI Agents, Pair-Programming Assistants, Talent Operations Engineers  

---

## 1. Executive Summary & Objective

In the `/v2` architecture, **all downstream modules**—including the [ProfileAnalyzer](file:///mnt/c/Users/prats/Documents/Uni(Tudelft)/job_hunt/pratham2442000/v2/core/profile_analyzer.py), [CompanyMatcher](file:///mnt/c/Users/prats/Documents/Uni(Tudelft)/job_hunt/pratham2442000/v2/core/company_matcher.py), [Scorer](file:///mnt/c/Users/prats/Documents/Uni(Tudelft)/job_hunt/pratham2442000/v2/core/scorer.py), and CLI tools—derive 100% of their evaluation heuristics from a single, standardized **Personalization Profile** (`user_profile.yaml` or `profile.json`).

There are **zero hardcoded candidate rules, names, locations, skills, or weights** in the engine code.

As an AI Agent, your role is to ingest unstructured candidate data (CV/resume, LinkedIn text, portfolio, preference notes, intake forms) and compile a **fully validated, syntactically correct, non-hallucinated Personalization Profile** conforming to [profile_schema.py](file:///mnt/c/Users/prats/Documents/Uni(Tudelft)/job_hunt/pratham2442000/v2/profile_schema.py).

---

## 2. Ingestion Protocol: Handling Unstructured Inputs

Candidates provide raw information across diverse formats. You must normalize and extract data using the following order of precedence:

```
[Raw CV / Resume] (Primary Ground Truth for Education, Skills, Experience, Projects)
       +
[Intake Preferences / Notes] (Primary Ground Truth for Target Roles, Locations, Visas, Tiers)
       +
[Portfolio / GitHub Links] (Supplemental Verification for Repositories, Metrics, Homelab)
       │
       ▼
┌──────────────────────────────────────────────┐
│  AI Agent Profile Extraction Pipeline        │
│  1. Information Normalization                │
│  2. Entity & Skill Extraction                │
│  3. Rule & Weight Derivation                 │
│  4. Regex Synthesis & Safety Check           │
│  5. Schema Validation & File Generation      │
└──────────────────────────────────────────────┘
```

### Ingestion Guidelines by Input Type
1. **Curriculum Vitae / Resume (`.tex`, `.pdf`, `.md`, `.txt`)**:
   - Extract chronological education, employment history, tools, and project highlights.
   - *Strict Rule:* Never infer or assume skills that are not explicitly documented.
2. **Preference Forms & Intake Notes**:
   - Extract desired job titles, acceptable locations, visa/sponsorship requirements, and target companies.
   - Note constraints: e.g. "strictly no senior roles", "remote-friendly", "only Dutch IND sponsors".
3. **Portfolio & GitHub Readmes**:
   - Extract repository URLs, thesis DOIs, live deployment links, and benchmark metrics (e.g. latency, recall, stars).

---

## 3. Field-by-Field Extraction Rules

Follow this step-by-step logic to populate every block of the `PersonalizationProfile` schema without hallucination.

### Block 1: `candidate_background`

#### 1.1 `personal_info`
| Field | Extraction Logic | Fallback / Default | Hallucination Guard |
| :--- | :--- | :--- | :--- |
| `name` | Candidate's full professional name from CV header. | *Required* | Do not abbreviate unless requested. |
| `email` | Primary email address. | `null` | Must be valid email format. |
| `location` | Current residence city and country. | `null` | Extract from CV contact block. |
| `linkedin` | Full LinkedIn URL. | `null` | If username only, prefix `https://www.linkedin.com/in/`. |
| `github` | Full GitHub URL. | `null` | If handle only, prefix `https://github.com/`. |
| `tagline` | Synthesize a concise 1-line professional title + highest credential. | `""` | e.g. `"AI & Software Engineer \| MSc Data Science & AI @ TU Delft"` |
| `career_objective` | Stated objective or summary paragraph. | Stated summary | Keep faithful to candidate's own words. |
| `agent_tone_instructions` | Candidate's desired tone for cover letters (e.g., confident, tinkerer, research-oriented). | Constructive default | Guide downstream cover letter generation. |

#### 1.2 `education`
Extract each degree into an `EducationEntry`:
- `institution`: Official university/college name.
- `degree`: Degree designation (e.g. `Master of Science (MSc)`, `Bachelor of Science (BSc)`).
- `field_of_study`: Major / academic program.
- `start_date` / `end_date`: Format as `YYYY-MM` or `YYYY`.
- `thesis_title` & `thesis_url`: Extract research title and link if available.
- `highlights`: 2–4 bullet points detailing core specializations, honors, or relevant coursework.

#### 1.3 `verified_technical_skills`
Group candidate skills into 4 to 8 thematic `SkillCategory` items:
- `category`: Clear group title (e.g. `Python Mastery`, `RAG & Compound AI`, `Perception & Robotics`, `MLOps & Infra`).
- `weight`: Assign between `10.0` and `20.0` points based on candidate seniority and relevance to target roles:
  - Core primary specialty: `16.0` – `18.0` pts
  - Secondary specialty: `14.0` – `16.0` pts
  - General software / tooling: `10.0` – `12.0` pts
- `skills`: List canonical names (e.g. `["PyTorch", "vLLM", "Docker"]`).
- `patterns`: Provide **case-insensitive regex patterns** that match these skills in job listings.
  - *Regex Rules:* Always use word boundaries `\b` (e.g. `\\b(pytorch|torch)\\b`).
  - *Escape Special Characters:* For C++, write `\\b(c\\+\\+|cpp)\\b`.
- `aliases`: Map variations (e.g. `"Python": ["python3", "py"]`).

#### 1.4 `experience_summaries`
For each role in CV:
- `company`, `title`, `location`, `start_date`, `end_date`, `is_current`.
- `role_type`: `"full-time"`, `"internship"`, `"research"`, or `"teaching"`.
- `technologies`: Array of tools used in that role.
- `key_achievements`: 2–3 quantifiable bullet points. Transform passive descriptions into active metrics (e.g. *"Engineered real-time LIDAR clustering at 30+ Hz"*).

#### 1.5 `project_highlights`
Extract 2–5 standout projects:
- `name`, `category`, `description`, `technologies`, `url`, `repo_url`, `impact_metrics`.
- Ensure impact metrics capture throughput, accuracy, scale, or benchmark improvements.

---

### Block 2: `candidate_preferences`

#### 2.1 `target_roles`
Define job titles the candidate actively seeks:
- `title`: Standardized title (e.g. `Machine Learning Engineer`, `AI Platform Engineer`).
- `weight`: Score contribution (`30.0` to `48.0` pts).
  - Primary target: `45.0` – `46.0` pts
  - Secondary target: `38.0` – `42.0` pts
  - Broad engineering baseline: `30.0` – `35.0` pts
- `patterns`: Comprehensive regex matching common title permutations (e.g. `\\b(machine\\s+learning|ml)\\s+engineer\\b`).
- `is_primary`: Set `true` for top 3 preferred role archetypes.

#### 2.2 `seniority`
Configure candidate experience level and exclusion boundaries:
- `accepted_levels`: Array of accepted tiers (e.g. `["intern", "graduate", "junior", "associate", "mid", "entry-level"]`).
- `disallowed_levels`: Tiers to exclude (e.g. `["senior", "lead", "principal", "staff", "director", "head of", "vp", "chief", "manager"]`).
- `strict_exclusion`: `true` if candidate strictly wants to filter out senior positions.
- `senior_exclusion_pattern`: Standardized regex to detect senior roles in titles.
- `max_experience_years`: Numeric threshold (e.g. `3`). Postings demanding more trigger a seniority warning.
- `entry_level_bonus`: Bonus points awarded to entry/junior-friendly roles (`+15.0` to `+20.0` pts).

#### 2.3 `locations`
- `tiers`: Array of geographic preference tiers:
  - **Tier 1 (Home Base / Priority 1):** Weight `+25.0` pts (e.g., Netherlands).
  - **Tier 2 (Secondary Target Countries):** Weight `+20.0` pts (e.g., UK, Australia).
  - **Tier 3 (Broader Region / Remote):** Weight `+15.0` pts (e.g., EU / Remote).
- `remote`:
  - `allow_remote`: `true` / `false`.
  - `bonus_points`: Points awarded for remote listings (`+15.0`).
- `us_target_hubs`: Specific US metropolitan hubs accepted even if general US is excluded (e.g. `"New York"`, `"San Francisco"`, `"Los Angeles"`).
- `excluded_locations`: Regex patterns matching regions to filter out unless remote.

#### 2.4 `sponsorship`
- `requires_sponsorship`: Boolean (`true` if candidate requires visa sponsorship).
- `current_status`: Descriptive visa status (e.g., `"MSc Student / Search Year (Zoekjaar) / Needs IND Recognised Sponsor"`).
- `target_sponsor_registers`: Target public registers (e.g., `["IND Public Register for Work (Netherlands)"]`).
- `sponsor_match_bonus`: Bonus points for verified sponsors (`+15.0` pts).

---

### Block 3: `target_companies_and_domains`

#### 3.1 `company_tiers`
- `tier_1_dream`: Handpicked dream employers (multiplier `1.20` – `1.25x`, bonus `+10` to `+15` pts). Include `name`, `domain`, `ats_type`, `ats_slug`, and `reason`.
- `tier_2_high_priority`: Strong secondary targets (multiplier `1.10` – `1.15x`, bonus `+5` to `+8` pts).
- `excluded_companies`: Blacklist of companies candidate refuses to join.

#### 3.2 `industry_preferences`
- `preferred_domains`: Sectors candidate is passionate about (e.g. AI, Autonomous Vehicles, Motorsport, Quant Trading) with positive weights (`+10` to `+15` pts) and regex patterns.
- `excluded_domains`: Sectors candidate avoids (e.g. Gambling, Sports Betting, Lead Gen) with negative weights (`-30` to `-50` pts).

#### 3.3 `tech_stack_alignment`
- `preferred_stacks`: Stacks candidate loves.
- `anti_patterns`: Stacks candidate wants to avoid (e.g. `PHP`, `WordPress`, `Legacy Java`) with negative penalty (`-20.0` pts).

---

### Block 4: `evaluation_and_scoring_rubric`

#### 4.1 Base Parameters & Component Weights
- `base_score`: Starting score for any posting evaluated (default `15.0`).
- `min_match_threshold`: Minimum score to be considered an active match (default `40.0`).
- `max_score`: Ceiling cap (default `99.0`).
- `component_weights`:
  - `role_title_match`: `0.35`
  - `skills_match`: `0.30`
  - `location_match`: `0.20`
  - `company_and_domain`: `0.15`
  *(Must sum to `1.00 ± 0.05`)*

#### 4.2 Penalties
Define explicit point deductions:
- Non-technical / Administrative (e.g. sales, marketing, recruiter): `-50.0` pts.
- Role mismatch (e.g. pure frontend for backend/AI candidate): `-25.0` pts.

#### 4.3 `cover_letter_templates`
Map candidate project strengths to tailored cover letter recommendations:
- Each template must have:
  - `template_id`: Unique identifier (e.g. `ai_engineer_builder`).
  - `title`: Display title (e.g. `7. AI ENGINEER (0-to-1 Builder)`).
  - `priority`: Higher integers evaluated first (`100`, `90`, `80`...).
  - `trigger_patterns`: Regexes matching in job title or description.
  - `talking_points`: 2–3 specific candidate experiences to emphasize.
- `default_cover_letter`: Fallback recommendation (e.g. `1. GENERIC / OPEN APPLICATION`).

---

## 4. Anti-Hallucination & Normalization Guardrails

To ensure absolute reliability, the AI Agent must strictly obey the following guardrails:

> [!CAUTION]
> **Zero Hallucination Rule**:
> 1. If a detail (e.g. GPA, thesis link, start date, previous employer) is not explicitly present in the candidate's input text, set it to `null` or leave the list empty.
> 2. Never invent companies, years of experience, or technical proficiencies.
> 3. Never assume sponsorship status—if not stated, set `requires_sponsorship: false` and flag for user confirmation.

### Regex Normalization Rules
1. **Always use raw regex strings with valid escape characters**:
   - Correct in YAML: `"\\b(c\\+\\+|cpp)\\b"`
   - Incorrect in YAML: `"\b(c++|cpp)\b"` (fails YAML parsing or matches invalid regex).
2. **Always test regex compilation before finalizing**:
   Every regex in `patterns`, `trigger_patterns`, `anti_pattern_regexes`, and `penalties` must successfully compile with `re.compile(pattern)`.

---

## 5. Pre-Flight Validation Checklist

Before saving any generated profile, run through this automated pre-flight checklist:

```bash
# Activate the environment
source /home/prat/miniconda3/etc/profile.d/conda.sh && conda activate mt

# Validate profile schema syntax and constraints
python v2/cli.py --profile path/to/generated_profile.yaml validate
```

### Manual Verification Checklist
- [ ] **Candidate Identity:** `name` is non-empty; email and URLs are properly formatted.
- [ ] **Education & Experience:** Every entry has valid institution/company, degree/title, and dates.
- [ ] **Skill Categories:** Each category has non-empty `skills` and valid, compilable `patterns`.
- [ ] **Role Weights:** `target_roles` weights are positive floats between `10.0` and `50.0`.
- [ ] **Seniority Policy:** `strict_exclusion` accurately reflects candidate preference.
- [ ] **Location Tiers:** All target countries/cities have matching regexes.
- [ ] **Cover Letter Mapping:** At least 3 specialized templates defined with distinct `priority` values and a valid `default_cover_letter`.
- [ ] **Weight Sums:** `component_weights` sum to `1.00 ± 0.05`.

---

## 6. AI Agent System Prompts & Few-Shot Examples

When instructing an autonomous LLM agent or subagent to transform a candidate CV into a profile, execute this prompt:

### System Prompt for AI Profile Generator Agent

```text
You are an expert Talent Systems Engineer and Personalization Profile Compiler for the /v2 Job Discovery Engine.

Your task is to convert raw candidate inputs (CV/resume, portfolio, career goals, intake preferences) into a complete, syntactically valid YAML Personalization Profile conforming strictly to Schema v2.0.0.

STRICT CONSTRAINTS:
1. Output valid YAML only. Do not wrap in markdown code blocks if saving directly to file.
2. NEVER hallucinate skills, metrics, degrees, or experiences not in the source text.
3. Every regex pattern must be syntactically valid and use double-escaped backslashes (e.g. "\\b(python|python3)\\b").
4. Ensure all required sections are fully populated:
   - candidate_background (personal_info, education, verified_technical_skills, experience_summaries, project_highlights)
   - candidate_preferences (target_roles, seniority, locations, sponsorship, work_setup)
   - target_companies_and_domains (company_tiers, industry_preferences, tech_stack_alignment)
   - evaluation_and_scoring_rubric (base_score, component_weights, penalties, cover_letter_templates, default_cover_letter)
```

### Few-Shot Extraction Example

#### Input Raw CV Snippet:
```text
Elena Rostova
Amsterdam, Netherlands | elena.rostova@tech.io | github.com/erostova
Senior Data Scientist transitioning to AI Platform Engineer. 
Passionate about ML inference optimization and vLLM.

Education:
MSc Artificial Intelligence, University of Amsterdam (2022 - 2024). GPA: 8.5/10.
Thesis: Quantization and Speculative Decoding for Large Language Models.

Experience:
Booking.com (Amsterdam) - Machine Learning Engineer (2024 - Present)
- Deployed real-time recommendation model with Triton Inference Server handling 12,000 req/sec.
- Reduced p99 latency by 35% using ONNX Runtime and TensorRT.

Preferences:
Targeting Amsterdam or Remote. Needs IND visa sponsorship. Strictly no people-management roles.
```

#### Output Profile YAML Extract:
```yaml
schema_version: "2.0.0"
profile_id: "elena_rostova"
created_at: "2026-09-30"
updated_at: "2026-09-30"

candidate_background:
  personal_info:
    name: "Elena Rostova"
    email: "elena.rostova@tech.io"
    location: "Amsterdam, Netherlands"
    github: "https://github.com/erostova"
    tagline: "AI Platform & ML Inference Engineer | MSc AI @ UvA"
    career_objective: "Optimize high-throughput ML inference and scalable AI platform infrastructure."

  education:
    - institution: "University of Amsterdam"
      degree: "Master of Science (MSc)"
      field_of_study: "Artificial Intelligence"
      location: "Amsterdam, Netherlands"
      start_date: "2022-09"
      end_date: "2024-07"
      gpa: "8.5/10"
      thesis_title: "Quantization and Speculative Decoding for Large Language Models"
      highlights:
        - "Specialization: Model Optimization, Speculative Decoding, Distributed Serving"

  verified_technical_skills:
    - category: "Inference & Optimization"
      weight: 18.0
      skills: ["vLLM", "Triton Inference Server", "TensorRT", "ONNX Runtime", "Quantization"]
      patterns:
        - "\\b(vllm|triton|tensorrt|onnx|quantization|speculative\\s+decoding)\\b"
    - category: "Languages & Frameworks"
      weight: 15.0
      skills: ["Python", "PyTorch", "C++"]
      patterns:
        - "\\b(python|pytorch|c\\+\\+)\\b"

  experience_summaries:
    - company: "Booking.com"
      title: "Machine Learning Engineer"
      location: "Amsterdam, Netherlands"
      start_date: "2024-01"
      end_date: "Present"
      is_current: true
      role_type: "full-time"
      technologies: ["Python", "Triton", "TensorRT", "ONNX Runtime"]
      key_achievements:
        - "Deployed real-time recommendation model handling 12,000 req/sec."
        - "Reduced p99 latency by 35% using ONNX Runtime and TensorRT."

candidate_preferences:
  target_roles:
    - title: "AI Platform Engineer"
      weight: 46.0
      patterns: ["\\bai\\s+platform\\s+engineer\\b"]
      is_primary: true
    - title: "Machine Learning Engineer"
      weight: 42.0
      patterns: ["\\b(machine\\s+learning|ml)\\s+engineer\\b"]
      is_primary: true

  seniority:
    accepted_levels: ["mid", "senior", "specialist"]
    disallowed_levels: ["manager", "director", "head of", "vp"]
    strict_exclusion: true
    senior_exclusion_pattern: "\\b(manager|management|director|head\\s+of|vp|chief)\\b"

  locations:
    tiers:
      - name: "Netherlands"
        weight: 25.0
        patterns: ["\\b(netherlands|amsterdam|rotterdam|utrecht)\\b"]
    remote:
      allow_remote: true
      bonus_points: 15.0

  sponsorship:
    requires_sponsorship: true
    current_status: "Needs IND Recognised Sponsor"
    target_sponsor_registers: ["IND Public Register for Work (Netherlands)"]
    sponsor_match_bonus: 15.0

target_companies_and_domains:
  company_tiers:
    tier_1_dream: []
    tier_2_high_priority: []
    tier_3_neutral: []
    excluded_companies: []
  industry_preferences:
    preferred_domains:
      - name: "AI Platforms & Infrastructure"
        weight: 15.0
        patterns: ["\\b(inference|serving|latency|llm\\s+infrastructure)\\b"]
    excluded_domains: []
  tech_stack_alignment:
    preferred_stacks: ["Python", "Triton", "vLLM", "TensorRT"]
    anti_patterns: ["PHP", "WordPress"]

evaluation_and_scoring_rubric:
  base_score: 15.0
  min_match_threshold: 40.0
  max_score: 99.0
  component_weights:
    role_title_match: 0.35
    skills_match: 0.30
    location_match: 0.20
    company_and_domain: 0.15
  penalties:
    - name: "People Management"
      deduction: -50.0
      pattern: "\\b(engineering\\s+manager|people\\s+management)\\b"
      reason: "Disallowed managerial role"
  cover_letter_templates:
    - template_id: "inference_platform"
      title: "1. HIGH-THROUGHPUT ML INFERENCE & PLATFORM"
      priority: 100
      trigger_patterns: ["\\b(inference|triton|tensorrt|serving|vllm|latency)\\b"]
      talking_points:
        - "Booking.com Triton Inference Server serving 12,000 req/sec"
        - "UvA Master's Thesis on Speculative Decoding & Quantization"
  default_cover_letter: "1. GENERAL ML & PLATFORM APPLICATION"
```

---

## 7. Interactive Clarification Protocol

When an AI agent ingests inputs that are ambiguous, it must execute this clarification routine rather than guessing:

```
IF candidate mentions "US roles" AND requires_sponsorship == True:
   ASK: "Do you have existing US work authorization (OPT, STEM-OPT, Green Card, Citizen) or do you require H-1B sponsorship?"

IF candidate lists 15+ disparate skills (e.g. React, C++, PyTorch, Solidity, Flutter):
   ASK: "Which 2-3 technical domains represent your primary target career focus versus secondary familiarity?"

IF candidate does not specify seniority preferences:
   INFER from years of experience:
     - 0-2 years: Junior / Entry-Level (strict exclusion of senior/lead).
     - 3-5 years: Mid-level.
     - 6+ years: Senior / Staff / Lead accepted.
```

Following this guide guarantees that any candidate profile generated is **accurate**, **syntactically compliant**, and **instantly executable** across the entire `/v2` job discovery ecosystem.
