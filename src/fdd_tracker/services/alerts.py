from __future__ import annotations

import json
import os
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest
from io import StringIO

from fdd_tracker.services.store import get_alert_feed, get_watchlist_emails, mark_alert_read

ALL_DIGEST_PREVIEW_ORDER_BY_OPTIONS = ["email", "unread_count", "has_unread", "generated_at"]
ALL_DIGEST_PREVIEW_ORDER_DIR_OPTIONS = ["asc", "desc"]


def get_digest_preview_options() -> dict:
    return {
        "constraints": {
            "email": {"type": "string", "required": True},
            "max_alerts": {"type": "int", "min": 1, "max": 1000},
            "max_chars": {"type": "int", "min": 200, "max": 10000},
        },
        "defaults": {
            "max_alerts": 25,
            "max_chars": 2500,
        },
        "surfaces": {
            "preview": "/alerts/digest/preview",
            "preview_markdown": "/alerts/digest/preview/markdown",
            "preview_telegram": "/alerts/digest/preview/telegram",
            "preview_csv": "/alerts/digest/preview/csv",
            "preview_packet": "/alerts/digest/preview/packet",
        },
    }


def get_digest_run_options() -> dict:
    return {
        "constraints": {
            "email": {"type": "string|null", "required": False},
            "max_alerts": {"type": "int", "min": 1, "max": 200},
            "mark_read": {"type": "bool"},
            "run_id": {"type": "string|null", "required": False},
        },
        "defaults": {
            "email": None,
            "max_alerts": 25,
            "mark_read": False,
            "run_id": None,
        },
        "modes": {
            "single_email": "Provide email to run digest for one watchlist owner.",
            "all_emails": "Omit email to run digest for all watchlist owners.",
        },
        "surfaces": {
            "run": "/alerts/digest/run",
            "preview_options": "/alerts/digest/preview/options",
            "preview_all_options": "/alerts/digest/preview/all/options",
        },
    }


def get_digest_preview_all_options() -> dict:
    return {
        "order_by": ALL_DIGEST_PREVIEW_ORDER_BY_OPTIONS,
        "order_dir": ALL_DIGEST_PREVIEW_ORDER_DIR_OPTIONS,
        "constraints": {
            "max_alerts": {"type": "int", "min": 1, "max": 1000},
            "limit": {"type": "int|null", "min": 1, "max": 1000},
            "offset": {"type": "int", "min": 0},
            "top_n": {"type": "int", "min": 1, "max": 1000},
            "min_unread": {"type": "int", "min": 0},
            "unread_only": {"type": "bool"},
            "max_chars": {"type": "int", "min": 200, "max": 10000},
        },
        "defaults": {
            "order_by": "email",
            "order_dir": "asc",
            "limit": None,
            "offset": 0,
            "top_n": 10,
            "max_alerts": 25,
            "min_unread": 0,
            "unread_only": False,
            "max_chars": 2500,
        },
        "surfaces": {
            "preview": "/alerts/digest/preview/all",
            "preview_markdown": "/alerts/digest/preview/all/markdown",
            "preview_telegram": "/alerts/digest/preview/all/telegram",
            "preview_csv": "/alerts/digest/preview/all/csv",
            "preview_packet": "/alerts/digest/preview/all/packet",
            "summary": "/alerts/digest/preview/all/summary",
            "summary_markdown": "/alerts/digest/preview/all/summary/markdown",
            "summary_telegram": "/alerts/digest/preview/all/summary/telegram",
            "summary_csv": "/alerts/digest/preview/all/summary/csv",
            "summary_packet": "/alerts/digest/preview/all/summary/packet",
        },
    }


def get_alerts_cron_options() -> dict:
    provider_catalog = get_dispatch_provider_catalog()
    provider_names = sorted(provider_catalog.get("providers", {}).keys())
    live_capable_providers = sorted(
        [name for name, meta in provider_catalog.get("providers", {}).items() if bool(meta.get("supports_live"))]
    )
    ready_providers = sorted(
        [name for name, meta in provider_catalog.get("providers", {}).items() if bool(meta.get("ready"))]
    )

    return {
        "constraints": {
            "max_alerts": {"type": "int", "min": 1, "max": 200},
            "generate_mark_read": {"type": "bool"},
            "dispatch_limit": {"type": "int", "min": 1, "max": 500},
            "retry_limit": {"type": "int", "min": 1, "max": 500},
            "dispatch_dry_run": {"type": "bool"},
            "dispatch_provider": {"type": "string", "enum": provider_names},
            "run_id": {"type": "string|null", "required": False},
            "lock_stale_after_seconds": {"type": "int", "min": 1, "max": 86400},
            "status_lock_stale_after_seconds": {"type": "int", "min": 1, "max": 86400},
            "history_limit": {"type": "int", "min": 1, "max": 500},
            "force": {"type": "bool"},
        },
        "defaults": {
            "max_alerts": 25,
            "generate_mark_read": False,
            "dispatch_limit": 100,
            "retry_limit": 100,
            "dispatch_dry_run": True,
            "dispatch_provider": "noop",
            "run_id": None,
            "lock_stale_after_seconds": 900,
            "status_lock_stale_after_seconds": 900,
            "history_limit": 50,
            "force": False,
        },
        "providers": {
            "default": provider_catalog.get("default", "noop"),
            "supported": provider_names,
            "live_capable": live_capable_providers,
            "ready": ready_providers,
        },
        "surfaces": {
            "options": "/alerts/cron/options",
            "tick": "/alerts/cron/tick",
            "preflight": "/alerts/cron/preflight",
            "recover_lock": "/alerts/cron/recover-lock",
            "status": "/alerts/cron/status",
            "history": "/alerts/cron/history",
            "history_latest": "/alerts/cron/history/latest",
        },
    }


@dataclass
class WatchlistAlert:
    email: str
    franchise_slug: str
    summary: str


@dataclass
class DigestPayload:
    email: str
    unread_count: int
    subject: str
    body: str
    generated_at: str


def enqueue_alert(alert: WatchlistAlert) -> None:
    """Alert dispatch stub.

    TODO: wire to Loops/Beehiiv/email provider.
    """
    _ = alert


def _default_data_path(filename: str) -> Path:
    return Path(__file__).resolve().parents[3] / "data" / filename


def _history_path() -> Path:
    return _default_data_path("alerts_cron_history.jsonl")


def _lock_path() -> Path:
    return _default_data_path("alerts_cron.lock")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_digest_body(email: str, alerts: list[dict]) -> str:
    lines = [f"FDD Tracker digest for {email}", "", f"Unread alerts: {len(alerts)}", ""]
    for idx, alert in enumerate(alerts, start=1):
        categories = ", ".join(alert["categories"])
        highlights = "; ".join(alert["highlights"])
        lines.append(
            f"{idx}. {alert['franchise_slug']} | risk={alert['risk_level']} | categories={categories} | at={alert['generated_at']}"
        )
        lines.append(f"   highlights: {highlights}")
    return "\n".join(lines)


def build_digest_payload(email: str, max_alerts: int = 25, db_path: str | None = None) -> DigestPayload | None:
    alerts = get_alert_feed(email=email, limit=max_alerts, unread_only=True, db_path=db_path)
    if not alerts:
        return None

    generated_at = _now_iso()
    return DigestPayload(
        email=email,
        unread_count=len(alerts),
        subject=f"FDD Tracker: {len(alerts)} unread changes",
        body=_build_digest_body(email=email, alerts=alerts),
        generated_at=generated_at,
    )


def build_digest_preview(email: str, max_alerts: int = 25, db_path: str | None = None) -> dict:
    """Build a deterministic digest preview payload without mutating outbox/read state."""
    payload = build_digest_payload(email=email, max_alerts=max_alerts, db_path=db_path)
    if payload is None:
        return {
            "email": email,
            "has_unread": False,
            "unread_count": 0,
            "subject": None,
            "body": None,
            "alerts": [],
        }

    alerts = get_alert_feed(email=email, limit=max_alerts, unread_only=True, db_path=db_path)
    return {
        "email": email,
        "has_unread": True,
        "unread_count": payload.unread_count,
        "subject": payload.subject,
        "body": payload.body,
        "generated_at": payload.generated_at,
        "alerts": alerts,
    }


def render_digest_preview_markdown(email: str, max_alerts: int = 25, db_path: str | None = None) -> str:
    preview = build_digest_preview(email=email, max_alerts=max_alerts, db_path=db_path)
    lines = [
        f"# Digest Preview — {email}",
        "",
        f"- Has unread: {preview.get('has_unread', False)}",
        f"- Unread count: {preview.get('unread_count', 0)}",
    ]

    if preview.get("subject"):
        lines.append(f"- Subject: {preview.get('subject')}")
    if preview.get("generated_at"):
        lines.append(f"- Generated at: {preview.get('generated_at')}")

    lines.extend(["", "## Body", preview.get("body") or "(no unread alerts)"])
    return "\n".join(lines)


def render_digest_preview_telegram_chunks(
    email: str,
    max_alerts: int = 25,
    db_path: str | None = None,
    max_chars: int = 3500,
) -> dict:
    markdown = render_digest_preview_markdown(email=email, max_alerts=max_alerts, db_path=db_path)
    max_chars = max(100, min(max_chars, 4096))

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in markdown.split("\n"):
        if len(line) > max_chars:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for i in range(0, len(line), max_chars):
                chunks.append(line[i : i + max_chars])
            continue

        line_len = len(line) + (1 if current else 0)
        if current and (current_len + line_len) > max_chars:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue

        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    indexed_chunks = [f"[{idx}/{len(chunks)}]\n{chunk}" for idx, chunk in enumerate(chunks, start=1)]
    return {
        "email": email,
        "total_chars": len(markdown),
        "max_chars": max_chars,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "chunks_with_index": indexed_chunks,
    }


