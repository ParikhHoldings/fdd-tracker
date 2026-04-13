from __future__ import annotations

from datetime import date
from fastapi import FastAPI, Query
from pydantic import BaseModel, EmailStr

from fdd_tracker.db import ensure_db
from fdd_tracker.models import Filing
from fdd_tracker.services.alerts import dispatch_outbox, enforce_live_dispatch_gate, get_alerts_cron_preflight, get_alerts_cron_status, get_dispatch_provider_catalog, get_integrity_dashboard_snapshot, get_latest_cron_history_entry, get_latest_run_id, get_latest_run_integrity_report, get_run_artifact_summary, get_run_integrity_report, list_cron_history, list_failing_run_integrity_reports, list_failed_outbox, list_latest_run_events, list_outbox, list_recent_run_integrity_reports, list_run_events, list_sent_outbox, prune_alert_artifacts, recover_alerts_cron_lock, render_integrity_dashboard_markdown, render_integrity_dashboard_telegram_chunks, retry_failed_outbox, run_alerts_cron_tick, run_digest_for_all_emails, run_digest_for_email, run_provider_smoke_test, summarize_integrity_trends, summarize_recent_run_integrity
from fdd_tracker.services.ingest import refresh_state_source_cache, run_ingestion
from fdd_tracker.services.store import (
    delete_watchlist,
    get_alert_feed,
    get_alert_summary,
    get_recent_changes,
    get_unread_alert_count,
    get_watchlists,
    mark_alert_read,
    mark_alerts_read_for_franchise,
    upsert_filing,
    upsert_watchlist,
)

app = FastAPI(title="FDD Tracker API", version="0.2.0")

FRANCHISES = [
    {"slug": "chick-fil-a", "name": "Chick-fil-A", "category": "QSR"},
    {"slug": "orangetheory", "name": "Orangetheory", "category": "Fitness"},
]


class WatchlistIn(BaseModel):
    email: EmailStr
    franchise_slug: str


class FilingIn(BaseModel):
    franchise_slug: str
    source: str
    filed_on: date | None = None
    document_url: str
    document_hash: str | None = None


class IngestRequest(BaseModel):
    states: list[str] | None = None


@app.on_event("startup")
def startup() -> None:
    ensure_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/franchises")
def franchises() -> list[dict]:
    return FRANCHISES


@app.post("/watchlists")
def create_watchlist(payload: WatchlistIn) -> dict:
    result = upsert_watchlist(email=payload.email, franchise_slug=payload.franchise_slug)
    created = result.pop("created")
    return {"created": created, "item": result}


@app.get("/watchlists")
def list_watchlists(email: str | None = Query(default=None)) -> list[dict]:
    return get_watchlists(email=email)


@app.delete("/watchlists")
def remove_watchlist(payload: WatchlistIn) -> dict:
    deleted = delete_watchlist(email=payload.email, franchise_slug=payload.franchise_slug)
    return {"deleted": deleted}


@app.post("/filings")
def create_filing(payload: FilingIn) -> dict:
    changed = upsert_filing(Filing(**payload.model_dump()))
    return {"stored": True, "changed_rows": changed}


@app.get("/changes/{franchise_slug}")
def changes(franchise_slug: str, limit: int = Query(default=20, ge=1, le=200)) -> dict:
    return {
        "franchise_slug": franchise_slug,
        "changes": get_recent_changes(franchise_slug=franchise_slug, limit=limit),
    }


@app.post("/ingest/run")
def ingest_run(payload: IngestRequest | None = None) -> dict:
    states = payload.states if payload else None
    return run_ingestion(states=states)


class RefreshStateSourcesRequest(BaseModel):
    states: list[str] | None = None


class AlertReadIn(BaseModel):
    email: EmailStr
    franchise_slug: str
    generated_at: str


class AlertDigestRunIn(BaseModel):
    email: EmailStr | None = None
    max_alerts: int = 25
    mark_read: bool = False
    run_id: str | None = None


