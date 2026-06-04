from __future__ import annotations

import json

from database import db
from web_helpers import esc, format_number, label_picker, layout, one, render_template, row_action_buttons


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
    ) or """<tr data-empty-budget-row>
  <td colspan="3" class="muted">Aucune entrée.</td>
  <td class="row-actions"></td>
</tr>"""
    labels_json = json.dumps([row["name"] for row in labels], ensure_ascii=False)
    body = render_template(
        "parameters.html",
        labels_json=labels_json,
        account_rows=account_rows,
        label_rows=label_rows,
        budget_html=budget_html,
    )
    return layout("Paramètres", body)


def settings_row(kind: str, row_id: int, name: str) -> str:
    if kind == "label":
        group_name, subcategory = split_label_name(name)
        return f"""<tr data-settings-row data-kind="{kind}" data-id="{row_id}">
  <td><input value="{esc(group_name)}" data-setting-value data-setting-part="group" data-original="{esc(group_name)}" autocomplete="off"></td>
  <td><input value="{esc(subcategory)}" data-setting-value data-setting-part="subcategory" data-original="{esc(subcategory)}" autocomplete="off"></td>
  <td class="row-actions">
    {row_action_buttons("setting")}
  </td>
</tr>"""
    return f"""<tr data-settings-row data-kind="{kind}" data-id="{row_id}">
  <td><input value="{esc(name)}" data-setting-value data-original="{esc(name)}" autocomplete="off"></td>
  <td class="row-actions">
    {row_action_buttons("setting")}
  </td>
</tr>"""


def split_label_name(name: str) -> tuple[str, str]:
    group_name, separator, subcategory = name.partition(" - ")
    if not separator:
        return name, ""
    return group_name, subcategory


def account_row(row_id: int, name: str, sort_index: int, show_in_summary: bool, visible_if_empty: bool) -> str:
    summary_checked = " checked" if show_in_summary else ""
    empty_checked = " checked" if visible_if_empty else ""
    return f"""<tr data-settings-row data-kind="account" data-id="{row_id}" draggable="false">
  <td class="row-index-cell"><button type="button" class="drag-handle" draggable="true" data-account-drag-handle title="Déplacer">↕</button><span class="row-index-value" data-account-index>{sort_index}</span></td>
  <td><input value="{esc(name)}" data-setting-value data-original="{esc(name)}" autocomplete="off"></td>
  <td class="center-cell"><input type="checkbox" data-account-summary data-id="{row_id}"{summary_checked}></td>
  <td class="center-cell"><input type="checkbox" data-account-visible-if-empty data-id="{row_id}"{empty_checked}></td>
  <td class="row-actions">
    {row_action_buttons("setting")}
  </td>
</tr>"""


def monthly_budget_row(row_id: int, day: int, label: str, amount: float) -> str:
    amount_class = "amount-positive" if amount > 0 else "amount-negative" if amount < 0 else ""
    amount_display = format_number(amount)
    return f"""<tr class="{amount_class}" data-budget-row data-id="{row_id}">
  <td><input data-budget-field="day" value="{day}" data-original="{day}" inputmode="numeric"></td>
  <td>{label_picker(label, 'data-budget-field="label"')}</td>
  <td><input data-budget-field="amount" value="{esc(amount_display)}" data-original="{esc(amount_display)}" inputmode="decimal"></td>
  <td class="row-actions">
    {row_action_buttons("budget")}
  </td>
</tr>"""


def create_account(data: dict[str, list[str]]) -> str:
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO accounts(name) VALUES (?)", (one(data, "name"),))
    return "/parameters"


def create_label(data: dict[str, list[str]]) -> str:
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO transaction_labels(name) VALUES (?)", (one(data, "name"),))
    return "/parameters"
