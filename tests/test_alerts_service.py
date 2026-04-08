import json
from pathlib import Path

from fdd_tracker.services.alerts import dispatch_outbox, list_outbox, retry_failed_outbox, run_alerts_cron_tick, run_digest_for_all_emails, run_digest_for_email
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
        run_id="run-123",
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



def test_dispatch_outbox_failure_bucket_and_retry(tmp_path):
    outbox = tmp_path / "alert_outbox.jsonl"
    sent = tmp_path / "alert_outbox_sent.jsonl"
    failed = tmp_path / "alert_outbox_failed.jsonl"

    rows = [
        {"email": "ok@example.com", "subject": "ok", "body": "ok", "generated_at": "2026-01-01T00:00:00Z"},
        {"email": "fail@example.com", "subject": "fail", "body": "fail", "generated_at": "2026-01-01T00:00:00Z", "force_fail": True},
    ]
    outbox.write_text("\n".join(__import__("json").dumps(r) for r in rows) + "\n", encoding="utf-8")

    dispatch = dispatch_outbox(limit=10, outbox_path=str(outbox), sent_path=str(sent), failed_path=str(failed))
    assert dispatch["dispatched"] == 1
    assert dispatch["failed"] == 1

    retry = retry_failed_outbox(limit=10, failed_path=str(failed), outbox_path=str(outbox))
    assert retry["retried"] == 1
    retried_row = json.loads(outbox.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert retried_row["retry_count"] >= 1
    assert "retried_at" in retried_row

    dispatch2 = dispatch_outbox(limit=10, outbox_path=str(outbox), sent_path=str(sent), failed_path=str(failed))
    assert dispatch2["dispatched"] == 1
    assert dispatch2["failed"] == 0



def test_digest_records_include_run_metadata(tmp_path):
    db = str(tmp_path / "test.db")
    outbox = tmp_path / "alert_outbox.jsonl"
    sent = tmp_path / "alert_outbox_sent.jsonl"

    upsert_watchlist("meta@example.com", "chick-fil-a", db_path=db)
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high", db_path=db)

    run_digest_for_email("meta@example.com", db_path=db, outbox_path=str(outbox), run_id="meta-run")
    queued = list_outbox(limit=10, outbox_path=str(outbox))
    assert queued[-1]["run_id"] == "meta-run"
    assert "queued_at" in queued[-1]

    dispatch_outbox(limit=10, outbox_path=str(outbox), sent_path=str(sent), failed_path=str(tmp_path / "failed.jsonl"))
    sent_rows = [json.loads(line) for line in sent.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert sent_rows[-1]["run_id"] == "meta-run"
    assert "dispatched_at" in sent_rows[-1]



def test_run_alerts_cron_tick(tmp_path):
    db = str(tmp_path / "test.db")
    upsert_watchlist("cron@example.com", "chick-fil-a", db_path=db)
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high", db_path=db)

    result = run_alerts_cron_tick(
        max_alerts=10,
        generate_mark_read=False,
        dispatch_limit=10,
        retry_limit=10,
        db_path=db,
        run_id="cron-test-run",
    )
    assert result["run_id"] == "cron-test-run"
    assert "generated" in result and "dispatched" in result and "retried" in result
    assert result["generated"]["digests_sent"] >= 1
