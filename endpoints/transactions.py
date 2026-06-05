from __future__ import annotations

from urllib.parse import parse_qs

from components.common import row_options
from components.transactions import transaction_view_rows
from database import db
from web_helpers import layout, one, render_template


def page(query: str) -> bytes:
    params = parse_qs(query)
    period_id = params.get("period", params.get("month", [""]))[0]
    account = params.get("account", [""])[0]
    search = params.get("q", [""])[0].strip()
    clauses = []
    values: list[object] = []
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
        periods = conn.execute("SELECT id, name FROM period ORDER BY id").fetchall()
        accounts = conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
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


def create(data: dict[str, list[str]]) -> str:
    label = one(data, "label")
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO transaction_labels(name) VALUES (?)", (label,))
        conn.execute(
            """
            INSERT INTO transactions(period_id, account_id, date, label, amount)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                one(data, "period_id"),
                one(data, "account_id"),
                one(data, "date") or None,
                label,
                float(one(data, "amount") or 0),
            ),
        )
    return one(data, "return_to") or "/transactions"
