from __future__ import annotations

import sqlite3
from urllib.parse import parse_qs, urlencode

from components.common import panel_message
from components.period import account_tab_view, budget_tab_view, overview_view, period_tabs_view
from database import db
from i18n import translate
from transfer_labels import is_internal_transfer_label
from web_helpers import period_label, render_template, user_layout


def page(period_id: int, query: str, user_id: str) -> bytes:
    params = parse_qs(query)
    active = params.get("account", ["overview"])[0]
    with db() as conn:
        period = conn.execute("SELECT * FROM period WHERE id = ? AND user_id = ?", (period_id, user_id)).fetchone()
        if period is None:
            return user_layout(translate("errors.period-not-found"), panel_message(translate("errors.period-not-found")), user_id)
        navigation_periods = conn.execute(
            """
            SELECT id, name, start_date
            FROM period
            WHERE user_id = ?
            ORDER BY COALESCE(start_date, ''), id
            """,
            (user_id,),
        ).fetchall()
        accounts = period_accounts(conn, period_id, user_id)
        labels = conn.execute("SELECT id, name FROM transaction_labels WHERE user_id = ? ORDER BY name", (user_id,)).fetchall()
        summary_rows = period_summary_rows(conn, period_id, user_id)
        balance_rows = period_balance_rows(conn, period_id, user_id)
        transfer_rows = period_transfer_rows(conn, period_id, user_id)
        selected_account = None
        account_transactions: list[sqlite3.Row] = []
        budget_rows = []
        if active == "budget":
            budget_rows = conn.execute(
                """
                SELECT *
                FROM budget_schedule
                WHERE period_id = ? AND user_id = ?
                ORDER BY id
                """,
                (period_id, user_id),
            ).fetchall()
        elif active != "overview":
            selected_account = conn.execute(
                """
                SELECT a.*, ab.opening
                FROM accounts a
                LEFT JOIN account_balances ab ON ab.account_id = a.id AND ab.period_id = ? AND ab.user_id = ?
                WHERE a.id = ? AND a.user_id = ?
                """,
                (period_id, user_id, active, user_id),
            ).fetchone()
            account_transactions = conn.execute(
                """
                SELECT t.*, a.name AS account_name
                FROM transactions t
                JOIN accounts a ON a.id = t.account_id
                WHERE t.period_id = ? AND t.account_id = ? AND t.user_id = ?
                ORDER BY COALESCE(t.date, '9999-12-31'), t.sort_index, t.id
                """,
                (period_id, active, user_id),
            ).fetchall()
            if selected_account is None:
                return user_layout(translate("errors.account-not-found"), panel_message(translate("errors.account-not-found")), user_id)

    visible_accounts = [
        account
        for account in accounts
        if account["visible_if_empty"] or account["transaction_count"] or active == str(account["id"])
    ]
    hidden_accounts = [account for account in accounts if account not in visible_accounts]
    if active == "overview":
        content = overview_view(period_id, summary_rows, balance_rows, transfer_rows)
    elif active == "budget":
        content = budget_tab_view(period_id, budget_rows, accounts, labels)
    else:
        content = account_tab_view(period_id, period, selected_account, account_transactions, labels)
    body = render_template(
        "period.html",
        period_label=period_label(period),
        period_name=period["name"],
        period_nav=period_navigation_view(navigation_periods, period_id, active),
        tabs=period_tabs_view(period_id, active, visible_accounts, hidden_accounts),
        content=content,
    )
    return user_layout(str(period["name"]), body, user_id)


def period_navigation_view(periods: list[sqlite3.Row], period_id: int, active: str) -> dict[str, object]:
    current_index = next((index for index, row in enumerate(periods) if row["id"] == period_id), None)
    if current_index is None:
        return {"next": None, "previous": None}
    next_period = periods[current_index + 1] if current_index + 1 < len(periods) else None
    previous_period = periods[current_index - 1] if current_index > 0 else None
    return {
        "next": period_navigation_link(next_period, active),
        "previous": period_navigation_link(previous_period, active),
    }


