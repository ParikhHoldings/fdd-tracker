from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

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
