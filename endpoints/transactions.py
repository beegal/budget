from __future__ import annotations

import json
from urllib.parse import parse_qs

from components.common import label_picker
from components.transactions import transaction_view_rows
from database import db
from endpoints.filters import account_selector_view, parse_account_ids, parse_period_ids, period_selector_view
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
    return user_layout("Transactions", body, user_id)


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
