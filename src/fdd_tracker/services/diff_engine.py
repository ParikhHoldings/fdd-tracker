from __future__ import annotations

from difflib import SequenceMatcher

CATEGORY_KEYWORDS = {
    "fees": ["initial franchise fee", "royalty", "transfer fee"],
    "litigation": ["litigation", "lawsuit", "arbitration"],
    "financials": ["item 19", "average unit volume", "auv"],
    "unit_counts": ["units", "open locations", "closed locations"],
}


def categorize_changes(old_text: str, new_text: str) -> list[str]:
    merged = f"{old_text}\n{new_text}".lower()
    matched = [cat for cat, kws in CATEGORY_KEYWORDS.items() if any(k in merged for k in kws)]
    return sorted(set(matched))


def change_ratio(old_text: str, new_text: str) -> float:
    return 1.0 - SequenceMatcher(None, old_text, new_text).ratio()
