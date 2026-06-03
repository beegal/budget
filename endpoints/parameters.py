from __future__ import annotations

import json

from database import db
from web_helpers import esc, label_picker, layout, one, row_action_buttons


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
    body = f"""<section class="page-title">
  <div>
    <p class="eyebrow">Comptes et intitulés</p>
    <h1>Paramètres</h1>
  </div>
  <span class="save-state" data-save-state>Modifications à valider</span>
</section>
<script>window.BUDGET_LABELS = {labels_json};</script>
<section class="settings-grid">
  <div class="panel">
    <h2>Comptes</h2>
    <div class="settings-table-scroll">
    <table class="sheet-table settings-table limited-rows account-settings-table" data-settings-table data-kind="account">
      <colgroup><col class="account-index-col"><col><col class="account-summary-col"><col class="account-empty-col"><col class="actions-col"></colgroup>
      <thead><tr><th class="row-index-head">#</th><th>Compte</th><th>Synthèse</th><th>Visible si vide</th><th></th></tr></thead>
      <tbody>{account_rows}</tbody>
      <tfoot><tr><td></td><td></td><td></td><td></td><td class="row-actions"><button type="button" class="add-row-button" data-add-setting-row>+</button></td></tr></tfoot>
    </table>
    </div>
  </div>
  <div class="panel">
    <h2>Intitulés</h2>
    <div class="settings-table-scroll">
    <table class="sheet-table settings-table limited-rows label-settings-table" data-settings-table data-kind="label">
      <colgroup><col><col class="actions-col"></colgroup>
      <thead><tr><th>Intitulé</th><th></th></tr></thead>
      <tbody>{label_rows}</tbody>
      <tfoot><tr><td></td><td class="row-actions"><button type="button" class="add-row-button" data-add-setting-row>+</button></td></tr></tfoot>
    </table>
    </div>
  </div>
  <div class="panel wide">
    <h2>Budget mensuel</h2>
    <div class="settings-table-scroll">
    <table class="sheet-table limited-rows monthly-budget-table" data-monthly-budget-table>
      <colgroup><col class="budget-day-col"><col><col class="budget-amount-col"><col class="actions-col"></colgroup>
      <thead><tr><th>Jour</th><th>Intitulé</th><th class="num">Montant</th><th></th></tr></thead>
      <tbody>{budget_html}</tbody>
      <tfoot><tr><td></td><td></td><td></td><td class="row-actions"><button type="button" class="add-row-button" data-add-budget-row>+</button></td></tr></tfoot>
    </table>
    </div>
  </div>
</section>"""
    return layout("Paramètres", body)


def settings_row(kind: str, row_id: int, name: str) -> str:
    return f"""<tr data-settings-row data-kind="{kind}" data-id="{row_id}">
  <td><input value="{esc(name)}" data-setting-value data-original="{esc(name)}" autocomplete="off"></td>
  <td class="row-actions">
    {row_action_buttons("setting")}
  </td>
</tr>"""


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
    return f"""<tr class="{amount_class}" data-budget-row data-id="{row_id}">
  <td><input data-budget-field="day" value="{day}" data-original="{day}" inputmode="numeric"></td>
  <td>{label_picker(label, 'data-budget-field="label"')}</td>
  <td><input data-budget-field="amount" value="{esc(amount)}" data-original="{esc(amount)}" inputmode="decimal"></td>
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
