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




def test_validate_dispatch_provider_resend_live_requires_env(monkeypatch):
    from fdd_tracker.services.alerts import validate_dispatch_provider

    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("ALERTS_FROM_EMAIL", raising=False)

    invalid = validate_dispatch_provider("resend", dry_run=False)
    assert invalid["ok"] is False
    assert invalid["reason"] == "missing-env"


def test_dispatch_outbox_resend_live_success(monkeypatch, tmp_path):
    from fdd_tracker.services import alerts

    outbox = tmp_path / "alert_outbox.jsonl"
    sent = tmp_path / "alert_outbox_sent.jsonl"

    outbox.write_text('{"email":"live@example.com","subject":"x","body":"y","generated_at":"2026-01-01T00:00:00Z"}\n', encoding='utf-8')

    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("ALERTS_FROM_EMAIL", "alerts@example.com")

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"id":"re_123"}'

    monkeypatch.setattr(alerts.urlrequest, "urlopen", lambda req, timeout=15: _Resp())

    result = alerts.dispatch_outbox(
        limit=10,
        outbox_path=str(outbox),
        sent_path=str(sent),
        dry_run=False,
        provider="resend",
    )

    assert result["dispatched"] == 1
    assert result["failed"] == 0
    sent_row = json.loads(sent.read_text(encoding='utf-8').strip())
    assert sent_row["delivery_provider"] == "resend"
    assert sent_row["delivery_mode"] == "live"
    assert sent_row["provider_message_id"] == "re_123"

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


def test_get_latest_cron_history_entry(tmp_path):
    from fdd_tracker.services.alerts import append_cron_history, get_latest_cron_history_entry

    history = tmp_path / "alerts_cron_history.jsonl"
    append_cron_history({"run_id": "r1"}, history_path=str(history))
    append_cron_history({"run_id": "r2"}, history_path=str(history))

    latest = get_latest_cron_history_entry(history_path=str(history))
    assert latest['exists'] is True
    assert latest['item']['run_id'] == 'r2'


def test_run_provider_smoke_test_unknown_provider():
    from fdd_tracker.services.alerts import run_provider_smoke_test

    result = run_provider_smoke_test(provider="unknown-provider", email="x@example.com", dry_run=True)
    assert result["success"] is False
    assert result["validation"]["reason"] == "unsupported-provider"


def test_run_provider_smoke_test_resend_live_success(monkeypatch):
    from fdd_tracker.services import alerts

    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("ALERTS_FROM_EMAIL", "alerts@example.com")

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"id":"re_smoke_123"}'

    monkeypatch.setattr(alerts.urlrequest, "urlopen", lambda req, timeout=15: _Resp())

    result = alerts.run_provider_smoke_test(provider="resend", email="live@example.com", dry_run=False)
    assert result["success"] is True
    assert result["provider"] == "resend"
    assert result["mode"] == "live"
    assert result["provider_message_id"] == "re_smoke_123"


def test_enforce_live_dispatch_gate_blocks_duplicate_idempotency_key(tmp_path):
    from fdd_tracker.services.alerts import enforce_live_dispatch_gate

    guard = tmp_path / "live_dispatch_guard.json"
    first = enforce_live_dispatch_gate(
        provider="resend",
        dry_run=False,
        confirm_live=True,
        idempotency_key="abc123",
        min_interval_seconds=1,
        guard_path=str(guard),
    )
    second = enforce_live_dispatch_gate(
        provider="resend",
        dry_run=False,
        confirm_live=True,
        idempotency_key="abc123",
        min_interval_seconds=1,
        guard_path=str(guard),
    )

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["reason"] == "live-dispatch-duplicate-idempotency-key"


