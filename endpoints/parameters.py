from __future__ import annotations

import json

from components.parameters import account_row, empty_monthly_budget_row, monthly_budget_row, settings_row
from database import db
from web_helpers import layout, one, render_template


def page() -> bytes:
    with db() as conn:
        accounts = conn.execute("SELECT * FROM accounts ORDER BY sort_index, name").fetchall()
        labels = conn.execute("SELECT * FROM transaction_labels ORDER BY name LIMIT 300").fetchall()
        budget_rows = conn.execute("SELECT * FROM monthly_budget ORDER BY day, label").fetchall()
    account_rows = "".join(
        account_row(
            row["id"],
            row["name"],
            row["sort_index"],
            bool(row["show_in_summary"]),
            bool(row["visible_if_empty"]),
        )
        for row in accounts
    )
    label_rows = "".join(
        settings_row("label", row["id"], row["name"])
        for row in labels
    )
    budget_html = "".join(
        monthly_budget_row(row["id"], row["day"], row["label"], row["amount"])
        for row in budget_rows
    ) or empty_monthly_budget_row()
    labels_json = json.dumps([row["name"] for row in labels], ensure_ascii=False)
    body = render_template(
        "parameters.html",
        labels_json=labels_json,
        account_rows=account_rows,
        label_rows=label_rows,
        budget_html=budget_html,
    )
    return layout("Paramètres", body)


def create_account(data: dict[str, list[str]]) -> str:
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO accounts(name) VALUES (?)", (one(data, "name"),))
    return "/parameters"


def create_label(data: dict[str, list[str]]) -> str:
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO transaction_labels(name) VALUES (?)", (one(data, "name"),))
    return "/parameters"
