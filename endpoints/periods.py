from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
import sqlite3

from components.period import is_transfer_group
from components.periods import period_card_view
from database import db
from endpoints.period import period_summary_rows
from i18n import translate
from web_helpers import format_date, normalize_date, one, period_label, render_template, user_layout


def page(user_id: str) -> bytes:
    with db() as conn:
        periods = conn.execute(
            """
            SELECT m.*,
                   COALESCE(tx.transaction_count, 0) AS transaction_count,
                   COALESCE(bs.budget_count, 0) AS budget_count
            FROM period m
            LEFT JOIN (
                SELECT period_id,
                       COUNT(*) AS transaction_count
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
        periods = [period_with_overview_totals(conn, row, user_id) for row in periods]
    overlap_reasons = period_warnings(periods)
    period_views = [
        period_card_view(row, overlap_reasons.get(row["id"]))
        for row in periods
    ]
    body = render_template("periods.html", today=format_date(date.today().isoformat()), periods=period_views)
    return user_layout(translate("nav.periods"), body, user_id)


def period_with_overview_totals(conn: sqlite3.Connection, row: sqlite3.Row, user_id: str) -> dict[str, object]:
    totals = period_overview_totals(conn, int(row["id"]), user_id)
    return {
        **dict(row),
        "income": totals["actual_income"],
        "expense": totals["actual_expense"],
        "planned_income": totals["planned_income"],
        "planned_expense": totals["planned_expense"],
        "has_planned": totals["planned_income"] != 0 or totals["planned_expense"] != 0,
        "net": totals["net"],
    }


def period_overview_totals(conn: sqlite3.Connection, period_id: int, user_id: str) -> dict[str, float]:
    planned_income_label = translate("summary.future-income").casefold()
    planned_expense_label = translate("summary.future-expense").casefold()
    totals = {
        "actual_income": 0.0,
        "actual_expense": 0.0,
        "planned_income": 0.0,
        "planned_expense": 0.0,
    }
    rows = [
        row
        for row in period_summary_rows(conn, period_id, user_id)
        if not is_transfer_group(str(row["label_group"]))
    ]
    for row in rows:
        label_group = str(row["label_group"]).casefold()
        if label_group == planned_income_label:
            totals["planned_income"] += float(row["income"] or 0)
        elif label_group == planned_expense_label:
            totals["planned_expense"] += float(row["expense"] or 0)
        else:
            totals["actual_income"] += float(row["income"] or 0)
            totals["actual_expense"] += float(row["expense"] or 0)

    totals["income"] = totals["actual_income"] + totals["planned_income"]
    totals["expense"] = totals["actual_expense"] + totals["planned_expense"]
    totals["net"] = totals["income"] + totals["expense"]
    return totals


def period_warnings(periods: list[sqlite3.Row]) -> dict[int, str]:
    warnings: dict[int, str] = {}
    ranges = []
    for row in periods:
        start = parse_iso_date(row["start_date"])
        end = parse_iso_date(row["end_date"])
        if start and end and end <= start:
            warnings[row["id"]] = translate("periods.end-after-start")
        ranges.append((row, start, end))

    for index, (row, start, end) in enumerate(ranges):
        if not start:
            continue
        for other, other_start, other_end in ranges[index + 1 :]:
            if not other_start:
                continue
            if periods_overlap(start, end, other_start, other_end):
                reason = translate("periods.overlap", name=other["name"], period=period_label(other))
                other_reason = translate("periods.overlap", name=row["name"], period=period_label(row))
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


def seed_budget_schedule(conn, period_id: int, user_id: str, reference_date: date | None = None) -> None:
    rows = conn.execute(
        """
        SELECT day, label, amount
        FROM monthly_budget
        WHERE user_id = ?
        ORDER BY day, id
        """,
        (user_id,),
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            INSERT INTO budget_schedule(user_id, period_id, date, label, amount, status)
            VALUES (?, ?, ?, ?, ?, 'scheduled')
            """,
            (user_id, period_id, scheduled_budget_date(int(row["day"]), reference_date), row["label"], row["amount"]),
        )


def scheduled_budget_date(day: int, reference_date: date | None = None) -> str:
    reference = reference_date or date.today()
    target_year = reference.year
    target_month = reference.month
    if day < reference.day:
        target_month += 1
        if target_month > 12:
            target_month = 1
            target_year += 1
    target_day = min(max(day, 1), calendar.monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day).isoformat()


def normalize_period_end(value: str) -> str | None:
    raw = str(value or "").strip()
    current_markers = {"en cours", "current", "laufend", "lopend", translate("periods.current").casefold()}
    if not raw or raw.casefold() in current_markers:
        return None
    return normalize_date(raw)