def test_enforce_live_dispatch_gate_rate_limit(tmp_path):
    from fdd_tracker.services.alerts import enforce_live_dispatch_gate

    guard = tmp_path / "live_dispatch_guard.json"
    first = enforce_live_dispatch_gate(
        provider="resend",
        dry_run=False,
        confirm_live=True,
        idempotency_key="first",
        min_interval_seconds=120,
        guard_path=str(guard),
    )
    second = enforce_live_dispatch_gate(
        provider="resend",
        dry_run=False,
        confirm_live=True,
        idempotency_key="second",
        min_interval_seconds=120,
        guard_path=str(guard),
    )

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["reason"] == "live-dispatch-rate-limited"


def test_get_provider_health_unknown():
    from fdd_tracker.services.alerts import get_provider_health

    health = get_provider_health('not-real')
    assert health['known'] is False
    assert health['ready'] is False
    assert health['reason'] == 'unsupported-provider'


def test_get_provider_health_resend_missing_env(monkeypatch):
    from fdd_tracker.services.alerts import get_provider_health

    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    monkeypatch.delenv('ALERTS_FROM_EMAIL', raising=False)
    health = get_provider_health('resend')
    assert health['known'] is True
    assert health['ready'] is False
    assert 'RESEND_API_KEY' in health['missing_env']


def test_resolve_dispatch_plan_fallbacks_to_noop_for_invalid_live_provider():
    from fdd_tracker.services.alerts import resolve_dispatch_plan

    plan = resolve_dispatch_plan(dispatch_provider='unknown-provider', dispatch_dry_run=False)
    assert plan['fallback_applied'] is True
    assert plan['effective_provider'] == 'noop'
    assert plan['effective_dry_run'] is True
    assert plan['validation']['ok'] is True


def test_run_alerts_cron_tick_uses_fallback_dispatch_plan(tmp_path):
    from fdd_tracker.services.alerts import run_alerts_cron_tick
    from fdd_tracker.services.store import upsert_watchlist, seed_change_summary

    db = str(tmp_path / 'test.db')
    history = tmp_path / 'history.jsonl'

    upsert_watchlist('fallback@example.com', 'chick-fil-a', db_path=db)
    seed_change_summary('chick-fil-a', ['fees'], risk_level='high', db_path=db)

    result = run_alerts_cron_tick(
        db_path=db,
        history_path=str(history),
        dispatch_provider='unknown-provider',
        dispatch_dry_run=False,
        run_id='fallback-run',
    )

    assert result['status'] == 'executed'
    assert result['degraded'] is True
    assert any(e['kind'] == 'dispatch-fallback' for e in result['events'])
    assert result['dispatch_plan']['fallback_applied'] is True
    assert result['dispatch_plan']['effective_provider'] == 'noop'
    assert result['dispatched']['provider'] == 'noop'
    assert result['dispatched']['dry_run'] is True


def test_run_alerts_cron_tick_no_fallback_not_degraded(tmp_path):
    from fdd_tracker.services.alerts import run_alerts_cron_tick
    from fdd_tracker.services.store import upsert_watchlist, seed_change_summary

    db = str(tmp_path / 'test.db')
    history = tmp_path / 'history.jsonl'

    upsert_watchlist('ok@example.com', 'chick-fil-a', db_path=db)
    seed_change_summary('chick-fil-a', ['fees'], risk_level='high', db_path=db)

    result = run_alerts_cron_tick(
        db_path=db,
        history_path=str(history),
        dispatch_provider='noop',
        dispatch_dry_run=True,
        run_id='no-fallback-run',
    )

    assert result['status'] == 'executed'
    assert result['degraded'] is False
    assert result['events'] == []


def test_list_sent_outbox_filters_by_email_and_run_id(tmp_path):
    from fdd_tracker.services.alerts import list_sent_outbox

    sent = tmp_path / "alert_outbox_sent.jsonl"
    sent.write_text(
        '\n'.join([
            '{"email":"a@example.com","run_id":"run-a","subject":"1"}',
            '{"email":"b@example.com","run_id":"run-b","subject":"2"}',
            '{"email":"a@example.com","run_id":"run-c","subject":"3"}',
        ]) + '\n',
        encoding='utf-8',
    )

    filtered_email = list_sent_outbox(limit=10, email='a@example.com', sent_path=str(sent))
    assert len(filtered_email) == 2
    assert all(item['email'] == 'a@example.com' for item in filtered_email)

    filtered_run = list_sent_outbox(limit=10, run_id='run-b', sent_path=str(sent))
    assert len(filtered_run) == 1
    assert filtered_run[0]['run_id'] == 'run-b'


