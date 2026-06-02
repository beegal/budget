from __future__ import annotations

from urllib.parse import parse_qs

from database import db
from web_helpers import esc, layout, money, one, row_options


def page(query: str) -> bytes:
    params = parse_qs(query)
    month = params.get("month", [""])[0]
    account = params.get("account", [""])[0]
    search = params.get("q", [""])[0].strip()
    clauses = []
    values: list[object] = []
    if month:
        clauses.append("t.month_id = ?")
        values.append(month)
    if account:
        clauses.append("t.account_id = ?")
        values.append(account)
    if search:
        clauses.append("t.label LIKE ?")
        values.append(f"%{search}%")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with db() as conn:
        months = conn.execute("SELECT id, name FROM months ORDER BY id").fetchall()
        accounts = conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
        rows = conn.execute(
            f"""
            SELECT t.*, m.name AS month_name, a.name AS account_name
            FROM transactions t
            JOIN months m ON m.id = t.month_id
            JOIN accounts a ON a.id = t.account_id
            {where}
            ORDER BY COALESCE(t.date, '9999-12-31'), t.id
            LIMIT 500
            """,
            values,
        ).fetchall()
    row_html = "".join(
        f"""<tr>
  <td>{esc(row["date"])}</td>
  <td>{esc(row["month_name"])}</td>
  <td>{esc(row["account_name"])}</td>
  <td>{esc(row["label"])}</td>
  <td class="num {'negative' if row["amount"] < 0 else 'positive'}">{money(row["amount"])}</td>
</tr>"""
        for row in rows
    )
    body = f"""<section class="page-title"><h1>Transactions</h1></section>
<form class="filters" method="get">
  <select name="month">{row_options(months, month, "Toutes les périodes")}</select>
  <select name="account">{row_options(accounts, account, "Tous les comptes")}</select>
  <input name="q" value="{esc(search)}" placeholder="Recherche intitulé">
  <button>Filtrer</button>
</form>
<section class="panel">
  <table>
    <thead><tr><th>Date</th><th>Période</th><th>Compte</th><th>Intitulé</th><th class="num">Montant</th></tr></thead>
    <tbody>{row_html}</tbody>
  </table>
</section>"""
    return layout("Transactions", body)


def create(data: dict[str, list[str]]) -> str:
    label = one(data, "label")
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO transaction_labels(name) VALUES (?)", (label,))
        conn.execute(
            """
            INSERT INTO transactions(month_id, account_id, date, label, amount)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                one(data, "month_id"),
                one(data, "account_id"),
                one(data, "date") or None,
                label,
                float(one(data, "amount") or 0),
            ),
        )
    return one(data, "return_to") or "/transactions"
