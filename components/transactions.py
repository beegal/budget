from __future__ import annotations

import sqlite3

from web_helpers import esc, format_date, money


def transaction_rows(rows: list[sqlite3.Row]) -> str:
    return "".join(transaction_row(row) for row in rows)


def transaction_row(row: sqlite3.Row) -> str:
    amount_class = "negative" if row["amount"] < 0 else "positive"
    return f"""<tr>
  <td>{esc(format_date(row["date"]))}</td>
  <td>{esc(row["period_name"])}</td>
  <td>{esc(row["account_name"])}</td>
  <td>{esc(row["label"])}</td>
  <td class="num {amount_class}">{money(row["amount"])}</td>
</tr>"""
