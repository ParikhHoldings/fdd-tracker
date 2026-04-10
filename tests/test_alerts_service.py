import json
from pathlib import Path

from fdd_tracker.services.alerts import dispatch_outbox, list_cron_history, list_outbox, prune_alert_artifacts, retry_failed_outbox, run_alerts_cron_tick, run_digest_for_all_emails, run_digest_for_email
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



def test_cron_history_written_and_listed(tmp_path):
    db = str(tmp_path / "test.db")
    history = tmp_path / "alerts_cron_history.jsonl"
    upsert_watchlist("history@example.com", "chick-fil-a", db_path=db)
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high", db_path=db)

    result = run_alerts_cron_tick(
        max_alerts=10,
        dispatch_limit=10,
        retry_limit=10,
        db_path=db,
        run_id="history-run",
        history_path=str(history),
    )
    assert result["run_id"] == "history-run"
    assert history.exists()

    rows = list_cron_history(limit=10, history_path=str(history))
    assert len(rows) >= 1
    assert rows[-1]["run_id"] == "history-run"
    assert "ran_at" in rows[-1]



def test_prune_alert_artifacts(tmp_path):
    outbox = tmp_path / "alert_outbox.jsonl"
    sent = tmp_path / "alert_outbox_sent.jsonl"
    failed = tmp_path / "alert_outbox_failed.jsonl"
    history = tmp_path / "alerts_cron_history.jsonl"

    sample = "{\"k\":1}\n{\"k\":2}\n{\"k\":3}\n"
    outbox.write_text(sample, encoding="utf-8")
    sent.write_text(sample, encoding="utf-8")
    failed.write_text(sample, encoding="utf-8")
    history.write_text(sample, encoding="utf-8")

    result = prune_alert_artifacts(
        outbox_keep_last=1,
        sent_keep_last=2,
        failed_keep_last=0,
        history_keep_last=2,
        outbox_path=str(outbox),
        sent_path=str(sent),
        failed_path=str(failed),
        history_path=str(history),
    )

    assert result["outbox"]["after"] == 1
    assert result["sent"]["after"] == 2
    assert result["failed"]["after"] == 0
    assert result["history"]["after"] == 2


def test_cron_lock_acquire_and_release(tmp_path):
    from fdd_tracker.services.alerts import acquire_cron_lock, release_cron_lock

    lock = tmp_path / "alerts_cron.lock"
    acquired = acquire_cron_lock("run-1", lock_path=str(lock), stale_after_seconds=900)
    assert acquired["acquired"] is True
    assert lock.exists()

    released = release_cron_lock("run-1", lock_path=str(lock))
    assert released["released"] is True
    assert not lock.exists()


def test_cron_lock_blocks_second_run(tmp_path):
    from fdd_tracker.services.alerts import acquire_cron_lock

    lock = tmp_path / "alerts_cron.lock"
    first = acquire_cron_lock("run-1", lock_path=str(lock), stale_after_seconds=900)
    second = acquire_cron_lock("run-2", lock_path=str(lock), stale_after_seconds=900)

    assert first["acquired"] is True
    assert second["acquired"] is False
    assert second["lock"]["run_id"] == "run-1"


def test_cron_lock_recovers_stale_lock(tmp_path):
    from fdd_tracker.services.alerts import acquire_cron_lock

    lock = tmp_path / "alerts_cron.lock"
    lock.write_text('{"run_id":"old-run","acquired_at":"2000-01-01T00:00:00+00:00","pid":1}', encoding="utf-8")

    recovered = acquire_cron_lock("new-run", lock_path=str(lock), stale_after_seconds=60)
    assert recovered["acquired"] is True
    assert recovered.get("stale_replaced", {}).get("run_id") == "old-run"


def test_run_alerts_cron_tick_skips_when_locked(tmp_path):
    from fdd_tracker.services.alerts import run_alerts_cron_tick

    db = str(tmp_path / "test.db")
    history = tmp_path / "history.jsonl"
    lock = tmp_path / "alerts_cron.lock"
    lock.write_text('{"run_id":"active-run","acquired_at":"2999-01-01T00:00:00+00:00","pid":1}', encoding="utf-8")

    result = run_alerts_cron_tick(
        db_path=db,
        history_path=str(history),
        lock_path=str(lock),
        run_id="blocked-run",
        lock_stale_after_seconds=900,
    )

    assert result["status"] == "skipped_locked"
    assert result["lock"]["acquired"] is False
    assert result["lock"]["lock"]["run_id"] == "active-run"
    assert history.exists()


