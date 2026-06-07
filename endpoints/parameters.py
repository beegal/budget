from __future__ import annotations

import json

from components.parameters import account_row, empty_monthly_budget_row, monthly_budget_row, settings_row
from database import db
from i18n import translate
from web_helpers import one, render_template, user_layout


def page(user_id: str) -> bytes:
    with db() as conn:
        accounts = conn.execute(
            """
            SELECT a.*,
                   COUNT(t.id) AS transaction_count
            FROM accounts a
            LEFT JOIN transactions t ON t.account_id = a.id AND t.user_id = ?
            WHERE a.user_id = ?
            GROUP BY a.id
            ORDER BY a.sort_index, a.name
            """,
            (user_id, user_id),
        ).fetchall()
        labels = conn.execute(
            "SELECT * FROM transaction_labels WHERE user_id = ? ORDER BY name LIMIT 300",
            (user_id,),
        ).fetchall()
        budget_rows = conn.execute(
            "SELECT * FROM monthly_budget WHERE user_id = ? ORDER BY day, label",
            (user_id,),
        ).fetchall()
    account_rows = "".join(
        account_row(
            row["id"],
            row["name"],
            row["sort_index"],
            bool(row["show_in_summary"]),
            bool(row["visible_if_empty"]),
            int(row["transaction_count"] or 0),
            accounts,
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
    return user_layout(translate("parameters.title"), body, user_id)


def create_account(data: dict[str, list[str]], user_id: str) -> str:
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO accounts(user_id, name) VALUES (?, ?)", (user_id, one(data, "name")))
    return "/parameters"


def create_label(data: dict[str, list[str]], user_id: str) -> str:
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, one(data, "name")))
    return "/parameters"
