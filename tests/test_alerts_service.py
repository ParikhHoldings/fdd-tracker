from pathlib import Path

from fdd_tracker.services.alerts import dispatch_outbox, list_outbox, run_digest_for_all_emails, run_digest_for_email
from fdd_tracker.services.store import get_alert_feed, seed_change_summary, upsert_watchlist


def test_run_digest_for_email_writes_outbox_and_optionally_marks_read(tmp_path):
    db = str(tmp_path / "test.db")
    outbox = tmp_path / "alert_outbox.jsonl"

    upsert_watchlist("digest@example.com", "chick-fil-a", db_path=db)
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high", db_path=db)

    result = run_digest_for_email(
        "digest@example.com",
        max_alerts=10,
        mark_read=True,
        db_path=db,
        outbox_path=str(outbox),
    )

    assert result["sent"] is True
    assert result["unread_count"] == 1
    assert result["marked_read"] == 1

    assert outbox.exists()
    unread = get_alert_feed("digest@example.com", unread_only=True, db_path=db)
    assert len(unread) == 0


def test_run_digest_for_all_emails(tmp_path):
    db = str(tmp_path / "test.db")
    upsert_watchlist("a@example.com", "chick-fil-a", db_path=db)
    upsert_watchlist("b@example.com", "orangetheory", db_path=db)
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high", db_path=db)
    seed_change_summary("orangetheory", ["litigation"], risk_level="medium", db_path=db)

    result = run_digest_for_all_emails(max_alerts=10, mark_read=False, db_path=db, outbox_path=str(tmp_path / "outbox.jsonl"))
    assert result["emails_scanned"] == 2
    assert result["digests_sent"] == 2
    assert len(result["results"]) == 2



def test_outbox_list_and_dispatch(tmp_path):
    db = str(tmp_path / "test.db")
    outbox = tmp_path / "alert_outbox.jsonl"
    sent = tmp_path / "alert_outbox_sent.jsonl"

    upsert_watchlist("dispatch@example.com", "chick-fil-a", db_path=db)
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high", db_path=db)

    run_digest_for_email("dispatch@example.com", max_alerts=10, mark_read=False, db_path=db, outbox_path=str(outbox))

    items = list_outbox(limit=10, outbox_path=str(outbox))
    assert len(items) >= 1

    result = dispatch_outbox(limit=1, outbox_path=str(outbox), sent_path=str(sent))
    assert result["dispatched"] >= 1
