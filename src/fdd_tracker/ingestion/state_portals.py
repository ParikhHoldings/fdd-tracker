from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class StatePortalRecord:
    state: str
    franchise_name: str
    filing_url: str
    filed_on: str | None


def fetch_state_filings(states: list[str] | None = None, path: str | None = None) -> Iterable[StatePortalRecord]:
    """Load state portal filing records from a JSON file.

    Args:
        states: Optional list of state codes to filter by.
        path: Path to JSON file. Defaults to data/sources/state_filings.json.

    Returns:
        Iterable of StatePortalRecord. Empty list if file is missing.
    """
    if path is None:
        repo_root = Path(__file__).resolve().parents[3]
        path = str(repo_root / "data" / "sources" / "state_filings.json")

    file_path = Path(path)
    if not file_path.exists():
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = [
        StatePortalRecord(
            state=record["state"],
            franchise_name=record["franchise_name"],
            filing_url=record["filing_url"],
            filed_on=record.get("filed_on"),
        )
        for record in data
    ]

    if states:
        records = [r for r in records if r.state in states]

    return records
