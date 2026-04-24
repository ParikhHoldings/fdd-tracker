from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from fdd_tracker.db import get_conn
from fdd_tracker.models import ChangeSummary, Filing, HealthSignal


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_franchise_slug(franchise_slug: str) -> str:
    return franchise_slug.strip().lower()


def upsert_filing(filing: Filing, db_path: str | None = None) -> int:
    normalized_slug = _normalize_franchise_slug(filing.franchise_slug)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO filings(franchise_slug, source, filed_on, document_url, document_hash)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(franchise_slug, source, document_url)
            DO UPDATE SET filed_on=excluded.filed_on, document_hash=excluded.document_hash
            """,
            (
                normalized_slug,
                filing.source,
                filing.filed_on.isoformat() if filing.filed_on else None,
                filing.document_url,
                filing.document_hash,
            ),
        )
        conn.commit()
        return cur.rowcount


def get_latest_filings(franchise_slug: str, limit: int = 2, db_path: str | None = None) -> list[dict]:
    """Get latest filings for a franchise, ordered by filed_on desc nulls last, then id desc."""
    normalized_slug = _normalize_franchise_slug(franchise_slug)
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, franchise_slug, source, filed_on, document_url, document_hash
            FROM filings
            WHERE franchise_slug = ?
            ORDER BY filed_on IS NULL, filed_on DESC, id DESC
            LIMIT ?
            """,
            (normalized_slug, limit),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "franchise_slug": row["franchise_slug"],
            "source": row["source"],
            "filed_on": row["filed_on"],
            "document_url": row["document_url"],
            "document_hash": row["document_hash"],
        }
        for row in rows
    ]


