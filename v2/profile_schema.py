"""
profile_schema.py - Standardized Personalization Profile Schema (v2).

Defines the Pydantic v2 data models, validation logic, and schema generation
for user-agnostic job discovery, matching, and scoring.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


# ============================================================================
# 1. CANDIDATE BACKGROUND MODELS
# ============================================================================

class PersonalInfo(BaseModel):
    """Personal and contact information for the candidate."""
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Full legal or professional name of the candidate")
    email: Optional[str] = Field(None, description="Contact email address")
    phone: Optional[str] = Field(None, description="Contact phone number (optional)")
    location: Optional[str] = Field(None, description="Current physical residence (City, Country)")
    linkedin: Optional[str] = Field(None, description="Full LinkedIn profile URL")
    github: Optional[str] = Field(None, description="Full GitHub profile URL")
    portfolio: Optional[str] = Field(None, description="Personal website or portfolio URL")
    tagline: Optional[str] = Field(None, description="1-line professional title or summary")
    career_objective: Optional[str] = Field(None, description="Primary career goal and high-level focus")
    agent_tone_instructions: Optional[str] = Field(
        None,
        description="Guidelines for how an AI agent should write cover letters or pitches for this candidate"
    )


class EducationEntry(BaseModel):
    """Educational degree or qualification."""
    model_config = ConfigDict(extra="ignore")

    institution: str = Field(..., description="University, college, or school name")
    degree: str = Field(..., description="Degree type (e.g. MSc, BSc, PhD, BootCamp)")
    field_of_study: str = Field(..., description="Major or area of specialization")
    location: Optional[str] = Field(None, description="City, Country of institution")
    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM or Year)")
    end_date: Optional[str] = Field(None, description="End or graduation date (YYYY-MM or Year)")
    gpa: Optional[str] = Field(None, description="GPA or grade classification if relevant")
    thesis_title: Optional[str] = Field(None, description="Master's or doctoral thesis title")
    thesis_url: Optional[str] = Field(None, description="Public repository or DOI URL for thesis")
    thesis_abstract: Optional[str] = Field(None, description="Brief summary of thesis research")
    highlights: List[str] = Field(default_factory=list, description="Key courses, awards, or distinctions")


class SkillCategory(BaseModel):
    """A verified category of technical skills with regex matching patterns."""
    model_config = ConfigDict(extra="ignore")

    category: str = Field(..., description="Category name (e.g. Python Mastery, Deep Learning, MLOps)")
    weight: float = Field(default=10.0, ge=0.0, le=100.0, description="Match score points awarded if found")
    skills: List[str] = Field(default_factory=list, description="Canonical skill names (e.g. ['PyTorch', 'ONNX'])")
    patterns: List[str] = Field(
        default_factory=list,
        description="Regex patterns to match this skill category in job postings (case-insensitive)"
    )
    aliases: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Skill aliases mapping canonical names to synonyms"
    )

    @field_validator("patterns")
    @classmethod
    def validate_regex_patterns(cls, patterns: List[str]) -> List[str]:
        """Validate that all provided regex patterns are syntactically valid."""
        for pat in patterns:
            try:
                re.compile(pat)
            except re.error as e:
                raise ValueError(f"Invalid regular expression in skill pattern '{pat}': {e}")
        return patterns


class ExperienceEntry(BaseModel):
    """Work, internship, or research experience."""
    model_config = ConfigDict(extra="ignore")

    company: str = Field(..., description="Employer or organization name")
    title: str = Field(..., description="Job title held")
    location: Optional[str] = Field(None, description="Location of work")
    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM or Year)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM or 'Present')")
    is_current: bool = Field(default=False, description="Whether the candidate currently works here")
    role_type: Optional[str] = Field(
        default="full-time",
        description="Type of role: full-time, part-time, internship, research, contractor"
    )
    technologies: List[str] = Field(default_factory=list, description="Tech stack utilized in this role")
    key_achievements: List[str] = Field(
        default_factory=list,
        description="Bullet points describing concrete achievements and metrics"
    )


class ProjectEntry(BaseModel):
    """A technical project, open-source repository, or key capability."""
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Project title")
    category: Optional[str] = Field(None, description="Project domain (e.g. RAG, Perception, Homelab)")
    description: str = Field(..., description="Detailed description of the project and methodology")
    technologies: List[str] = Field(default_factory=list, description="Technologies and libraries used")
    url: Optional[str] = Field(None, description="Live demo or website URL")
    repo_url: Optional[str] = Field(None, description="GitHub or source repository URL")
    impact_metrics: List[str] = Field(
        default_factory=list,
        description="Quantitative benchmarks, stars, throughput, or accuracy results"
    )


class InfrastructureEntry(BaseModel):
    """Hands-on homelab, self-hosting, or infrastructure highlights."""
    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., description="Infrastructure component (e.g. Bare-Metal Server, Mesh VPN)")
    description: str = Field(..., description="Technical implementation details")
    tools: List[str] = Field(default_factory=list, description="Tools/services (e.g. Docker, Tailscale, Pi-hole)")


class CandidateBackground(BaseModel):
    """Complete candidate background extracted from CV/resume and portfolio."""
    model_config = ConfigDict(extra="ignore")

    personal_info: PersonalInfo
    education: List[EducationEntry] = Field(default_factory=list)
    verified_technical_skills: List[SkillCategory] = Field(default_factory=list)
    experience_summaries: List[ExperienceEntry] = Field(default_factory=list)
    project_highlights: List[ProjectEntry] = Field(default_factory=list)
    infrastructure_and_homelab: Optional[List[InfrastructureEntry]] = Field(default_factory=list)


# ============================================================================
# 2. CANDIDATE PREFERENCES & CONSTRAINTS MODELS
# ============================================================================

class TargetRole(BaseModel):
    """A target job title or role archetype with custom scoring priority."""
    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., description="Role title (e.g. 'Machine Learning Engineer', 'Python Specialist')")
    weight: float = Field(default=35.0, ge=0.0, le=100.0, description="Match score bonus awarded for this role")
    patterns: List[str] = Field(
        default_factory=list,
        description="Regex patterns to match this role in job titles"
    )
    is_primary: bool = Field(default=False, description="Flag indicating if this is a top-priority role")

    @field_validator("patterns")
    @classmethod
    def validate_patterns(cls, patterns: List[str]) -> List[str]:
        for pat in patterns:
            try:
                re.compile(pat)
            except re.error as e:
                raise ValueError(f"Invalid regex in role pattern '{pat}': {e}")
        return patterns


class SeniorityPreferences(BaseModel):
    """Seniority filtering, preferences, and strict exclusions."""
    model_config = ConfigDict(extra="ignore")

    accepted_levels: List[str] = Field(
        default_factory=lambda: ["intern", "graduate", "junior", "associate", "mid", "entry-level"],
        description="List of accepted seniority levels"
    )
    disallowed_levels: List[str] = Field(
        default_factory=lambda: ["senior", "lead", "principal", "staff", "director", "head of", "vp", "chief", "manager"],
        description="Seniority designations to exclude"
    )
    strict_exclusion: bool = Field(
        default=True,
        description="If True, any job with a disallowed seniority term receives 0 match score"
    )
    senior_exclusion_pattern: Optional[str] = Field(
        default=r"\b(senior|sr\.?|sr\s+|lead|principal|staff|director|head\s+of|vp|vice\s+president|chief|manager|management|architect|distinguished|founding\s+engineer)\b",
        description="Regex pattern used to detect disallowed senior roles"
    )
    max_experience_years: Optional[int] = Field(
        default=3,
        description="Maximum required years of experience accepted before issuing a warning or exclusion"
    )
    entry_level_bonus: float = Field(
        default=20.0,
        description="Bonus points awarded to graduate, entry-level, or junior-friendly postings"
    )
    entry_level_patterns: List[str] = Field(
        default_factory=lambda: [r"\b(intern|internship|trainee|working\s+student|junior|graduate|entry\s+level|associate)\b"],
        description="Regex patterns identifying entry-friendly roles"
    )

    def get_effective_exclusion_pattern(self) -> Optional[str]:
        """Combine senior_exclusion_pattern and disallowed_levels into a unified regex pattern."""
        patterns: List[str] = []
        if self.senior_exclusion_pattern:
            patterns.append(self.senior_exclusion_pattern)
        for level in self.disallowed_levels:
            lvl = level.strip()
            if lvl:
                escaped = re.escape(lvl).replace(r"\ ", r"\s+")
                patterns.append(rf"\b{escaped}\b")
        if not patterns:
            return None
        return "|".join(f"(?:{p})" for p in patterns)


class LocationTier(BaseModel):
    """A geographic target tier with associated bonus points and matching regex patterns."""
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Tier or region name (e.g. Netherlands, United Kingdom, US Tech Hubs)")
    weight: float = Field(default=20.0, ge=0.0, le=100.0, description="Bonus points for matching this location")
    patterns: List[str] = Field(default_factory=list, description="Regex patterns matching cities/countries in this tier")

    @field_validator("patterns")
    @classmethod
    def validate_patterns(cls, patterns: List[str]) -> List[str]:
        for pat in patterns:
            try:
                re.compile(pat)
            except re.error as e:
                raise ValueError(f"Invalid regex in location tier '{pat}': {e}")
        return patterns


class RemotePreference(BaseModel):
    """Remote work settings and scoring."""
    model_config = ConfigDict(extra="ignore")

    allow_remote: bool = Field(default=True, description="Whether remote jobs are acceptable")
    bonus_points: float = Field(default=15.0, description="Points awarded for remote postings")
    remote_only: bool = Field(default=False, description="If True, strictly exclude non-remote jobs")
    remote_patterns: List[str] = Field(
        default_factory=lambda: [r"\bremote\b", r"\banywhere\b", r"\bwork\s+from\s+home\b", r"\bwfh\b"],
        description="Regex patterns detecting remote availability"
    )


class LocationPreferences(BaseModel):
    """Geographic preferences, regional tiers, and explicit exclusions."""
    model_config = ConfigDict(extra="ignore")

    tiers: List[LocationTier] = Field(default_factory=list, description="Ordered location preference tiers")
    remote: RemotePreference = Field(default_factory=RemotePreference)
    us_target_hubs: List[str] = Field(
        default_factory=lambda: ["New York", "San Francisco / Bay Area", "Los Angeles"],
        description="Specific US metro areas accepted even if broader US is excluded"
    )
    us_hub_patterns: List[str] = Field(
        default_factory=list,
        description="Regex patterns identifying target US metropolitan hubs"
    )
    excluded_locations: List[str] = Field(
        default_factory=list,
        description="Regex patterns of regions to filter out unless explicitly remote or in target hubs"
    )


class SponsorshipPreferences(BaseModel):
    """Visa, work authorization, and sponsorship requirements."""
    model_config = ConfigDict(extra="ignore")

    requires_sponsorship: bool = Field(default=True, description="Whether candidate requires visa sponsorship")
    current_status: str = Field(
        default="Needs Sponsorship",
        description="Current visa/authorization status (e.g. Student Visa, Search Year, Citizen)"
    )
    target_sponsor_registers: List[str] = Field(
        default_factory=lambda: ["IND Public Register (Netherlands)"],
        description="Government registries of verified sponsors to check"
    )
    strict_sponsorship_only: bool = Field(
        default=False,
        description="If True, filter out any employer not verified in a sponsor registry"
    )
    sponsor_match_bonus: float = Field(
        default=15.0,
        description="Bonus points awarded if the employer is a verified sponsor"
    )


class CompensationPreference(BaseModel):
    """Salary and compensation expectations."""
    model_config = ConfigDict(extra="ignore")

    minimum_amount: Optional[float] = Field(None, description="Minimum acceptable base salary")
    target_amount: Optional[float] = Field(None, description="Target base salary")
    currency: str = Field(default="EUR", description="ISO 4217 Currency code (EUR, USD, GBP, etc.)")
    period: str = Field(default="yearly", description="Compensation period: yearly, monthly, hourly")


class WorkSetupPreferences(BaseModel):
    """Workplace environment preferences."""
    model_config = ConfigDict(extra="ignore")

    work_modes: List[str] = Field(
        default_factory=lambda: ["hybrid", "remote", "onsite"],
        description="Accepted work modes: remote, hybrid, onsite"
    )
    employment_types: List[str] = Field(
        default_factory=lambda: ["full-time"],
        description="Accepted contract types: full-time, contract, internship"
    )
    compensation: Optional[CompensationPreference] = None


class CandidatePreferences(BaseModel):
    """Unified candidate preferences and hard constraints."""
    model_config = ConfigDict(extra="ignore")

    target_roles: List[TargetRole] = Field(default_factory=list)
    seniority: SeniorityPreferences = Field(default_factory=SeniorityPreferences)
    locations: LocationPreferences = Field(default_factory=LocationPreferences)
    sponsorship: SponsorshipPreferences = Field(default_factory=SponsorshipPreferences)
    work_setup: WorkSetupPreferences = Field(default_factory=WorkSetupPreferences)


# ============================================================================
# 3. TARGET COMPANIES & DOMAINS MODELS
# ============================================================================

class CompanyTierItem(BaseModel):
    """Company specification within a preference tier."""
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Clean company name")
    keyword: Optional[str] = Field(None, description="Lookup keyword or identifier")
    domain: Optional[str] = Field(None, description="Primary company website domain")
    careers_url: Optional[str] = Field(None, description="Direct careers or jobs portal URL")
    ats_slug: Optional[str] = Field(None, description="ATS slug (for Greenhouse, Lever, etc.)")
    ats_type: Optional[str] = Field(None, description="ATS platform name")
    multiplier: float = Field(default=1.0, ge=0.0, le=5.0, description="Match score multiplier")
    bonus_points: float = Field(default=0.0, description="Flat bonus points added for this company")
    tier: Optional[str] = Field(default="Curated Sponsor", description="Tier category")
    reason: Optional[str] = Field(None, description="Why this company is in this tier")


class CompanyTiers(BaseModel):
    """Ranked company tier lists."""
    model_config = ConfigDict(extra="ignore")

    tier_1_dream: List[CompanyTierItem] = Field(
        default_factory=list,
        description="Tier 1 dream companies (highest priority)"
    )
    tier_2_high_priority: List[CompanyTierItem] = Field(
        default_factory=list,
        description="Tier 2 high-priority companies"
    )
    tier_3_neutral: List[CompanyTierItem] = Field(
        default_factory=list,
        description="Tier 3 acceptable / standard companies"
    )
    curated_sponsors: List[CompanyTierItem] = Field(
        default_factory=list,
        description="Comprehensive catalog of curated sponsor endpoints across all ATS platforms"
    )
    excluded_companies: List[str] = Field(
        default_factory=list,
        description="Company names or patterns to strictly ignore / blacklist"
    )


class DomainItem(BaseModel):
    """Industry sector or technical domain."""
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Domain name (e.g. Autonomous Vehicles, FinTech, Foundation Models)")
    weight: float = Field(default=10.0, description="Score impact (positive bonus or negative penalty)")
    patterns: List[str] = Field(default_factory=list, description="Regex patterns identifying this domain")

    @field_validator("patterns")
    @classmethod
    def validate_patterns(cls, patterns: List[str]) -> List[str]:
        for pat in patterns:
            try:
                re.compile(pat)
            except re.error as e:
                raise ValueError(f"Invalid regex in domain pattern '{pat}': {e}")
        return patterns


class IndustryPreferences(BaseModel):
    """Preferred and anti-pattern industry domains."""
    model_config = ConfigDict(extra="ignore")

    preferred_domains: List[DomainItem] = Field(default_factory=list)
    excluded_domains: List[DomainItem] = Field(default_factory=list)


class TechStackAlignment(BaseModel):
    """Technical stack alignment and anti-patterns."""
    model_config = ConfigDict(extra="ignore")

    preferred_stacks: List[str] = Field(default_factory=list, description="Stacks candidate wants to work with")
    anti_patterns: List[str] = Field(
        default_factory=list,
        description="Stacks candidate wants to avoid (e.g. PHP, legacy monolithic Java)"
    )
    anti_pattern_penalty: float = Field(default=-20.0, description="Penalty points for anti-pattern tech stacks")
    anti_pattern_regexes: List[str] = Field(
        default_factory=list,
        description="Regex patterns for detecting anti-pattern tech stacks"
    )


class TargetCompaniesAndDomains(BaseModel):
    """Target employers, company tiers, and industry preferences."""
    model_config = ConfigDict(extra="ignore")

    company_tiers: CompanyTiers = Field(default_factory=CompanyTiers)
    industry_preferences: IndustryPreferences = Field(default_factory=IndustryPreferences)
    company_size_preference: List[str] = Field(
        default_factory=lambda: ["scaleup", "enterprise", "midsize", "startup"],
        description="Preferred organization sizes"
    )
    tech_stack_alignment: TechStackAlignment = Field(default_factory=TechStackAlignment)


# ============================================================================
# 4. EVALUATION & SCORING RUBRIC MODELS
# ============================================================================

class ComponentWeights(BaseModel):
    """Relative importance weights for major scoring dimensions (should sum close to 1.0)."""
    model_config = ConfigDict(extra="ignore")

    role_title_match: float = Field(default=0.35, ge=0.0, le=1.0)
    skills_match: float = Field(default=0.30, ge=0.0, le=1.0)
    location_match: float = Field(default=0.20, ge=0.0, le=1.0)
    company_and_domain: float = Field(default=0.15, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_sum(self) -> "ComponentWeights":
        total = self.role_title_match + self.skills_match + self.location_match + self.company_and_domain
        if abs(total - 1.0) > 0.05:
            # Non-fatal warning / soft normalization allowed, but loggable
            pass
        return self


class PenaltyItem(BaseModel):
    """A deduction rule applied when specific anti-patterns are found."""
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Penalty name (e.g. Non-technical, Frontend, Sales)")
    deduction: float = Field(..., description="Points to subtract (negative value or positive deduction amount)")
    pattern: str = Field(..., description="Regex pattern triggering this penalty")
    reason: str = Field(..., description="Explanation displayed in match rationale")

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regex in penalty pattern '{v}': {e}")
        return v


class CoverLetterTemplate(BaseModel):
    """A personalized cover letter body template matched dynamically to jobs."""
    model_config = ConfigDict(extra="ignore")

    template_id: str = Field(..., description="Unique slug (e.g. 'formula1_motorsport')")
    title: str = Field(..., description="Display title (e.g. '10. FORMULA 1 & MOTORSPORT')")
    priority: int = Field(default=50, description="Evaluation priority (higher checked first)")
    trigger_patterns: List[str] = Field(
        default_factory=list,
        description="Regex patterns in job title or description that trigger this recommendation"
    )
    letter_file_reference: Optional[str] = Field(
        None,
        description="Path or anchor in letter_bodies.tex or templates directory"
    )
    body_snippet: Optional[str] = Field(
        None,
        description="Raw text or LaTeX snippet of the cover letter core body"
    )
    talking_points: List[str] = Field(
        default_factory=list,
        description="Key candidate projects/experiences to highlight in this letter"
    )

    @field_validator("trigger_patterns")
    @classmethod
    def validate_patterns(cls, patterns: List[str]) -> List[str]:
        for pat in patterns:
            try:
                re.compile(pat)
            except re.error as e:
                raise ValueError(f"Invalid regex in cover letter trigger '{pat}': {e}")
        return patterns


class EvaluationAndScoringRubric(BaseModel):
    """Custom weights, thresholds, penalties, and cover letter mapping rules."""
    model_config = ConfigDict(extra="ignore")

    base_score: float = Field(default=15.0, ge=0.0, le=50.0, description="Baseline starting score for any evaluated job")
    min_match_threshold: float = Field(default=40.0, ge=0.0, le=100.0, description="Minimum score to be considered a match")
    max_score: float = Field(default=99.0, ge=50.0, le=100.0, description="Ceiling cap for match scores")
    component_weights: ComponentWeights = Field(default_factory=ComponentWeights)
    enable_company_multipliers: bool = Field(default=False, description="Whether to apply employer tier multipliers and bonuses")
    enable_domain_bonuses: bool = Field(default=False, description="Whether to award additional industry domain bonuses")
    penalties: List[PenaltyItem] = Field(default_factory=list)
    cover_letter_templates: List[CoverLetterTemplate] = Field(default_factory=list)
    default_cover_letter: str = Field(
        default="1. GENERIC / OPEN APPLICATION",
        description="Fallback cover letter when no specialized trigger matches"
    )


# ============================================================================
# 5. UNIFIED PERSONALIZATION PROFILE (ROOT MODEL)
# ============================================================================

class OutputSettings(BaseModel):
    """Customizable paths and reporting options."""
    model_config = ConfigDict(extra="ignore")

    reports_dir: Optional[str] = Field(None, description="Directory where reports are saved")
    markdown_filename: str = Field(default="recommended_jobs.md", description="Markdown report filename")
    json_filename: str = Field(default="recommended_jobs.json", description="JSON export filename")
    sqlite_db_path: Optional[str] = Field("v2/data/sponsors.db", description="Custom SQLite database path")


class PersonalizationProfile(BaseModel):
    """
    Standardized Personalization Profile (v2).
    
    This is the Single Source of Truth for candidate personalization,
    preferences, company tier lists, and scoring heuristics.
    """
    model_config = ConfigDict(extra="ignore")

    schema_version: str = Field(default="2.0.0", description="Profile schema version (semver)")
    profile_id: str = Field(..., description="Unique machine identifier for this profile (e.g. 'pratham_johari')")
    created_at: Optional[str] = Field(default_factory=lambda: str(date.today()))
    updated_at: Optional[str] = Field(default_factory=lambda: str(date.today()))

    # Core Personalization Blocks
    candidate_background: CandidateBackground
    candidate_preferences: CandidatePreferences
    target_companies_and_domains: TargetCompaniesAndDomains
    evaluation_and_scoring_rubric: EvaluationAndScoringRubric

    # Optional local overrides
    output_settings: OutputSettings = Field(default_factory=OutputSettings)

    @classmethod
    def get_json_schema(cls) -> Dict[str, Any]:
        """Generate standard JSON Schema for IDE validation."""
        return cls.model_json_schema()
