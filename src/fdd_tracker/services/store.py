from __future__ import annotations

import json
from datetime import datetime, timezone

from fdd_tracker.db import get_conn
from fdd_tracker.models import ChangeSummary, Filing


def upsert_filing(filing: Filing, db_path: str | None = None) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO filings(franchise_slug, source, filed_on, document_url, document_hash)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(franchise_slug, source, document_url)
            DO UPDATE SET filed_on=excluded.filed_on, document_hash=excluded.document_hash
            """,
            (
                filing.franchise_slug,
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
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, franchise_slug, source, filed_on, document_url, document_hash
            FROM filings
            WHERE franchise_slug = ?
            ORDER BY filed_on IS NULL, filed_on DESC, id DESC
            LIMIT ?
            """,
            (franchise_slug, limit),
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


def insert_change_summary(summary: ChangeSummary, db_path: str | None = None) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO change_summaries(franchise_slug, generated_at, categories, highlights, risk_level)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                summary.franchise_slug,
                summary.generated_at.isoformat(),
                json.dumps(summary.categories),
                json.dumps(summary.highlights),
                summary.risk_level,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_recent_changes(franchise_slug: str, limit: int = 20, db_path: str | None = None) -> list[dict]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT franchise_slug, generated_at, categories, highlights, risk_level
            FROM change_summaries
            WHERE franchise_slug = ?
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (franchise_slug, limit),
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


def seed_change_summary(franchise_slug: str, categories: list[str], risk_level: str = "medium", db_path: str | None = None):
    summary = ChangeSummary(
        franchise_slug=franchise_slug,
        generated_at=datetime.now(timezone.utc),
        categories=categories,
        highlights=["seeded"],
        risk_level=risk_level,
    )
    return insert_change_summary(summary, db_path=db_path)


def upsert_watchlist(email: str, franchise_slug: str, db_path: str | None = None) -> dict:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO watchlists(email, franchise_slug)
            VALUES (?, ?)
            ON CONFLICT(email, franchise_slug) DO NOTHING
            """,
            (email, franchise_slug),
        )
        conn.commit()
        created = cur.rowcount > 0

        row = conn.execute(
            """
            SELECT id, email, franchise_slug, created_at
            FROM watchlists
            WHERE email = ? AND franchise_slug = ?
            """,
            (email, franchise_slug),
        ).fetchone()

    return {
        "created": created,
        "id": row["id"],
        "email": row["email"],
        "franchise_slug": row["franchise_slug"],
        "created_at": row["created_at"],
    }


def get_watchlists(email: str | None = None, db_path: str | None = None) -> list[dict]:
    with get_conn(db_path) as conn:
        if email:
            rows = conn.execute(
                """
                SELECT id, email, franchise_slug, created_at
                FROM watchlists
                WHERE email = ?
                ORDER BY created_at DESC
                """,
                (email,),
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
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            DELETE FROM watchlists
            WHERE email = ? AND franchise_slug = ?
            """,
            (email, franchise_slug),
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
    params: list = [email]

    if risk_levels:
        placeholders = ",".join("?" for _ in risk_levels)
        query += f" AND c.risk_level IN ({placeholders})"
        params.extend(risk_levels)

    if unread_only:
        query += " AND ar.id IS NULL"

    if franchise_slug:
        query += " AND w.franchise_slug = ?"
        params.append(franchise_slug)

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
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO alert_reads(email, franchise_slug, generated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(email, franchise_slug, generated_at) DO NOTHING
            """,
            (email, franchise_slug, generated_at),
        )
        conn.commit()
        return cur.rowcount


def mark_alerts_read_for_franchise(email: str, franchise_slug: str, db_path: str | None = None) -> int:
    """Mark all currently unread alerts as read for a user+franchise."""
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
            (email, franchise_slug),
        ).fetchall()

        inserted = 0
        for row in rows:
            cur = conn.execute(
                """
                INSERT INTO alert_reads(email, franchise_slug, generated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(email, franchise_slug, generated_at) DO NOTHING
                """,
                (email, franchise_slug, row["generated_at"]),
            )
            inserted += cur.rowcount

        conn.commit()
        return inserted


def get_unread_alert_count(email: str, db_path: str | None = None) -> int:
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
            (email,),
        ).fetchone()
    return int(row["unread_count"])



def get_alert_summary(email: str, db_path: str | None = None) -> dict:
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
            (email,),
        ).fetchone()

        risk_rows = conn.execute(
            """
            SELECT c.risk_level, COUNT(*) AS cnt
            FROM watchlists w
            JOIN change_summaries c ON c.franchise_slug = w.franchise_slug
            WHERE w.email = ?
            GROUP BY c.risk_level
            """,
            (email,),
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
            (email,),
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
