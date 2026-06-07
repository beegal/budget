from __future__ import annotations

import sqlite3

from web_helpers import format_date, money


def transaction_view_rows(rows: list[sqlite3.Row]) -> list[dict[str, str]]:
    return [transaction_view_row(row) for row in rows]


def transaction_view_row(row: sqlite3.Row) -> dict[str, str]:
    amount_class = "negative" if row["amount"] < 0 else "positive"
    return {
        "date": format_date(row["date"]),
        "period_name": row["period_name"],
        "account_name": row["account_name"],
        "label": row["label"],
        "comment": row["comment"] or "",
        "amount": money(row["amount"]),
        "amount_class": amount_class,
    }