def test_list_failed_outbox_filters_and_limit(tmp_path):
    from fdd_tracker.services.alerts import list_failed_outbox

    failed = tmp_path / "alert_outbox_failed.jsonl"
    failed.write_text(
        '\n'.join([
            '{"email":"x@example.com","run_id":"r1","failure_reason":"x"}',
            '{"email":"x@example.com","run_id":"r2","failure_reason":"y"}',
            '{"email":"y@example.com","run_id":"r3","failure_reason":"z"}',
        ]) + '\n',
        encoding='utf-8',
    )

    latest_one = list_failed_outbox(limit=1, failed_path=str(failed))
    assert len(latest_one) == 1
    assert latest_one[0]['run_id'] == 'r3'

    filtered = list_failed_outbox(limit=10, email='x@example.com', failed_path=str(failed))
    assert len(filtered) == 2
    assert all(item['email'] == 'x@example.com' for item in filtered)


def test_get_run_artifact_summary_counts_and_latest(tmp_path):
    from fdd_tracker.services.alerts import get_run_artifact_summary

    outbox = tmp_path / "alert_outbox.jsonl"
    sent = tmp_path / "alert_outbox_sent.jsonl"
    failed = tmp_path / "alert_outbox_failed.jsonl"
    history = tmp_path / "alerts_cron_history.jsonl"

    outbox.write_text(
        '{"run_id":"run-1","queued_at":"2026-04-11T08:00:00+00:00"}\n'
        '{"run_id":"run-2","queued_at":"2026-04-11T08:01:00+00:00"}\n',
        encoding='utf-8',
    )
    sent.write_text(
        '{"run_id":"run-1","dispatched_at":"2026-04-11T08:02:00+00:00"}\n',
        encoding='utf-8',
    )
    failed.write_text(
        '{"run_id":"run-1","failed_at":"2026-04-11T08:03:00+00:00"}\n',
        encoding='utf-8',
    )
    history.write_text(
        '{"run_id":"run-1","ran_at":"2026-04-11T08:04:00+00:00","status":"executed","degraded":false,"dispatch_plan":{"fallback_applied":false,"effective_provider":"noop","effective_dry_run":true,"requested_provider":"noop","requested_dry_run":true},"dispatched":{"validation":{"ok":true}}}\n',
        encoding='utf-8',
    )

    result = get_run_artifact_summary(
        run_id='run-1',
        outbox_path=str(outbox),
        sent_path=str(sent),
        failed_path=str(failed),
        history_path=str(history),
    )

    assert result['exists'] is True
    assert result['counts']['queued'] == 1
    assert result['counts']['sent'] == 1
    assert result['counts']['failed'] == 1
    assert result['counts']['history'] == 1
    assert result['latest']['queued_at'] == '2026-04-11T08:00:00+00:00'
    assert result['latest']['dispatched_at'] == '2026-04-11T08:02:00+00:00'
    assert result['latest']['failed_at'] == '2026-04-11T08:03:00+00:00'
    assert result['latest']['cron_ran_at'] == '2026-04-11T08:04:00+00:00'
    assert result['paths']['outbox'] == str(outbox)
    assert result['paths']['sent'] == str(sent)
    assert result['paths']['failed'] == str(failed)
    assert result['paths']['history'] == str(history)
    assert result['operational']['status'] == 'executed'
    assert result['operational']['degraded'] is False
    assert result['operational']['fallback_applied'] is False
    assert result['operational']['effective_provider'] == 'noop'
    assert result['operational']['dispatch_validation_ok'] is True


