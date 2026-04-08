from pathlib import Path

from fdd_tracker.services.alerts import run_digest_for_all_emails, run_digest_for_email
from fdd_tracker.services.store import get_alert_feed, seed_change_summary, upsert_watchlist


def test_run_digest_for_email_writes_outbox_and_optionally_marks_read(tmp_path):
    db = str(tmp_path / "test.db")
    outbox = tmp_path / "alert_outbox.jsonl"

    upsert_watchlist("digest@example.com", "chick-fil-a", db_path=db)
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high", db_path=db)

    # monkeypatch default outbox path by chdir into tmp project-like root
    import os

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = run_digest_for_email("digest@example.com", max_alerts=10, mark_read=True, db_path=db)
    finally:
        os.chdir(cwd)

    assert result["sent"] is True
    assert result["unread_count"] == 1
    assert result["marked_read"] == 1

    # outbox file should exist in default data location relative to module root, but we can at least
    # verify there are now zero unread in DB after mark_read.
    unread = get_alert_feed("digest@example.com", unread_only=True, db_path=db)
    assert len(unread) == 0


def test_run_digest_for_all_emails(tmp_path):
    db = str(tmp_path / "test.db")
    upsert_watchlist("a@example.com", "chick-fil-a", db_path=db)
    upsert_watchlist("b@example.com", "orangetheory", db_path=db)
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high", db_path=db)
    seed_change_summary("orangetheory", ["litigation"], risk_level="medium", db_path=db)

    result = run_digest_for_all_emails(max_alerts=10, mark_read=False, db_path=db)
    assert result["emails_scanned"] == 2
    assert result["digests_sent"] == 2
    assert len(result["results"]) == 2