def upsert_health_signal(signal: HealthSignal, db_path: str | None = None) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO health_signals(
                franchise_slug, source, observed_at, signal_name, metric_value, sentiment, notes, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(franchise_slug, source, observed_at, signal_name)
            DO UPDATE SET
                metric_value=excluded.metric_value,
                sentiment=excluded.sentiment,
                notes=excluded.notes,
                metadata_json=excluded.metadata_json
            """,
            (
                signal.franchise_slug,
                signal.source,
                signal.observed_at.isoformat(),
                signal.signal_name,
                signal.metric_value,
                signal.sentiment,
                signal.notes,
                json.dumps(signal.metadata or {}),
            ),
        )
        conn.commit()
        return cur.rowcount


def list_health_signals(
    franchise_slug: str,
    source: str | None = None,
    limit: int = 100,
    db_path: str | None = None,
) -> list[dict]:
    query = """
        SELECT franchise_slug, source, observed_at, signal_name, metric_value, sentiment, notes, metadata_json
        FROM health_signals
        WHERE franchise_slug = ?
    """
    params: list = [franchise_slug]
    if source:
        query += " AND source = ?"
        params.append(source)
    query += " ORDER BY observed_at DESC, id DESC LIMIT ?"
    params.append(limit)

    with get_conn(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    return [
        {
            "franchise_slug": row["franchise_slug"],
            "source": row["source"],
            "observed_at": row["observed_at"],
            "signal_name": row["signal_name"],
            "metric_value": row["metric_value"],
            "sentiment": row["sentiment"],
            "notes": row["notes"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
        }
        for row in rows
    ]


def get_health_signal_summary(
    franchise_slug: str,
    source: str | None = None,
    limit: int = 200,
    db_path: str | None = None,
) -> dict:
    items = list_health_signals(franchise_slug=franchise_slug, source=source, limit=limit, db_path=db_path)

    sentiment_counts: dict[str, int] = {"positive": 0, "neutral": 0, "negative": 0, "unknown": 0}
    by_source: dict[str, int] = {}
    signal_sums: dict[str, float] = {}
    signal_counts: dict[str, int] = {}

    for item in items:
        source_name = str(item.get("source") or "unknown")
        by_source[source_name] = by_source.get(source_name, 0) + 1

        sentiment = str(item.get("sentiment") or "unknown").lower().strip()
        if sentiment not in sentiment_counts:
            sentiment = "unknown"
        sentiment_counts[sentiment] += 1

        metric_value = item.get("metric_value")
        signal_name = str(item.get("signal_name") or "unknown").strip().lower() or "unknown"
        if metric_value is not None:
            signal_sums[signal_name] = signal_sums.get(signal_name, 0.0) + float(metric_value)
            signal_counts[signal_name] = signal_counts.get(signal_name, 0) + 1

    metric_averages = {
        key: round(signal_sums[key] / signal_counts[key], 4)
        for key in sorted(signal_sums.keys())
        if signal_counts.get(key, 0) > 0
    }

    return {
        "franchise_slug": franchise_slug,
        "source_filter": source,
        "total_signals": len(items),
        "latest_observed_at": items[0]["observed_at"] if items else None,
        "first_observed_at": items[-1]["observed_at"] if items else None,
        "by_source": dict(sorted(by_source.items(), key=lambda kv: (-kv[1], kv[0]))),
        "sentiment_counts": sentiment_counts,
        "metric_averages": metric_averages,
    }


def render_health_signal_summary_markdown(payload: dict) -> str:
    sentiments = payload.get("sentiment_counts", {})
    sources = payload.get("by_source", {})
    metrics = payload.get("metric_averages", {})
    source_lines = [f"- {k}: {v}" for k, v in sources.items()] or ["- none"]
    metric_lines = [f"- {k}: {v}" for k, v in metrics.items()] or ["- none"]

    return "\n".join(
        [
            f"# Franchise Health Signals — {payload.get('franchise_slug')}",
            "",
            f"- Total signals: {payload.get('total_signals', 0)}",
            f"- Source filter: {payload.get('source_filter') or 'all'}",
            f"- Latest observed: {payload.get('latest_observed_at') or 'n/a'}",
            f"- First observed: {payload.get('first_observed_at') or 'n/a'}",
            "",
            "## Sentiment",
            f"- Positive: {sentiments.get('positive', 0)}",
            f"- Neutral: {sentiments.get('neutral', 0)}",
            f"- Negative: {sentiments.get('negative', 0)}",
            f"- Unknown: {sentiments.get('unknown', 0)}",
            "",
            "## Sources",
            *source_lines,
            "",
            "## Metric Averages",
            *metric_lines,
        ]
    )


def render_health_signal_summary_telegram_chunks(payload: dict, max_chars: int = 2500) -> list[str]:
    text = render_health_signal_summary_markdown(payload)
    lines = text.splitlines()
    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = line
        else:
            chunks.append(line[:max_chars])
            current = line[max_chars:]
    if current:
        chunks.append(current)
    return [f"[{i+1}/{len(chunks)}] {chunk}" for i, chunk in enumerate(chunks)]


def render_health_signal_summary_csv(payload: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["section", "key", "value"])
    w.writerow(["meta", "franchise_slug", payload.get("franchise_slug")])
    w.writerow(["meta", "source_filter", payload.get("source_filter") or "all"])
    w.writerow(["meta", "total_signals", payload.get("total_signals", 0)])
    w.writerow(["meta", "latest_observed_at", payload.get("latest_observed_at") or ""])
    w.writerow(["meta", "first_observed_at", payload.get("first_observed_at") or ""])
    for key, value in (payload.get("sentiment_counts") or {}).items():
        w.writerow(["sentiment", key, value])
    for key, value in (payload.get("by_source") or {}).items():
        w.writerow(["source", key, value])
    for key, value in (payload.get("metric_averages") or {}).items():
        w.writerow(["metric_average", key, value])
    return out.getvalue()


def build_health_signal_summary_packet(payload: dict, max_chars: int = 2500) -> dict:
    markdown = render_health_signal_summary_markdown(payload)
    csv_text = render_health_signal_summary_csv(payload)
    telegram_chunks = render_health_signal_summary_telegram_chunks(payload, max_chars=max_chars)
    return {
        "summary": payload,
        "markdown": markdown,
        "csv": csv_text,
        "telegram": {
            "max_chars": max_chars,
            "chunk_count": len(telegram_chunks),
            "chunks_with_index": telegram_chunks,
        },
    }


def insert_change_summary(summary: ChangeSummary, db_path: str | None = None) -> int:
    normalized_slug = _normalize_franchise_slug(summary.franchise_slug)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO change_summaries(franchise_slug, generated_at, categories, highlights, risk_level)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                normalized_slug,
                summary.generated_at.isoformat(),
                json.dumps(summary.categories),
                json.dumps(summary.highlights),
                summary.risk_level,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_recent_changes(franchise_slug: str, limit: int = 20, db_path: str | None = None) -> list[dict]:
    normalized_slug = _normalize_franchise_slug(franchise_slug)
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT franchise_slug, generated_at, categories, highlights, risk_level
            FROM change_summaries
            WHERE franchise_slug = ?
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (normalized_slug, limit),
        ).fetchall()

    out = []
    for row in rows:
        out.append(
            {
                "franchise_slug": row["franchise_slug"],
                "generated_at": row["generated_at"],
                "categories": json.loads(row["categories"]),
                "highlights": json.loads(row["highlights"]),
                "risk_level": row["risk_level"],
            }
        )
    return out


def get_change_insights(franchise_slug: str, limit: int = 200, db_path: str | None = None) -> dict:
    changes = get_recent_changes(franchise_slug=franchise_slug, limit=limit, db_path=db_path)

    by_risk = {"low": 0, "medium": 0, "high": 0, "unknown": 0}
    category_counts: dict[str, int] = {}

    for change in changes:
        risk = str(change.get("risk_level") or "unknown").lower()
        if risk not in by_risk:
            risk = "unknown"
        by_risk[risk] += 1

        for category in change.get("categories") or []:
            key = str(category).strip().lower()
            if not key:
                continue
            category_counts[key] = category_counts.get(key, 0) + 1

    risk_scores = {"low": 1, "medium": 2, "high": 3, "unknown": 0}
    risk_series = [str(item.get("risk_level") or "unknown").lower() for item in changes[:5]]
    if len(risk_series) >= 2:
        delta = risk_scores.get(risk_series[0], 0) - risk_scores.get(risk_series[-1], 0)
        if delta > 0:
            risk_direction = "up"
        elif delta < 0:
            risk_direction = "down"
        else:
            risk_direction = "flat"
    else:
        risk_direction = "flat"

    return {
        "franchise_slug": franchise_slug,
        "total_changes": len(changes),
        "by_risk": by_risk,
        "category_counts": dict(sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))),
        "latest_change_at": changes[0]["generated_at"] if changes else None,
        "first_change_at": changes[-1]["generated_at"] if changes else None,
        "risk_trend_last_5": {
            "window": min(len(risk_series), 5),
            "series": risk_series,
            "direction": risk_direction,
        },
    }


def compare_change_insights(left_slug: str, right_slug: str, limit: int = 200, db_path: str | None = None) -> dict:
    left = get_change_insights(franchise_slug=left_slug, limit=limit, db_path=db_path)
    right = get_change_insights(franchise_slug=right_slug, limit=limit, db_path=db_path)

    risk_scores = {"low": 1, "medium": 2, "high": 3, "unknown": 0}

    def average_risk(series: list[str]) -> float:
        if not series:
            return 0.0
        return round(sum(risk_scores.get(level, 0) for level in series) / len(series), 3)

    left_recent_score = average_risk(left["risk_trend_last_5"]["series"])
    right_recent_score = average_risk(right["risk_trend_last_5"]["series"])

    if left_recent_score > right_recent_score:
        higher_recent_risk = left_slug
    elif right_recent_score > left_recent_score:
        higher_recent_risk = right_slug
    else:
        higher_recent_risk = "tie"

    shared_categories = sorted(set(left["category_counts"].keys()) & set(right["category_counts"].keys()))

    return {
        "left": left,
        "right": right,
        "comparison": {
            "left_recent_risk_score": left_recent_score,
            "right_recent_risk_score": right_recent_score,
            "higher_recent_risk": higher_recent_risk,
            "change_volume_delta": left["total_changes"] - right["total_changes"],
            "shared_categories": shared_categories,
        },
    }


def render_change_comparison_markdown(payload: dict) -> str:
    left = payload["left"]
    right = payload["right"]
    cmp = payload["comparison"]

    return "\n".join(
        [
            "# Franchise Change Comparison",
            "",
            f"Left: {left['franchise_slug']}",
            f"Right: {right['franchise_slug']}",
            "",
            "## Summary",
            f"- Higher recent risk: {cmp['higher_recent_risk']}",
            f"- Change volume delta (left-right): {cmp['change_volume_delta']}",
            f"- Left recent risk score: {cmp['left_recent_risk_score']}",
            f"- Right recent risk score: {cmp['right_recent_risk_score']}",
            "",
            "## Shared Categories",
            ", ".join(cmp["shared_categories"]) if cmp["shared_categories"] else "none",
        ]
    )


def render_change_comparison_telegram_chunks(payload: dict, max_chars: int = 2500) -> list[str]:
    text = render_change_comparison_markdown(payload)
    lines = text.splitlines()
    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = line
        else:
            chunks.append(line[:max_chars])
            current = line[max_chars:]
    if current:
        chunks.append(current)
    return [f"[{i+1}/{len(chunks)}] {chunk}" for i, chunk in enumerate(chunks)]


def render_change_comparison_csv(payload: dict) -> str:
    left = payload["left"]
    right = payload["right"]
    cmp = payload["comparison"]

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([
        "left_slug",
        "right_slug",
        "higher_recent_risk",
        "change_volume_delta",
        "left_recent_risk_score",
        "right_recent_risk_score",
        "shared_categories",
    ])
    w.writerow(
        [
            left["franchise_slug"],
            right["franchise_slug"],
            cmp["higher_recent_risk"],
            cmp["change_volume_delta"],
            cmp["left_recent_risk_score"],
            cmp["right_recent_risk_score"],
            "|".join(cmp["shared_categories"]),
        ]
    )
    return out.getvalue()


def build_change_comparison_packet(payload: dict, max_chars: int = 2500) -> dict:
    return {
        "comparison": payload,
        "markdown": render_change_comparison_markdown(payload),
        "csv": render_change_comparison_csv(payload),
        "telegram": {
            "max_chars": max_chars,
            "chunks_with_index": render_change_comparison_telegram_chunks(payload, max_chars=max_chars),
        },
    }


def get_change_comparison_options() -> dict:
    return {
        "constraints": {
            "left_slug": {"type": "string", "required": True, "min_length": 1},
            "right_slug": {"type": "string", "required": True, "min_length": 1},
            "limit": {"type": "int", "min": 1, "max": 500},
            "max_chars": {"type": "int", "min": 200, "max": 10000},
        },
        "defaults": {"limit": 200, "max_chars": 2500},
        "surfaces": {
            "options": "/change-comparisons/options",
            "compare": "/change-comparisons",
            "markdown": "/change-comparisons/markdown",
            "telegram": "/change-comparisons/telegram",
            "csv": "/change-comparisons/csv",
            "packet": "/change-comparisons/packet",
        },
    }


def render_change_comparison_options_markdown(options: dict) -> str:
    return "\n".join(
        [
            "# Change Comparison Options",
            "",
            f"- limit: {options['constraints']['limit']['min']}..{options['constraints']['limit']['max']} (default {options['defaults']['limit']})",
            f"- max_chars: {options['constraints']['max_chars']['min']}..{options['constraints']['max_chars']['max']} (default {options['defaults']['max_chars']})",
            "",
            "## Surfaces",
            *[f"- {key}: {value}" for key, value in options["surfaces"].items()],
        ]
    )


def render_change_comparison_options_telegram_chunks(options: dict, max_chars: int = 2500) -> list[str]:
    text = render_change_comparison_options_markdown(options)
    lines = text.splitlines()
    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = line
        else:
            chunks.append(line[:max_chars])
            current = line[max_chars:]
    if current:
        chunks.append(current)
    return [f"[{i+1}/{len(chunks)}] {chunk}" for i, chunk in enumerate(chunks)]


def render_change_comparison_options_csv(options: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["section", "key", "value"])
    for key, value in options["constraints"].items():
        w.writerow(["constraints", key, json.dumps(value, sort_keys=True)])
    for key, value in options["defaults"].items():
        w.writerow(["defaults", key, value])
    for key, value in options["surfaces"].items():
        w.writerow(["surfaces", key, value])
    return out.getvalue()


def build_change_comparison_options_packet(options: dict, max_chars: int = 2500) -> dict:
    return {
        "options": options,
        "markdown": render_change_comparison_options_markdown(options),
        "csv": render_change_comparison_options_csv(options),
        "telegram": {
            "max_chars": max_chars,
            "chunks_with_index": render_change_comparison_options_telegram_chunks(options, max_chars=max_chars),
        },
    }


def seed_change_summary(franchise_slug: str, categories: list[str], risk_level: str = "medium", db_path: str | None = None):
    summary = ChangeSummary(
        franchise_slug=_normalize_franchise_slug(franchise_slug),
        generated_at=datetime.now(timezone.utc),
        categories=categories,
        highlights=["seeded"],
        risk_level=risk_level,
    )
    return insert_change_summary(summary, db_path=db_path)


def upsert_watchlist(email: str, franchise_slug: str, db_path: str | None = None) -> dict:
    normalized_email = _normalize_email(email)
    normalized_slug = _normalize_franchise_slug(franchise_slug)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO watchlists(email, franchise_slug)
            VALUES (?, ?)
            ON CONFLICT(email, franchise_slug) DO NOTHING
            """,
            (normalized_email, normalized_slug),
        )
        conn.commit()
        created = cur.rowcount > 0

        row = conn.execute(
            """
            SELECT id, email, franchise_slug, created_at
            FROM watchlists
            WHERE email = ? AND franchise_slug = ?
            """,
            (normalized_email, normalized_slug),
        ).fetchone()

    return {
        "created": created,
        "id": row["id"],
        "email": row["email"],
        "franchise_slug": row["franchise_slug"],
        "created_at": row["created_at"],
    }