def test_get_run_integrity_report_ok_and_latest(tmp_path):
    from fdd_tracker.services.alerts import append_cron_history, get_latest_run_integrity_report, get_run_integrity_report

    history = tmp_path / "alerts_cron_history.jsonl"
    append_cron_history(
        {
            "run_id": "integrity-ok",
            "status": "executed",
            "ran_at": "2026-04-11T08:04:00+00:00",
            "degraded": True,
            "events": [{"kind": "dispatch-fallback", "reason": "invalid-provider"}],
        },
        history_path=str(history),
    )

    report = get_run_integrity_report(run_id="integrity-ok", history_path=str(history))
    assert report["ok"] is True
    assert report["issues"] == []

    latest = get_latest_run_integrity_report(history_path=str(history))
    assert latest["exists"] is True
    assert latest["run_id"] == "integrity-ok"
    assert latest["report"]["ok"] is True


def test_get_run_integrity_report_flags_issues(tmp_path):
    from fdd_tracker.services.alerts import get_run_integrity_report

    report = get_run_integrity_report(run_id="does-not-exist", history_path=str(tmp_path / "history.jsonl"))
    assert report["ok"] is False
    assert "run-not-found" in report["issues"]
    assert "missing-history" in report["issues"]


def test_list_recent_run_integrity_reports_with_status_filter(tmp_path):
    from fdd_tracker.services.alerts import append_cron_history, list_recent_run_integrity_reports

    history = tmp_path / "alerts_cron_history.jsonl"
    append_cron_history({"run_id": "run-a", "status": "executed", "ran_at": "2026-04-11T08:00:00+00:00", "events": []}, history_path=str(history))
    append_cron_history({"run_id": "run-b", "status": "skipped_locked", "ran_at": "2026-04-11T08:01:00+00:00", "events": []}, history_path=str(history))
    append_cron_history({"run_id": "run-c", "status": "executed", "ran_at": "2026-04-11T08:02:00+00:00", "events": []}, history_path=str(history))

    all_reports = list_recent_run_integrity_reports(limit=2, history_path=str(history))
    assert all_reports["count"] == 2
    assert all_reports["reports"][0]["run_id"] == "run-c"

    executed_only = list_recent_run_integrity_reports(limit=10, status="executed", history_path=str(history))
    assert executed_only["count"] == 2
    assert all(r["summary"]["operational"]["status"] == "executed" for r in executed_only["reports"])


def test_summarize_recent_run_integrity(tmp_path):
    from fdd_tracker.services.alerts import append_cron_history, summarize_recent_run_integrity

    history = tmp_path / "alerts_cron_history.jsonl"
    append_cron_history(
        {
            "run_id": "sum-a",
            "status": "executed",
            "ran_at": "2026-04-11T08:00:00+00:00",
            "degraded": True,
            "events": [{"kind": "dispatch-fallback", "reason": "invalid-provider"}],
        },
        history_path=str(history),
    )
    append_cron_history(
        {
            "run_id": "sum-b",
            "status": "executed",
            "ran_at": "2026-04-11T08:01:00+00:00",
            "degraded": False,
            "events": [],
        },
        history_path=str(history),
    )

    summary = summarize_recent_run_integrity(limit=10, history_path=str(history))
    assert summary["count"] == 2
    assert summary["ok_count"] == 2
    assert summary["failing_count"] == 0
    assert summary["failing_rate"] == 0.0
    assert summary["degraded_count"] == 1
    assert summary["degraded_rate"] == 0.5
    assert isinstance(summary["top_issues"], list)


def test_list_failing_run_integrity_reports(tmp_path):
    from fdd_tracker.services.alerts import append_cron_history, get_run_integrity_report, list_failing_run_integrity_reports

    history = tmp_path / "alerts_cron_history.jsonl"
    append_cron_history({"run_id": "ok-run", "status": "executed", "ran_at": "2026-04-11T08:00:00+00:00", "events": []}, history_path=str(history))
    _ = get_run_integrity_report(run_id="missing-run", history_path=str(history))

    failing = list_failing_run_integrity_reports(limit=10, history_path=str(history))
    assert "count" in failing
    assert "reports" in failing
    assert isinstance(failing["reports"], list)