def render_digest_preview_csv(email: str, max_alerts: int = 25, db_path: str | None = None) -> str:
    preview = build_digest_preview(email=email, max_alerts=max_alerts, db_path=db_path)
    alerts = preview.get("alerts") or []

    output = StringIO()
    fieldnames = [
        "email",
        "has_unread",
        "unread_count",
        "subject",
        "generated_at",
        "franchise_slug",
        "risk_level",
        "generated_alert_at",
        "highlights",
        "categories",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    if not alerts:
        writer.writerow(
            {
                "email": email,
                "has_unread": preview.get("has_unread", False),
                "unread_count": preview.get("unread_count", 0),
                "subject": preview.get("subject"),
                "generated_at": preview.get("generated_at"),
            }
        )
        return output.getvalue()

    for alert in alerts:
        writer.writerow(
            {
                "email": email,
                "has_unread": preview.get("has_unread", False),
                "unread_count": preview.get("unread_count", 0),
                "subject": preview.get("subject"),
                "generated_at": preview.get("generated_at"),
                "franchise_slug": alert.get("franchise_slug"),
                "risk_level": alert.get("risk_level"),
                "generated_alert_at": alert.get("generated_at"),
                "highlights": "; ".join(alert.get("highlights") or []),
                "categories": ", ".join(alert.get("categories") or []),
            }
        )
    return output.getvalue()


def build_digest_preview_packet(
    email: str,
    max_alerts: int = 25,
    db_path: str | None = None,
    max_chars: int = 3500,
) -> dict:
    return {
        "email": email,
        "preview": build_digest_preview(email=email, max_alerts=max_alerts, db_path=db_path),
        "markdown": render_digest_preview_markdown(email=email, max_alerts=max_alerts, db_path=db_path),
        "csv": render_digest_preview_csv(email=email, max_alerts=max_alerts, db_path=db_path),
        "telegram": render_digest_preview_telegram_chunks(
            email=email,
            max_alerts=max_alerts,
            db_path=db_path,
            max_chars=max_chars,
        ),
    }


def build_digest_previews_for_all_emails(
    max_alerts: int = 25,
    unread_only: bool = False,
    min_unread: int = 0,
    order_by: str = "email",
    order_dir: str = "asc",
    limit: int | None = None,
    offset: int = 0,
    db_path: str | None = None,
) -> dict:
    emails = sorted(get_watchlist_emails(db_path=db_path))
    previews = [build_digest_preview(email=email, max_alerts=max_alerts, db_path=db_path) for email in emails]
    min_unread = max(0, min(min_unread, 10_000))
    if unread_only:
        previews = [item for item in previews if item.get("has_unread")]
    if min_unread > 0:
        previews = [item for item in previews if int(item.get("unread_count") or 0) >= min_unread]

    order_by = (order_by or "email").strip().lower()
    if order_by not in set(ALL_DIGEST_PREVIEW_ORDER_BY_OPTIONS):
        order_by = "email"
    order_dir = (order_dir or "asc").strip().lower()
    if order_dir not in set(ALL_DIGEST_PREVIEW_ORDER_DIR_OPTIONS):
        order_dir = "asc"

    def _key(item: dict) -> tuple:
        if order_by == "unread_count":
            return (int(item.get("unread_count") or 0), item.get("email") or "")
        if order_by == "has_unread":
            return (int(bool(item.get("has_unread"))), item.get("email") or "")
        if order_by == "generated_at":
            return (item.get("generated_at") or "", item.get("email") or "")
        return ((item.get("email") or "").lower(),)

    previews = sorted(previews, key=_key, reverse=(order_dir == "desc"))

    total_matched = len(previews)
    offset = max(0, min(offset, total_matched))
    if limit is None:
        paged_previews = previews[offset:]
        applied_limit = None
        effective_limit = max(1, total_matched) if total_matched > 0 else 1
    else:
        applied_limit = max(1, min(limit, 10_000))
        effective_limit = applied_limit
        paged_previews = previews[offset : offset + applied_limit]

    page_end = offset + len(paged_previews)
    has_more = page_end < total_matched
    next_offset = page_end if has_more else None
    prev_offset = max(0, offset - (applied_limit or offset)) if offset > 0 else None
    current_page = (offset // effective_limit) + 1 if total_matched > 0 else 1
    total_pages = max(1, (total_matched + effective_limit - 1) // effective_limit)

    return {
        "emails_scanned": len(emails),
        "matched": total_matched,
        "returned": len(paged_previews),
        "limit": applied_limit,
        "offset": offset,
        "page_end": page_end,
        "has_more": has_more,
        "next_offset": next_offset,
        "prev_offset": prev_offset,
        "effective_limit": effective_limit,
        "current_page": current_page,
        "total_pages": total_pages,
        "unread_only": unread_only,
        "min_unread": min_unread,
        "order_by": order_by,
        "order_dir": order_dir,
        "previews": paged_previews,
    }


def render_digest_previews_all_markdown(
    max_alerts: int = 25,
    unread_only: bool = False,
    min_unread: int = 0,
    order_by: str = "email",
    order_dir: str = "asc",
    limit: int | None = None,
    offset: int = 0,
    db_path: str | None = None,
) -> str:
    payload = build_digest_previews_for_all_emails(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        db_path=db_path,
    )
    lines = [
        "# Digest Preview All Emails",
        "",
        f"- Emails scanned: {payload.get('emails_scanned', 0)}",
        f"- Matched: {payload.get('matched', 0)}",
        f"- Returned: {payload.get('returned', 0)}",
        f"- Pagination: limit={payload.get('limit')} offset={payload.get('offset', 0)}",
        f"- Paging: has_more={payload.get('has_more', False)} next_offset={payload.get('next_offset')} prev_offset={payload.get('prev_offset')}",
        f"- Page: {payload.get('current_page', 1)}/{payload.get('total_pages', 1)} (effective_limit={payload.get('effective_limit')})",
        f"- Unread-only mode: {payload.get('unread_only', False)}",
        f"- Min unread filter: {payload.get('min_unread', 0)}",
        f"- Ordering: {payload.get('order_by', 'email')} {payload.get('order_dir', 'asc')}",
        "",
        "## Previews",
    ]
    previews = payload.get("previews") or []
    if not previews:
        lines.append("- none")
        return "\n".join(lines)

    for item in previews:
        lines.append(f"- {item.get('email')}: unread={item.get('unread_count', 0)} has_unread={item.get('has_unread', False)}")
    return "\n".join(lines)


def render_digest_previews_all_telegram_chunks(
    max_alerts: int = 25,
    unread_only: bool = False,
    min_unread: int = 0,
    order_by: str = "email",
    order_dir: str = "asc",
    limit: int | None = None,
    offset: int = 0,
    db_path: str | None = None,
    max_chars: int = 3500,
) -> dict:
    payload = build_digest_previews_for_all_emails(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        db_path=db_path,
    )
    markdown = render_digest_previews_all_markdown(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        limit=limit,
        offset=offset,
        db_path=db_path,
    )
    max_chars = max(100, min(max_chars, 4096))

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in markdown.split("\n"):
        if len(line) > max_chars:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for i in range(0, len(line), max_chars):
                chunks.append(line[i : i + max_chars])
            continue
        line_len = len(line) + (1 if current else 0)
        if current and (current_len + line_len) > max_chars:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    indexed_chunks = [f"[{idx}/{len(chunks)}]\n{chunk}" for idx, chunk in enumerate(chunks, start=1)]
    return {
        "max_alerts": max_alerts,
        "unread_only": unread_only,
        "min_unread": max(0, min(min_unread, 10_000)),
        "limit": limit,
        "offset": max(0, offset),
        "has_more": payload.get("has_more", False),
        "next_offset": payload.get("next_offset"),
        "prev_offset": payload.get("prev_offset"),
        "effective_limit": payload.get("effective_limit"),
        "current_page": payload.get("current_page", 1),
        "total_pages": payload.get("total_pages", 1),
        "order_by": payload.get("order_by", "email"),
        "order_dir": payload.get("order_dir", "asc"),
        "total_chars": len(markdown),
        "max_chars": max_chars,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "chunks_with_index": indexed_chunks,
    }


def render_digest_previews_all_csv(
    max_alerts: int = 25,
    unread_only: bool = False,
    min_unread: int = 0,
    order_by: str = "email",
    order_dir: str = "asc",
    limit: int | None = None,
    offset: int = 0,
    db_path: str | None = None,
) -> str:
    payload = build_digest_previews_for_all_emails(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        db_path=db_path,
    )
    output = StringIO()
    fieldnames = [
        "emails_scanned",
        "matched",
        "returned",
        "limit",
        "offset",
        "page_end",
        "has_more",
        "next_offset",
        "prev_offset",
        "effective_limit",
        "current_page",
        "total_pages",
        "order_by",
        "order_dir",
        "unread_only",
        "min_unread",
        "email",
        "has_unread",
        "unread_count",
        "subject",
        "generated_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    previews = payload.get("previews") or []
    if not previews:
        writer.writerow(
            {
                "emails_scanned": payload.get("emails_scanned", 0),
                "matched": payload.get("matched", 0),
                "returned": payload.get("returned", 0),
                "limit": payload.get("limit"),
                "offset": payload.get("offset", 0),
                "page_end": payload.get("page_end", 0),
                "has_more": payload.get("has_more", False),
                "next_offset": payload.get("next_offset"),
                "prev_offset": payload.get("prev_offset"),
                "effective_limit": payload.get("effective_limit"),
                "current_page": payload.get("current_page", 1),
                "total_pages": payload.get("total_pages", 1),
                "order_by": payload.get("order_by", "email"),
                "order_dir": payload.get("order_dir", "asc"),
                "unread_only": payload.get("unread_only", False),
                "min_unread": payload.get("min_unread", 0),
            }
        )
        return output.getvalue()

    for item in previews:
        writer.writerow(
            {
                "emails_scanned": payload.get("emails_scanned", 0),
                "matched": payload.get("matched", 0),
                "returned": payload.get("returned", 0),
                "limit": payload.get("limit"),
                "offset": payload.get("offset", 0),
                "page_end": payload.get("page_end", 0),
                "has_more": payload.get("has_more", False),
                "next_offset": payload.get("next_offset"),
                "prev_offset": payload.get("prev_offset"),
                "effective_limit": payload.get("effective_limit"),
                "current_page": payload.get("current_page", 1),
                "total_pages": payload.get("total_pages", 1),
                "order_by": payload.get("order_by", "email"),
                "order_dir": payload.get("order_dir", "asc"),
                "unread_only": payload.get("unread_only", False),
                "min_unread": payload.get("min_unread", 0),
                "email": item.get("email"),
                "has_unread": item.get("has_unread", False),
                "unread_count": item.get("unread_count", 0),
                "subject": item.get("subject"),
                "generated_at": item.get("generated_at"),
            }
        )
    return output.getvalue()


def build_digest_previews_all_packet(
    max_alerts: int = 25,
    unread_only: bool = False,
    min_unread: int = 0,
    order_by: str = "email",
    order_dir: str = "asc",
    limit: int | None = None,
    offset: int = 0,
    db_path: str | None = None,
    max_chars: int = 3500,
) -> dict:
    return {
        "payload": build_digest_previews_for_all_emails(
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_unread=min_unread,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
            db_path=db_path,
        ),
        "markdown": render_digest_previews_all_markdown(
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_unread=min_unread,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
            db_path=db_path,
        ),
        "csv": render_digest_previews_all_csv(
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_unread=min_unread,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
            db_path=db_path,
        ),
        "telegram": render_digest_previews_all_telegram_chunks(
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_unread=min_unread,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
            db_path=db_path,
            max_chars=max_chars,
        ),
    }


def summarize_digest_previews_for_all_emails(
    max_alerts: int = 25,
    unread_only: bool = False,
    min_unread: int = 0,
    order_by: str = "email",
    order_dir: str = "asc",
    limit: int | None = None,
    offset: int = 0,
    top_n: int = 10,
    db_path: str | None = None,
) -> dict:
    payload = build_digest_previews_for_all_emails(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        db_path=db_path,
    )
    previews = payload.get("previews") or []

    unread_total = int(sum(int(item.get("unread_count") or 0) for item in previews))
    emails_with_unread = int(sum(1 for item in previews if item.get("has_unread")))
    top_n = max(1, min(top_n, 100))
    top_unread = sorted(
        (
            {
                "email": item.get("email"),
                "unread_count": int(item.get("unread_count") or 0),
            }
            for item in previews
        ),
        key=lambda row: (-row["unread_count"], row["email"] or ""),
    )[:top_n]

    return {
        "emails_scanned": payload.get("emails_scanned", 0),
        "matched": payload.get("matched", 0),
        "returned": payload.get("returned", 0),
        "limit": payload.get("limit"),
        "offset": payload.get("offset", 0),
        "page_end": payload.get("page_end", 0),
        "has_more": payload.get("has_more", False),
        "next_offset": payload.get("next_offset"),
        "prev_offset": payload.get("prev_offset"),
        "effective_limit": payload.get("effective_limit"),
        "current_page": payload.get("current_page", 1),
        "total_pages": payload.get("total_pages", 1),
        "order_by": payload.get("order_by", "email"),
        "order_dir": payload.get("order_dir", "asc"),
        "unread_only": unread_only,
        "min_unread": payload.get("min_unread", 0),
        "emails_with_unread": emails_with_unread,
        "emails_without_unread": max(0, int(payload.get("returned", 0)) - emails_with_unread),
        "unread_alert_total": unread_total,
        "top_n": top_n,
        "top_unread_emails": top_unread,
    }


def render_digest_preview_all_summary_markdown(
    max_alerts: int = 25,
    unread_only: bool = False,
    min_unread: int = 0,
    order_by: str = "email",
    order_dir: str = "asc",
    limit: int | None = None,
    offset: int = 0,
    top_n: int = 10,
    db_path: str | None = None,
) -> str:
    summary = summarize_digest_previews_for_all_emails(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        top_n=top_n,
        db_path=db_path,
    )
    lines = [
        "# Digest Preview All-Email Summary",
        "",
        f"- Emails scanned: {summary.get('emails_scanned', 0)}",
        f"- Matched: {summary.get('matched', 0)}",
        f"- Returned: {summary.get('returned', 0)}",
        f"- Pagination: limit={summary.get('limit')} offset={summary.get('offset', 0)}",
        f"- Paging: has_more={summary.get('has_more', False)} next_offset={summary.get('next_offset')} prev_offset={summary.get('prev_offset')}",
        f"- Page: {summary.get('current_page', 1)}/{summary.get('total_pages', 1)} (effective_limit={summary.get('effective_limit')})",
        f"- Unread-only mode: {summary.get('unread_only', False)}",
        f"- Min unread filter: {summary.get('min_unread', 0)}",
        f"- Emails with unread: {summary.get('emails_with_unread', 0)}",
        f"- Emails without unread: {summary.get('emails_without_unread', 0)}",
        f"- Total unread alerts: {summary.get('unread_alert_total', 0)}",
        f"- Ordering: {summary.get('order_by', 'email')} {summary.get('order_dir', 'asc')}",
        "",
        f"## Top Unread Emails ({summary.get('top_n', top_n)})",
    ]
    top = summary.get("top_unread_emails") or []
    if top:
        for item in top:
            lines.append(f"- {item.get('email')}: {item.get('unread_count', 0)}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def render_digest_preview_all_summary_telegram_chunks(
    max_alerts: int = 25,
    unread_only: bool = False,
    min_unread: int = 0,
    order_by: str = "email",
    order_dir: str = "asc",
    limit: int | None = None,
    offset: int = 0,
    top_n: int = 10,
    db_path: str | None = None,
    max_chars: int = 3500,
) -> dict:
    summary = summarize_digest_previews_for_all_emails(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        top_n=top_n,
        db_path=db_path,
    )
    markdown = render_digest_preview_all_summary_markdown(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        limit=limit,
        offset=offset,
        top_n=top_n,
        db_path=db_path,
    )
    max_chars = max(100, min(max_chars, 4096))

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in markdown.split("\n"):
        if len(line) > max_chars:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for i in range(0, len(line), max_chars):
                chunks.append(line[i : i + max_chars])
            continue
        line_len = len(line) + (1 if current else 0)
        if current and (current_len + line_len) > max_chars:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    indexed_chunks = [f"[{idx}/{len(chunks)}]\n{chunk}" for idx, chunk in enumerate(chunks, start=1)]
    return {
        "max_alerts": max_alerts,
        "unread_only": unread_only,
        "min_unread": max(0, min(min_unread, 10_000)),
        "limit": limit,
        "offset": max(0, offset),
        "has_more": summary.get("has_more", False),
        "next_offset": summary.get("next_offset"),
        "prev_offset": summary.get("prev_offset"),
        "effective_limit": summary.get("effective_limit"),
        "current_page": summary.get("current_page", 1),
        "total_pages": summary.get("total_pages", 1),
        "order_by": summary.get("order_by", "email"),
        "order_dir": summary.get("order_dir", "asc"),
        "top_n": top_n,
        "total_chars": len(markdown),
        "max_chars": max_chars,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "chunks_with_index": indexed_chunks,
    }


def render_digest_preview_all_summary_csv(
    max_alerts: int = 25,
    unread_only: bool = False,
    min_unread: int = 0,
    order_by: str = "email",
    order_dir: str = "asc",
    limit: int | None = None,
    offset: int = 0,
    top_n: int = 10,
    db_path: str | None = None,
) -> str:
    summary = summarize_digest_previews_for_all_emails(
        max_alerts=max_alerts,
        unread_only=unread_only,
        min_unread=min_unread,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
        top_n=top_n,
        db_path=db_path,
    )
    output = StringIO()
    fieldnames = [
        "emails_scanned",
        "matched",
        "returned",
        "limit",
        "offset",
        "page_end",
        "has_more",
        "next_offset",
        "prev_offset",
        "effective_limit",
        "current_page",
        "total_pages",
        "order_by",
        "order_dir",
        "unread_only",
        "min_unread",
        "emails_with_unread",
        "emails_without_unread",
        "unread_alert_total",
        "top_n",
        "top_unread_email",
        "top_unread_count",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    top = summary.get("top_unread_emails") or []
    if not top:
        writer.writerow(
            {
                "emails_scanned": summary.get("emails_scanned", 0),
                "matched": summary.get("matched", 0),
                "returned": summary.get("returned", 0),
                "limit": summary.get("limit"),
                "offset": summary.get("offset", 0),
                "page_end": summary.get("page_end", 0),
                "has_more": summary.get("has_more", False),
                "next_offset": summary.get("next_offset"),
                "prev_offset": summary.get("prev_offset"),
                "effective_limit": summary.get("effective_limit"),
                "current_page": summary.get("current_page", 1),
                "total_pages": summary.get("total_pages", 1),
                "order_by": summary.get("order_by", "email"),
                "order_dir": summary.get("order_dir", "asc"),
                "unread_only": summary.get("unread_only", False),
                "min_unread": summary.get("min_unread", 0),
                "emails_with_unread": summary.get("emails_with_unread", 0),
                "emails_without_unread": summary.get("emails_without_unread", 0),
                "unread_alert_total": summary.get("unread_alert_total", 0),
                "top_n": summary.get("top_n", top_n),
            }
        )
        return output.getvalue()

    for item in top:
        writer.writerow(
            {
                "emails_scanned": summary.get("emails_scanned", 0),
                "matched": summary.get("matched", 0),
                "returned": summary.get("returned", 0),
                "limit": summary.get("limit"),
                "offset": summary.get("offset", 0),
                "page_end": summary.get("page_end", 0),
                "has_more": summary.get("has_more", False),
                "next_offset": summary.get("next_offset"),
                "prev_offset": summary.get("prev_offset"),
                "effective_limit": summary.get("effective_limit"),
                "current_page": summary.get("current_page", 1),
                "total_pages": summary.get("total_pages", 1),
                "order_by": summary.get("order_by", "email"),
                "order_dir": summary.get("order_dir", "asc"),
                "unread_only": summary.get("unread_only", False),
                "min_unread": summary.get("min_unread", 0),
                "emails_with_unread": summary.get("emails_with_unread", 0),
                "emails_without_unread": summary.get("emails_without_unread", 0),
                "unread_alert_total": summary.get("unread_alert_total", 0),
                "top_n": summary.get("top_n", top_n),
                "top_unread_email": item.get("email"),
                "top_unread_count": item.get("unread_count", 0),
            }
        )
    return output.getvalue()


def build_digest_preview_all_summary_packet(
    max_alerts: int = 25,
    unread_only: bool = False,
    min_unread: int = 0,
    order_by: str = "email",
    order_dir: str = "asc",
    limit: int | None = None,
    offset: int = 0,
    top_n: int = 10,
    db_path: str | None = None,
    max_chars: int = 3500,
) -> dict:
    return {
        "summary": summarize_digest_previews_for_all_emails(
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_unread=min_unread,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
            top_n=top_n,
            db_path=db_path,
        ),
        "markdown": render_digest_preview_all_summary_markdown(
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_unread=min_unread,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
            top_n=top_n,
            db_path=db_path,
        ),
        "csv": render_digest_preview_all_summary_csv(
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_unread=min_unread,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
            top_n=top_n,
            db_path=db_path,
        ),
        "telegram": render_digest_preview_all_summary_telegram_chunks(
            max_alerts=max_alerts,
            unread_only=unread_only,
            min_unread=min_unread,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
            top_n=top_n,
            db_path=db_path,
            max_chars=max_chars,
        ),
    }


def write_digest_outbox(payload: DigestPayload, outbox_path: str | None = None, run_id: str | None = None) -> str:
    path = Path(outbox_path) if outbox_path else _default_data_path("alert_outbox.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "email": payload.email,
        "unread_count": payload.unread_count,
        "subject": payload.subject,
        "body": payload.body,
        "generated_at": payload.generated_at,
        "queued_at": _now_iso(),
        "run_id": run_id,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return str(path)


def list_outbox(limit: int = 100, outbox_path: str | None = None) -> list[dict]:
    path = Path(outbox_path) if outbox_path else _default_data_path("alert_outbox.jsonl")
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    rows = [json.loads(line) for line in lines]
    return rows[-limit:]



def _list_jsonl_records(
    path: Path,
    limit: int = 100,
    email: str | None = None,
    run_id: str | None = None,
) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    if email:
        rows = [row for row in rows if row.get("email") == email]
    if run_id:
        rows = [row for row in rows if row.get("run_id") == run_id]

    return rows[-max(1, limit):]


def list_sent_outbox(
    limit: int = 100,
    email: str | None = None,
    run_id: str | None = None,
    sent_path: str | None = None,
) -> list[dict]:
    path = Path(sent_path) if sent_path else _default_data_path("alert_outbox_sent.jsonl")
    return _list_jsonl_records(path=path, limit=limit, email=email, run_id=run_id)


def list_failed_outbox(
    limit: int = 100,
    email: str | None = None,
    run_id: str | None = None,
    failed_path: str | None = None,
) -> list[dict]:
    path = Path(failed_path) if failed_path else _default_data_path("alert_outbox_failed.jsonl")
    return _list_jsonl_records(path=path, limit=limit, email=email, run_id=run_id)



def get_dispatch_provider_catalog() -> dict:
    providers = {
        "noop": {
            "supports_live": False,
            "requires_env": [],
            "ready": True,
            "description": "No-op dispatcher for deterministic dry-run testing.",
        },
        "loops": {
            "supports_live": False,
            "requires_env": ["LOOPS_API_KEY"],
            "ready": bool(os.getenv("LOOPS_API_KEY")),
            "description": "Reserved provider slot for future Loops integration.",
        },
        "beehiiv": {
            "supports_live": False,
            "requires_env": ["BEEHIIV_API_KEY"],
            "ready": bool(os.getenv("BEEHIIV_API_KEY")),
            "description": "Reserved provider slot for future Beehiiv integration.",
        },
        "resend": {
            "supports_live": True,
            "requires_env": ["RESEND_API_KEY", "ALERTS_FROM_EMAIL"],
            "ready": bool(os.getenv("RESEND_API_KEY")) and bool(os.getenv("ALERTS_FROM_EMAIL")),
            "description": "Resend email provider for live alert delivery.",
        },
    }
    return {"default": "noop", "providers": providers}




def get_provider_health(provider: str) -> dict:
    provider_name = (provider or "noop").strip().lower() or "noop"
    catalog = get_dispatch_provider_catalog()
    meta = catalog["providers"].get(provider_name)
    if not meta:
        return {"provider": provider_name, "known": False, "ready": False, "reason": "unsupported-provider"}

    missing = [k for k in meta.get("requires_env", []) if not os.getenv(k)]
    return {
        "provider": provider_name,
        "known": True,
        "supports_live": bool(meta.get("supports_live", False)),
        "ready": bool(meta.get("ready", False)) and not missing,
        "missing_env": missing,
        "description": meta.get("description"),
    }

def validate_dispatch_provider(provider: str, dry_run: bool = True) -> dict:
    provider_name = (provider or "noop").strip().lower() or "noop"
    catalog = get_dispatch_provider_catalog()
    providers = catalog["providers"]
    if provider_name not in providers:
        return {
            "ok": False,
            "provider": provider_name,
            "reason": "unsupported-provider",
            "supported": sorted(providers.keys()),
            "dry_run": dry_run,
        }

    meta = providers[provider_name]
    if dry_run:
        return {"ok": True, "provider": provider_name, "dry_run": True, "meta": meta}

    if not meta.get("supports_live", False):
        return {
            "ok": False,
            "provider": provider_name,
            "reason": "live-not-supported",
            "supported_live": [name for name, m in providers.items() if m.get("supports_live")],
            "dry_run": False,
        }

    missing = [k for k in meta.get("requires_env", []) if not os.getenv(k)]
    if missing:
        return {
            "ok": False,
            "provider": provider_name,
            "reason": "missing-env",
            "missing_env": missing,
            "dry_run": False,
        }

    return {"ok": True, "provider": provider_name, "dry_run": False, "meta": meta}



def _live_dispatch_guard_path() -> Path:
    return _default_data_path("live_dispatch_guard.json")


def enforce_live_dispatch_gate(
    provider: str,
    dry_run: bool,
    confirm_live: bool,
    idempotency_key: str | None = None,
    min_interval_seconds: int = 60,
    guard_path: str | None = None,
) -> dict:
    provider_name = (provider or "noop").strip().lower() or "noop"
    if dry_run:
        return {"ok": True, "provider": provider_name, "mode": "dry_run"}

    if not confirm_live:
        return {"ok": False, "reason": "live-dispatch-confirmation-required", "provider": provider_name}

    path = Path(guard_path) if guard_path else _live_dispatch_guard_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    state = {"last_live_dispatch_at": None, "idempotency_keys": []}
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            state = {"last_live_dispatch_at": None, "idempotency_keys": []}

    keys = list(state.get("idempotency_keys", []))
    if idempotency_key:
        if idempotency_key in keys:
            return {"ok": False, "reason": "live-dispatch-duplicate-idempotency-key", "provider": provider_name}

    last_at = state.get("last_live_dispatch_at")
    if last_at:
        try:
            last_dt = datetime.fromisoformat(last_at)
            if now < last_dt + timedelta(seconds=max(1, min_interval_seconds)):
                return {
                    "ok": False,
                    "reason": "live-dispatch-rate-limited",
                    "provider": provider_name,
                    "retry_after_seconds": int((last_dt + timedelta(seconds=max(1, min_interval_seconds)) - now).total_seconds()),
                }
        except ValueError:
            pass

    if idempotency_key:
        keys.append(idempotency_key)

    state["last_live_dispatch_at"] = now.isoformat()
    state["idempotency_keys"] = keys[-200:]
    path.write_text(json.dumps(state), encoding="utf-8")

    return {"ok": True, "provider": provider_name, "mode": "live", "idempotency_key": idempotency_key}

def dispatch_outbox(
    limit: int = 100,
    outbox_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    dry_run: bool = True,
    provider: str = "noop",
) -> dict:
    provider_check = validate_dispatch_provider(provider=provider, dry_run=dry_run)
    provider_name = provider_check.get("provider", (provider or "noop").strip().lower() or "noop")
    outbox = Path(outbox_path) if outbox_path else _default_data_path("alert_outbox.jsonl")
    sent = Path(sent_path) if sent_path else _default_data_path("alert_outbox_sent.jsonl")
    failed = Path(failed_path) if failed_path else _default_data_path("alert_outbox_failed.jsonl")

    if not provider_check.get("ok", False):
        remaining = 0
        if outbox.exists():
            with outbox.open("r", encoding="utf-8") as f:
                remaining = sum(1 for line in f if line.strip())
        return {
            "dispatched": 0,
            "failed": 0,
            "remaining": remaining,
            "sent_path": str(sent),
            "failed_path": str(failed),
            "outbox_path": str(outbox),
            "dry_run": dry_run,
            "provider": provider_name,
            "error": provider_check,
        }

    if not outbox.exists():
        return {"dispatched": 0, "failed": 0, "remaining": 0, "sent_path": str(sent), "failed_path": str(failed), "outbox_path": str(outbox), "dry_run": dry_run, "provider": provider_name, "validation": provider_check}

    with outbox.open("r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]

    to_dispatch = lines[:limit]
    remaining = lines[limit:]

    dispatched_lines: list[str] = []
    failed_lines: list[str] = []
    for line in to_dispatch:
        row = json.loads(line)
        row["delivery_provider"] = provider_name
        row["delivery_mode"] = "dry_run" if dry_run else "live"
        if row.get("force_fail"):
            row["failure_reason"] = row.get("failure_reason", "forced failure")
            row["failed_at"] = _now_iso()
            failed_lines.append(json.dumps(row) + "\n")
        else:
            if dry_run:
                row["dispatched_at"] = _now_iso()
                row["delivery_status"] = "simulated_sent"
                row["provider_message_id"] = (
                    f"{provider_name}-{row.get('run_id') or 'adhoc'}-{int(datetime.now(timezone.utc).timestamp())}"
                )
                dispatched_lines.append(json.dumps(row) + "\n")
            else:
                live_result = _dispatch_live(provider_name=provider_name, payload=row)
                if live_result["ok"]:
                    row["dispatched_at"] = _now_iso()
                    row["delivery_status"] = "sent"
                    row["provider_message_id"] = live_result.get("provider_message_id")
                    dispatched_lines.append(json.dumps(row) + "\n")
                else:
                    row["failure_reason"] = live_result.get("error", "provider dispatch failed")
                    row["failed_at"] = _now_iso()
                    failed_lines.append(json.dumps(row) + "\n")

    if dispatched_lines:
        sent.parent.mkdir(parents=True, exist_ok=True)
        with sent.open("a", encoding="utf-8") as sf:
            sf.writelines(dispatched_lines)

    if failed_lines:
        failed.parent.mkdir(parents=True, exist_ok=True)
        with failed.open("a", encoding="utf-8") as ff:
            ff.writelines(failed_lines)

    with outbox.open("w", encoding="utf-8") as of:
        of.writelines(remaining)

    return {
        "dispatched": len(dispatched_lines),
        "failed": len(failed_lines),
        "remaining": len(remaining),
        "sent_path": str(sent),
        "failed_path": str(failed),
        "outbox_path": str(outbox),
        "dry_run": dry_run,
        "provider": provider_name,
        "validation": provider_check,
    }


def _dispatch_live(provider_name: str, payload: dict) -> dict:
    if provider_name == "resend":
        return _dispatch_via_resend(payload)
    return {"ok": False, "error": f"live dispatch handler missing for provider={provider_name}"}


def _dispatch_via_resend(payload: dict) -> dict:
    api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("ALERTS_FROM_EMAIL")
    if not api_key or not from_email:
        return {"ok": False, "error": "missing resend env vars"}

    body = {
        "from": from_email,
        "to": [payload["email"]],
        "subject": payload["subject"],
        "text": payload["body"],
    }
    reply_to = os.getenv("ALERTS_REPLY_TO_EMAIL")
    if reply_to:
        body["reply_to"] = reply_to

    req = urlrequest.Request(
        url="https://api.resend.com/emails",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw or "{}")
            return {"ok": True, "provider_message_id": parsed.get("id")}
    except (urlerror.URLError, json.JSONDecodeError, TimeoutError) as exc:
        return {"ok": False, "error": str(exc)}


def run_provider_smoke_test(provider: str, email: str, dry_run: bool = True) -> dict:
    provider_name = (provider or "noop").strip().lower() or "noop"
    validation = validate_dispatch_provider(provider=provider_name, dry_run=dry_run)

    if not validation.get("ok", False):
        return {
            "success": False,
            "provider": provider_name,
            "email": email,
            "mode": "dry_run" if dry_run else "live",
            "validation": validation,
        }

    now = datetime.now(timezone.utc)
    payload = {
        "email": email,
        "subject": f"FDD Tracker provider smoke test ({provider_name})",
        "body": f"Smoke test at {now.isoformat()} for provider={provider_name}, dry_run={dry_run}",
        "generated_at": now.isoformat(),
        "run_id": f"smoke-{int(now.timestamp())}",
    }

    if dry_run:
        return {
            "success": True,
            "provider": provider_name,
            "email": email,
            "mode": "dry_run",
            "provider_message_id": f"{provider_name}-smoke-{int(now.timestamp())}",
            "validation": validation,
        }

    live_result = _dispatch_live(provider_name=provider_name, payload=payload)
    if live_result.get("ok", False):
        return {
            "success": True,
            "provider": provider_name,
            "email": email,
            "mode": "live",
            "provider_message_id": live_result.get("provider_message_id"),
            "validation": validation,
        }

    return {
        "success": False,
        "provider": provider_name,
        "email": email,
        "mode": "live",
        "validation": validation,
        "error": live_result.get("error", "provider dispatch failed"),
    }


def run_digest_for_email(
    email: str,
    max_alerts: int = 25,
    mark_read: bool = False,
    db_path: str | None = None,
    outbox_path: str | None = None,
    run_id: str | None = None,
) -> dict:
    unread_alerts = get_alert_feed(email=email, limit=max_alerts, unread_only=True, db_path=db_path)
    payload = build_digest_payload(email=email, max_alerts=max_alerts, db_path=db_path)
    if payload is None:
        return {"email": email, "sent": False, "unread_count": 0, "outbox_path": None, "marked_read": 0}

    outbox_path = write_digest_outbox(payload, outbox_path=outbox_path, run_id=run_id)

    marked_read = 0
    if mark_read:
        for alert in unread_alerts:
            marked_read += mark_alert_read(
                email=email,
                franchise_slug=alert["franchise_slug"],
                generated_at=alert["generated_at"],
                db_path=db_path,
            )

    return {
        "email": email,
        "sent": True,
        "unread_count": payload.unread_count,
        "outbox_path": outbox_path,
        "marked_read": marked_read,
        "run_id": run_id,
    }


def run_digest_for_all_emails(
    max_alerts: int = 25,
    mark_read: bool = False,
    db_path: str | None = None,
    outbox_path: str | None = None,
    run_id: str | None = None,
) -> dict:
    run_id = run_id or f"digest-run-{int(datetime.now(timezone.utc).timestamp())}"
    emails = get_watchlist_emails(db_path=db_path)
    results = [
        run_digest_for_email(
            email,
            max_alerts=max_alerts,
            mark_read=mark_read,
            db_path=db_path,
            outbox_path=outbox_path,
            run_id=run_id,
        )
        for email in emails
    ]
    sent_count = sum(1 for item in results if item["sent"])
    return {"run_id": run_id, "emails_scanned": len(emails), "digests_sent": sent_count, "results": results}



def retry_failed_outbox(limit: int = 100, failed_path: str | None = None, outbox_path: str | None = None) -> dict:
    failed = Path(failed_path) if failed_path else _default_data_path("alert_outbox_failed.jsonl")
    outbox = Path(outbox_path) if outbox_path else _default_data_path("alert_outbox.jsonl")

    if not failed.exists():
        return {"retried": 0, "remaining_failed": 0, "failed_path": str(failed), "outbox_path": str(outbox)}

    with failed.open("r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]

    to_retry = lines[:limit]
    remaining = lines[limit:]

    cleaned = []
    for line in to_retry:
        row = json.loads(line)
        row.pop("force_fail", None)
        row.pop("failure_reason", None)
        row.pop("failed_at", None)
        row["retry_count"] = int(row.get("retry_count", 0)) + 1
        row["retried_at"] = _now_iso()
        cleaned.append(json.dumps(row) + "\n")

    if cleaned:
        outbox.parent.mkdir(parents=True, exist_ok=True)
        with outbox.open("a", encoding="utf-8") as of:
            of.writelines(cleaned)

    with failed.open("w", encoding="utf-8") as ff:
        ff.writelines(remaining)

    return {"retried": len(cleaned), "remaining_failed": len(remaining), "failed_path": str(failed), "outbox_path": str(outbox)}



def _read_lock_row(lock_path: Path) -> dict | None:
    if not lock_path.exists():
        return None
    try:
        return json.loads(lock_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _lock_is_stale(lock_row: dict | None, stale_after_seconds: int, now: datetime) -> bool:
    if lock_row is None:
        return True
    acquired_at = lock_row.get("acquired_at")
    if not acquired_at:
        return True
    try:
        acquired_dt = datetime.fromisoformat(acquired_at)
    except ValueError:
        return True
    return acquired_dt <= now - timedelta(seconds=max(1, stale_after_seconds))


def acquire_cron_lock(run_id: str, stale_after_seconds: int = 900, lock_path: str | None = None) -> dict:
    lock_file = Path(lock_path) if lock_path else _lock_path()
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    payload = {"run_id": run_id, "acquired_at": now.isoformat(), "pid": os.getpid()}
    serialized = json.dumps(payload)

    def _create_lock() -> bool:
        try:
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(serialized)
            return True
        except OSError:
            return False

    if _create_lock():
        return {"acquired": True, "lock_path": str(lock_file), "lock": payload}

    existing = _read_lock_row(lock_file)
    if _lock_is_stale(existing, stale_after_seconds=stale_after_seconds, now=now):
        try:
            lock_file.unlink(missing_ok=True)
        except OSError:
            pass
        if _create_lock():
            return {
                "acquired": True,
                "lock_path": str(lock_file),
                "lock": payload,
                "stale_replaced": existing,
            }

    return {
        "acquired": False,
        "lock_path": str(lock_file),
        "lock": existing,
        "stale_after_seconds": max(1, stale_after_seconds),
    }


def release_cron_lock(run_id: str, lock_path: str | None = None) -> dict:
    lock_file = Path(lock_path) if lock_path else _lock_path()
    current = _read_lock_row(lock_file)
    if not lock_file.exists():
        return {"released": False, "reason": "missing", "lock_path": str(lock_file)}

    if current and current.get("run_id") != run_id:
        return {"released": False, "reason": "owner-mismatch", "lock_path": str(lock_file), "lock": current}

    try:
        lock_file.unlink(missing_ok=True)
    except OSError:
        return {"released": False, "reason": "io-error", "lock_path": str(lock_file), "lock": current}
    return {"released": True, "lock_path": str(lock_file), "lock": current}








def resolve_dispatch_plan(dispatch_provider: str = "noop", dispatch_dry_run: bool = True) -> dict:
    provider_name = (dispatch_provider or "noop").strip().lower() or "noop"
    provider_health = get_provider_health(provider_name)
    validation = validate_dispatch_provider(provider=provider_name, dry_run=dispatch_dry_run)

    plan = {
        "requested_provider": provider_name,
        "requested_dry_run": dispatch_dry_run,
        "effective_provider": provider_name,
        "effective_dry_run": dispatch_dry_run,
        "fallback_applied": False,
        "fallback_reason": None,
        "provider_health": provider_health,
        "validation": validation,
    }

    if validation.get("ok", False):
        return plan

    if not dispatch_dry_run:
        plan["effective_provider"] = "noop"
        plan["effective_dry_run"] = True
        plan["fallback_applied"] = True
        plan["fallback_reason"] = validation.get("reason", "invalid-live-provider")
        plan["validation"] = validate_dispatch_provider(provider="noop", dry_run=True)
        plan["provider_health"] = get_provider_health("noop")

    return plan

def get_alerts_cron_preflight(
    dispatch_provider: str = "noop",
    dispatch_dry_run: bool = True,
    lock_stale_after_seconds: int = 900,
    lock_path: str | None = None,
) -> dict:
    dispatch_plan = resolve_dispatch_plan(dispatch_provider=dispatch_provider, dispatch_dry_run=dispatch_dry_run)
    lock_file = Path(lock_path) if lock_path else _lock_path()
    now = datetime.now(timezone.utc)
    lock_row = _read_lock_row(lock_file)
    lock_present = lock_file.exists()
    lock_stale = _lock_is_stale(lock_row, stale_after_seconds=max(1, lock_stale_after_seconds), now=now) if lock_present else False

    return {
        "checked_at": _now_iso(),
        "dispatch": dispatch_plan,
        "lock": {
            "path": str(lock_file),
            "present": lock_present,
            "stale": lock_stale,
            "stale_after_seconds": max(1, lock_stale_after_seconds),
            "metadata": lock_row,
        },
        "ready_to_run": bool(dispatch_plan.get("validation", {}).get("ok", False)) and (not lock_present or lock_stale),
    }


def get_alerts_cron_status(
    outbox_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    history_path: str | None = None,
    lock_path: str | None = None,
    lock_stale_after_seconds: int = 900,
) -> dict:
    outbox = Path(outbox_path) if outbox_path else _default_data_path("alert_outbox.jsonl")
    sent = Path(sent_path) if sent_path else _default_data_path("alert_outbox_sent.jsonl")
    failed = Path(failed_path) if failed_path else _default_data_path("alert_outbox_failed.jsonl")
    history = Path(history_path) if history_path else _history_path()
    lock_file = Path(lock_path) if lock_path else _lock_path()

    def _count_rows(path: Path) -> int:
        if not path.exists():
            return 0
        with path.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    now = datetime.now(timezone.utc)
    lock_row = _read_lock_row(lock_file)
    lock_present = lock_file.exists()
    lock_stale = _lock_is_stale(lock_row, stale_after_seconds=max(1, lock_stale_after_seconds), now=now) if lock_present else False

    return {
        "checked_at": _now_iso(),
        "paths": {
            "outbox": str(outbox),
            "sent": str(sent),
            "failed": str(failed),
            "history": str(history),
            "lock": str(lock_file),
        },
        "counts": {
            "outbox": _count_rows(outbox),
            "sent": _count_rows(sent),
            "failed": _count_rows(failed),
            "history": _count_rows(history),
        },
        "lock": {
            "present": lock_present,
            "stale": lock_stale,
            "stale_after_seconds": max(1, lock_stale_after_seconds),
            "metadata": lock_row,
        },
    }



def recover_alerts_cron_lock(
    lock_path: str | None = None,
    lock_stale_after_seconds: int = 900,
    force: bool = False,
) -> dict:
    lock_file = Path(lock_path) if lock_path else _lock_path()
    now = datetime.now(timezone.utc)

    if not lock_file.exists():
        return {
            "recovered": False,
            "reason": "missing",
            "lock_path": str(lock_file),
            "checked_at": _now_iso(),
        }

    lock_row = _read_lock_row(lock_file)
    stale = _lock_is_stale(lock_row, stale_after_seconds=max(1, lock_stale_after_seconds), now=now)
    if not stale and not force:
        return {
            "recovered": False,
            "reason": "active-lock",
            "lock_path": str(lock_file),
            "checked_at": _now_iso(),
            "lock": lock_row,
            "stale": False,
            "force": False,
        }

    try:
        lock_file.unlink(missing_ok=True)
    except OSError:
        return {
            "recovered": False,
            "reason": "io-error",
            "lock_path": str(lock_file),
            "checked_at": _now_iso(),
            "lock": lock_row,
            "stale": stale,
            "force": force,
        }

    return {
        "recovered": True,
        "reason": "forced" if force and not stale else "stale-lock",
        "lock_path": str(lock_file),
        "checked_at": _now_iso(),
        "lock": lock_row,
        "stale": stale,
        "force": force,
    }


def run_alerts_cron_tick(
    max_alerts: int = 25,
    generate_mark_read: bool = False,
    dispatch_limit: int = 100,
    retry_limit: int = 100,
    dispatch_dry_run: bool = True,
    dispatch_provider: str = "noop",
    db_path: str | None = None,
    run_id: str | None = None,
    history_path: str | None = None,
    lock_path: str | None = None,
    lock_stale_after_seconds: int = 900,
) -> dict:
    run_id = run_id or f"cron-{int(datetime.now(timezone.utc).timestamp())}"

    lock_result = acquire_cron_lock(
        run_id=run_id,
        stale_after_seconds=max(1, lock_stale_after_seconds),
        lock_path=lock_path,
    )
    if not lock_result["acquired"]:
        result = {
            "status": "skipped_locked",
            "run_id": run_id,
            "ran_at": _now_iso(),
            "lock": lock_result,
        }
        result["history_path"] = append_cron_history(result, history_path=history_path)
        return result

    try:
        generation = run_digest_for_all_emails(
            max_alerts=max_alerts,
            mark_read=generate_mark_read,
            db_path=db_path,
            run_id=run_id,
        )
        dispatch_plan = resolve_dispatch_plan(dispatch_provider=dispatch_provider, dispatch_dry_run=dispatch_dry_run)
        dispatch = dispatch_outbox(
            limit=dispatch_limit,
            dry_run=dispatch_plan["effective_dry_run"],
            provider=dispatch_plan["effective_provider"],
        )
        retry = retry_failed_outbox(limit=retry_limit)

        fallback_events = []
        degraded = False
        if dispatch_plan.get("fallback_applied"):
            degraded = True
            fallback_events.append({
                "kind": "dispatch-fallback",
                "requested_provider": dispatch_plan.get("requested_provider"),
                "effective_provider": dispatch_plan.get("effective_provider"),
                "requested_dry_run": dispatch_plan.get("requested_dry_run"),
                "effective_dry_run": dispatch_plan.get("effective_dry_run"),
                "reason": dispatch_plan.get("fallback_reason"),
            })

        result = {
            "status": "executed",
            "run_id": run_id,
            "ran_at": _now_iso(),
            "degraded": degraded,
            "events": fallback_events,
            "generated": generation,
            "dispatch_plan": dispatch_plan,
            "dispatched": dispatch,
            "retried": retry,
            "lock": lock_result,
        }
        history_file = append_cron_history(result, history_path=history_path)
        result["history_path"] = history_file
        return result
    finally:
        release_result = release_cron_lock(run_id=run_id, lock_path=lock_path)
        lock_result["release"] = release_result



def append_cron_history(row: dict, history_path: str | None = None) -> str:
    path = Path(history_path) if history_path else _history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return str(path)






def list_run_events(
    run_id: str,
    history_path: str | None = None,
    kinds: list[str] | None = None,
    statuses: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    rows = [row for row in list_cron_history(limit=5000, history_path=history_path) if row.get("run_id") == run_id]
    events: list[dict] = []
    normalized_kinds = {k.strip().lower() for k in (kinds or []) if k and k.strip()}
    normalized_statuses = {s.strip().lower() for s in (statuses or []) if s and s.strip()}
    for row in rows:
        row_status = str(row.get("status") or "").lower()
        if normalized_statuses and row_status not in normalized_statuses:
            continue
        row_events = row.get("events") or []
        for idx, event in enumerate(row_events):
            kind = str(event.get("kind") or "").lower()
            if normalized_kinds and kind not in normalized_kinds:
                continue
            events.append(
                {
                    "run_id": run_id,
                    "ran_at": row.get("ran_at"),
                    "status": row.get("status"),
                    "degraded": bool(row.get("degraded", False)),
                    "index": idx,
                    **event,
                }
            )

    start = max(0, offset)
    if limit is None:
        return events[start:]
    return events[start : start + max(1, limit)]



def list_latest_run_events(
    history_path: str | None = None,
    kinds: list[str] | None = None,
    statuses: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    run_id = get_latest_run_id(history_path=history_path)
    if not run_id:
        return {"exists": False, "run_id": None, "events": []}
    events = list_run_events(
        run_id=run_id,
        history_path=history_path,
        kinds=kinds,
        statuses=statuses,
        limit=limit,
        offset=offset,
    )
    return {"exists": True, "run_id": run_id, "events": events}


def render_run_events_csv(
    run_id: str,
    history_path: str | None = None,
    kinds: list[str] | None = None,
    statuses: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> str:
    events = list_run_events(
        run_id=run_id,
        history_path=history_path,
        kinds=kinds,
        statuses=statuses,
        limit=limit,
        offset=offset,
    )
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["run_id", "ran_at", "status", "degraded", "index", "kind", "reason", "requested_provider", "effective_provider", "requested_dry_run", "effective_dry_run"],
    )
    writer.writeheader()
    for event in events:
        writer.writerow(
            {
                "run_id": event.get("run_id"),
                "ran_at": event.get("ran_at"),
                "status": event.get("status"),
                "degraded": event.get("degraded"),
                "index": event.get("index"),
                "kind": event.get("kind"),
                "reason": event.get("reason"),
                "requested_provider": event.get("requested_provider"),
                "effective_provider": event.get("effective_provider"),
                "requested_dry_run": event.get("requested_dry_run"),
                "effective_dry_run": event.get("effective_dry_run"),
            }
        )
    return output.getvalue()


def render_latest_run_events_csv(
    history_path: str | None = None,
    kinds: list[str] | None = None,
    statuses: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    run_id = get_latest_run_id(history_path=history_path)
    if not run_id:
        return {"exists": False, "run_id": None, "csv": ""}
    return {
        "exists": True,
        "run_id": run_id,
        "csv": render_run_events_csv(
            run_id=run_id,
            history_path=history_path,
            kinds=kinds,
            statuses=statuses,
            limit=limit,
            offset=offset,
        ),
    }


def get_latest_run_id(history_path: str | None = None) -> str | None:
    latest = get_latest_cron_history_entry(history_path=history_path)
    if not latest.get("exists"):
        return None
    return (latest.get("item") or {}).get("run_id")

def get_latest_cron_history_entry(history_path: str | None = None) -> dict:
    items = list_cron_history(limit=1, history_path=history_path)
    if not items:
        return {"exists": False, "item": None}
    return {"exists": True, "item": items[-1]}


def list_cron_history(limit: int = 50, history_path: str | None = None) -> list[dict]:
    path = Path(history_path) if history_path else _history_path()
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return rows[-limit:]





def get_run_artifact_summary(
    run_id: str,
    outbox_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    history_path: str | None = None,
) -> dict:
    outbox = list_outbox(limit=5000, outbox_path=outbox_path)
    sent = list_sent_outbox(limit=5000, sent_path=sent_path)
    failed = list_failed_outbox(limit=5000, failed_path=failed_path)
    history = list_cron_history(limit=5000, history_path=history_path)

    outbox_rows = [row for row in outbox if row.get("run_id") == run_id]
    sent_rows = [row for row in sent if row.get("run_id") == run_id]
    failed_rows = [row for row in failed if row.get("run_id") == run_id]
    history_rows = [row for row in history if row.get("run_id") == run_id]

    latest_history = max(
        history_rows,
        key=lambda row: row.get("ran_at") or "",
        default=None,
    )

    latest = {
        "queued_at": max((row.get("queued_at") for row in outbox_rows if row.get("queued_at")), default=None),
        "dispatched_at": max((row.get("dispatched_at") for row in sent_rows if row.get("dispatched_at")), default=None),
        "failed_at": max((row.get("failed_at") for row in failed_rows if row.get("failed_at")), default=None),
        "cron_ran_at": max((row.get("ran_at") for row in history_rows if row.get("ran_at")), default=None),
    }

    dispatch = (latest_history or {}).get("dispatched") or {}
    dispatch_plan = (latest_history or {}).get("dispatch_plan") or {}
    operational = {
        "status": (latest_history or {}).get("status"),
        "degraded": bool((latest_history or {}).get("degraded", False)),
        "fallback_applied": bool(dispatch_plan.get("fallback_applied", False)),
        "fallback_reason": dispatch_plan.get("fallback_reason"),
        "effective_provider": dispatch_plan.get("effective_provider"),
        "effective_dry_run": dispatch_plan.get("effective_dry_run"),
        "requested_provider": dispatch_plan.get("requested_provider"),
        "requested_dry_run": dispatch_plan.get("requested_dry_run"),
        "dispatch_validation_ok": bool((dispatch.get("validation") or {}).get("ok", False)) if dispatch else None,
        "dispatch_validation_reason": (dispatch.get("validation") or {}).get("reason") if dispatch else None,
    }

    outbox_path_resolved = str(Path(outbox_path) if outbox_path else _default_data_path("alert_outbox.jsonl"))
    sent_path_resolved = str(Path(sent_path) if sent_path else _default_data_path("alert_outbox_sent.jsonl"))
    failed_path_resolved = str(Path(failed_path) if failed_path else _default_data_path("alert_outbox_failed.jsonl"))
    history_path_resolved = str(Path(history_path) if history_path else _history_path())

    return {
        "run_id": run_id,
        "counts": {
            "queued": len(outbox_rows),
            "sent": len(sent_rows),
            "failed": len(failed_rows),
            "history": len(history_rows),
        },
        "latest": latest,
        "paths": {
            "outbox": outbox_path_resolved,
            "sent": sent_path_resolved,
            "failed": failed_path_resolved,
            "history": history_path_resolved,
        },
        "operational": operational,
        "exists": any([outbox_rows, sent_rows, failed_rows, history_rows]),
    }


def get_run_integrity_report(
    run_id: str,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
) -> dict:
    summary = get_run_artifact_summary(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
    )
    events = list_run_events(run_id=run_id, history_path=history_path)
    sent_rows = list_sent_outbox(limit=5000, run_id=run_id, sent_path=sent_path)
    failed_rows = list_failed_outbox(limit=5000, run_id=run_id, failed_path=failed_path)

    counts = summary.get("counts", {})
    queued = int(counts.get("queued", 0))
    sent = int(counts.get("sent", 0))
    failed = int(counts.get("failed", 0))
    history_count = int(counts.get("history", 0))

    fallback_events = [event for event in events if str(event.get("kind", "")).lower() == "dispatch-fallback"]
    degraded = bool((summary.get("operational") or {}).get("degraded", False))

    issues: list[str] = []
    if not summary.get("exists", False):
        issues.append("run-not-found")
    if history_count == 0:
        issues.append("missing-history")
    if queued == 0 and (sent > 0 or failed > 0):
        issues.append("delivery-without-queued")
    if sent + failed > queued and queued > 0:
        issues.append("delivery-count-exceeds-queued")
    if degraded and not fallback_events:
        issues.append("degraded-without-fallback-event")
    if any(not row.get("delivery_status") or not row.get("dispatched_at") for row in sent_rows):
        issues.append("sent-missing-delivery-metadata")
    if any(not row.get("failure_reason") or not row.get("failed_at") for row in failed_rows):
        issues.append("failed-missing-failure-metadata")

    return {
        "run_id": run_id,
        "ok": len(issues) == 0,
        "issues": issues,
        "checks": {
            "exists": bool(summary.get("exists", False)),
            "history_present": history_count > 0,
            "delivery_leq_queued": (sent + failed) <= queued if queued > 0 else (sent + failed) == 0,
            "degraded_has_fallback_event": (not degraded) or bool(fallback_events),
            "sent_rows_have_delivery_metadata": all(
                row.get("delivery_status") and row.get("dispatched_at") for row in sent_rows
            ),
            "failed_rows_have_failure_metadata": all(
                row.get("failure_reason") and row.get("failed_at") for row in failed_rows
            ),
        },
        "summary": summary,
    }


def get_latest_run_integrity_report(
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
) -> dict:
    run_id = get_latest_run_id(history_path=history_path)
    if not run_id:
        return {"exists": False, "run_id": None, "report": None}
    return {
        "exists": True,
        "run_id": run_id,
        "report": get_run_integrity_report(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
        ),
    }


def get_run_integrity_issue_details(
    run_id: str,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
) -> dict:
    report = get_run_integrity_report(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
    )

    summary = report.get("summary", {})
    counts = summary.get("counts", {})
    checks = report.get("checks", {})
    issue_rows: list[dict] = []

    action_map = {
        "run-not-found": "Verify run_id source and ensure cron history artifact retention has not pruned this run.",
        "missing-history": "Confirm cron tick writes history rows and verify alerts_cron_history.jsonl is writable.",
        "delivery-without-queued": "Inspect outbox retention/rotation and run_id propagation to ensure queue rows are preserved.",
        "delivery-count-exceeds-queued": "Validate dispatch/retry idempotency and ensure queue accounting uses one row per send attempt.",
        "degraded-without-fallback-event": "Ensure degraded dispatch paths always append dispatch-fallback event entries.",
        "sent-missing-delivery-metadata": "Backfill sent rows with delivery_status and dispatched_at, then audit dispatch write path.",
        "failed-missing-failure-metadata": "Backfill failed rows with failure_reason and failed_at, then audit failure write path.",
    }

    evidence = {
        "queued": int(counts.get("queued", 0)),
        "sent": int(counts.get("sent", 0)),
        "failed": int(counts.get("failed", 0)),
        "history": int(counts.get("history", 0)),
        "checks": checks,
    }

    for issue in report.get("issues", []):
        issue_rows.append(
            {
                "issue": issue,
                "severity": "high" if issue in {"run-not-found", "missing-history", "delivery-count-exceeds-queued"} else "medium",
                "recommended_action": action_map.get(issue, "Review run artifacts and dispatch pipeline for this issue."),
                "evidence": evidence,
            }
        )

    return {
        "run_id": run_id,
        "ok": report.get("ok", False),
        "issue_count": len(issue_rows),
        "issues": issue_rows,
    }


def get_latest_run_integrity_issue_details(
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
) -> dict:
    latest = get_latest_run_integrity_report(
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
    )
    if not latest.get("exists"):
        return {"exists": False, "run_id": None, "details": None}
    run_id = latest.get("run_id")
    return {
        "exists": True,
        "run_id": run_id,
        "details": get_run_integrity_issue_details(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
        ),
    }


def render_run_integrity_issues_markdown(
    run_id: str,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
) -> str:
    details = get_run_integrity_issue_details(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
    )
    if details.get("ok"):
        return "\n".join(
            [
                f"# Run Integrity Issues — {run_id}",
                "",
                "- Status: OK",
                "- Issue count: 0",
            ]
        )

    lines = [
        f"# Run Integrity Issues — {run_id}",
        "",
        "- Status: FAILING",
        f"- Issue count: {details.get('issue_count', 0)}",
        "",
        "## Issues",
    ]
    for idx, issue in enumerate(details.get("issues", []), start=1):
        lines.extend(
            [
                f"{idx}. {issue.get('issue')} (severity={issue.get('severity')})",
                f"   action: {issue.get('recommended_action')}",
            ]
        )
    return "\n".join(lines)


def render_run_integrity_issues_telegram_chunks(
    run_id: str,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    max_chars: int = 3500,
) -> dict:
    max_chars = max(100, min(max_chars, 4096))
    markdown = render_run_integrity_issues_markdown(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
    )
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in markdown.split("\n"):
        if len(line) > max_chars:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for i in range(0, len(line), max_chars):
                chunks.append(line[i : i + max_chars])
            continue
        line_len = len(line) + (1 if current else 0)
        if current and (current_len + line_len) > max_chars:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    indexed_chunks = [f"[{idx}/{len(chunks)}]\n{chunk}" for idx, chunk in enumerate(chunks, start=1)]

    return {
        "run_id": run_id,
        "total_chars": len(markdown),
        "max_chars": max_chars,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "chunks_with_index": indexed_chunks,
    }


def render_latest_run_integrity_issues_markdown(
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
) -> dict:
    run_id = get_latest_run_id(history_path=history_path)
    if not run_id:
        return {"exists": False, "run_id": None, "markdown": ""}
    return {
        "exists": True,
        "run_id": run_id,
        "markdown": render_run_integrity_issues_markdown(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
        ),
    }


def render_latest_run_integrity_issues_telegram_chunks(
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    max_chars: int = 3500,
) -> dict:
    run_id = get_latest_run_id(history_path=history_path)
    if not run_id:
        return {
            "exists": False,
            "run_id": None,
            "total_chars": 0,
            "max_chars": max(100, min(max_chars, 4096)),
            "chunk_count": 0,
            "chunks": [],
            "chunks_with_index": [],
        }

    payload = render_run_integrity_issues_telegram_chunks(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
        max_chars=max_chars,
    )
    payload["exists"] = True
    return payload


def render_run_integrity_issues_csv(
    run_id: str,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
) -> str:
    details = get_run_integrity_issue_details(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
    )
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["run_id", "ok", "issue_count", "issue", "severity", "recommended_action", "evidence"],
    )
    writer.writeheader()
    issues = details.get("issues") or []
    if not issues:
        writer.writerow(
            {
                "run_id": run_id,
                "ok": True,
                "issue_count": 0,
                "issue": "",
                "severity": "",
                "recommended_action": "",
                "evidence": "",
            }
        )
        return output.getvalue()

    for issue in issues:
        writer.writerow(
            {
                "run_id": run_id,
                "ok": False,
                "issue_count": details.get("issue_count", len(issues)),
                "issue": issue.get("issue"),
                "severity": issue.get("severity"),
                "recommended_action": issue.get("recommended_action"),
                "evidence": json.dumps(issue.get("evidence") or {}, ensure_ascii=False),
            }
        )
    return output.getvalue()


def render_latest_run_integrity_issues_csv(
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
) -> dict:
    run_id = get_latest_run_id(history_path=history_path)
    if not run_id:
        return {"exists": False, "run_id": None, "csv": ""}
    return {
        "exists": True,
        "run_id": run_id,
        "csv": render_run_integrity_issues_csv(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
        ),
    }


def build_run_incident_payload(
    run_id: str,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    event_kinds: list[str] | None = None,
    event_statuses: list[str] | None = None,
    event_limit: int | None = None,
    event_offset: int = 0,
) -> dict:
    return {
        "run_id": run_id,
        "summary": get_run_artifact_summary(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
        ),
        "integrity": get_run_integrity_report(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
        ),
        "issues": get_run_integrity_issue_details(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
        ),
        "events": list_run_events(
            run_id=run_id,
            history_path=history_path,
            kinds=event_kinds,
            statuses=event_statuses,
            limit=event_limit,
            offset=event_offset,
        ),
    }


def build_latest_run_incident_payload(
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    event_kinds: list[str] | None = None,
    event_statuses: list[str] | None = None,
    event_limit: int | None = None,
    event_offset: int = 0,
) -> dict:
    run_id = get_latest_run_id(history_path=history_path)
    if not run_id:
        return {"exists": False, "run_id": None, "incident": None}
    return {
        "exists": True,
        "run_id": run_id,
        "incident": build_run_incident_payload(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
            event_kinds=event_kinds,
            event_statuses=event_statuses,
            event_limit=event_limit,
            event_offset=event_offset,
        ),
    }


def render_run_incident_markdown(
    run_id: str,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    event_kinds: list[str] | None = None,
    event_statuses: list[str] | None = None,
    event_limit: int | None = None,
    event_offset: int = 0,
) -> str:
    payload = build_run_incident_payload(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
        event_kinds=event_kinds,
        event_statuses=event_statuses,
        event_limit=event_limit,
        event_offset=event_offset,
    )
    summary = payload.get("summary") or {}
    integrity = payload.get("integrity") or {}
    issues = (payload.get("issues") or {}).get("issues") or []
    events = payload.get("events") or []

    lines = [
        f"# Run Incident — {run_id}",
        "",
        "## Summary",
        f"- Exists: {summary.get('exists')}",
        f"- Queued: {(summary.get('counts') or {}).get('queued', 0)}",
        f"- Sent: {(summary.get('counts') or {}).get('sent', 0)}",
        f"- Failed: {(summary.get('counts') or {}).get('failed', 0)}",
        f"- Status: {(summary.get('operational') or {}).get('status')}",
        f"- Degraded: {(summary.get('operational') or {}).get('degraded')}",
        "",
        "## Integrity",
        f"- OK: {integrity.get('ok')}",
        f"- Issue count: {len(issues)}",
        "",
        "## Issues",
    ]

    if issues:
        for idx, issue in enumerate(issues, start=1):
            lines.append(f"{idx}. {issue.get('issue')} (severity={issue.get('severity')})")
            lines.append(f"   action: {issue.get('recommended_action')}")
    else:
        lines.append("- none")

    lines.extend(["", "## Events"])
    if events:
        for idx, event in enumerate(events, start=1):
            lines.append(
                f"{idx}. {event.get('kind')} | status={event.get('status')} | degraded={event.get('degraded')} | ran_at={event.get('ran_at')}"
            )
    else:
        lines.append("- none")

    return "\n".join(lines)


def render_latest_run_incident_markdown(
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    event_kinds: list[str] | None = None,
    event_statuses: list[str] | None = None,
    event_limit: int | None = None,
    event_offset: int = 0,
) -> dict:
    run_id = get_latest_run_id(history_path=history_path)
    if not run_id:
        return {"exists": False, "run_id": None, "markdown": ""}
    return {
        "exists": True,
        "run_id": run_id,
        "markdown": render_run_incident_markdown(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
            event_kinds=event_kinds,
            event_statuses=event_statuses,
            event_limit=event_limit,
            event_offset=event_offset,
        ),
    }


def render_run_incident_telegram_chunks(
    run_id: str,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    event_kinds: list[str] | None = None,
    event_statuses: list[str] | None = None,
    event_limit: int | None = None,
    event_offset: int = 0,
    max_chars: int = 3500,
) -> dict:
    max_chars = max(100, min(max_chars, 4096))
    markdown = render_run_incident_markdown(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
        event_kinds=event_kinds,
        event_statuses=event_statuses,
        event_limit=event_limit,
        event_offset=event_offset,
    )

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in markdown.split("\n"):
        if len(line) > max_chars:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for i in range(0, len(line), max_chars):
                chunks.append(line[i : i + max_chars])
            continue

        line_len = len(line) + (1 if current else 0)
        if current and (current_len + line_len) > max_chars:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue

        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    indexed_chunks = [f"[{idx}/{len(chunks)}]\n{chunk}" for idx, chunk in enumerate(chunks, start=1)]
    return {
        "run_id": run_id,
        "total_chars": len(markdown),
        "max_chars": max_chars,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "chunks_with_index": indexed_chunks,
    }


def render_latest_run_incident_telegram_chunks(
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    event_kinds: list[str] | None = None,
    event_statuses: list[str] | None = None,
    event_limit: int | None = None,
    event_offset: int = 0,
    max_chars: int = 3500,
) -> dict:
    run_id = get_latest_run_id(history_path=history_path)
    if not run_id:
        return {"exists": False, "run_id": None, "chunk_count": 0, "chunks": [], "chunks_with_index": []}

    payload = render_run_incident_telegram_chunks(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
        event_kinds=event_kinds,
        event_statuses=event_statuses,
        event_limit=event_limit,
        event_offset=event_offset,
        max_chars=max_chars,
    )
    payload["exists"] = True
    return payload


def render_run_incident_csv(
    run_id: str,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    event_kinds: list[str] | None = None,
    event_statuses: list[str] | None = None,
    event_limit: int | None = None,
    event_offset: int = 0,
) -> str:
    payload = build_run_incident_payload(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
        event_kinds=event_kinds,
        event_statuses=event_statuses,
        event_limit=event_limit,
        event_offset=event_offset,
    )
    summary = payload.get("summary") or {}
    counts = summary.get("counts") or {}
    operational = summary.get("operational") or {}
    integrity = payload.get("integrity") or {}
    issues = (payload.get("issues") or {}).get("issues") or []
    events = payload.get("events") or []

    output = StringIO()
    fieldnames = [
        "run_id",
        "summary_exists",
        "queued",
        "sent",
        "failed",
        "status",
        "degraded",
        "integrity_ok",
        "integrity_issue_count",
        "issue",
        "issue_severity",
        "issue_recommended_action",
        "event_kind",
        "event_status",
        "event_degraded",
        "event_ran_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    if not issues and not events:
        writer.writerow(
            {
                "run_id": run_id,
                "summary_exists": summary.get("exists"),
                "queued": counts.get("queued", 0),
                "sent": counts.get("sent", 0),
                "failed": counts.get("failed", 0),
                "status": operational.get("status"),
                "degraded": operational.get("degraded"),
                "integrity_ok": integrity.get("ok"),
                "integrity_issue_count": len(issues),
            }
        )
        return output.getvalue()

    issue_rows = issues or [None]
    event_rows = events or [None]
    for issue in issue_rows:
        for event in event_rows:
            writer.writerow(
                {
                    "run_id": run_id,
                    "summary_exists": summary.get("exists"),
                    "queued": counts.get("queued", 0),
                    "sent": counts.get("sent", 0),
                    "failed": counts.get("failed", 0),
                    "status": operational.get("status"),
                    "degraded": operational.get("degraded"),
                    "integrity_ok": integrity.get("ok"),
                    "integrity_issue_count": len(issues),
                    "issue": (issue or {}).get("issue") if issue else None,
                    "issue_severity": (issue or {}).get("severity") if issue else None,
                    "issue_recommended_action": (issue or {}).get("recommended_action") if issue else None,
                    "event_kind": (event or {}).get("kind") if event else None,
                    "event_status": (event or {}).get("status") if event else None,
                    "event_degraded": (event or {}).get("degraded") if event else None,
                    "event_ran_at": (event or {}).get("ran_at") if event else None,
                }
            )
    return output.getvalue()


def render_latest_run_incident_csv(
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    event_kinds: list[str] | None = None,
    event_statuses: list[str] | None = None,
    event_limit: int | None = None,
    event_offset: int = 0,
) -> dict:
    run_id = get_latest_run_id(history_path=history_path)
    if not run_id:
        return {"exists": False, "run_id": None, "csv": ""}

    return {
        "exists": True,
        "run_id": run_id,
        "csv": render_run_incident_csv(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
            event_kinds=event_kinds,
            event_statuses=event_statuses,
            event_limit=event_limit,
            event_offset=event_offset,
        ),
    }


def build_run_incident_export_packet(
    run_id: str,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    event_kinds: list[str] | None = None,
    event_statuses: list[str] | None = None,
    event_limit: int | None = None,
    event_offset: int = 0,
    max_chars: int = 3500,
) -> dict:
    return {
        "run_id": run_id,
        "incident": build_run_incident_payload(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
            event_kinds=event_kinds,
            event_statuses=event_statuses,
            event_limit=event_limit,
            event_offset=event_offset,
        ),
        "markdown": render_run_incident_markdown(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
            event_kinds=event_kinds,
            event_statuses=event_statuses,
            event_limit=event_limit,
            event_offset=event_offset,
        ),
        "csv": render_run_incident_csv(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
            event_kinds=event_kinds,
            event_statuses=event_statuses,
            event_limit=event_limit,
            event_offset=event_offset,
        ),
        "telegram": render_run_incident_telegram_chunks(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
            event_kinds=event_kinds,
            event_statuses=event_statuses,
            event_limit=event_limit,
            event_offset=event_offset,
            max_chars=max_chars,
        ),
    }


def build_latest_run_incident_export_packet(
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    event_kinds: list[str] | None = None,
    event_statuses: list[str] | None = None,
    event_limit: int | None = None,
    event_offset: int = 0,
    max_chars: int = 3500,
) -> dict:
    run_id = get_latest_run_id(history_path=history_path)
    if not run_id:
        return {"exists": False, "run_id": None, "packet": None}
    return {
        "exists": True,
        "run_id": run_id,
        "packet": build_run_incident_export_packet(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
            event_kinds=event_kinds,
            event_statuses=event_statuses,
            event_limit=event_limit,
            event_offset=event_offset,
            max_chars=max_chars,
        ),
    }


def list_recent_run_integrity_reports(
    limit: int = 10,
    status: str | None = None,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
) -> dict:
    rows = list_cron_history(limit=max(1, min(limit * 5, 5000)), history_path=history_path)
    status_filter = (status or "").strip().lower() or None

    run_ids: list[str] = []
    seen: set[str] = set()
    for row in reversed(rows):
        run_id = row.get("run_id")
        if not run_id or run_id in seen:
            continue
        row_status = str(row.get("status") or "").lower()
        if status_filter and row_status != status_filter:
            continue
        seen.add(run_id)
        run_ids.append(run_id)
        if len(run_ids) >= max(1, limit):
            break

    reports = [
        get_run_integrity_report(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
        )
        for run_id in run_ids
    ]
    return {
        "count": len(reports),
        "status_filter": status_filter,
        "reports": reports,
    }


def summarize_recent_run_integrity(
    limit: int = 25,
    status: str | None = None,
    history_path: str | None = None,
) -> dict:
    recent = list_recent_run_integrity_reports(limit=limit, status=status, history_path=history_path)
    reports = recent.get("reports", [])

    issue_counts: dict[str, int] = {}
    ok_count = 0
    degraded_count = 0
    for report in reports:
        if report.get("ok"):
            ok_count += 1
        operational = ((report.get("summary") or {}).get("operational") or {})
        if operational.get("degraded"):
            degraded_count += 1
        for issue in report.get("issues", []):
            issue_counts[issue] = issue_counts.get(issue, 0) + 1

    total = len(reports)
    failing = total - ok_count
    failing_rate = (failing / total) if total else 0.0
    degraded_rate = (degraded_count / total) if total else 0.0
    top_issues = [
        {"issue": issue, "count": count}
        for issue, count in sorted(issue_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    issue_total = int(sum(issue_counts.values()))

    return {
        "count": total,
        "status_filter": recent.get("status_filter"),
        "ok_count": ok_count,
        "failing_count": failing,
        "failing_rate": round(failing_rate, 4),
        "degraded_count": degraded_count,
        "degraded_rate": round(degraded_rate, 4),
        "issue_total": issue_total,
        "issue_counts": issue_counts,
        "top_issues": top_issues,
    }


def list_failing_run_integrity_reports(
    limit: int = 25,
    status: str | None = None,
    history_path: str | None = None,
) -> dict:
    recent = list_recent_run_integrity_reports(limit=limit, status=status, history_path=history_path)
    failing = [report for report in recent.get("reports", []) if not report.get("ok", False)]
    return {
        "count": len(failing),
        "status_filter": recent.get("status_filter"),
        "reports": failing,
    }


def get_integrity_dashboard_snapshot(limit: int = 25, status: str | None = None, history_path: str | None = None) -> dict:
    summary = summarize_recent_run_integrity(limit=limit, status=status, history_path=history_path)
    failures = list_failing_run_integrity_reports(limit=limit, status=status, history_path=history_path)
    latest = get_latest_run_integrity_report(history_path=history_path)
    return {
        "summary": summary,
        "failures": failures,
        "latest": latest,
    }


def render_integrity_dashboard_markdown(limit: int = 25, status: str | None = None, history_path: str | None = None) -> str:
    snapshot = get_integrity_dashboard_snapshot(limit=limit, status=status, history_path=history_path)
    summary = snapshot.get("summary", {})
    failures = snapshot.get("failures", {})
    latest = snapshot.get("latest", {})
    latest_report = latest.get("report") or {}
    latest_summary = latest_report.get("summary") or {}
    latest_operational = latest_summary.get("operational") or {}
    latest_ok = bool(latest_report.get("ok", False)) if latest.get("exists") else False
    latest_degraded = bool(latest_operational.get("degraded", False)) if latest.get("exists") else False

    lines = [
        "# Alert Integrity Dashboard",
        "",
        f"- Runs analyzed: {summary.get('count', 0)}",
        f"- Healthy runs: {summary.get('ok_count', 0)}",
        f"- Failing runs: {summary.get('failing_count', 0)} ({summary.get('failing_rate', 0)})",
        f"- Degraded runs: {summary.get('degraded_count', 0)} ({summary.get('degraded_rate', 0)})",
        f"- Total issues: {summary.get('issue_total', 0)}",
        "",
        "## Latest Run",
        f"- Run ID: {latest.get('run_id', 'n/a')}",
        f"- OK: {latest_ok}",
        f"- Degraded: {latest_degraded}",
        "",
        "## Top Issues",
    ]

    for issue in summary.get("top_issues", [])[:5]:
        lines.append(f"- {issue.get('issue')}: {issue.get('count')}")
    if not summary.get("top_issues"):
        lines.append("- none")

    lines += ["", "## Failing Reports", f"- Count: {failures.get('count', 0)}"]
    return "\n".join(lines)


def render_integrity_dashboard_telegram_chunks(
    limit: int = 25,
    status: str | None = None,
    history_path: str | None = None,
    max_chars: int = 3500,
) -> dict:
    max_chars = max(100, min(max_chars, 4096))
    markdown = render_integrity_dashboard_markdown(limit=limit, status=status, history_path=history_path)

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in markdown.split("\n"):
        if len(line) > max_chars:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for i in range(0, len(line), max_chars):
                chunks.append(line[i : i + max_chars])
            continue
        line_len = len(line) + (1 if current else 0)
        if current and (current_len + line_len) > max_chars:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    indexed_chunks = [f"[{idx}/{len(chunks)}]\n{chunk}" for idx, chunk in enumerate(chunks, start=1)]

    return {
        "total_chars": len(markdown),
        "max_chars": max_chars,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "chunks_with_index": indexed_chunks,
    }






def render_run_integrity_issues_telegram_chunks(
    run_id: str,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    max_chars: int = 3500,
) -> dict:
    max_chars = max(100, min(max_chars, 4096))
    markdown = render_run_integrity_issues_markdown(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
    )

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in markdown.split("\n"):
        if len(line) > max_chars:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for i in range(0, len(line), max_chars):
                chunks.append(line[i : i + max_chars])
            continue

        line_len = len(line) + (1 if current else 0)
        if current and (current_len + line_len) > max_chars:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue

        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    indexed_chunks = [f"[{idx}/{len(chunks)}]\n{chunk}" for idx, chunk in enumerate(chunks, start=1)]

    return {
        "run_id": run_id,
        "total_chars": len(markdown),
        "max_chars": max_chars,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "chunks_with_index": indexed_chunks,
    }


def render_latest_run_integrity_issues_telegram_chunks(
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    max_chars: int = 3500,
) -> dict:
    latest = get_latest_run_integrity_report(
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
    )
    if not latest.get("exists"):
        return {"exists": False, "run_id": None, "chunk_count": 0, "chunks": [], "chunks_with_index": []}

    run_id = str(latest.get("run_id"))
    payload = render_run_integrity_issues_telegram_chunks(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
        max_chars=max_chars,
    )
    payload["exists"] = True
    return payload

def render_run_integrity_issues_markdown(
    run_id: str,
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
) -> str:
    details = get_run_integrity_issue_details(
        run_id=run_id,
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
    )

    lines = [
        f"# Run Integrity Issues — {run_id}",
        "",
        f"- OK: {details.get('ok', False)}",
        f"- Issue count: {details.get('issue_count', 0)}",
        "",
    ]

    issues = details.get("issues") or []
    if not issues:
        lines.append("- No integrity issues detected for this run.")
        return "\n".join(lines)

    lines.append("## Issues")
    for idx, issue in enumerate(issues, start=1):
        evidence = issue.get("evidence") or {}
        lines += [
            f"{idx}. **{issue.get('issue', 'unknown')}** ({issue.get('severity', 'unknown')})",
            f"   - Recommended action: {issue.get('recommended_action', 'Review run artifacts.')}",
            (
                "   - Evidence: "
                f"queued={evidence.get('queued', 0)}, "
                f"sent={evidence.get('sent', 0)}, "
                f"failed={evidence.get('failed', 0)}, "
                f"history={evidence.get('history', 0)}"
            ),
        ]

    return "\n".join(lines)


def render_latest_run_integrity_issues_markdown(
    history_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
) -> dict:
    latest = get_latest_run_integrity_report(
        history_path=history_path,
        sent_path=sent_path,
        failed_path=failed_path,
    )
    if not latest.get("exists"):
        return {"exists": False, "run_id": None, "markdown": None}

    run_id = str(latest.get("run_id"))
    return {
        "exists": True,
        "run_id": run_id,
        "markdown": render_run_integrity_issues_markdown(
            run_id=run_id,
            history_path=history_path,
            sent_path=sent_path,
            failed_path=failed_path,
        ),
    }

def summarize_integrity_trends(
    limit: int = 200,
    status: str | None = None,
    history_path: str | None = None,
) -> dict:
    recent = list_recent_run_integrity_reports(limit=limit, status=status, history_path=history_path)
    reports = recent.get("reports", [])

    buckets: dict[str, dict[str, int]] = {}
    unknown_bucket = "unknown"
    for report in reports:
        ran_at = (((report.get("summary") or {}).get("latest") or {}).get("cron_ran_at"))
        bucket = unknown_bucket
        if ran_at:
            try:
                dt = datetime.fromisoformat(str(ran_at).replace("Z", "+00:00"))
                bucket = dt.date().isoformat()
            except ValueError:
                bucket = unknown_bucket

        entry = buckets.setdefault(bucket, {"total": 0, "ok": 0, "failing": 0, "degraded": 0})
        entry["total"] += 1
        if report.get("ok", False):
            entry["ok"] += 1
        else:
            entry["failing"] += 1
        if (((report.get("summary") or {}).get("operational") or {}).get("degraded", False)):
            entry["degraded"] += 1

    trend = [
        {
            "bucket": bucket,
            "total": counts["total"],
            "ok": counts["ok"],
            "failing": counts["failing"],
            "degraded": counts["degraded"],
        }
        for bucket, counts in sorted(buckets.items(), key=lambda item: item[0])
    ]

    return {
        "count": len(reports),
        "status_filter": recent.get("status_filter"),
        "trend": trend,
    }

def prune_jsonl_records(path: Path, keep_last: int) -> dict:
    if not path.exists():
        return {"path": str(path), "before": 0, "after": 0, "removed": 0}

    with path.open("r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]

    before = len(lines)
    keep_last = max(0, keep_last)
    kept = lines[-keep_last:] if keep_last > 0 else []

    with path.open("w", encoding="utf-8") as f:
        f.writelines(kept)

    after = len(kept)
    return {"path": str(path), "before": before, "after": after, "removed": before - after}


def prune_alert_artifacts(
    outbox_keep_last: int = 1000,
    sent_keep_last: int = 2000,
    failed_keep_last: int = 1000,
    history_keep_last: int = 2000,
    outbox_path: str | None = None,
    sent_path: str | None = None,
    failed_path: str | None = None,
    history_path: str | None = None,
) -> dict:
    outbox = Path(outbox_path) if outbox_path else _default_data_path("alert_outbox.jsonl")
    sent = Path(sent_path) if sent_path else _default_data_path("alert_outbox_sent.jsonl")
    failed = Path(failed_path) if failed_path else _default_data_path("alert_outbox_failed.jsonl")
    history = Path(history_path) if history_path else _history_path()

    outbox_result = prune_jsonl_records(outbox, outbox_keep_last)
    sent_result = prune_jsonl_records(sent, sent_keep_last)
    failed_result = prune_jsonl_records(failed, failed_keep_last)
    history_result = prune_jsonl_records(history, history_keep_last)

    return {
        "outbox": outbox_result,
        "sent": sent_result,
        "failed": failed_result,
        "history": history_result,
    }
