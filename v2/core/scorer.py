"""
scorer.py - Dynamic, Profile-Driven Job Match Scorer (v2).

Calculates match scores (0-100), reasoning tags, technical keyword matches,
and cover letter recommendations dynamically derived from a PersonalizationProfile.
Zero hardcoded assumptions.
"""

from __future__ import annotations

import re
import logging
from typing import Dict, Any, List, Tuple, Optional
from pydantic import BaseModel, Field

from v2.profile_schema import PersonalizationProfile

logger = logging.getLogger(__name__)


class JobScoreResult(BaseModel):
    """Detailed scoring breakdown and evaluation results for a single job."""
    score: float = Field(..., description="Overall match score (0-100)")
    reasons: List[str] = Field(default_factory=list, description="List of positive & negative scoring rationales")
    matched_skills: List[str] = Field(default_factory=list, description="Skills or skill categories found in job text")
    recommended_letter: str = Field(..., description="Title of recommended tailored cover letter body")
    location_category: str = Field(..., description="Categorized location tier or region name")
    is_target_location: bool = Field(default=True, description="Whether location matches candidate criteria")
    is_senior: bool = Field(default=False, description="Whether job is detected as senior/leadership")
    is_active: bool = Field(default=True, description="Whether job meets minimum thresholds to remain active")
    company_tier: Optional[str] = Field(None, description="Tier 1, Tier 2, or Neutral company classification")
    company_multiplier: float = Field(default=1.0, description="Multiplier applied based on employer tier")
    talking_points: List[str] = Field(default_factory=list, description="Recommended bullet points for pitch/letter")


