from __future__ import annotations

from database import db
from web_helpers import esc, layout, one


def page() -> bytes:
    with db() as conn:
        accounts = conn.execute("SELECT * FROM accounts ORDER BY sort_index, name").fetchall()
        labels = conn.execute("SELECT * FROM transaction_labels ORDER BY name LIMIT 300").fetchall()
        budget_rows = conn.execute("SELECT * FROM monthly_budget ORDER BY day, label").fetchall()
    account_rows = "".join(
        account_row(row["id"], row["name"], row["sort_index"], bool(row["show_in_summary"]))
        for row in accounts
    )
    label_rows = "".join(
        settings_row("label", row["id"], row["name"])
        for row in labels
    )
    budget_html = "".join(
        monthly_budget_row(row["id"], row["day"], row["label"], row["amount"])
        for row in budget_rows
    )
    body = f"""<section class="page-title">
  <div>
    <p class="eyebrow">Comptes et intitulés</p>
    <h1>Paramètres</h1>
  </div>
  <span class="save-state" data-save-state>Modifications à valider</span>
</section>
<section class="settings-grid">
  <div class="panel">
    <h2>Comptes</h2>
    <table class="sheet-table settings-table" data-settings-table data-kind="account">
      <thead><tr><th class="row-index-head">#</th><th>Compte</th><th>Synthèse</th><th></th></tr></thead>
      <tbody>{account_rows}</tbody>
      <tfoot><tr><td colspan="4"><button type="button" class="add-row-button" data-add-setting-row>+</button></td></tr></tfoot>
    </table>
  </div>
  <div class="panel">
    <h2>Intitulés</h2>
    <table class="sheet-table settings-table" data-settings-table data-kind="label">
      <thead><tr><th>Intitulé</th><th></th></tr></thead>
      <tbody>{label_rows}</tbody>
      <tfoot><tr><td colspan="2"><button type="button" class="add-row-button" data-add-setting-row>+</button></td></tr></tfoot>
    </table>
  </div>
  <div class="panel wide">
    <h2>Budget mensuel</h2>
    <table class="sheet-table" data-monthly-budget-table>
      <thead><tr><th>Jour</th><th>Intitulé</th><th class="num">Montant</th><th></th></tr></thead>
      <tbody>{budget_html}</tbody>
      <tfoot><tr><td colspan="4"><button type="button" class="add-row-button" data-add-budget-row>+</button></td></tr></tfoot>
    </table>
  </div>
</section>"""
    return layout("Paramètres", body)


def settings_row(kind: str, row_id: int, name: str) -> str:
    return f"""<tr data-settings-row data-kind="{kind}" data-id="{row_id}">
  <td><input value="{esc(name)}" data-setting-value data-original="{esc(name)}" autocomplete="off"></td>
  <td class="row-actions">
    <button type="button" class="row-confirm" data-confirm-setting hidden>V</button>
    <button type="button" class="row-cancel" data-cancel-setting hidden>X</button>
    <button type="button" class="row-delete" data-delete-setting hidden>-</button>
  </td>
</tr>"""


def account_row(row_id: int, name: str, sort_index: int, show_in_summary: bool) -> str:
    checked = " checked" if show_in_summary else ""
    return f"""<tr data-settings-row data-kind="account" data-id="{row_id}" draggable="false">
  <td class="row-index-cell"><button type="button" class="drag-handle" draggable="true" data-account-drag-handle title="Déplacer">↕</button><span class="row-index-value" data-account-index>{sort_index}</span></td>
  <td><input value="{esc(name)}" data-setting-value data-original="{esc(name)}" autocomplete="off"></td>
  <td class="center-cell"><input type="checkbox" data-account-summary data-id="{row_id}"{checked}></td>
  <td class="row-actions">
    <button type="button" class="row-confirm" data-confirm-setting hidden>V</button>
    <button type="button" class="row-cancel" data-cancel-setting hidden>X</button>
    <button type="button" class="row-delete" data-delete-setting hidden>-</button>
  </td>
</tr>"""


def monthly_budget_row(row_id: int, day: int, label: str, amount: float) -> str:
    return f"""<tr data-budget-row data-id="{row_id}">
  <td><input data-budget-field="day" value="{day}" data-original="{day}" inputmode="numeric"></td>
  <td><input data-budget-field="label" value="{esc(label)}" data-original="{esc(label)}"></td>
  <td><input data-budget-field="amount" value="{esc(amount)}" data-original="{esc(amount)}" inputmode="decimal"></td>
  <td class="row-actions">
    <button type="button" class="row-confirm" data-confirm-budget hidden>V</button>
    <button type="button" class="row-cancel" data-cancel-budget hidden>X</button>
    <button type="button" class="row-delete" data-delete-budget hidden>-</button>
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