def period_navigation_link(period: sqlite3.Row | None, active: str) -> dict[str, object] | None:
    if period is None:
        return None
    query = "" if active == "overview" else f"?{urlencode({'account': active})}"
    return {
        "name": period["name"],
        "href": f"/period/{period['id']}{query}",
    }


def period_accounts(conn: sqlite3.Connection, period_id: int, user_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT a.id,
               a.name,
               a.visible_if_empty,
               COUNT(t.id) AS transaction_count,
               COALESCE(SUM(t.amount), 0) AS transaction_total,
               CASE
                   WHEN ab.opening IS NULL THEN NULL
                   ELSE ab.opening + COALESCE(SUM(t.amount), 0)
               END AS current
        FROM accounts a
        LEFT JOIN account_balances ab ON ab.account_id = a.id AND ab.period_id = ? AND ab.user_id = ?
        LEFT JOIN transactions t ON t.account_id = a.id AND t.period_id = ? AND t.user_id = ?
        WHERE a.user_id = ?
        GROUP BY a.id
        ORDER BY a.sort_index, a.name
        """,
        (period_id, user_id, period_id, user_id, user_id),
    ).fetchall()


def period_summary_rows(conn: sqlite3.Connection, period_id: int, user_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        WITH grouped AS (
            SELECT
                CASE
                    WHEN INSTR(t.label, '-') > 0 THEN TRIM(SUBSTR(t.label, 1, INSTR(t.label, '-') - 1))
                    ELSE TRIM(t.label)
                END AS label_group,
                t.amount
            FROM transactions t
            WHERE t.period_id = ? AND t.user_id = ?
            UNION ALL
            SELECT CASE
                       WHEN bs.amount > 0 THEN ?
                       ELSE ?
                   END AS label_group,
                   bs.amount
            FROM budget_schedule bs
            WHERE bs.period_id = ? AND bs.user_id = ? AND bs.status = 'scheduled' AND bs.amount != 0
        )
        SELECT grouped.label_group,
               COALESCE(SUM(CASE WHEN grouped.amount > 0 THEN grouped.amount END), 0) AS income,
               COALESCE(SUM(CASE WHEN grouped.amount < 0 THEN grouped.amount END), 0) AS expense,
               COALESCE(SUM(grouped.amount), 0) AS net
        FROM grouped
        GROUP BY grouped.label_group
        ORDER BY grouped.label_group
        """,
        (period_id, user_id, translate("summary.future-income"), translate("summary.future-expense"), period_id, user_id),
    ).fetchall()


def period_balance_rows(conn: sqlite3.Connection, period_id: int, user_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT a.id AS account_id,
               a.name,
               ab.opening,
               COALESCE(SUM(t.amount), 0) AS transaction_total,
               CASE
                   WHEN ab.opening IS NULL THEN NULL
                   ELSE ab.opening + COALESCE(SUM(t.amount), 0)
               END AS current
        FROM accounts a
        LEFT JOIN account_balances ab ON ab.account_id = a.id AND ab.period_id = ? AND ab.user_id = ?
        LEFT JOIN transactions t ON t.account_id = a.id AND t.period_id = ? AND t.user_id = ?
        WHERE a.show_in_summary = 1 AND a.user_id = ?
        GROUP BY a.id
        ORDER BY a.sort_index, a.name
        """,
        (period_id, user_id, period_id, user_id, user_id),
    ).fetchall()


def period_transfer_rows(conn: sqlite3.Connection, period_id: int, user_id: str) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT t.date,
               a.name AS account_name,
               t.label,
               t.amount
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE t.period_id = ?
          AND t.user_id = ?
        ORDER BY COALESCE(t.date, '9999-12-31'), t.sort_index, t.id
        """,
        (period_id, user_id),
    ).fetchall()
    return [row for row in rows if is_internal_transfer_label(row["label"])]
