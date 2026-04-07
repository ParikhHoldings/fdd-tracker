from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class FTCFilingRecord:
    franchise_name: str
    filing_url: str
    filed_on: str | None


def fetch_ftc_filings(path: str | None = None) -> Iterable[FTCFilingRecord]:
    """Load FTC filing records from a JSON file.

    Args:
        path: Path to JSON file. Defaults to data/sources/ftc_filings.json.

    Returns:
        Iterable of FTCFilingRecord. Empty list if file is missing.
    """
    if path is None:
        repo_root = Path(__file__).resolve().parents[3]
        path = str(repo_root / "data" / "sources" / "ftc_filings.json")

    file_path = Path(path)
    if not file_path.exists():
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [
        FTCFilingRecord(
            franchise_name=record["franchise_name"],
            filing_url=record["filing_url"],
            filed_on=record.get("filed_on"),
        )
        for record in data
    ]
