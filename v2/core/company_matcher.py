"""
company_matcher.py - Profile-Driven Company Tier & Sponsorship Matcher (v2).

Matches employers against user-defined company tiers, industry preferences,
and visa sponsorship registries dynamically derived from the PersonalizationProfile.
"""

from __future__ import annotations

import os
import re
import sqlite3
import logging
from collections import defaultdict
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from v2.profile_schema import PersonalizationProfile

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "the", "and", "for", "bv", "nv", "holding", "holdings", "nederland", "netherlands",
    "group", "europe", "international", "services", "solutions", "technology", "technologies"
}


class CompanyMatchResult(BaseModel):
    """Result of matching a company name against profile tiers and sponsor database."""
    query_name: str
    matched_name: str
    tier: str = Field(default="Standard", description="Tier 1 Dream, Tier 2 High Priority, Neutral, or Excluded")
    multiplier: float = Field(default=1.0, description="Match score multiplier")
    bonus_points: float = Field(default=0.0, description="Bonus score points")
    is_excluded: bool = Field(default=False, description="Whether company is blacklisted")
    is_verified_sponsor: bool = Field(default=False, description="Whether verified in sponsor register")
    kvk: Optional[str] = None
    sector_tags: Optional[str] = None
    ats_type: Optional[str] = None
    reason: Optional[str] = None


