from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path

from fdd_tracker.ingestion.ftc import FTCFilingRecord, fetch_ftc_filings
from fdd_tracker.ingestion.state_portals import (
    StatePortalRecord,
    fetch_live_state_filings,
    fetch_state_filings,
)
from fdd_tracker.models import Filing
from fdd_tracker.services.store import upsert_filing


def slugify(name: str) -> str:
    """Convert franchise name to URL-friendly slug.

    Lowercase, replace non-alphanumeric with hyphens, strip leading/trailing hyphens.
    """
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def _parse_date(date_str: str | None) -> date | None:
    """Parse ISO date string to date object."""
    if not date_str:
        return None
    return date.fromisoformat(date_str)


def run_ingestion(
    states: list[str] | None = None,
    ftc_path: str | None = None,
    state_path: str | None = None,
    db_path: str | None = None,
) -> dict:
    """Run full ingestion from FTC and state portal sources.

    Args:
        states: Optional list of state codes to filter state filings.
        ftc_path: Optional path to FTC JSON file.
        state_path: Optional path to state filings JSON file.
        db_path: Optional database path for testing.

    Returns:
        Summary dict with counts: total_seen, inserted_or_updated, sources_breakdown.
    """
    ftc_records = list(fetch_ftc_filings(path=ftc_path))
    state_records = list(fetch_state_filings(states=states, path=state_path))

    total_seen = len(ftc_records) + len(state_records)
    inserted_or_updated = 0
    sources_breakdown = {"ftc": 0, "state": 0}

    for record in ftc_records:
        filing = _ftc_to_filing(record)
        changed = upsert_filing(filing, db_path=db_path)
        if changed > 0:
            inserted_or_updated += 1
            sources_breakdown["ftc"] += 1

    for record in state_records:
        filing = _state_to_filing(record)
        changed = upsert_filing(filing, db_path=db_path)
        if changed > 0:
            inserted_or_updated += 1
            sources_breakdown["state"] += 1

    return {
        "total_seen": total_seen,
        "inserted_or_updated": inserted_or_updated,
        "sources_breakdown": sources_breakdown,
    }


def _ftc_to_filing(record: FTCFilingRecord) -> Filing:
    """Convert FTC record to Filing model."""
    return Filing(
        franchise_slug=slugify(record.franchise_name),
        source="ftc",
        filed_on=_parse_date(record.filed_on),
        document_url=record.filing_url,
        document_hash=None,
    )


def _state_to_filing(record: StatePortalRecord) -> Filing:
    """Convert state portal record to Filing model."""
    return Filing(
        franchise_slug=slugify(record.franchise_name),
        source=f"state-{record.state.lower()}",
        filed_on=_parse_date(record.filed_on),
        document_url=record.filing_url,
        document_hash=None,
    )


# ---------------------------------------------------------------------------
# State source cache refresh
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_PATH = "data/sources/state_filings.json"


def refresh_state_source_cache(
    states: list[str] | None = None,
    output_path: str | None = None,
    ca_text: str | None = None,
    il_text: str | None = None,
) -> dict:
    """Fetch live state filings and write to JSON cache file.

    Args:
        states: List of state codes to fetch. Defaults to CA and IL.
        output_path: Output JSON file path. Defaults to data/sources/state_filings.json.
        ca_text: If provided, use this text for CA parsing (for tests).
        il_text: If provided, use this text for IL parsing (for tests).

    Returns:
        Summary dict with keys: written (bool), output_path, records (count).
    """
    if output_path is None:
        repo_root = Path(__file__).resolve().parents[3]
        output_path = str(repo_root / _DEFAULT_CACHE_PATH)

    records = fetch_live_state_filings(
        states=states,
        ca_text=ca_text,
        il_text=il_text,
    )

    # Convert dataclass records to dicts for JSON serialization
    records_dicts = [asdict(r) for r in records]

    # Ensure output directory exists
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(records_dicts, f, indent=2)

    return {
        "written": True,
        "output_path": output_path,
        "records": len(records),
    }