class AlertOutboxDispatchIn(BaseModel):
    limit: int = 100
    dry_run: bool = True
    provider: str = "noop"
    confirm_live: bool = False
    idempotency_key: str | None = None
    live_min_interval_seconds: int = 60


class AlertProviderSmokeTestIn(BaseModel):
    provider: str = "noop"
    email: EmailStr
    dry_run: bool = True


class AlertOutboxRetryIn(BaseModel):
    limit: int = 100


class AlertCronTickIn(BaseModel):
    max_alerts: int = 25
    generate_mark_read: bool = False
    dispatch_limit: int = 100
    retry_limit: int = 100
    dispatch_dry_run: bool = True
    dispatch_provider: str = "noop"
    run_id: str | None = None
    lock_stale_after_seconds: int = 900


class AlertCronRecoverIn(BaseModel):
    lock_stale_after_seconds: int = 900
    force: bool = False


class AlertCronPreflightIn(BaseModel):
    dispatch_dry_run: bool = True
    dispatch_provider: str = "noop"
    lock_stale_after_seconds: int = 900


class AlertRetentionPruneIn(BaseModel):
    outbox_keep_last: int = 1000
    sent_keep_last: int = 2000
    failed_keep_last: int = 1000
    history_keep_last: int = 2000


@app.post("/ingest/refresh-state-sources")
def refresh_state_sources(payload: RefreshStateSourcesRequest | None = None) -> dict:
    """Refresh state filings from live portal sources and update JSON cache."""
    states = payload.states if payload else None
    return refresh_state_source_cache(states=states)


@app.get("/alerts")
def alerts(
    email: EmailStr,
    limit: int = Query(default=50, ge=1, le=200),
    risk_level: str | None = Query(default=None, description="Comma-separated: low,medium,high"),
    unread_only: bool = Query(default=False),
    franchise_slug: str | None = Query(default=None),
) -> dict:
    risk_levels = [item.strip().lower() for item in risk_level.split(",") if item.strip()] if risk_level else None
    return {
        "email": email,
        "alerts": get_alert_feed(
            email=str(email),
            limit=limit,
            risk_levels=risk_levels,
            unread_only=unread_only,
            franchise_slug=franchise_slug,
        ),
    }


@app.post("/alerts/read")
def alerts_read(payload: AlertReadIn) -> dict:
    marked = mark_alert_read(
        email=str(payload.email),
        franchise_slug=payload.franchise_slug,
        generated_at=payload.generated_at,
    )
    return {"marked": bool(marked), "created": marked}


@app.post("/alerts/read/franchise")
def alerts_read_franchise(email: EmailStr, franchise_slug: str) -> dict:
    marked = mark_alerts_read_for_franchise(email=str(email), franchise_slug=franchise_slug)
    return {"marked": marked}


@app.get("/alerts/unread-count")
def alerts_unread_count(email: EmailStr) -> dict:
    return {"email": email, "unread_count": get_unread_alert_count(email=str(email))}


@app.get("/alerts/summary")
def alerts_summary(email: EmailStr) -> dict:
    return {"email": email, **get_alert_summary(email=str(email))}


@app.post("/alerts/digest/run")
def alerts_digest_run(payload: AlertDigestRunIn) -> dict:
    max_alerts = max(1, min(payload.max_alerts, 200))
    if payload.email:
        return run_digest_for_email(
            email=str(payload.email),
            max_alerts=max_alerts,
            mark_read=payload.mark_read,
            run_id=payload.run_id,
        )
    return run_digest_for_all_emails(max_alerts=max_alerts, mark_read=payload.mark_read, run_id=payload.run_id)