def test_dispatch_outbox_includes_delivery_metadata(tmp_path):
    outbox = tmp_path / "alert_outbox.jsonl"
    sent = tmp_path / "alert_outbox_sent.jsonl"

    outbox.write_text("""{"email":"meta@example.com","subject":"x","body":"y","generated_at":"2026-01-01T00:00:00Z","run_id":"run-meta"}
""", encoding="utf-8")
    result = dispatch_outbox(limit=10, outbox_path=str(outbox), sent_path=str(sent), dry_run=True, provider="noop")

    assert result["dispatched"] == 1
    assert result["validation"]["ok"] is True
    sent_row = json.loads(sent.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert sent_row["delivery_mode"] == "dry_run"
    assert sent_row["delivery_provider"] == "noop"
    assert sent_row["delivery_status"] == "simulated_sent"
    assert "provider_message_id" in sent_row


def test_validate_dispatch_provider_catalog_and_rejection():
    from fdd_tracker.services.alerts import get_dispatch_provider_catalog, validate_dispatch_provider

    catalog = get_dispatch_provider_catalog()
    assert "noop" in catalog["providers"]
    assert catalog["default"] == "noop"

    ok = validate_dispatch_provider("noop", dry_run=True)
    assert ok["ok"] is True

    bad = validate_dispatch_provider("unknown", dry_run=True)
    assert bad["ok"] is False
    assert bad["reason"] == "unsupported-provider"


def test_dispatch_outbox_rejects_unsupported_provider(tmp_path):
    outbox = tmp_path / "alert_outbox.jsonl"
    outbox.write_text('{"email":"x@example.com","subject":"x","body":"x","generated_at":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")

    result = dispatch_outbox(limit=10, outbox_path=str(outbox), provider="invalid-provider", dry_run=True)
    assert result["dispatched"] == 0
    assert result["remaining"] == 1
    assert result["error"]["reason"] == "unsupported-provider"


def test_get_alerts_cron_status_counts_and_lock(tmp_path):
    from fdd_tracker.services.alerts import get_alerts_cron_status

    outbox = tmp_path / "alert_outbox.jsonl"
    sent = tmp_path / "alert_outbox_sent.jsonl"
    failed = tmp_path / "alert_outbox_failed.jsonl"
    history = tmp_path / "alerts_cron_history.jsonl"
    lock = tmp_path / "alerts_cron.lock"

    outbox.write_text('{"a":1}\n{"a":2}\n', encoding='utf-8')
    sent.write_text('{"a":1}\n', encoding='utf-8')
    failed.write_text('', encoding='utf-8')
    history.write_text('{"run_id":"x"}\n', encoding='utf-8')
    lock.write_text('{"run_id":"active-run","acquired_at":"2999-01-01T00:00:00+00:00","pid":1}', encoding='utf-8')

    status = get_alerts_cron_status(
        outbox_path=str(outbox),
        sent_path=str(sent),
        failed_path=str(failed),
        history_path=str(history),
        lock_path=str(lock),
        lock_stale_after_seconds=900,
    )

    assert status['counts']['outbox'] == 2
    assert status['counts']['sent'] == 1
    assert status['counts']['history'] == 1
    assert status['lock']['present'] is True
    assert status['lock']['stale'] is False
    assert status['lock']['metadata']['run_id'] == 'active-run'


def test_recover_alerts_cron_lock_stale_and_active(tmp_path):
    from fdd_tracker.services.alerts import recover_alerts_cron_lock

    lock = tmp_path / "alerts_cron.lock"

    # Active lock should not recover without force
    lock.write_text('{"run_id":"active","acquired_at":"2999-01-01T00:00:00+00:00","pid":1}', encoding='utf-8')
    active = recover_alerts_cron_lock(lock_path=str(lock), lock_stale_after_seconds=900, force=False)
    assert active['recovered'] is False
    assert active['reason'] == 'active-lock'
    assert lock.exists()

    # Stale lock should recover
    lock.write_text('{"run_id":"stale","acquired_at":"2000-01-01T00:00:00+00:00","pid":1}', encoding='utf-8')
    stale = recover_alerts_cron_lock(lock_path=str(lock), lock_stale_after_seconds=900, force=False)
    assert stale['recovered'] is True
    assert stale['reason'] == 'stale-lock'
    assert not lock.exists()


def test_recover_alerts_cron_lock_force(tmp_path):
    from fdd_tracker.services.alerts import recover_alerts_cron_lock

    lock = tmp_path / "alerts_cron.lock"
    lock.write_text('{"run_id":"active","acquired_at":"2999-01-01T00:00:00+00:00","pid":1}', encoding='utf-8')

    forced = recover_alerts_cron_lock(lock_path=str(lock), lock_stale_after_seconds=900, force=True)
    assert forced['recovered'] is True
    assert forced['reason'] == 'forced'
    assert not lock.exists()


def test_run_alerts_cron_tick_with_dispatch_config(tmp_path):
    db = str(tmp_path / "test.db")
    upsert_watchlist("croncfg@example.com", "chick-fil-a", db_path=db)
    seed_change_summary("chick-fil-a", ["fees"], risk_level="high", db_path=db)

    result = run_alerts_cron_tick(
        max_alerts=10,
        generate_mark_read=False,
        dispatch_limit=10,
        retry_limit=10,
        dispatch_dry_run=True,
        dispatch_provider="noop",
        db_path=db,
        run_id="cron-config-run",
    )

    assert result["status"] == "executed"
    assert result["dispatched"]["provider"] == "noop"
    assert result["dispatched"]["dry_run"] is True


def test_get_alerts_cron_preflight(tmp_path):
    from fdd_tracker.services.alerts import get_alerts_cron_preflight

    lock = tmp_path / "alerts_cron.lock"
    lock.write_text('{"run_id":"active","acquired_at":"2999-01-01T00:00:00+00:00","pid":1}', encoding='utf-8')

    ready = get_alerts_cron_preflight(
        dispatch_provider='noop',
        dispatch_dry_run=True,
        lock_stale_after_seconds=900,
        lock_path=str(lock),
    )
    assert ready['dispatch']['validation']['ok'] is True
    assert ready['lock']['present'] is True
    assert ready['ready_to_run'] is False

    bad_provider = get_alerts_cron_preflight(
        dispatch_provider='bad-provider',
        dispatch_dry_run=True,
        lock_stale_after_seconds=900,
        lock_path=str(lock),
    )
    assert bad_provider['dispatch']['validation']['ok'] is False
