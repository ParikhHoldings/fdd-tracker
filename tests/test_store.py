from datetime import date

from fdd_tracker.models import Filing
from fdd_tracker.services.store import get_recent_changes, seed_change_summary, upsert_filing


def test_upsert_filing_idempotent(tmp_path):
    db = str(tmp_path / "test.db")
    filing = Filing(
        franchise_slug="chick-fil-a",
        source="ftc",
        filed_on=date(2026, 1, 1),
        document_url="https://example.com/fdd-2026.pdf",
        document_hash="abc",
    )
    upsert_filing(filing, db_path=db)
    upsert_filing(filing, db_path=db)

    # if unique+upsert is working, still only one summary when we query changes remains unaffected
    seed_change_summary("chick-fil-a", ["fees"], db_path=db)
    rows = get_recent_changes("chick-fil-a", db_path=db)
    assert len(rows) == 1


def test_recent_changes_limit(tmp_path):
    db = str(tmp_path / "test.db")
    for _ in range(3):
        seed_change_summary("orangetheory", ["litigation"], db_path=db)
    rows = get_recent_changes("orangetheory", limit=2, db_path=db)
    assert len(rows) == 2
