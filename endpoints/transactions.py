from __future__ import annotations

from urllib.parse import parse_qs

from components.common import row_options
from components.transactions import transaction_view_rows
from database import db
from web_helpers import layout, one, render_template


def page(query: str, user_id: str) -> bytes:
    params = parse_qs(query)
    period_id = params.get("period", params.get("month", [""]))[0]
    account = params.get("account", [""])[0]
    search = params.get("q", [""])[0].strip()
    clauses = ["t.user_id = ?"]
    values: list[object] = [user_id]
    if period_id:
        clauses.append("t.period_id = ?")
        values.append(period_id)
    if account:
        clauses.append("t.account_id = ?")
        values.append(account)
    if search:
        clauses.append("t.label LIKE ?")
        values.append(f"%{search}%")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with db() as conn:
        periods = conn.execute("SELECT id, name FROM period WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()
        accounts = conn.execute("SELECT id, name FROM accounts WHERE user_id = ? ORDER BY name", (user_id,)).fetchall()
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
    body = render_template(
        "transactions.html",
        period_options=row_options(periods, period_id, "Toutes les périodes"),
        account_options=row_options(accounts, account, "Tous les comptes"),
        search=search,
        rows=transaction_view_rows(rows),
    )
    return layout("Transactions", body)


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