@app.get("/alerts/outbox")
def alerts_outbox(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    return {"items": list_outbox(limit=limit)}


@app.get("/alerts/outbox/sent")
def alerts_outbox_sent(
    limit: int = Query(default=100, ge=1, le=500),
    email: EmailStr | None = Query(default=None),
    run_id: str | None = Query(default=None),
) -> dict:
    return {"items": list_sent_outbox(limit=limit, email=str(email) if email else None, run_id=run_id)}


@app.get("/alerts/outbox/failed")
def alerts_outbox_failed(
    limit: int = Query(default=100, ge=1, le=500),
    email: EmailStr | None = Query(default=None),
    run_id: str | None = Query(default=None),
) -> dict:
    return {"items": list_failed_outbox(limit=limit, email=str(email) if email else None, run_id=run_id)}


@app.get("/alerts/providers")
def alerts_providers() -> dict:
    return get_dispatch_provider_catalog()


@app.post("/alerts/providers/smoke-test")
def alerts_provider_smoke_test(payload: AlertProviderSmokeTestIn) -> dict:
    provider = (payload.provider or "noop").strip() or "noop"
    return run_provider_smoke_test(provider=provider, email=str(payload.email), dry_run=payload.dry_run)


@app.post("/alerts/outbox/dispatch")
def alerts_outbox_dispatch(payload: AlertOutboxDispatchIn) -> dict:
    limit = max(1, min(payload.limit, 500))
    provider = (payload.provider or "noop").strip() or "noop"

    gate = enforce_live_dispatch_gate(
        provider=provider,
        dry_run=payload.dry_run,
        confirm_live=payload.confirm_live,
        idempotency_key=(payload.idempotency_key or None),
        min_interval_seconds=max(1, min(payload.live_min_interval_seconds, 3600)),
    )
    if not gate.get("ok", False):
        return {
            "dispatched": 0,
            "failed": 0,
            "remaining": None,
            "dry_run": payload.dry_run,
            "provider": provider,
            "error": gate,
        }

    result = dispatch_outbox(limit=limit, dry_run=payload.dry_run, provider=provider)
    result["gate"] = gate
    return result


@app.post("/alerts/outbox/retry-failed")
def alerts_outbox_retry_failed(payload: AlertOutboxRetryIn) -> dict:
    limit = max(1, min(payload.limit, 500))
    return retry_failed_outbox(limit=limit)


@app.post("/alerts/cron/tick")
def alerts_cron_tick(payload: AlertCronTickIn) -> dict:
    return run_alerts_cron_tick(
        max_alerts=max(1, min(payload.max_alerts, 200)),
        generate_mark_read=payload.generate_mark_read,
        dispatch_limit=max(1, min(payload.dispatch_limit, 500)),
        retry_limit=max(1, min(payload.retry_limit, 500)),
        dispatch_dry_run=payload.dispatch_dry_run,
        dispatch_provider=(payload.dispatch_provider or "noop").strip() or "noop",
        run_id=payload.run_id,
        lock_stale_after_seconds=max(1, min(payload.lock_stale_after_seconds, 86400)),
    )




@app.get("/alerts/cron/status")
def alerts_cron_status(lock_stale_after_seconds: int = Query(default=900, ge=1, le=86400)) -> dict:
    return get_alerts_cron_status(lock_stale_after_seconds=lock_stale_after_seconds)


@app.post("/alerts/cron/preflight")
def alerts_cron_preflight(payload: AlertCronPreflightIn) -> dict:
    return get_alerts_cron_preflight(
        dispatch_provider=(payload.dispatch_provider or "noop").strip() or "noop",
        dispatch_dry_run=payload.dispatch_dry_run,
        lock_stale_after_seconds=max(1, min(payload.lock_stale_after_seconds, 86400)),
    )


@app.post("/alerts/cron/recover-lock")
def alerts_cron_recover_lock(payload: AlertCronRecoverIn) -> dict:
    return recover_alerts_cron_lock(
        lock_stale_after_seconds=max(1, min(payload.lock_stale_after_seconds, 86400)),
        force=payload.force,
    )


@app.get("/alerts/cron/history/latest")
def alerts_cron_history_latest() -> dict:
    return get_latest_cron_history_entry()


@app.get("/alerts/runs/latest/summary")
def alerts_latest_run_summary() -> dict:
    run_id = get_latest_run_id()
    if not run_id:
        return {"exists": False, "run_id": None, "summary": None}
    return {"exists": True, "run_id": run_id, "summary": get_run_artifact_summary(run_id=run_id)}


@app.get("/alerts/runs/latest/integrity")
def alerts_latest_run_integrity() -> dict:
    return get_latest_run_integrity_report()


@app.get("/alerts/runs/integrity")
def alerts_recent_runs_integrity(
    limit: int = Query(default=10, ge=1, le=100),
    status: str | None = Query(default=None),
) -> dict:
    return list_recent_run_integrity_reports(limit=limit, status=status)


@app.get("/alerts/runs/integrity/summary")
def alerts_recent_runs_integrity_summary(
    limit: int = Query(default=25, ge=1, le=200),
    status: str | None = Query(default=None),
) -> dict:
    return summarize_recent_run_integrity(limit=limit, status=status)


@app.get("/alerts/runs/integrity/failures")
def alerts_recent_runs_integrity_failures(
    limit: int = Query(default=25, ge=1, le=200),
    status: str | None = Query(default=None),
) -> dict:
    return list_failing_run_integrity_reports(limit=limit, status=status)


@app.get("/alerts/runs/integrity/dashboard")
def alerts_runs_integrity_dashboard(
    limit: int = Query(default=25, ge=1, le=200),
    status: str | None = Query(default=None),
) -> dict:
    return get_integrity_dashboard_snapshot(limit=limit, status=status)


@app.get("/alerts/runs/integrity/dashboard/markdown")
def alerts_runs_integrity_dashboard_markdown(
    limit: int = Query(default=25, ge=1, le=200),
    status: str | None = Query(default=None),
) -> dict:
    return {"markdown": render_integrity_dashboard_markdown(limit=limit, status=status)}


@app.get("/alerts/runs/integrity/dashboard/telegram")
def alerts_runs_integrity_dashboard_telegram(
    limit: int = Query(default=25, ge=1, le=200),
    status: str | None = Query(default=None),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return render_integrity_dashboard_telegram_chunks(limit=limit, status=status, max_chars=max_chars)


@app.get("/alerts/runs/integrity/trends")
def alerts_runs_integrity_trends(
    limit: int = Query(default=200, ge=1, le=2000),
    status: str | None = Query(default=None),
) -> dict:
    return summarize_integrity_trends(limit=limit, status=status)


@app.get("/alerts/runs/{run_id}/summary")
def alerts_run_summary(run_id: str) -> dict:
    return get_run_artifact_summary(run_id=run_id)


@app.get("/alerts/runs/{run_id}/integrity")
def alerts_run_integrity(run_id: str) -> dict:
    return get_run_integrity_report(run_id=run_id)


@app.get("/alerts/runs/latest/events")
def alerts_latest_run_events(
    kind: str | None = Query(default=None, description="Comma-separated event kinds"),
    status: str | None = Query(default=None, description="Comma-separated run statuses"),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return list_latest_run_events(kinds=kinds, statuses=statuses, limit=limit, offset=offset)


@app.get("/alerts/runs/{run_id}/events")
def alerts_run_events(
    run_id: str,
    kind: str | None = Query(default=None, description="Comma-separated event kinds"),
    status: str | None = Query(default=None, description="Comma-separated run statuses"),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return {
        "run_id": run_id,
        "events": list_run_events(run_id=run_id, kinds=kinds, statuses=statuses, limit=limit, offset=offset),
    }


@app.get("/alerts/cron/history")
def alerts_cron_history(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    return {"items": list_cron_history(limit=limit)}


@app.post("/alerts/retention/prune")
def alerts_retention_prune(payload: AlertRetentionPruneIn) -> dict:
    return prune_alert_artifacts(
        outbox_keep_last=max(0, payload.outbox_keep_last),
        sent_keep_last=max(0, payload.sent_keep_last),
        failed_keep_last=max(0, payload.failed_keep_last),
        history_keep_last=max(0, payload.history_keep_last),
    )
