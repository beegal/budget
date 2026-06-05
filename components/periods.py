from __future__ import annotations

import sqlite3

from components.common import icon
from web_helpers import format_date, money, period_label


def period_card_view(row: sqlite3.Row, warning: str | None) -> dict[str, object]:
    transaction_count = int(row["transaction_count"] or 0)
    budget_count = int(row["budget_count"] or 0)
    can_delete = transaction_count == 0 and budget_count == 0
    delete_title = (
        "Supprimer la période"
        if can_delete
        else f"Supprimer {transaction_count} transaction(s) et {budget_count} entrée(s) de budget avant de supprimer cette période."
    )
    start_display = format_date(row["start_date"] or "")
    end_date = format_date(row["end_date"]) if row["end_date"] else "en cours"
    return {
        "id": row["id"],
        "name": row["name"],
        "warning": warning or "",
        "warning_class": " period-overlap" if warning else "",
        "can_delete": can_delete,
        "delete_title": delete_title,
        "period_label": period_label(row),
        "start_display": start_display,
        "end_date": end_date,
        "income": money(row["income"]),
        "expense": money(row["expense"]),
        "net": money(row["net"]),
        "trash_icon": icon("trash"),
    }
