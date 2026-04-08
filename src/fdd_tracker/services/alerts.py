from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fdd_tracker.services.store import get_alert_feed, get_watchlist_emails, mark_alert_read


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

    generated_at = datetime.now(timezone.utc).isoformat()
    return DigestPayload(
        email=email,
        unread_count=len(alerts),
        subject=f"FDD Tracker: {len(alerts)} unread changes",
        body=_build_digest_body(email=email, alerts=alerts),
        generated_at=generated_at,
    )


def write_digest_outbox(payload: DigestPayload, outbox_path: str | None = None) -> str:
    path = Path(outbox_path) if outbox_path else _default_data_path("alert_outbox.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "email": payload.email,
        "unread_count": payload.unread_count,
        "subject": payload.subject,
        "body": payload.body,
        "generated_at": payload.generated_at,
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


def dispatch_outbox(limit: int = 100, outbox_path: str | None = None, sent_path: str | None = None) -> dict:
    outbox = Path(outbox_path) if outbox_path else _default_data_path("alert_outbox.jsonl")
    sent = Path(sent_path) if sent_path else _default_data_path("alert_outbox_sent.jsonl")

    if not outbox.exists():
        return {"dispatched": 0, "remaining": 0, "sent_path": str(sent), "outbox_path": str(outbox)}

    with outbox.open("r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]

    to_dispatch = lines[:limit]
    remaining = lines[limit:]

    if to_dispatch:
        sent.parent.mkdir(parents=True, exist_ok=True)
        with sent.open("a", encoding="utf-8") as sf:
            sf.writelines(to_dispatch)

    with outbox.open("w", encoding="utf-8") as of:
        of.writelines(remaining)

    return {
        "dispatched": len(to_dispatch),
        "remaining": len(remaining),
        "sent_path": str(sent),
        "outbox_path": str(outbox),
    }


def run_digest_for_email(
    email: str,
    max_alerts: int = 25,
    mark_read: bool = False,
    db_path: str | None = None,
    outbox_path: str | None = None,
) -> dict:
    unread_alerts = get_alert_feed(email=email, limit=max_alerts, unread_only=True, db_path=db_path)
    payload = build_digest_payload(email=email, max_alerts=max_alerts, db_path=db_path)
    if payload is None:
        return {"email": email, "sent": False, "unread_count": 0, "outbox_path": None, "marked_read": 0}

    outbox_path = write_digest_outbox(payload, outbox_path=outbox_path)

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
    }


def run_digest_for_all_emails(
    max_alerts: int = 25,
    mark_read: bool = False,
    db_path: str | None = None,
    outbox_path: str | None = None,
) -> dict:
    emails = get_watchlist_emails(db_path=db_path)
    results = [
        run_digest_for_email(
            email,
            max_alerts=max_alerts,
            mark_read=mark_read,
            db_path=db_path,
            outbox_path=outbox_path,
        )
        for email in emails
    ]
    sent_count = sum(1 for item in results if item["sent"])
    return {"emails_scanned": len(emails), "digests_sent": sent_count, "results": results}
