from __future__ import annotations

from datetime import date, datetime, timedelta
import sqlite3

from components.periods import period_card_view
import database
from database import db
from web_helpers import format_date, layout, normalize_date, one, period_label, render_template


def page(user_id: str) -> bytes:
    with db() as conn:
        database.ensure_user_data(conn, user_id)
        periods = conn.execute(
            """
            SELECT m.*,
                   COALESCE(tx.transaction_count, 0) AS transaction_count,
                   COALESCE(bs.budget_count, 0) AS budget_count,
                   COALESCE(tx.income, 0) AS income,
                   COALESCE(tx.expense, 0) AS expense,
                   COALESCE(tx.net, 0) AS net
            FROM period m
            LEFT JOIN (
                SELECT period_id,
                       COUNT(*) AS transaction_count,
                       COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0) AS income,
                       COALESCE(SUM(CASE WHEN amount < 0 THEN amount END), 0) AS expense,
                       COALESCE(SUM(amount), 0) AS net
                FROM transactions
                WHERE user_id = ?
                GROUP BY period_id
            ) tx ON tx.period_id = m.id
            LEFT JOIN (
                SELECT period_id, COUNT(*) AS budget_count
                FROM budget_schedule
                WHERE user_id = ?
                GROUP BY period_id
            ) bs ON bs.period_id = m.id
            WHERE m.user_id = ?
            ORDER BY COALESCE(m.start_date, '') DESC, m.id DESC
            """,
            (user_id, user_id, user_id),
        ).fetchall()
    overlap_reasons = period_warnings(periods)
    period_views = [
        period_card_view(row, overlap_reasons.get(row["id"]))
        for row in periods
    ]
    body = render_template("periods.html", today=format_date(date.today().isoformat()), periods=period_views)
    return layout("Périodes", body)


def period_warnings(periods: list[sqlite3.Row]) -> dict[int, str]:
    warnings: dict[int, str] = {}
    ranges = []
    for row in periods:
        start = parse_iso_date(row["start_date"])
        end = parse_iso_date(row["end_date"])
        if start and end and end <= start:
            warnings[row["id"]] = "La date de fin doit être après la date de début."
        ranges.append((row, start, end))

    for index, (row, start, end) in enumerate(ranges):
        if not start:
            continue
        for other, other_start, other_end in ranges[index + 1 :]:
            if not other_start:
                continue
            if periods_overlap(start, end, other_start, other_end):
                reason = f"Chevauche la période {other['name']} ({period_label(other)})."
                other_reason = f"Chevauche la période {row['name']} ({period_label(row)})."
                warnings.setdefault(row["id"], reason)
                warnings.setdefault(other["id"], other_reason)
    return warnings


def parse_iso_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def periods_overlap(start: date, end: date | None, other_start: date, other_end: date | None) -> bool:
    return start < (other_end or date.max) and other_start < (end or date.max)


def create(data: dict[str, list[str]], user_id: str) -> str:
    start_date = datetime.strptime(normalize_date(one(data, "start_date")), "%Y-%m-%d").date()
    end_date = normalize_period_end(one(data, "end_date"))
    previous_end_date = (start_date - timedelta(days=1)).isoformat()
    with db() as conn:
        conn.execute(
            """
            UPDATE period
            SET end_date = ?
            WHERE user_id = ? AND start_date IS NOT NULL AND end_date IS NULL AND start_date < ?
            """,
            (previous_end_date, user_id, start_date.isoformat()),
        )
        conn.execute(
            "INSERT INTO period(user_id, name, start_date, end_date) VALUES (?, ?, ?, ?)",
            (user_id, one(data, "name"), start_date.isoformat(), end_date),
        )
        period_id = conn.execute(
            "SELECT id FROM period WHERE user_id = ? AND name = ?",
            (user_id, one(data, "name")),
        ).fetchone()["id"]
        account_ids = conn.execute("SELECT id FROM accounts WHERE user_id = ?", (user_id,)).fetchall()
        for account in account_ids:
            conn.execute(
                """
                INSERT OR IGNORE INTO account_balances(user_id, period_id, account_id, opening)
                VALUES (?, ?, ?, NULL)
                """,
                (user_id, period_id, account["id"]),
            )
        seed_budget_schedule(conn, period_id, user_id)
    return "/"


def seed_budget_schedule(conn, period_id: int, user_id: str) -> None:
    conn.execute(
        """
        INSERT INTO budget_schedule(user_id, period_id, label, amount, status)
        SELECT ?, ?, label, amount, 'scheduled'
        FROM monthly_budget
        WHERE user_id = ?
        ORDER BY day, id
        """,
        (user_id, period_id, user_id),
    )


def normalize_period_end(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw or raw.casefold() == "en cours":
        return None
    return normalize_date(raw)
