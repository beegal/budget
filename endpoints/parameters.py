from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import json

from components.parameters import account_row, empty_monthly_budget_row, monthly_budget_row, recurring_budget_candidates_panel, settings_row
from database import db, ensure_internal_transfer_labels
from i18n import translate
from transfer_labels import is_internal_transfer_label
from web_helpers import format_date, money, one, render_template, settings_tabs_context, user_layout


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
        labels = [row for row in labels if not is_internal_transfer_label(row["name"])]
        budget_rows = conn.execute(
            "SELECT * FROM monthly_budget WHERE user_id = ? ORDER BY day, label",
            (user_id,),
        ).fetchall()
        recurring_candidates = recurring_payment_candidates(conn, user_id)
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
    budget_total_value = sum(float(row["amount"] or 0) for row in budget_rows)
    budget_html = "".join(
        monthly_budget_row(row["id"], row["day"], row["label"], row["amount"])
        for row in budget_rows
    ) or empty_monthly_budget_row()
    recurring_candidates_html = recurring_budget_candidates_panel(recurring_candidates)
    labels_json = json.dumps([row["name"] for row in labels], ensure_ascii=False)
    body = render_template(
        "parameters.html",
        labels_json=labels_json,
        account_rows=account_rows,
        label_rows=label_rows,
        budget_html=budget_html,
        budget_total=money(budget_total_value),
        budget_total_class=amount_class(budget_total_value),
        recurring_candidates_html=recurring_candidates_html,
        **settings_tabs_context(user_id, "parameters"),
    )
    return user_layout(translate("parameters.title"), body, user_id)


def recurring_payment_candidates(conn, user_id: str) -> list[dict[str, object]]:
    existing_keys = {
        (label_group(str(row["label"])).casefold(), int(round(float(row["amount"] or 0) * 100)))
        for row in conn.execute("SELECT label, amount FROM monthly_budget WHERE user_id = ?", (user_id,)).fetchall()
    }
    period_ids = recent_period_ids(conn, user_id, 4)
    if not period_ids:
        return []
    placeholders = ", ".join("?" for _ in period_ids)
    rows = conn.execute(
        f"""
        SELECT t.label,
               t.amount,
               t.date,
               t.period_id
        FROM transactions t
        WHERE t.user_id = ?
          AND t.period_id IN ({placeholders})
          AND t.date IS NOT NULL
          AND t.date <> ''
          AND t.amount <> 0
        ORDER BY t.date, t.id
        """,
        (user_id, *period_ids),
    ).fetchall()
    groups: dict[tuple[str, int], list[object]] = defaultdict(list)
    for row in rows:
        label = str(row["label"] or "").strip()
        group_label = label_group(label)
        if not label or not group_label or is_internal_transfer_label(label):
            continue
        amount = float(row["amount"] or 0)
        amount_cents = int(round(amount * 100))
        group_key = group_label.casefold()
        if amount_cents == 0:
            continue
        groups[(group_key, amount_cents)].append(row)

    candidates = []
    for (group_key, amount_cents), group_rows in groups.items():
        period_ids = {int(row["period_id"]) for row in group_rows if row["period_id"] is not None}
        if len(period_ids) < 3:
            continue
        parsed_dates = [date.fromisoformat(str(row["date"])) for row in group_rows]
        day = round(sum(parsed.day for parsed in parsed_dates) / len(parsed_dates))
        day = max(1, min(31, day))
        label = str(group_rows[0]["label"]).strip()
        amount = amount_cents / 100
        candidates.append(
            {
                "day": day,
                "label": label,
                "amount": money(amount),
                "amount_raw": f"{amount:.2f}",
                "amount_class": "amount-positive" if amount > 0 else "amount-negative",
                "occurrences": len(group_rows),
                "periods": len(period_ids),
                "last_date": format_date(max(parsed_dates).isoformat()),
                "existing": (group_key, amount_cents) in existing_keys,
            }
        )

    return sorted(candidates, key=lambda item: (int(item["day"]), str(item["label"]).casefold(), bool(item["existing"])))[:25]


def recent_period_ids(conn, user_id: str, limit: int) -> list[int]:
    rows = conn.execute(
        """
        SELECT id
        FROM period
        WHERE user_id = ?
        ORDER BY COALESCE(start_date, ''), id
        """,
        (user_id,),
    ).fetchall()
    return [int(row["id"]) for row in rows[-limit:]]


def label_group(label: str) -> str:
    group, separator, _subcategory = label.partition(" - ")
    return group.strip() if separator else label.strip()


def amount_class(amount: float) -> str:
    if amount > 0:
        return "positive"
    if amount < 0:
        return "negative"
    return ""


def create_account(data: dict[str, list[str]], user_id: str) -> str:
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO accounts(user_id, name) VALUES (?, ?)", (user_id, one(data, "name")))
        ensure_internal_transfer_labels(conn, user_id)
    return "/parameters"


def create_label(data: dict[str, list[str]], user_id: str) -> str:
    name = one(data, "name")
    if is_internal_transfer_label(name):
        return "/parameters"
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, name))
    return "/parameters"