class Scorer:
    """
    Profile-driven dynamic evaluation engine.
    Ingests a PersonalizationProfile and evaluates job listings against it.
    """

    def __init__(self, profile: PersonalizationProfile):
        self.profile = profile
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns from profile for high-throughput batch evaluation."""
        seniority_cfg = self.profile.candidate_preferences.seniority
        
        # Build comprehensive disallowed seniority regex from disallowed_levels and senior_exclusion_pattern
        disallowed_patterns: List[str] = []
        if seniority_cfg.senior_exclusion_pattern:
            disallowed_patterns.append(seniority_cfg.senior_exclusion_pattern)
        for level in seniority_cfg.disallowed_levels:
            lvl = level.strip()
            if lvl:
                escaped = re.escape(lvl).replace(r"\ ", r"\s+")
                disallowed_patterns.append(rf"\b{escaped}\b")

        if disallowed_patterns:
            combined = "|".join(f"(?:{p})" for p in disallowed_patterns)
            self.senior_regex = re.compile(combined, re.IGNORECASE)
        else:
            self.senior_regex = None

        self.entry_level_regexes = [
            re.compile(pat, re.IGNORECASE) for pat in seniority_cfg.entry_level_patterns
        ]

        # Location patterns
        loc_cfg = self.profile.candidate_preferences.locations
        self.location_tier_regexes = [
            (tier.name, tier.weight, [re.compile(p, re.IGNORECASE) for p in tier.patterns])
            for tier in loc_cfg.tiers
        ]
        self.remote_regexes = [
            re.compile(p, re.IGNORECASE) for p in loc_cfg.remote.remote_patterns
        ]
        self.us_hub_regexes = [
            re.compile(p, re.IGNORECASE) for p in loc_cfg.us_hub_patterns
        ]
        self.excluded_loc_regexes = [
            re.compile(p, re.IGNORECASE) for p in loc_cfg.excluded_locations
        ]

        # Role weights
        self.role_patterns = [
            (role.title, role.weight, [re.compile(p, re.IGNORECASE) for p in role.patterns])
            for role in self.profile.candidate_preferences.target_roles
        ]

        # Skills categories
        self.skill_categories = [
            (cat.category, cat.weight, [re.compile(p, re.IGNORECASE) for p in cat.patterns])
            for cat in self.profile.candidate_background.verified_technical_skills
        ]

        # Penalties
        self.penalties = [
            (pen.name, pen.deduction, re.compile(pen.pattern, re.IGNORECASE), pen.reason)
            for pen in self.profile.evaluation_and_scoring_rubric.penalties
        ]

        # Industry domains
        ind_cfg = self.profile.target_companies_and_domains.industry_preferences
        self.preferred_domains = [
            (d.name, d.weight, [re.compile(p, re.IGNORECASE) for p in d.patterns])
            for d in ind_cfg.preferred_domains
        ]
        self.excluded_domains = [
            (d.name, d.weight, [re.compile(p, re.IGNORECASE) for p in d.patterns])
            for d in ind_cfg.excluded_domains
        ]

        # Anti-pattern tech stacks
        tech_cfg = self.profile.target_companies_and_domains.tech_stack_alignment
        self.anti_stack_regexes = [
            re.compile(p, re.IGNORECASE) for p in tech_cfg.anti_pattern_regexes
        ]
        self.anti_stack_penalty = tech_cfg.anti_pattern_penalty

        # Cover letter templates sorted by priority descending
        self.cover_templates = sorted(
            self.profile.evaluation_and_scoring_rubric.cover_letter_templates,
            key=lambda t: t.priority,
            reverse=True
        )
        self.compiled_cover_templates = [
            (t.title, [re.compile(p, re.IGNORECASE) for p in t.trigger_patterns], t.talking_points)
            for t in self.cover_templates
        ]

        # Company tiers lookup
        tiers = self.profile.target_companies_and_domains.company_tiers
        self.tier1_map = {item.name.lower(): item for item in tiers.tier_1_dream}
        self.tier2_map = {item.name.lower(): item for item in tiers.tier_2_high_priority}
        self.tier3_map = {item.name.lower(): item for item in tiers.tier_3_neutral}
        self.excluded_companies = [c.lower() for c in tiers.excluded_companies]

    def is_senior_role(self, title: str) -> bool:
        """Determine whether job title denotes a disallowed seniority level."""
        if not title or not self.senior_regex:
            return False
        return bool(self.senior_regex.search(title))

    def get_disallowed_seniority_match(self, title: str) -> Optional[str]:
        """Return the matched disallowed seniority token if present, else None."""
        if not title or not self.senior_regex:
            return None
        m = self.senior_regex.search(title)
        return m.group(0) if m else None

    def is_target_location(self, location: str) -> bool:
        """Check whether a location matches candidate's geographic criteria."""
        if not location or location.strip() == "":
            return True

        loc = location.strip()
        loc_cfg = self.profile.candidate_preferences.locations

        # Check remote settings
        is_remote = any(rgx.search(loc) for rgx in self.remote_regexes)
        if is_remote and loc_cfg.remote.allow_remote:
            return True
        if loc_cfg.remote.remote_only:
            return is_remote

        # Check if in US target hubs
        if any(rgx.search(loc) for rgx in self.us_hub_regexes):
            return True

        # Check if location matches any target tier pattern
        matches_target_tier = any(
            any(rgx.search(loc) for rgx in rgx_list)
            for _, _, rgx_list in self.location_tier_regexes
        )

        # Check if matching an excluded location pattern
        matches_excluded = any(rgx.search(loc) for rgx in self.excluded_loc_regexes)

        if matches_excluded:
            # If excluded token is present, only accept if target tier or US hub is also explicitly matched
            return matches_target_tier

        return matches_target_tier or (not self.location_tier_regexes)

    def get_location_category(self, location: str) -> str:
        """Classify location into candidate's configured primary region categories."""
        loc = (location or "").strip()
        if not loc:
            return "Unknown"

        # Check configured tiers in priority order (Netherlands, UK, Australia, US hubs before Remote)
        for name, _, rgx_list in self.location_tier_regexes:
            if any(rgx.search(loc) for rgx in rgx_list):
                return name

        # Then check remote
        if any(rgx.search(loc) for rgx in self.remote_regexes):
            return "Remote"

        return "Europe (Other)"

    def score_job(
        self,
        title: str,
        location: str,
        description: str = "",
        company_name: str = "",
        allow_senior: bool = False
    ) -> JobScoreResult:
        """
        Evaluate and score a job posting against the personalization profile.

        Args:
            title: Job position title.
            location: Job location string.
            description: Job description or summary text.
            company_name: Name of hiring company.
            allow_senior: If True, bypass strict seniority exclusion (used for manual additions).

        Returns:
            JobScoreResult object with score, rationale tags, and letter recommendation.
        """
        rubric = self.profile.evaluation_and_scoring_rubric
        seniority_cfg = self.profile.candidate_preferences.seniority
        loc_cfg = self.profile.candidate_preferences.locations

        is_senior = self.is_senior_role(title)
        disallowed_token = self.get_disallowed_seniority_match(title)
        is_target_loc = self.is_target_location(location)

        # 1. Strict Seniority Exclusion
        if not allow_senior and seniority_cfg.strict_exclusion and is_senior:
            reason = (
                f"Seniority level '{disallowed_token}' strictly excluded by candidate profile"
                if disallowed_token
                else "Seniority level strictly excluded by candidate profile"
            )
            return JobScoreResult(
                score=0.0,
                reasons=[reason],
                matched_skills=[],
                recommended_letter="EXCLUDED (Seniority)",
                location_category=self.get_location_category(location),
                is_target_location=is_target_loc,
                is_senior=True,
                is_active=False,
                company_tier=None,
                company_multiplier=1.0,
                talking_points=[]
            )

        # 2. Excluded Company Check
        company_lower = (company_name or "").strip().lower()
        if any(ex in company_lower for ex in self.excluded_companies):
            return JobScoreResult(
                score=0.0,
                reasons=[f"Company '{company_name}' is in candidate exclusion blacklist"],
                matched_skills=[],
                recommended_letter="EXCLUDED (Company)",
                location_category=self.get_location_category(location),
                is_target_location=is_target_loc,
                is_senior=is_senior,
                is_active=False,
                company_tier="Excluded",
                company_multiplier=0.0,
                talking_points=[]
            )

        text = f"{title} {description}".lower()
        reasons: List[str] = []
        score = rubric.base_score

        # 3. Location Scoring — driven by profile tier weights
        loc_category = self.get_location_category(location)
        loc_scored = False

        # Check configured location tiers (uses profile-defined weights)
        for name, weight, rgx_list in self.location_tier_regexes:
            if name == loc_category:
                score += weight
                reasons.append(f"{name} (+{weight:.0f} pts)")
                loc_scored = True
                break

        # Fallback: check remote patterns if remote is accepted
        if not loc_scored and loc_cfg.remote.allow_remote:
            if any(rgx.search(location) for rgx in self.remote_regexes):
                score += loc_cfg.remote.bonus_points
                reasons.append(f"Remote (+{loc_cfg.remote.bonus_points:.0f} pts)")
                loc_scored = True

        # 4. Target Role Matching — driven by profile target_roles weights
        for role_title, role_weight, rgx_list in self.role_patterns:
            if any(rgx.search(text) for rgx in rgx_list):
                score += role_weight
                reasons.append(f"Target role: {role_title} (+{role_weight:.0f} pts)")
                break

        # 5. Seniority / Entry-Level Bonus
        # Only award entry-level bonus if role does not have a disallowed seniority
        if not is_senior:
            for rgx in self.entry_level_regexes:
                m = rgx.search(text)
                if m:
                    matched_str = m.group(0)
                    if not (self.senior_regex and self.senior_regex.search(matched_str)):
                        score += seniority_cfg.entry_level_bonus
                        reasons.append(f"Graduate/Entry friendly (+{seniority_cfg.entry_level_bonus:.0f} pts)")
                        break

        # 6. Technical Skills Matching
        matched_skills: List[str] = []
        for cat_name, cat_weight, rgx_list in self.skill_categories:
            if any(rgx.search(text) for rgx in rgx_list):
                score += cat_weight
                if cat_name == "Python Mastery":
                    matched_skills.append("🐍 Python Mastery")
                else:
                    matched_skills.append(cat_name)

        if matched_skills:
            reasons.append(f"Skills: {', '.join(matched_skills)}")

        # 7. Preferred & Excluded Domains (if enabled in rubric)
        if rubric.enable_domain_bonuses:
            for domain_name, weight, rgx_list in self.preferred_domains:
                if any(rgx.search(text) for rgx in rgx_list):
                    score += weight
                    reasons.append(f"Target Domain: {domain_name} (+{weight:.0f} pts)")
                    break

            for domain_name, penalty, rgx_list in self.excluded_domains:
                if any(rgx.search(text) for rgx in rgx_list):
                    score += penalty
                    reasons.append(f"Excluded Domain: {domain_name} ({penalty:.0f} pts)")
                    break

        # 8. Tech Stack Anti-Pattern Check
        for rgx in self.anti_stack_regexes:
            if rgx.search(text):
                score += self.anti_stack_penalty
                reasons.append(f"Anti-pattern Tech Stack ({self.anti_stack_penalty:.0f} pts)")
                break

        # 9. Penalties
        for pen_name, deduction, rgx, pen_reason in self.penalties:
            if rgx.search(text):
                score += deduction  # deduction is negative
                reasons.append(pen_reason or f"{pen_name} ({deduction:.0f} pts)")

        # 10. Company Tier Multiplier & Bonus
        company_tier = None
        multiplier = 1.0

        for tier1_name, item in self.tier1_map.items():
            if tier1_name in company_lower:
                company_tier = "Tier 1 Dream"
                multiplier = item.multiplier
                if rubric.enable_company_multipliers and item.bonus_points:
                    score += item.bonus_points
                    reasons.append(f"Tier 1 Employer Bonus: {item.name} (+{item.bonus_points:.0f} pts)")
                break

        if not company_tier:
            for tier2_name, item in self.tier2_map.items():
                if tier2_name in company_lower:
                    company_tier = "Tier 2 High Priority"
                    multiplier = item.multiplier
                    if rubric.enable_company_multipliers and item.bonus_points:
                        score += item.bonus_points
                        reasons.append(f"Tier 2 Employer Bonus: {item.name} (+{item.bonus_points:.0f} pts)")
                    break

        if not company_tier:
            for tier3_name, item in self.tier3_map.items():
                if tier3_name in company_lower:
                    company_tier = "Tier 3 Neutral"
                    multiplier = item.multiplier
                    if rubric.enable_company_multipliers and item.bonus_points:
                        score += item.bonus_points
                        reasons.append(f"Tier 3 Employer Bonus: {item.name} (+{item.bonus_points:.0f} pts)")
                    break

        if rubric.enable_company_multipliers and multiplier != 1.0:
            score = score * multiplier
            reasons.append(f"Employer Multiplier ({multiplier}x)")

        # Normalization and clamping
        final_score = max(5.0, min(rubric.max_score, round(score, 1)))

        # 11. Tailored Cover Letter Template Recommendation
        recommended_letter = rubric.default_cover_letter
        selected_talking_points: List[str] = []

        for template_title, rgx_list, talking_pts in self.compiled_cover_templates:
            if any(rgx.search(text) for rgx in rgx_list):
                recommended_letter = template_title
                selected_talking_points = talking_pts
                break

        is_active = final_score >= rubric.min_match_threshold

        return JobScoreResult(
            score=final_score,
            reasons=reasons,
            matched_skills=matched_skills,
            recommended_letter=recommended_letter,
            location_category=loc_category,
            is_target_location=is_target_loc,
            is_senior=is_senior,
            is_active=is_active,
            company_tier=company_tier,
            company_multiplier=multiplier,
            talking_points=selected_talking_points
        )
