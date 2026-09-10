#!/usr/bin/env python3
"""
sponsor_matcher.py - High-performance cross-referencing of employer names
against the 12,927 IND Recognised Sponsors using inverted word indexing.
"""

import os
import re
import sqlite3
import logging
from collections import defaultdict
from typing import Dict, Any, Optional, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sponsors.db"))

STOP_WORDS = {
    "the", "and", "for", "bv", "nv", "holding", "holdings", "nederland", "netherlands",
    "group", "europe", "international", "services", "solutions", "technology", "technologies"
}


class SponsorMatcher:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._exact_cache = {}
        self._clean_cache = {}
        self._word_index = defaultdict(list)
        self._load_cache()

    def _normalize(self, name: str) -> str:
        name = name.lower().strip()
        name = re.sub(r'\b(b\.?v\.?|n\.?v\.?|holding|holdings|nederland|netherlands|group|europe|international)\b', '', name)
        name = re.sub(r'[^\w\s]', '', name)
        return re.sub(r'\s+', ' ', name).strip()

    def _tokenize(self, text: str) -> List[str]:
        words = re.findall(r'\b[a-z0-9]{3,}\b', text.lower())
        return [w for w in words if w not in STOP_WORDS]

    def _load_cache(self):
        if not os.path.exists(self.db_path):
            return
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, name, clean_name, kvk, is_target_sector, sector_tags FROM sponsors")
        rows = cur.fetchall()
        conn.close()

        for sp_id, full_name, clean_name, kvk, is_target, tags in rows:
            entry = {
                "id": sp_id,
                "name": full_name,
                "clean_name": clean_name,
                "kvk": kvk,
                "is_target_sector": bool(is_target),
                "sector_tags": tags
            }
            # 1. Exact lowercase
            self._exact_cache[full_name.lower().strip()] = entry
            
            # 2. Normalized
            clean_norm = self._normalize(clean_name)
            if clean_norm:
                self._clean_cache[clean_norm] = entry

            # 3. Inverted index of words
            tokens = self._tokenize(clean_norm or full_name)
            for token in tokens:
                self._word_index[token].append(entry)

    def match(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Instant O(1) matching with token intersection."""
        if not company_name:
            return None

        # 1. Exact
        raw_key = company_name.lower().strip()
        if raw_key in self._exact_cache:
            return self._exact_cache[raw_key]

        # 2. Normalized
        clean_input = self._normalize(company_name)
        if clean_input in self._clean_cache:
            return self._clean_cache[clean_input]

        # 3. Token-based lookup
        tokens = self._tokenize(clean_input)
        if not tokens:
            return None

        # Find candidates matching primary token
        for t in tokens:
            candidates = self._word_index.get(t, [])
            for cand in candidates:
                cand_clean = self._normalize(cand["clean_name"])
                # Require clean input equals cand_clean or is exact word in cand_clean
                if clean_input == cand_clean or f" {clean_input} " in f" {cand_clean} " or f" {cand_clean} " in f" {clean_input} ":
                    return cand

        return None


if __name__ == "__main__":
    matcher = SponsorMatcher()
    tests = ["ASML", "Picnic", "TomTom", "Mollie", "Uber", "Random Non-Sponsor Bakery"]
    for t in tests:
        res = matcher.match(t)
        print(f"'{t}' -> {res['name'] if res else 'None'}")