def test_list_run_events_from_history(tmp_path):
    from fdd_tracker.services.alerts import list_run_events

    history = tmp_path / "alerts_cron_history.jsonl"
    history.write_text(
        '{"run_id":"run-ev","ran_at":"2026-04-11T09:00:00+00:00","status":"executed","degraded":true,"events":[{"kind":"dispatch-fallback","reason":"missing-env"},{"kind":"notify","channel":"ops"}]}\n'
        '{"run_id":"other","ran_at":"2026-04-11T09:01:00+00:00","status":"executed","events":[{"kind":"x"}]}\n',
        encoding='utf-8',
    )

    events = list_run_events(run_id='run-ev', history_path=str(history))
    assert len(events) == 2
    assert all(item['run_id'] == 'run-ev' for item in events)
    assert events[0]['kind'] == 'dispatch-fallback'
    assert events[0]['degraded'] is True


def test_list_run_events_filters_kind_and_status(tmp_path):
    from fdd_tracker.services.alerts import list_run_events

    history = tmp_path / "alerts_cron_history.jsonl"
    history.write_text(
        '{"run_id":"run-filter","ran_at":"2026-04-11T09:00:00+00:00","status":"executed","degraded":true,"events":[{"kind":"dispatch-fallback","reason":"missing-env"},{"kind":"notify"}]}\n'
        '{"run_id":"run-filter","ran_at":"2026-04-11T09:02:00+00:00","status":"skipped_locked","events":[{"kind":"lock-skip"}]}\n',
        encoding='utf-8',
    )

    only_fallback = list_run_events(
        run_id='run-filter',
        history_path=str(history),
        kinds=['dispatch-fallback'],
        statuses=['executed'],
    )
    assert len(only_fallback) == 1
    assert only_fallback[0]['kind'] == 'dispatch-fallback'
    assert only_fallback[0]['status'] == 'executed'


def test_get_latest_run_id(tmp_path):
    from fdd_tracker.services.alerts import append_cron_history, get_latest_run_id

    history = tmp_path / "alerts_cron_history.jsonl"
    append_cron_history({"run_id": "r1", "ran_at": "2026-04-11T09:00:00+00:00"}, history_path=str(history))
    append_cron_history({"run_id": "r2", "ran_at": "2026-04-11T09:01:00+00:00"}, history_path=str(history))

    assert get_latest_run_id(history_path=str(history)) == 'r2'


def test_list_run_events_pagination(tmp_path):
    from fdd_tracker.services.alerts import list_run_events

    history = tmp_path / "alerts_cron_history.jsonl"
    history.write_text(
        '{"run_id":"run-page","ran_at":"2026-04-11T09:00:00+00:00","status":"executed","events":[{"kind":"a"},{"kind":"b"},{"kind":"c"}]}\n',
        encoding='utf-8',
    )

    rows = list_run_events(run_id='run-page', history_path=str(history), limit=2, offset=1)
    assert len(rows) == 2
    assert rows[0]['kind'] == 'b'
    assert rows[1]['kind'] == 'c'


def test_list_latest_run_events(tmp_path):
    from fdd_tracker.services.alerts import append_cron_history, list_latest_run_events

    history = tmp_path / "alerts_cron_history.jsonl"
    append_cron_history({"run_id": "r1", "ran_at": "2026-04-11T09:00:00+00:00", "events": [{"kind": "x"}]}, history_path=str(history))
    append_cron_history({"run_id": "r2", "ran_at": "2026-04-11T09:01:00+00:00", "events": [{"kind": "y"}]}, history_path=str(history))

    latest = list_latest_run_events(history_path=str(history))
    assert latest['exists'] is True
    assert latest['run_id'] == 'r2'
    assert len(latest['events']) == 1
    assert latest['events'][0]['kind'] == 'y'
