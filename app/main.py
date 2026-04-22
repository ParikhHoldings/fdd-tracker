from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from fastapi import FastAPI, Query
from pydantic import BaseModel, EmailStr

from fdd_tracker.db import ensure_db
from fdd_tracker.models import Filing
from fdd_tracker.services.alerts import build_digest_preview, build_digest_preview_all_summary_packet, build_digest_preview_packet, build_digest_previews_all_packet, build_digest_previews_for_all_emails, build_latest_run_incident_export_packet, build_latest_run_incident_payload, build_provider_catalog_options_packet, build_provider_details_options_packet, build_provider_health_options_packet, build_provider_health_summary_options_packet, build_provider_health_summary_packet, build_provider_recommendations_options_packet, build_provider_recommendations_packet, build_run_incident_export_packet, build_run_incident_payload, build_weekly_brief, build_weekly_brief_all_options_packet, build_weekly_brief_options_packet, build_weekly_brief_packet, build_weekly_briefs_all_packet, build_weekly_briefs_all_summary_packet, build_weekly_briefs_for_all_emails, dispatch_outbox, enforce_live_dispatch_gate, get_alerts_cron_options, get_alerts_cron_preflight, get_alerts_cron_status, get_cron_history_options, get_digest_preview_all_options, get_digest_preview_options, get_digest_run_options, get_dispatch_provider_catalog, get_integrity_dashboard_snapshot, get_latest_cron_history_entry, get_latest_run_id, get_latest_run_integrity_issue_details, get_latest_run_integrity_report, get_outbox_dispatch_options, get_outbox_retry_failed_options, get_provider_catalog_options, get_provider_details, get_provider_details_options, get_provider_health_details, get_provider_health_options, get_provider_health_summary_options, get_provider_recommendations, get_provider_recommendations_options, get_provider_smoke_test_options, get_weekly_brief_all_options, get_weekly_brief_options, list_provider_health, get_retention_prune_options, get_run_artifact_summary, get_run_integrity_issue_details, get_run_integrity_report, list_cron_history, list_failing_run_integrity_reports, list_failed_outbox, list_latest_run_events, list_outbox, list_recent_run_integrity_reports, list_run_events, list_sent_outbox, prune_alert_artifacts, recover_alerts_cron_lock, render_digest_preview_all_summary_csv, render_digest_preview_all_summary_markdown, render_digest_preview_all_summary_telegram_chunks, render_digest_preview_csv, render_digest_preview_markdown, render_digest_preview_telegram_chunks, render_digest_previews_all_csv, render_digest_previews_all_markdown, render_digest_previews_all_telegram_chunks, render_integrity_dashboard_markdown, render_integrity_dashboard_telegram_chunks, render_latest_run_events_csv, render_latest_run_incident_csv, render_latest_run_incident_markdown, render_latest_run_incident_telegram_chunks, render_latest_run_integrity_issues_csv, render_latest_run_integrity_issues_markdown, render_latest_run_integrity_issues_telegram_chunks, render_provider_catalog_options_csv, render_provider_catalog_options_markdown, render_provider_catalog_options_telegram_chunks, render_provider_details_options_csv, render_provider_details_options_markdown, render_provider_details_options_telegram_chunks, render_provider_health_options_csv, render_provider_health_options_markdown, render_provider_health_options_telegram_chunks, render_provider_health_recommendations_csv, render_provider_health_recommendations_markdown, render_provider_health_recommendations_telegram_chunks, render_provider_health_summary_csv, render_provider_health_summary_markdown, render_provider_health_summary_options_csv, render_provider_health_summary_options_markdown, render_provider_health_summary_options_telegram_chunks, render_provider_health_summary_telegram_chunks, render_provider_recommendations_csv, render_provider_recommendations_markdown, render_provider_recommendations_options_csv, render_provider_recommendations_options_markdown, render_provider_recommendations_options_telegram_chunks, render_provider_recommendations_telegram_chunks, render_run_events_csv, render_run_incident_csv, render_run_incident_markdown, render_run_incident_telegram_chunks, render_run_integrity_issues_csv, render_run_integrity_issues_markdown, render_run_integrity_issues_telegram_chunks, render_weekly_brief_all_options_csv, render_weekly_brief_all_options_markdown, render_weekly_brief_all_options_telegram_chunks, render_weekly_brief_csv, render_weekly_brief_markdown, render_weekly_brief_options_csv, render_weekly_brief_options_markdown, render_weekly_brief_options_telegram_chunks, render_weekly_briefs_all_csv, render_weekly_briefs_all_markdown, render_weekly_briefs_all_summary_csv, render_weekly_briefs_all_summary_markdown, render_weekly_briefs_all_summary_telegram_chunks, render_weekly_briefs_all_telegram_chunks, render_weekly_brief_telegram_chunks, retry_failed_outbox, run_alerts_cron_tick, run_digest_for_all_emails, run_digest_for_email, run_provider_smoke_test, summarize_digest_previews_for_all_emails, summarize_integrity_trends, summarize_provider_health, summarize_provider_health_recommendations, summarize_recent_run_integrity, summarize_weekly_briefs_for_all_emails, build_provider_health_recommendations_packet
from fdd_tracker.services.ingest import refresh_state_source_cache, run_ingestion
from fdd_tracker.services.store import (
    build_change_comparison_options_packet,
    build_change_comparison_packet,
    compare_change_insights,
    delete_watchlist,
    get_alert_feed,
    get_alert_summary,
    get_change_comparison_options,
    get_change_insights,
    get_recent_changes,
    get_unread_alert_count,
    get_watchlists,
    mark_alert_read,
    render_change_comparison_csv,
    render_change_comparison_markdown,
    render_change_comparison_options_csv,
    render_change_comparison_options_markdown,
    render_change_comparison_options_telegram_chunks,
    render_change_comparison_telegram_chunks,
    mark_alerts_read_for_franchise,
    upsert_filing,
    upsert_watchlist,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_db()
    yield


app = FastAPI(title="FDD Tracker API", version="0.2.0", lifespan=lifespan)

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


@app.get("/changes/{franchise_slug}/insights")
def change_insights(franchise_slug: str, limit: int = Query(default=200, ge=1, le=500)) -> dict:
    return get_change_insights(franchise_slug=franchise_slug, limit=limit)


@app.get("/change-comparisons")
def change_comparisons(
    left_slug: str = Query(..., min_length=1),
    right_slug: str = Query(..., min_length=1),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    return compare_change_insights(left_slug=left_slug, right_slug=right_slug, limit=limit)


@app.get("/change-comparisons/markdown")
def change_comparisons_markdown(
    left_slug: str = Query(..., min_length=1),
    right_slug: str = Query(..., min_length=1),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    payload = compare_change_insights(left_slug=left_slug, right_slug=right_slug, limit=limit)
    return {"left_slug": left_slug, "right_slug": right_slug, "markdown": render_change_comparison_markdown(payload)}


@app.get("/change-comparisons/telegram")
def change_comparisons_telegram(
    left_slug: str = Query(..., min_length=1),
    right_slug: str = Query(..., min_length=1),
    limit: int = Query(default=200, ge=1, le=500),
    max_chars: int = Query(default=2500, ge=200, le=10000),
) -> dict:
    payload = compare_change_insights(left_slug=left_slug, right_slug=right_slug, limit=limit)
    chunks = render_change_comparison_telegram_chunks(payload, max_chars=max_chars)
    return {
        "left_slug": left_slug,
        "right_slug": right_slug,
        "max_chars": max_chars,
        "chunk_count": len(chunks),
        "chunks_with_index": chunks,
    }


@app.get("/change-comparisons/csv")
def change_comparisons_csv(
    left_slug: str = Query(..., min_length=1),
    right_slug: str = Query(..., min_length=1),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    payload = compare_change_insights(left_slug=left_slug, right_slug=right_slug, limit=limit)
    return {"left_slug": left_slug, "right_slug": right_slug, "csv": render_change_comparison_csv(payload)}


@app.get("/change-comparisons/packet")
def change_comparisons_packet(
    left_slug: str = Query(..., min_length=1),
    right_slug: str = Query(..., min_length=1),
    limit: int = Query(default=200, ge=1, le=500),
    max_chars: int = Query(default=2500, ge=200, le=10000),
) -> dict:
    payload = compare_change_insights(left_slug=left_slug, right_slug=right_slug, limit=limit)
    packet = build_change_comparison_packet(payload, max_chars=max_chars)
    return {"left_slug": left_slug, "right_slug": right_slug, **packet}


@app.get("/change-comparisons/options")
def change_comparisons_options() -> dict:
    return get_change_comparison_options()


@app.get("/change-comparisons/options/markdown")
def change_comparisons_options_markdown() -> dict:
    options = get_change_comparison_options()
    return {"markdown": render_change_comparison_options_markdown(options)}


@app.get("/change-comparisons/options/telegram")
def change_comparisons_options_telegram(max_chars: int = Query(default=2500, ge=200, le=10000)) -> dict:
    options = get_change_comparison_options()
    chunks = render_change_comparison_options_telegram_chunks(options, max_chars=max_chars)
    return {"max_chars": max_chars, "chunk_count": len(chunks), "chunks_with_index": chunks}


@app.get("/change-comparisons/options/csv")
def change_comparisons_options_csv() -> dict:
    options = get_change_comparison_options()
    return {"csv": render_change_comparison_options_csv(options)}


@app.get("/change-comparisons/options/packet")
def change_comparisons_options_packet(max_chars: int = Query(default=2500, ge=200, le=10000)) -> dict:
    options = get_change_comparison_options()
    return build_change_comparison_options_packet(options, max_chars=max_chars)


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


@app.get("/alerts/weekly-brief")
def alerts_weekly_brief(
    email: EmailStr,
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
) -> dict:
    return build_weekly_brief(email=str(email), days=days, max_alerts=max_alerts)


@app.get("/alerts/weekly-brief/options")
def alerts_weekly_brief_options() -> dict:
    return get_weekly_brief_options()


@app.get("/alerts/weekly-brief/all/options")
def alerts_weekly_brief_all_options() -> dict:
    return get_weekly_brief_all_options()


@app.get("/alerts/weekly-brief/all/options/markdown")
def alerts_weekly_brief_all_options_markdown() -> dict:
    return {"markdown": render_weekly_brief_all_options_markdown()}


@app.get("/alerts/weekly-brief/all/options/telegram")
def alerts_weekly_brief_all_options_telegram(
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return render_weekly_brief_all_options_telegram_chunks(max_chars=max_chars)


@app.get("/alerts/weekly-brief/all/options/csv")
def alerts_weekly_brief_all_options_csv() -> dict:
    return {"csv": render_weekly_brief_all_options_csv()}


@app.get("/alerts/weekly-brief/all/options/packet")
def alerts_weekly_brief_all_options_packet(
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return build_weekly_brief_all_options_packet(max_chars=max_chars)


@app.get("/alerts/weekly-brief/all")
def alerts_weekly_brief_all(
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
    unread_only: bool = Query(default=False),
    min_total_alerts: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict:
    return build_weekly_briefs_for_all_emails(
        days=days,
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_total_alerts=min_total_alerts,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
    )


@app.get("/alerts/weekly-brief/all/summary")
def alerts_weekly_brief_all_summary(
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
    unread_only: bool = Query(default=False),
    min_total_alerts: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    top_n: int = Query(default=10, ge=1, le=1000),
) -> dict:
    return summarize_weekly_briefs_for_all_emails(
        days=days,
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_total_alerts=min_total_alerts,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        top_n=top_n,
    )


@app.get("/alerts/weekly-brief/all/summary/markdown")
def alerts_weekly_brief_all_summary_markdown(
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
    unread_only: bool = Query(default=False),
    min_total_alerts: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    top_n: int = Query(default=10, ge=1, le=1000),
) -> dict:
    return {
        "markdown": render_weekly_briefs_all_summary_markdown(
            days=days,
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_total_alerts=min_total_alerts,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
            top_n=top_n,
        )
    }


@app.get("/alerts/weekly-brief/all/summary/telegram")
def alerts_weekly_brief_all_summary_telegram(
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
    unread_only: bool = Query(default=False),
    min_total_alerts: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    top_n: int = Query(default=10, ge=1, le=1000),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return render_weekly_briefs_all_summary_telegram_chunks(
        days=days,
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_total_alerts=min_total_alerts,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        top_n=top_n,
        max_chars=max_chars,
    )


@app.get("/alerts/weekly-brief/all/summary/csv")
def alerts_weekly_brief_all_summary_csv(
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
    unread_only: bool = Query(default=False),
    min_total_alerts: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    top_n: int = Query(default=10, ge=1, le=1000),
) -> dict:
    return {
        "csv": render_weekly_briefs_all_summary_csv(
            days=days,
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_total_alerts=min_total_alerts,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
            top_n=top_n,
        )
    }


@app.get("/alerts/weekly-brief/all/summary/packet")
def alerts_weekly_brief_all_summary_packet(
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
    unread_only: bool = Query(default=False),
    min_total_alerts: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    top_n: int = Query(default=10, ge=1, le=1000),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return build_weekly_briefs_all_summary_packet(
        days=days,
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_total_alerts=min_total_alerts,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        top_n=top_n,
        max_chars=max_chars,
    )


@app.get("/alerts/weekly-brief/all/markdown")
def alerts_weekly_brief_all_markdown(
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
    unread_only: bool = Query(default=False),
    min_total_alerts: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict:
    return {
        "markdown": render_weekly_briefs_all_markdown(
            days=days,
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_total_alerts=min_total_alerts,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
        )
    }


@app.get("/alerts/weekly-brief/all/telegram")
def alerts_weekly_brief_all_telegram(
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
    unread_only: bool = Query(default=False),
    min_total_alerts: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return render_weekly_briefs_all_telegram_chunks(
        days=days,
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_total_alerts=min_total_alerts,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        max_chars=max_chars,
    )


@app.get("/alerts/weekly-brief/all/csv")
def alerts_weekly_brief_all_csv(
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
    unread_only: bool = Query(default=False),
    min_total_alerts: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict:
    return {
        "csv": render_weekly_briefs_all_csv(
            days=days,
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_total_alerts=min_total_alerts,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
        )
    }


@app.get("/alerts/weekly-brief/all/packet")
def alerts_weekly_brief_all_packet(
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
    unread_only: bool = Query(default=False),
    min_total_alerts: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return build_weekly_briefs_all_packet(
        days=days,
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_total_alerts=min_total_alerts,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        max_chars=max_chars,
    )


@app.get("/alerts/weekly-brief/options/markdown")
def alerts_weekly_brief_options_markdown() -> dict:
    return {"markdown": render_weekly_brief_options_markdown()}


@app.get("/alerts/weekly-brief/options/telegram")
def alerts_weekly_brief_options_telegram(
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return render_weekly_brief_options_telegram_chunks(max_chars=max_chars)


@app.get("/alerts/weekly-brief/options/csv")
def alerts_weekly_brief_options_csv() -> dict:
    return {"csv": render_weekly_brief_options_csv()}


@app.get("/alerts/weekly-brief/options/packet")
def alerts_weekly_brief_options_packet(
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return build_weekly_brief_options_packet(max_chars=max_chars)


@app.get("/alerts/weekly-brief/markdown")
def alerts_weekly_brief_markdown(
    email: EmailStr,
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
) -> dict:
    return {"email": str(email), "markdown": render_weekly_brief_markdown(email=str(email), days=days, max_alerts=max_alerts)}


@app.get("/alerts/weekly-brief/telegram")
def alerts_weekly_brief_telegram(
    email: EmailStr,
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return render_weekly_brief_telegram_chunks(email=str(email), days=days, max_alerts=max_alerts, max_chars=max_chars)


@app.get("/alerts/weekly-brief/csv")
def alerts_weekly_brief_csv(
    email: EmailStr,
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
) -> dict:
    return {"email": str(email), "csv": render_weekly_brief_csv(email=str(email), days=days, max_alerts=max_alerts)}


@app.get("/alerts/weekly-brief/packet")
def alerts_weekly_brief_packet(
    email: EmailStr,
    days: int = Query(default=7, ge=1, le=30),
    max_alerts: int = Query(default=200, ge=1, le=1000),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return build_weekly_brief_packet(email=str(email), days=days, max_alerts=max_alerts, max_chars=max_chars)


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


@app.get("/alerts/digest/run/options")
def alerts_digest_run_options() -> dict:
    return get_digest_run_options()


@app.get("/alerts/digest/preview")
def alerts_digest_preview(email: EmailStr, max_alerts: int = Query(default=25, ge=1, le=200)) -> dict:
    return build_digest_preview(email=str(email), max_alerts=max_alerts)


@app.get("/alerts/digest/preview/markdown")
def alerts_digest_preview_markdown(email: EmailStr, max_alerts: int = Query(default=25, ge=1, le=200)) -> dict:
    return {
        "email": str(email),
        "markdown": render_digest_preview_markdown(email=str(email), max_alerts=max_alerts),
    }


@app.get("/alerts/digest/preview/telegram")
def alerts_digest_preview_telegram(
    email: EmailStr,
    max_alerts: int = Query(default=25, ge=1, le=200),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return render_digest_preview_telegram_chunks(email=str(email), max_alerts=max_alerts, max_chars=max_chars)


@app.get("/alerts/digest/preview/csv")
def alerts_digest_preview_csv(email: EmailStr, max_alerts: int = Query(default=25, ge=1, le=200)) -> dict:
    return {
        "email": str(email),
        "csv": render_digest_preview_csv(email=str(email), max_alerts=max_alerts),
    }


@app.get("/alerts/digest/preview/packet")
def alerts_digest_preview_packet(
    email: EmailStr,
    max_alerts: int = Query(default=25, ge=1, le=200),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return build_digest_preview_packet(email=str(email), max_alerts=max_alerts, max_chars=max_chars)


@app.get("/alerts/digest/preview/options")
def alerts_digest_preview_options() -> dict:
    return get_digest_preview_options()


@app.get("/alerts/digest/preview/all/options")
def alerts_digest_preview_all_options() -> dict:
    return get_digest_preview_all_options()


@app.get("/alerts/digest/preview/all")
def alerts_digest_preview_all(
    max_alerts: int = Query(default=25, ge=1, le=200),
    unread_only: bool = Query(default=False),
    min_unread: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict:
    return build_digest_previews_for_all_emails(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
    )


@app.get("/alerts/digest/preview/all/markdown")
def alerts_digest_preview_all_markdown(
    max_alerts: int = Query(default=25, ge=1, le=200),
    unread_only: bool = Query(default=False),
    min_unread: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict:
    return {
        "markdown": render_digest_previews_all_markdown(
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_unread=min_unread,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
        ),
    }


@app.get("/alerts/digest/preview/all/telegram")
def alerts_digest_preview_all_telegram(
    max_alerts: int = Query(default=25, ge=1, le=200),
    unread_only: bool = Query(default=False),
    min_unread: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return render_digest_previews_all_telegram_chunks(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        max_chars=max_chars,
    )


@app.get("/alerts/digest/preview/all/csv")
def alerts_digest_preview_all_csv(
    max_alerts: int = Query(default=25, ge=1, le=200),
    unread_only: bool = Query(default=False),
    min_unread: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict:
    return {
        "csv": render_digest_previews_all_csv(
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_unread=min_unread,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
        ),
    }


@app.get("/alerts/digest/preview/all/packet")
def alerts_digest_preview_all_packet(
    max_alerts: int = Query(default=25, ge=1, le=200),
    unread_only: bool = Query(default=False),
    min_unread: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return build_digest_previews_all_packet(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        max_chars=max_chars,
    )


@app.get("/alerts/digest/preview/all/summary")
def alerts_digest_preview_all_summary(
    max_alerts: int = Query(default=25, ge=1, le=200),
    unread_only: bool = Query(default=False),
    min_unread: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    top_n: int = Query(default=10, ge=1, le=100),
) -> dict:
    return summarize_digest_previews_for_all_emails(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        top_n=top_n,
    )


@app.get("/alerts/digest/preview/all/summary/markdown")
def alerts_digest_preview_all_summary_markdown(
    max_alerts: int = Query(default=25, ge=1, le=200),
    unread_only: bool = Query(default=False),
    min_unread: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    top_n: int = Query(default=10, ge=1, le=100),
) -> dict:
    return {
        "markdown": render_digest_preview_all_summary_markdown(
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_unread=min_unread,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
            top_n=top_n,
        ),
    }


@app.get("/alerts/digest/preview/all/summary/telegram")
def alerts_digest_preview_all_summary_telegram(
    max_alerts: int = Query(default=25, ge=1, le=200),
    unread_only: bool = Query(default=False),
    min_unread: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    top_n: int = Query(default=10, ge=1, le=100),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return render_digest_preview_all_summary_telegram_chunks(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        top_n=top_n,
        max_chars=max_chars,
    )


@app.get("/alerts/digest/preview/all/summary/csv")
def alerts_digest_preview_all_summary_csv(
    max_alerts: int = Query(default=25, ge=1, le=200),
    unread_only: bool = Query(default=False),
    min_unread: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    top_n: int = Query(default=10, ge=1, le=100),
) -> dict:
    return {
        "csv": render_digest_preview_all_summary_csv(
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_unread=min_unread,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
            top_n=top_n,
        ),
    }


@app.get("/alerts/digest/preview/all/summary/packet")
def alerts_digest_preview_all_summary_packet(
    max_alerts: int = Query(default=25, ge=1, le=200),
    unread_only: bool = Query(default=False),
    min_unread: int = Query(default=0, ge=0, le=10000),
    order_by: str = Query(default="email"),
    order_dir: str = Query(default="asc"),
    limit: int | None = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=10000),
    top_n: int = Query(default=10, ge=1, le=100),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return build_digest_preview_all_summary_packet(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        top_n=top_n,
        max_chars=max_chars,
    )


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


@app.get("/alerts/providers/options")
def alerts_providers_options() -> dict:
    return get_provider_catalog_options()


@app.get("/alerts/providers/options/markdown")
def alerts_providers_options_markdown() -> dict:
    return {"markdown": render_provider_catalog_options_markdown()}


@app.get("/alerts/providers/options/telegram")
def alerts_providers_options_telegram(
    max_chars: int = Query(default=3500, ge=100, le=4096)
) -> dict:
    return render_provider_catalog_options_telegram_chunks(max_chars=max_chars)


@app.get("/alerts/providers/options/csv")
def alerts_providers_options_csv() -> dict:
    return {"csv": render_provider_catalog_options_csv()}


@app.get("/alerts/providers/options/packet")
def alerts_providers_options_packet(
    max_chars: int = Query(default=3500, ge=100, le=4096)
) -> dict:
    return build_provider_catalog_options_packet(max_chars=max_chars)


@app.get("/alerts/providers/health")
def alerts_providers_health(provider: str | None = Query(default=None, description="Comma-separated provider names")) -> dict:
    providers = [p.strip() for p in provider.split(",") if p.strip()] if provider else None
    return list_provider_health(providers=providers)


@app.get("/alerts/providers/health/summary")
def alerts_providers_health_summary(provider: str | None = Query(default=None, description="Comma-separated provider names")) -> dict:
    providers = [p.strip() for p in provider.split(",") if p.strip()] if provider else None
    return summarize_provider_health(providers=providers)


@app.get("/alerts/providers/health/summary/recommendations")
def alerts_providers_health_summary_recommendations(provider: str | None = Query(default=None, description="Comma-separated provider names")) -> dict:
    providers = [p.strip() for p in provider.split(",") if p.strip()] if provider else None
    return summarize_provider_health_recommendations(providers=providers)


@app.get("/alerts/providers/health/summary/recommendations/markdown")
def alerts_providers_health_summary_recommendations_markdown(provider: str | None = Query(default=None, description="Comma-separated provider names")) -> dict:
    providers = [p.strip() for p in provider.split(",") if p.strip()] if provider else None
    return {"requested": providers or [], "markdown": render_provider_health_recommendations_markdown(providers=providers)}


@app.get("/alerts/providers/health/summary/recommendations/telegram")
def alerts_providers_health_summary_recommendations_telegram(
    provider: str | None = Query(default=None, description="Comma-separated provider names"),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    providers = [p.strip() for p in provider.split(",") if p.strip()] if provider else None
    return render_provider_health_recommendations_telegram_chunks(providers=providers, max_chars=max_chars)


@app.get("/alerts/providers/health/summary/recommendations/csv")
def alerts_providers_health_summary_recommendations_csv(provider: str | None = Query(default=None, description="Comma-separated provider names")) -> dict:
    providers = [p.strip() for p in provider.split(",") if p.strip()] if provider else None
    return {"requested": providers or [], "csv": render_provider_health_recommendations_csv(providers=providers)}


@app.get("/alerts/providers/health/summary/recommendations/packet")
def alerts_providers_health_summary_recommendations_packet(
    provider: str | None = Query(default=None, description="Comma-separated provider names"),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    providers = [p.strip() for p in provider.split(",") if p.strip()] if provider else None
    return build_provider_health_recommendations_packet(providers=providers, max_chars=max_chars)


@app.get("/alerts/providers/health/summary/options")
def alerts_providers_health_summary_options() -> dict:
    return get_provider_health_summary_options()


@app.get("/alerts/providers/health/summary/options/markdown")
def alerts_providers_health_summary_options_markdown() -> dict:
    return {"markdown": render_provider_health_summary_options_markdown()}


@app.get("/alerts/providers/health/summary/options/telegram")
def alerts_providers_health_summary_options_telegram(
    max_chars: int = Query(default=3500, ge=100, le=4096)
) -> dict:
    return render_provider_health_summary_options_telegram_chunks(max_chars=max_chars)


@app.get("/alerts/providers/health/summary/options/csv")
def alerts_providers_health_summary_options_csv() -> dict:
    return {"csv": render_provider_health_summary_options_csv()}


@app.get("/alerts/providers/health/summary/options/packet")
def alerts_providers_health_summary_options_packet(
    max_chars: int = Query(default=3500, ge=100, le=4096)
) -> dict:
    return build_provider_health_summary_options_packet(max_chars=max_chars)


@app.get("/alerts/providers/health/summary/markdown")
def alerts_providers_health_summary_markdown(provider: str | None = Query(default=None, description="Comma-separated provider names")) -> dict:
    providers = [p.strip() for p in provider.split(",") if p.strip()] if provider else None
    return {"requested": providers or [], "markdown": render_provider_health_summary_markdown(providers=providers)}


@app.get("/alerts/providers/health/summary/telegram")
def alerts_providers_health_summary_telegram(
    provider: str | None = Query(default=None, description="Comma-separated provider names"),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    providers = [p.strip() for p in provider.split(",") if p.strip()] if provider else None
    return render_provider_health_summary_telegram_chunks(providers=providers, max_chars=max_chars)


@app.get("/alerts/providers/health/summary/csv")
def alerts_providers_health_summary_csv(provider: str | None = Query(default=None, description="Comma-separated provider names")) -> dict:
    providers = [p.strip() for p in provider.split(",") if p.strip()] if provider else None
    return {"requested": providers or [], "csv": render_provider_health_summary_csv(providers=providers)}


@app.get("/alerts/providers/health/summary/packet")
def alerts_providers_health_summary_packet(
    provider: str | None = Query(default=None, description="Comma-separated provider names"),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    providers = [p.strip() for p in provider.split(",") if p.strip()] if provider else None
    return build_provider_health_summary_packet(providers=providers, max_chars=max_chars)


@app.get("/alerts/providers/health/options")
def alerts_providers_health_options() -> dict:
    return get_provider_health_options()


@app.get("/alerts/providers/health/options/markdown")
def alerts_providers_health_options_markdown() -> dict:
    return {"markdown": render_provider_health_options_markdown()}


@app.get("/alerts/providers/health/options/telegram")
def alerts_providers_health_options_telegram(
    max_chars: int = Query(default=3500, ge=100, le=4096)
) -> dict:
    return render_provider_health_options_telegram_chunks(max_chars=max_chars)


@app.get("/alerts/providers/health/options/csv")
def alerts_providers_health_options_csv() -> dict:
    return {"csv": render_provider_health_options_csv()}


@app.get("/alerts/providers/health/options/packet")
def alerts_providers_health_options_packet(
    max_chars: int = Query(default=3500, ge=100, le=4096)
) -> dict:
    return build_provider_health_options_packet(max_chars=max_chars)


@app.get("/alerts/providers/details/options")
def alerts_provider_details_options() -> dict:
    return get_provider_details_options()


@app.get("/alerts/providers/details/options/markdown")
def alerts_provider_details_options_markdown() -> dict:
    return {"markdown": render_provider_details_options_markdown()}


@app.get("/alerts/providers/details/options/telegram")
def alerts_provider_details_options_telegram(
    max_chars: int = Query(default=3500, ge=100, le=4096)
) -> dict:
    return render_provider_details_options_telegram_chunks(max_chars=max_chars)


@app.get("/alerts/providers/details/options/csv")
def alerts_provider_details_options_csv() -> dict:
    return {"csv": render_provider_details_options_csv()}


@app.get("/alerts/providers/details/options/packet")
def alerts_provider_details_options_packet(
    max_chars: int = Query(default=3500, ge=100, le=4096)
) -> dict:
    return build_provider_details_options_packet(max_chars=max_chars)


@app.get("/alerts/providers/{provider}/health")
def alerts_provider_health_details(provider: str) -> dict:
    return get_provider_health_details(provider=provider)


@app.get("/alerts/providers/{provider}")
def alerts_provider_details(provider: str) -> dict:
    return get_provider_details(provider=provider)


@app.get("/alerts/providers/recommendations/options")
def alerts_provider_recommendations_options() -> dict:
    return get_provider_recommendations_options()


@app.get("/alerts/providers/recommendations/options/markdown")
def alerts_provider_recommendations_options_markdown() -> dict:
    return {"markdown": render_provider_recommendations_options_markdown()}


@app.get("/alerts/providers/recommendations/options/telegram")
def alerts_provider_recommendations_options_telegram(
    max_chars: int = Query(default=3500, ge=100, le=4096)
) -> dict:
    return render_provider_recommendations_options_telegram_chunks(max_chars=max_chars)


@app.get("/alerts/providers/recommendations/options/csv")
def alerts_provider_recommendations_options_csv() -> dict:
    return {"csv": render_provider_recommendations_options_csv()}


@app.get("/alerts/providers/recommendations/options/packet")
def alerts_provider_recommendations_options_packet(
    max_chars: int = Query(default=3500, ge=100, le=4096)
) -> dict:
    return build_provider_recommendations_options_packet(max_chars=max_chars)


@app.get("/alerts/providers/{provider}/recommendations")
def alerts_provider_recommendations(provider: str) -> dict:
    return get_provider_recommendations(provider=provider)


@app.get("/alerts/providers/{provider}/recommendations/markdown")
def alerts_provider_recommendations_markdown(provider: str) -> dict:
    return {"provider": provider, "markdown": render_provider_recommendations_markdown(provider=provider)}


@app.get("/alerts/providers/{provider}/recommendations/telegram")
def alerts_provider_recommendations_telegram(
    provider: str,
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return render_provider_recommendations_telegram_chunks(provider=provider, max_chars=max_chars)


@app.get("/alerts/providers/{provider}/recommendations/csv")
def alerts_provider_recommendations_csv(provider: str) -> dict:
    return {"provider": provider, "csv": render_provider_recommendations_csv(provider=provider)}


@app.get("/alerts/providers/{provider}/recommendations/packet")
def alerts_provider_recommendations_packet(
    provider: str,
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return build_provider_recommendations_packet(provider=provider, max_chars=max_chars)


@app.post("/alerts/providers/smoke-test")
def alerts_provider_smoke_test(payload: AlertProviderSmokeTestIn) -> dict:
    provider = (payload.provider or "noop").strip() or "noop"
    return run_provider_smoke_test(provider=provider, email=str(payload.email), dry_run=payload.dry_run)


@app.get("/alerts/providers/smoke-test/options")
def alerts_provider_smoke_test_options() -> dict:
    return get_provider_smoke_test_options()


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


@app.get("/alerts/outbox/dispatch/options")
def alerts_outbox_dispatch_options() -> dict:
    return get_outbox_dispatch_options()


@app.post("/alerts/outbox/retry-failed")
def alerts_outbox_retry_failed(payload: AlertOutboxRetryIn) -> dict:
    limit = max(1, min(payload.limit, 500))
    return retry_failed_outbox(limit=limit)


@app.get("/alerts/outbox/retry-failed/options")
def alerts_outbox_retry_failed_options() -> dict:
    return get_outbox_retry_failed_options()


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


@app.get("/alerts/cron/options")
def alerts_cron_options() -> dict:
    return get_alerts_cron_options()




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


@app.get("/alerts/runs/latest/integrity/issues")
def alerts_latest_run_integrity_issues() -> dict:
    return get_latest_run_integrity_issue_details()

@app.get("/alerts/runs/latest/integrity/issues/markdown")
def alerts_latest_run_integrity_issues_markdown() -> dict:
    return render_latest_run_integrity_issues_markdown()

@app.get("/alerts/runs/latest/integrity/issues/telegram")
def alerts_latest_run_integrity_issues_telegram(
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return render_latest_run_integrity_issues_telegram_chunks(max_chars=max_chars)


@app.get("/alerts/runs/latest/integrity/issues/csv")
def alerts_latest_run_integrity_issues_csv() -> dict:
    return render_latest_run_integrity_issues_csv()


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


@app.get("/alerts/runs/{run_id}/integrity/issues")
def alerts_run_integrity_issues(run_id: str) -> dict:
    return get_run_integrity_issue_details(run_id=run_id)

@app.get("/alerts/runs/{run_id}/integrity/issues/markdown")
def alerts_run_integrity_issues_markdown(run_id: str) -> dict:
    return {"run_id": run_id, "markdown": render_run_integrity_issues_markdown(run_id=run_id)}

@app.get("/alerts/runs/{run_id}/integrity/issues/telegram")
def alerts_run_integrity_issues_telegram(
    run_id: str,
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    return render_run_integrity_issues_telegram_chunks(run_id=run_id, max_chars=max_chars)


@app.get("/alerts/runs/{run_id}/integrity/issues/csv")
def alerts_run_integrity_issues_csv(run_id: str) -> dict:
    return {"run_id": run_id, "csv": render_run_integrity_issues_csv(run_id=run_id)}


@app.get("/alerts/runs/latest/incident")
def alerts_latest_run_incident(
    kind: str | None = Query(default=None, description="Comma-separated event kinds"),
    status: str | None = Query(default=None, description="Comma-separated run statuses"),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return build_latest_run_incident_payload(event_kinds=kinds, event_statuses=statuses, event_limit=limit, event_offset=offset)


@app.get("/alerts/runs/latest/incident/markdown")
def alerts_latest_run_incident_markdown(
    kind: str | None = Query(default=None, description="Comma-separated event kinds"),
    status: str | None = Query(default=None, description="Comma-separated run statuses"),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return render_latest_run_incident_markdown(event_kinds=kinds, event_statuses=statuses, event_limit=limit, event_offset=offset)


@app.get("/alerts/runs/latest/incident/telegram")
def alerts_latest_run_incident_telegram(
    kind: str | None = Query(default=None, description="Comma-separated event kinds"),
    status: str | None = Query(default=None, description="Comma-separated run statuses"),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return render_latest_run_incident_telegram_chunks(
        event_kinds=kinds,
        event_statuses=statuses,
        event_limit=limit,
        event_offset=offset,
        max_chars=max_chars,
    )


@app.get("/alerts/runs/latest/incident/csv")
def alerts_latest_run_incident_csv(
    kind: str | None = Query(default=None, description="Comma-separated event kinds"),
    status: str | None = Query(default=None, description="Comma-separated run statuses"),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return render_latest_run_incident_csv(
        event_kinds=kinds,
        event_statuses=statuses,
        event_limit=limit,
        event_offset=offset,
    )


@app.get("/alerts/runs/latest/incident/packet")
def alerts_latest_run_incident_packet(
    kind: str | None = Query(default=None, description="Comma-separated event kinds"),
    status: str | None = Query(default=None, description="Comma-separated run statuses"),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return build_latest_run_incident_export_packet(
        event_kinds=kinds,
        event_statuses=statuses,
        event_limit=limit,
        event_offset=offset,
        max_chars=max_chars,
    )


@app.get("/alerts/runs/{run_id}/incident")
def alerts_run_incident(
    run_id: str,
    kind: str | None = Query(default=None, description="Comma-separated event kinds"),
    status: str | None = Query(default=None, description="Comma-separated run statuses"),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return build_run_incident_payload(
        run_id=run_id,
        event_kinds=kinds,
        event_statuses=statuses,
        event_limit=limit,
        event_offset=offset,
    )


@app.get("/alerts/runs/{run_id}/incident/markdown")
def alerts_run_incident_markdown(
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
        "markdown": render_run_incident_markdown(
            run_id=run_id,
            event_kinds=kinds,
            event_statuses=statuses,
            event_limit=limit,
            event_offset=offset,
        ),
    }


@app.get("/alerts/runs/{run_id}/incident/telegram")
def alerts_run_incident_telegram(
    run_id: str,
    kind: str | None = Query(default=None, description="Comma-separated event kinds"),
    status: str | None = Query(default=None, description="Comma-separated run statuses"),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return render_run_incident_telegram_chunks(
        run_id=run_id,
        event_kinds=kinds,
        event_statuses=statuses,
        event_limit=limit,
        event_offset=offset,
        max_chars=max_chars,
    )


@app.get("/alerts/runs/{run_id}/incident/csv")
def alerts_run_incident_csv(
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
        "csv": render_run_incident_csv(
            run_id=run_id,
            event_kinds=kinds,
            event_statuses=statuses,
            event_limit=limit,
            event_offset=offset,
        ),
    }


@app.get("/alerts/runs/{run_id}/incident/packet")
def alerts_run_incident_packet(
    run_id: str,
    kind: str | None = Query(default=None, description="Comma-separated event kinds"),
    status: str | None = Query(default=None, description="Comma-separated run statuses"),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    max_chars: int = Query(default=3500, ge=100, le=4096),
) -> dict:
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return build_run_incident_export_packet(
        run_id=run_id,
        event_kinds=kinds,
        event_statuses=statuses,
        event_limit=limit,
        event_offset=offset,
        max_chars=max_chars,
    )


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


@app.get("/alerts/runs/latest/events/csv")
def alerts_latest_run_events_csv(
    kind: str | None = Query(default=None, description="Comma-separated event kinds"),
    status: str | None = Query(default=None, description="Comma-separated run statuses"),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return render_latest_run_events_csv(kinds=kinds, statuses=statuses, limit=limit, offset=offset)


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


@app.get("/alerts/runs/{run_id}/events/csv")
def alerts_run_events_csv(
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
        "csv": render_run_events_csv(run_id=run_id, kinds=kinds, statuses=statuses, limit=limit, offset=offset),
    }


@app.get("/alerts/cron/history")
def alerts_cron_history(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    return {"items": list_cron_history(limit=limit)}


@app.get("/alerts/cron/history/options")
def alerts_cron_history_options() -> dict:
    return get_cron_history_options()


@app.post("/alerts/retention/prune")
def alerts_retention_prune(payload: AlertRetentionPruneIn) -> dict:
    return prune_alert_artifacts(
        outbox_keep_last=max(0, payload.outbox_keep_last),
        sent_keep_last=max(0, payload.sent_keep_last),
        failed_keep_last=max(0, payload.failed_keep_last),
        history_keep_last=max(0, payload.history_keep_last),
    )


@app.get("/alerts/retention/prune/options")
def alerts_retention_prune_options() -> dict:
    return get_retention_prune_options()