def get_watchlists(email: str | None = None, db_path: str | None = None) -> list[dict]:
    normalized_email = _normalize_email(email) if email else None
    with get_conn(db_path) as conn:
        if normalized_email:
            rows = conn.execute(
                """
                SELECT id, email, franchise_slug, created_at
                FROM watchlists
                WHERE email = ?
                ORDER BY created_at DESC
                """,
                (normalized_email,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, email, franchise_slug, created_at
                FROM watchlists
                ORDER BY created_at DESC
                """
            ).fetchall()

    return [
        {
            "id": row["id"],
            "email": row["email"],
            "franchise_slug": row["franchise_slug"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_watchlist_emails(db_path: str | None = None) -> list[str]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT email
            FROM watchlists
            ORDER BY email ASC
            """
        ).fetchall()
    return [row["email"] for row in rows]


def delete_watchlist(email: str, franchise_slug: str, db_path: str | None = None) -> int:
    normalized_email = _normalize_email(email)
    normalized_slug = _normalize_franchise_slug(franchise_slug)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            DELETE FROM watchlists
            WHERE email = ? AND franchise_slug = ?
            """,
            (normalized_email, normalized_slug),
        )
        conn.commit()
        return cur.rowcount


def get_alert_feed(
    email: str,
    limit: int = 50,
    risk_levels: list[str] | None = None,
    unread_only: bool = False,
    franchise_slug: str | None = None,
    db_path: str | None = None,
) -> list[dict]:
    """Return alert feed entries by joining a user's watchlist to recent change summaries."""
    normalized_email = _normalize_email(email)
    normalized_slug = _normalize_franchise_slug(franchise_slug) if franchise_slug else None

    query = """
            SELECT
                w.email,
                w.franchise_slug,
                c.generated_at,
                c.categories,
                c.highlights,
                c.risk_level,
                ar.read_at
            FROM watchlists w
            JOIN change_summaries c ON c.franchise_slug = w.franchise_slug
            LEFT JOIN alert_reads ar
              ON ar.email = w.email
             AND ar.franchise_slug = c.franchise_slug
             AND ar.generated_at = c.generated_at
            WHERE w.email = ?
    """
    params: list = [normalized_email]

    if risk_levels:
        placeholders = ",".join("?" for _ in risk_levels)
        query += f" AND c.risk_level IN ({placeholders})"
        params.extend(risk_levels)

    if unread_only:
        query += " AND ar.id IS NULL"

    if normalized_slug:
        query += " AND w.franchise_slug = ?"
        params.append(normalized_slug)

    query += " ORDER BY c.generated_at DESC LIMIT ?"
    params.append(limit)

    with get_conn(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    return [
        {
            "email": row["email"],
            "franchise_slug": row["franchise_slug"],
            "generated_at": row["generated_at"],
            "categories": json.loads(row["categories"]),
            "highlights": json.loads(row["highlights"]),
            "risk_level": row["risk_level"],
            "read": row["read_at"] is not None,
            "read_at": row["read_at"],
        }
        for row in rows
    ]


def mark_alert_read(email: str, franchise_slug: str, generated_at: str, db_path: str | None = None) -> int:
    normalized_email = _normalize_email(email)
    normalized_slug = _normalize_franchise_slug(franchise_slug)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO alert_reads(email, franchise_slug, generated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(email, franchise_slug, generated_at) DO NOTHING
            """,
            (normalized_email, normalized_slug, generated_at),
        )
        conn.commit()
        return cur.rowcount


def mark_alerts_read_for_franchise(email: str, franchise_slug: str, db_path: str | None = None) -> int:
    """Mark all currently unread alerts as read for a user+franchise."""
    normalized_email = _normalize_email(email)
    normalized_slug = _normalize_franchise_slug(franchise_slug)
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT c.generated_at
            FROM change_summaries c
            JOIN watchlists w ON w.franchise_slug = c.franchise_slug
            LEFT JOIN alert_reads ar
              ON ar.email = w.email
             AND ar.franchise_slug = c.franchise_slug
             AND ar.generated_at = c.generated_at
            WHERE w.email = ?
              AND w.franchise_slug = ?
              AND ar.id IS NULL
            """,
            (normalized_email, normalized_slug),
        ).fetchall()

        inserted = 0
        for row in rows:
            cur = conn.execute(
                """
                INSERT INTO alert_reads(email, franchise_slug, generated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(email, franchise_slug, generated_at) DO NOTHING
                """,
                (normalized_email, normalized_slug, row["generated_at"]),
            )
            inserted += cur.rowcount

        conn.commit()
        return inserted


def get_unread_alert_count(email: str, db_path: str | None = None) -> int:
    normalized_email = _normalize_email(email)
    with get_conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS unread_count
            FROM watchlists w
            JOIN change_summaries c ON c.franchise_slug = w.franchise_slug
            LEFT JOIN alert_reads ar
              ON ar.email = w.email
             AND ar.franchise_slug = c.franchise_slug
             AND ar.generated_at = c.generated_at
            WHERE w.email = ?
              AND ar.id IS NULL
            """,
            (normalized_email,),
        ).fetchone()
    return int(row["unread_count"])


def get_alert_summary(email: str, db_path: str | None = None) -> dict:
    normalized_email = _normalize_email(email)
    with get_conn(db_path) as conn:
        totals = conn.execute(
            """
            SELECT
              COUNT(*) AS total_alerts,
              SUM(CASE WHEN ar.id IS NULL THEN 1 ELSE 0 END) AS unread_alerts
            FROM watchlists w
            JOIN change_summaries c ON c.franchise_slug = w.franchise_slug
            LEFT JOIN alert_reads ar
              ON ar.email = w.email
             AND ar.franchise_slug = c.franchise_slug
             AND ar.generated_at = c.generated_at
            WHERE w.email = ?
            """,
            (normalized_email,),
        ).fetchone()

        risk_rows = conn.execute(
            """
            SELECT c.risk_level, COUNT(*) AS cnt
            FROM watchlists w
            JOIN change_summaries c ON c.franchise_slug = w.franchise_slug
            WHERE w.email = ?
            GROUP BY c.risk_level
            """,
            (normalized_email,),
        ).fetchall()

        top_unread = conn.execute(
            """
            SELECT c.franchise_slug, COUNT(*) AS unread_count
            FROM watchlists w
            JOIN change_summaries c ON c.franchise_slug = w.franchise_slug
            LEFT JOIN alert_reads ar
              ON ar.email = w.email
             AND ar.franchise_slug = c.franchise_slug
             AND ar.generated_at = c.generated_at
            WHERE w.email = ?
              AND ar.id IS NULL
            GROUP BY c.franchise_slug
            ORDER BY unread_count DESC, c.franchise_slug ASC
            LIMIT 5
            """,
            (normalized_email,),
        ).fetchall()

    by_risk = {"low": 0, "medium": 0, "high": 0}
    for row in risk_rows:
        level = row["risk_level"]
        if level in by_risk:
            by_risk[level] = int(row["cnt"])

    return {
        "total_alerts": int(totals["total_alerts"] or 0),
        "unread_alerts": int(totals["unread_alerts"] or 0),
        "by_risk": by_risk,
        "top_unread_franchises": [
            {"franchise_slug": row["franchise_slug"], "unread_count": int(row["unread_count"])} for row in top_unread
        ],
    }
