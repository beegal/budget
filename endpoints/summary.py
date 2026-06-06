from __future__ import annotations

import sqlite3
from urllib.parse import parse_qs

from components.period import balance_tone, is_transfer_group, money_or_empty
from database import db
from endpoints.filters import parse_period_ids, period_selector_view
from web_helpers import money, render_template, transaction_filter_url, user_layout


def page(query: str, user_id: str) -> bytes:
    params = parse_qs(query)
    with db() as conn:
        periods = conn.execute(
            "SELECT id, name FROM period WHERE user_id = ? ORDER BY COALESCE(start_date, ''), id",
            (user_id,),
        ).fetchall()
        selected_period_ids, all_periods = parse_period_ids(params, periods)
        rows = summary_rows(conn, selected_period_ids, user_id) if selected_period_ids else []

    visible_rows = [row for row in rows if not is_transfer_group(str(row["label_group"]))]
    total_income = sum(float(row["income"] or 0) for row in visible_rows)
    total_expense = sum(float(row["expense"] or 0) for row in visible_rows)
    total_net = sum(float(row["net"] or 0) for row in visible_rows)
    body = render_template(
        "summary.html",
        period_selector=period_selector_view(periods, selected_period_ids, all_periods),
        rows=[summary_row_view(row, selected_period_ids) for row in visible_rows],
        totals={
            "income": money(total_income),
            "expense": money(total_expense),
            "net": money(total_net),
            "net_class": balance_tone(total_net),
        },
    )
    return user_layout("Synthèse", body, user_id)


def summary_rows(conn: sqlite3.Connection, period_ids: list[int], user_id: str) -> list[sqlite3.Row]:
    placeholders = ", ".join("?" for _ in period_ids)
    return conn.execute(
        f"""
        WITH grouped AS (
            SELECT
                CASE
                    WHEN INSTR(t.label, '-') > 0 THEN TRIM(SUBSTR(t.label, 1, INSTR(t.label, '-') - 1))
                    ELSE TRIM(t.label)
                END AS label_group,
                t.amount
            FROM transactions t
            WHERE t.user_id = ? AND t.period_id IN ({placeholders})
        )
        SELECT grouped.label_group,
               COALESCE(SUM(CASE WHEN grouped.amount > 0 THEN grouped.amount END), 0) AS income,
               COALESCE(SUM(CASE WHEN grouped.amount < 0 THEN grouped.amount END), 0) AS expense,
               COALESCE(SUM(grouped.amount), 0) AS net
        FROM grouped
        GROUP BY grouped.label_group
        ORDER BY grouped.label_group
        """,
        [user_id, *period_ids],
    ).fetchall()


def summary_row_view(row: sqlite3.Row, period_ids: list[int]) -> dict[str, object]:
    return {
        "label_group": row["label_group"],
        "href": transaction_filter_url(period_ids, row["label_group"]),
        "income": money_or_empty(row["income"]),
        "expense": money_or_empty(row["expense"]),
        "net": money_or_empty(row["net"]),
        "net_class": balance_tone(row["net"]),
    }
