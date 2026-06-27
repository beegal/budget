from __future__ import annotations

import json
from urllib.parse import parse_qs

from components.common import label_picker
from components.transactions import transaction_view_rows
from database import db
from endpoints.filters import account_selector_view, parse_account_ids, parse_period_ids, period_selector_view
from i18n import translate
from web_helpers import money, one, render_template, user_layout


def page(query: str, user_id: str) -> bytes:
    params = parse_qs(query)
    search = params.get("q", [""])[0].strip()
    clauses = ["t.user_id = ?"]
    values: list[object] = [user_id]
    with db() as conn:
        periods = conn.execute("SELECT id, name FROM period WHERE user_id = ? ORDER BY COALESCE(start_date, ''), id", (user_id,)).fetchall()
        accounts = conn.execute("SELECT id, name FROM accounts WHERE user_id = ? ORDER BY name", (user_id,)).fetchall()
        selected_period_ids, all_periods = parse_period_ids(params, periods)
        selected_account_ids, all_accounts = parse_account_ids(params, accounts)
        if selected_period_ids:
            clauses.append(f"t.period_id IN ({', '.join('?' for _ in selected_period_ids)})")
            values.extend(selected_period_ids)
        elif not all_periods:
            clauses.append("1 = 0")
        if selected_account_ids:
            clauses.append(f"t.account_id IN ({', '.join('?' for _ in selected_account_ids)})")
            values.extend(selected_account_ids)
        elif not all_accounts:
            clauses.append("1 = 0")
        if search:
            clauses.append("t.label LIKE ?")
            values.append(f"%{search}%")
        where = "WHERE " + " AND ".join(clauses)
        labels = conn.execute("SELECT name FROM transaction_labels WHERE user_id = ? ORDER BY name", (user_id,)).fetchall()
        rows = conn.execute(
            f"""
            SELECT t.*, p.name AS period_name, a.name AS account_name
            FROM transactions t
            JOIN period p ON p.id = t.period_id
            JOIN accounts a ON a.id = t.account_id
            {where}
            ORDER BY COALESCE(t.date, '9999-12-31'), t.id
            LIMIT 500
            """,
            values,
        ).fetchall()
        planned_budget_filter = planned_budget_search_filter(search, all_accounts)
        if planned_budget_filter:
            rows = [*rows, *planned_budget_rows(conn, selected_period_ids, user_id, planned_budget_filter)]
    total_debit = sum(float(row["amount"] or 0) for row in rows if float(row["amount"] or 0) < 0)
    total_credit = sum(float(row["amount"] or 0) for row in rows if float(row["amount"] or 0) > 0)
    total = total_debit + total_credit
    body = render_template(
        "transactions.html",
        labels_json=json.dumps([row["name"] for row in labels], ensure_ascii=False),
        period_selector=period_selector_view(periods, selected_period_ids, all_periods),
        account_selector=account_selector_view(accounts, selected_account_ids, all_accounts),
        search=search,
        label_filter=label_picker(search, 'name="q"'),
        rows=transaction_view_rows(rows),
        totals={
            "debit": money(total_debit),
            "credit": money(total_credit),
            "total": money(total),
            "total_class": "positive" if total > 0 else "negative" if total < 0 else "",
        },
    )
    return user_layout(translate("transactions.title"), body, user_id)


def planned_budget_search_filter(search: str, all_accounts: bool) -> str:
    if not all_accounts:
        return ""
    normalized = search.casefold()
    if normalized == translate("summary.future-income").casefold():
        return "income"
    if normalized == translate("summary.future-expense").casefold():
        return "expense"
    if normalized == translate("summary.planned-budget").casefold():
        return "all"
    return ""


def should_show_planned_budget_rows(search: str, all_accounts: bool) -> bool:
    return bool(planned_budget_search_filter(search, all_accounts))


def planned_budget_rows(conn, period_ids: list[int], user_id: str, amount_filter: str = "all") -> list[dict[str, object]]:
    if not period_ids:
        return []
    placeholders = ", ".join("?" for _ in period_ids)
    amount_condition = {
        "income": "AND bs.amount > 0",
        "expense": "AND bs.amount < 0",
    }.get(amount_filter, "")
    return conn.execute(
        f"""
        SELECT bs.id,
               bs.user_id,
               bs.period_id,
               0 AS account_id,
               COALESCE(p.start_date, '') AS date,
               CASE
                   WHEN ? = 'all' THEN ?
                   WHEN bs.amount > 0 THEN ?
                   ELSE ?
               END AS label,
               bs.amount,
               0 AS sort_index,
               bs.label AS comment,
               p.name AS period_name,
               ? AS account_name
        FROM budget_schedule bs
        JOIN period p ON p.id = bs.period_id AND p.user_id = bs.user_id
        WHERE bs.user_id = ?
          AND bs.period_id IN ({placeholders})
          AND bs.status = 'scheduled'
          {amount_condition}
        ORDER BY COALESCE(p.start_date, ''), bs.id
        """,
        [
            amount_filter,
            translate("summary.planned-budget"),
            translate("summary.future-income"),
            translate("summary.future-expense"),
            translate("period.budget"),
            user_id,
            *period_ids,
        ],
    ).fetchall()


def create(data: dict[str, list[str]], user_id: str) -> str:
    label = one(data, "label")
    with db() as conn:
        period = conn.execute("SELECT id FROM period WHERE id = ? AND user_id = ?", (one(data, "period_id"), user_id)).fetchone()
        account = conn.execute("SELECT id FROM accounts WHERE id = ? AND user_id = ?", (one(data, "account_id"), user_id)).fetchone()
        if period is None or account is None:
            return "/transactions"
        conn.execute("INSERT OR IGNORE INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, label))
        conn.execute(
            """
            INSERT INTO transactions(user_id, period_id, account_id, date, label, amount)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                one(data, "period_id"),
                one(data, "account_id"),
                one(data, "date") or None,
                label,
                float(one(data, "amount") or 0),
            ),
        )
    return one(data, "return_to") or "/transactions"