class CompanyMatcher:
    """
    Evaluates hiring companies against candidate's company tiers,
    exclusion lists, and target visa sponsorship registers.
    """

    def __init__(self, profile: PersonalizationProfile, db_path: Optional[str] = None):
        self.profile = profile
        self.db_path = db_path or profile.output_settings.sqlite_db_path or "v2/data/sponsors.db"

        tiers_cfg = profile.target_companies_and_domains.company_tiers
        self.tier1_dict = {item.name.lower().strip(): item for item in tiers_cfg.tier_1_dream}
        self.tier2_dict = {item.name.lower().strip(): item for item in tiers_cfg.tier_2_high_priority}
        self.tier3_dict = {item.name.lower().strip(): item for item in tiers_cfg.tier_3_neutral}
        self.excluded_set = {name.lower().strip() for name in tiers_cfg.excluded_companies}

        self._db_loaded = False
        self._exact_cache: Dict[str, Dict[str, Any]] = {}
        self._clean_cache: Dict[str, Dict[str, Any]] = {}
        self._word_index = defaultdict(list)

    def _normalize(self, name: str) -> str:
        name = (name or "").lower().strip()
        name = re.sub(r'\b(b\.?v\.?|n\.?v\.?|holding|holdings|nederland|netherlands|group|europe|international)\b', '', name)
        name = re.sub(r'[^\w\s]', '', name)
        return re.sub(r'\s+', ' ', name).strip()

    def _tokenize(self, text: str) -> List[str]:
        words = re.findall(r'\b[a-z0-9]{3,}\b', text.lower())
        return [w for w in words if w not in STOP_WORDS]

    def _ensure_db_loaded(self):
        """Lazy load the sponsor database on first lookup."""
        if self._db_loaded:
            return
        self._db_loaded = True

        if not self.db_path or not os.path.exists(self.db_path):
            return

        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sponsors'")
            if not cur.fetchone():
                conn.close()
                return

            cur.execute("""
            SELECT id, name, clean_name, kvk, is_target_sector, sector_tags, ats_type, ats_slug
            FROM sponsors
            """)
            for row in cur.fetchall():
                sid, name, clean_name, kvk, target_sec, sector_tags, ats_type, ats_slug = row
                entry = {
                    "id": sid,
                    "name": name,
                    "clean_name": clean_name or name,
                    "kvk": kvk,
                    "is_target_sector": bool(target_sec),
                    "sector_tags": sector_tags,
                    "ats_type": ats_type,
                    "ats_slug": ats_slug
                }
                raw_key = (name or "").lower().strip()
                if raw_key:
                    self._exact_cache[raw_key] = entry
                clean_norm = self._normalize(clean_name or name)
                if clean_norm:
                    self._clean_cache[clean_norm] = entry

                tokens = self._tokenize(clean_norm or raw_key)
                for t in tokens:
                    self._word_index[t].append(entry)

            conn.close()
            logger.info(f"Loaded {len(self._clean_cache)} sponsor records into fast memory cache.")
        except Exception as e:
            logger.debug(f"Sponsor DB load skipped: {e}")

    def match(self, company_name: str) -> CompanyMatchResult:
        """
        Match a company against candidate tiers and sponsor registers.
        """
        name_clean = (company_name or "").strip()
        name_lower = name_clean.lower()
        name_norm = self._normalize(name_clean)

        # 1. Check Exclusion Blacklist
        for ex in self.excluded_set:
            if ex in name_lower or self._normalize(ex) in name_norm:
                return CompanyMatchResult(
                    query_name=name_clean,
                    matched_name=name_clean,
                    tier="Excluded",
                    multiplier=0.0,
                    bonus_points=-100.0,
                    is_excluded=True,
                    is_verified_sponsor=False,
                    reason="Company is blacklisted in candidate profile"
                )

        # 2. Check Candidate Tiers (Tier 1 Dream)
        for t1_name, item in self.tier1_dict.items():
            if t1_name in name_lower or self._normalize(t1_name) in name_norm:
                sponsor_info = self._lookup_sponsor(name_clean)
                return CompanyMatchResult(
                    query_name=name_clean,
                    matched_name=item.name,
                    tier="Tier 1 Dream",
                    multiplier=item.multiplier,
                    bonus_points=item.bonus_points,
                    is_excluded=False,
                    is_verified_sponsor=bool(sponsor_info),
                    kvk=sponsor_info.get("kvk") if sponsor_info else None,
                    sector_tags=sponsor_info.get("sector_tags") if sponsor_info else None,
                    ats_type=item.ats_type or (sponsor_info.get("ats_type") if sponsor_info else None),
                    reason=item.reason or "Candidate Dream Employer"
                )

        # 3. Check Candidate Tiers (Tier 2 High Priority)
        for t2_name, item in self.tier2_dict.items():
            if t2_name in name_lower or self._normalize(t2_name) in name_norm:
                sponsor_info = self._lookup_sponsor(name_clean)
                return CompanyMatchResult(
                    query_name=name_clean,
                    matched_name=item.name,
                    tier="Tier 2 High Priority",
                    multiplier=item.multiplier,
                    bonus_points=item.bonus_points,
                    is_excluded=False,
                    is_verified_sponsor=bool(sponsor_info),
                    kvk=sponsor_info.get("kvk") if sponsor_info else None,
                    sector_tags=sponsor_info.get("sector_tags") if sponsor_info else None,
                    ats_type=item.ats_type or (sponsor_info.get("ats_type") if sponsor_info else None),
                    reason=item.reason or "High Priority Target Employer"
                )

        # 3.5. Check Candidate Tiers (Tier 3 Neutral / Specialized Pipeline)
        for t3_name, item in self.tier3_dict.items():
            if t3_name in name_lower or self._normalize(t3_name) in name_norm:
                sponsor_info = self._lookup_sponsor(name_clean)
                return CompanyMatchResult(
                    query_name=name_clean,
                    matched_name=item.name,
                    tier="Tier 3 Neutral",
                    multiplier=item.multiplier,
                    bonus_points=item.bonus_points,
                    is_excluded=False,
                    is_verified_sponsor=bool(sponsor_info),
                    kvk=sponsor_info.get("kvk") if sponsor_info else None,
                    sector_tags=sponsor_info.get("sector_tags") if sponsor_info else None,
                    ats_type=item.ats_type or (sponsor_info.get("ats_type") if sponsor_info else None),
                    reason=item.reason or "Specialized Pipeline Target Employer"
                )

        # 4. Standard / Neutral Company lookup
        sponsor_info = self._lookup_sponsor(name_clean)
        is_sponsor = bool(sponsor_info)
        bonus = self.profile.candidate_preferences.sponsorship.sponsor_match_bonus if is_sponsor else 0.0

        return CompanyMatchResult(
            query_name=name_clean,
            matched_name=sponsor_info["clean_name"] if sponsor_info else name_clean,
            tier="Verified Sponsor" if is_sponsor else "Standard",
            multiplier=1.0,
            bonus_points=bonus,
            is_excluded=False,
            is_verified_sponsor=is_sponsor,
            kvk=sponsor_info.get("kvk") if sponsor_info else None,
            sector_tags=sponsor_info.get("sector_tags") if sponsor_info else None,
            ats_type=sponsor_info.get("ats_type") if sponsor_info else None,
            reason="Verified Recognised Sponsor" if is_sponsor else "Standard Employer"
        )

    def _lookup_sponsor(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Look up company in the sponsor database using exact, clean, or token index."""
        if not company_name:
            return None
        self._ensure_db_loaded()

        raw_key = company_name.lower().strip()
        if raw_key in self._exact_cache:
            return self._exact_cache[raw_key]

        clean_input = self._normalize(company_name)
        if clean_input in self._clean_cache:
            return self._clean_cache[clean_input]

        tokens = self._tokenize(clean_input)
        for t in tokens:
            candidates = self._word_index.get(t, [])
            for cand in candidates:
                cand_clean = self._normalize(cand["clean_name"])
                if clean_input == cand_clean or f" {clean_input} " in f" {cand_clean} " or f" {cand_clean} " in f" {clean_input} ":
                    return cand

        return None

    # Alias for API compatibility
    evaluate_employer = match
