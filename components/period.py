from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from components.common import icon, label_picker, row_action_buttons
from config import NUMBER_DECIMALS
from web_helpers import esc, format_date, format_number, money


def period_tabs(
    period_id: int,
    active: str,
    visible_accounts: list[sqlite3.Row],
    hidden_accounts: list[sqlite3.Row],
) -> str:
    tabs = [simple_tab("Synthèse", f"/period/{period_id}", active == "overview")]
    tabs.append(simple_tab("Budget", f"/period/{period_id}?account=budget", active == "budget"))
    tabs.extend(account_tab_link(period_id, active, account) for account in visible_accounts)
    tabs.append(hidden_account_tabs(period_id, hidden_accounts))
    return "".join(tabs)


def simple_tab(label: str, href: str, selected: bool) -> str:
    active_class = "active" if selected else ""
    return f'<a class="tab {active_class}" href="{esc(href)}">{esc(label)}</a>'


def overview(
    period_id: int,
    summary_rows: list[sqlite3.Row],
    balance_rows: list[sqlite3.Row],
    transfer_rows: list[sqlite3.Row],
) -> str:
    non_transfer_rows = [row for row in summary_rows if not is_transfer_group(str(row["label_group"]))]
    total_income = sum(float(row["income"] or 0) for row in non_transfer_rows)
    total_expense = sum(float(row["expense"] or 0) for row in non_transfer_rows)
    total_net = sum(float(row["net"] or 0) for row in non_transfer_rows)
    transfer_total = sum(float(row["amount"] or 0) for row in transfer_rows)
    balance_html = "".join(balance_row(period_id, row) for row in balance_rows)
    summary_html = "".join(summary_row(row) for row in non_transfer_rows)
    transfer_html = "".join(transfer_row(row) for row in transfer_rows)
    transfer_total_html = (
        f"""<tfoot>
  <tr class="total-row">
    <th colspan="3">Total</th>
    <th class="num {balance_tone(transfer_total)}">{money(transfer_total)}</th>
  </tr>
</tfoot>"""
        if transfer_rows
        else ""
    )
    total_html = (
        f"""<tfoot>
  <tr class="total-row">
    <th>Total</th>
    <th class="num positive">{money(total_income)}</th>
    <th class="num negative">{money(total_expense)}</th>
    <th class="num {balance_tone(total_net)}">{money(total_net)}</th>
  </tr>
</tfoot>"""
        if non_transfer_rows
        else ""
    )
    return f"""<section class="two-col">
  <div class="panel">
    <h2>Soldes par compte</h2>
    <table class="overview-table balance-table">
      <thead><tr><th>Compte</th><th class="num">Début</th><th class="num">Actuel</th></tr></thead>
      <tbody>{balance_html or "<tr><td colspan='3'>Aucun solde saisi.</td></tr>"}</tbody>
    </table>
    <h2 class="subsection-title">Transferts</h2>
    <table class="overview-table transfer-table">
      <thead><tr><th>Date</th><th>Compte</th><th>Intitulé</th><th class="num">Montant</th></tr></thead>
      <tbody>{transfer_html or "<tr><td colspan='4'>Aucun transfert.</td></tr>"}</tbody>
      {transfer_total_html}
    </table>
  </div>
  <div class="panel">
    <h2>Entrées / sorties par intitulé</h2>
    <table class="overview-table">
      <thead><tr><th>Intitulé</th><th class="num">Entrées</th><th class="num">Sorties</th><th class="num">Net</th></tr></thead>
      <tbody>{summary_html or "<tr><td colspan='4'>Aucune transaction.</td></tr>"}</tbody>
      {total_html}
    </table>
  </div>
</section>"""


def account_tab_link(period_id: int, active: str, account: sqlite3.Row) -> str:
    transaction_count = int(account["transaction_count"] or 0)
    current_balance = float(account["current"] or 0)
    balance_class = "positive" if current_balance > 0 else "negative" if current_balance < 0 else "neutral"
    can_hide = transaction_count == 0
    hide_disabled = "" if can_hide else " disabled"
    hide_title = (
        "Retirer ce compte des onglets"
        if can_hide
        else f"Impossible de supprimer le compte car il contient {transaction_count} transaction(s)"
    )
    tooltip = "\n".join(
        [
            f"Solde: {money(account['current']).replace(' EUR', ' euro')}",
            f"{transaction_count} transaction(s) pour un total de {money(account['transaction_total']).replace(' EUR', ' euro')}",
        ]
    )
    selected = "active" if active == str(account["id"]) else ""
    return f"""<span class="account-tab-wrapper">
  <a class="tab account-tab {selected}" href="/period/{period_id}?account={account["id"]}">
    <span>{esc(account["name"])}</span>
    <span class="tab-info tab-info-{balance_class}" title="{esc(tooltip)}" aria-label="{esc(tooltip)}">i</span>
  </a>
  <button type="button" class="tab-account-hide" data-hide-account-tab data-period-id="{period_id}" data-account-id="{account["id"]}" title="{esc(hide_title)}" aria-label="{esc(hide_title)}"{hide_disabled}>{icon("trash")}</button>
</span>"""


def hidden_account_tabs(period_id: int, hidden_accounts: list[sqlite3.Row]) -> str:
    if not hidden_accounts:
        return ""
    hidden_account_links = "".join(
        f'<a href="/period/{period_id}?account={account["id"]}">{esc(account["name"])}</a>'
        for account in hidden_accounts
    )
    return f"""<span class="tab-add-wrapper">
  <button type="button" class="tab tab-add icon-button" data-tab-add-toggle title="Ajouter un compte" aria-label="Ajouter un compte">{icon("plus")}</button>
  <span class="tab-add-menu" data-tab-add-menu hidden>{hidden_account_links}</span>
</span>"""


def balance_row(period_id: int, row: sqlite3.Row) -> str:
    return f"""<tr>
  <td>{esc(row["name"])}</td>
  <td class="num {balance_tone(row["opening"])}" data-account-balance-cell data-period-id="{period_id}" data-account-id="{row["account_id"]}" data-original="{esc(balance_raw(row["opening"]))}">
    <button type="button" class="balance-display {balance_defined_class(row["opening"])}" data-balance-display>{esc(balance_display(row["opening"]))}</button>
    <span class="balance-edit" data-balance-edit hidden>
      <input class="num" data-balance-input value="{esc(balance_raw(row["opening"]))}" inputmode="decimal">
      <button type="button" class="row-confirm" data-confirm-account-balance>V</button>
      <button type="button" class="row-cancel" data-cancel-account-balance>X</button>
    </span>
  </td>
  <td class="num {balance_tone(row["current"])} {balance_defined_class(row["current"])}" data-account-current-cell>{esc(balance_money_display(row["current"]))}</td>
</tr>"""


def summary_row(row: sqlite3.Row) -> str:
    return f"""<tr>
  <td>{esc(row["label_group"])}</td>
  <td class="num positive">{money_or_empty(row["income"])}</td>
  <td class="num negative">{money_or_empty(row["expense"])}</td>
  <td class="num {balance_tone(row["net"])}">{money_or_empty(row["net"])}</td>
</tr>"""


def transfer_row(row: sqlite3.Row) -> str:
    return f"""<tr>
  <td>{esc(row["date"])}</td>
  <td>{esc(row["account_name"])}</td>
  <td>{esc(row["label"])}</td>
  <td class="num {balance_tone(row["amount"])}">{money(row["amount"])}</td>
</tr>"""


def balance_raw(value: object) -> str:
    return "" if value is None else format_number(value)


def money_or_empty(value: object) -> str:
    return "" if abs(float(value or 0)) < 0.005 else money(value)


def balance_display(value: object) -> str:
    return "non défini" if value is None else format_number(value)


def balance_money_display(value: object) -> str:
    return "non défini" if value is None else money(value)


def balance_defined_class(value: object) -> str:
    return "balance-undefined" if value is None else ""


def balance_tone(value: object) -> str:
    if value is None:
        return ""
    amount = float(value or 0)
    if amount > 0:
        return "positive"
    if amount < 0:
        return "negative"
    return ""


def budget_tab(period_id: int, rows: list[sqlite3.Row], accounts: list[sqlite3.Row], labels: list[sqlite3.Row]) -> str:
    account_buttons = "".join(
        f'<button type="button" class="budget-account-choice" data-budget-account="{account["id"]}">{esc(account["name"])}</button>'
        for account in accounts
    )
    labels_json = json.dumps([row["name"] for row in labels], ensure_ascii=False)
    body_rows = "".join(budget_schedule_row(index, row, account_buttons) for index, row in enumerate(rows, start=1))
    return f"""<script>window.BUDGET_LABELS = {labels_json};</script>
<section class="panel sheet-panel">
  <div class="section-head">
    <h2>Budget</h2>
    <span class="save-state" data-save-state></span>
  </div>
  <table class="sheet-table budget-schedule-table" data-budget-schedule-table data-period-id="{period_id}">
    <thead><tr><th class="row-index-head">#</th><th>Intitulé</th><th class="num">Montant</th><th>Status</th><th></th></tr></thead>
    <tbody>{body_rows or "<tr><td colspan='5'>Aucune entrée planifiée.</td></tr>"}</tbody>
    <tfoot>
      <tr class="table-actions-row">
        <td colspan="4"></td>
        <td class="row-actions table-footer-actions">
          <button type="button" class="row-confirm icon-button" data-add-budget-schedule title="Ajouter une entrée budget" aria-label="Ajouter une entrée budget">{icon("plus")}</button>
          <button type="button" class="row-delete icon-button" data-budget-schedule-clear title="Supprimer toutes les entrées budget" aria-label="Supprimer toutes les entrées budget">{icon("clear-list")}</button>
        </td>
      </tr>
    </tfoot>
  </table>
</section>"""


def budget_schedule_row(index: int, row: sqlite3.Row, account_buttons: str) -> str:
    status = str(row["status"])
    status_label = {"scheduled": "Planifié", "found": "Trouvé", "cancel": "Annulé"}.get(status, status)
    actions = budget_schedule_actions(status)
    return f"""<tr class="budget-schedule-row budget-status-{esc(status)}" data-budget-schedule-id="{row["id"]}">
  <td class="row-index-cell"><span class="row-index-value">{index}</span></td>
  <td>{esc(row["label"])}</td>
  <td class="num">{money(row["amount"])}</td>
  <td><span class="budget-status-pill" data-budget-status>{esc(status_label)}</span></td>
  <td class="row-actions budget-actions">
    {actions}
    <div class="budget-account-list" data-budget-account-list hidden>{account_buttons}</div>
    <div class="budget-created" data-budget-created hidden></div>
  </td>
</tr>"""


def budget_schedule_actions(status: str) -> str:
    if status != "scheduled":
        return ""
    return f"""<button type="button" class="row-cancel icon-button" data-budget-schedule-cancel title="Annuler cette entrée prévue" aria-label="Annuler cette entrée prévue">{icon("ban")}</button>
    <button type="button" class="row-confirm icon-button" data-budget-schedule-confirm title="Envoyer vers un compte" aria-label="Envoyer vers un compte">{icon("send")}</button>"""


def is_transfer_group(label_group: str) -> bool:
    normalized = label_group.strip().lower()
    return normalized in {"virement interne", "transfert", "transferts", "transfert interne", "transferts internes"}


def account_tab(
    period_id: int,
    period: sqlite3.Row,
    account: sqlite3.Row | None,
    transactions: list[sqlite3.Row],
    labels: list[sqlite3.Row],
) -> str:
    if account is None:
        return "<section class='panel'><h2>Compte introuvable</h2></section>"
    opening_balance = account["opening"]
    running_balance = float(opening_balance or 0)
    operations_total = 0.0
    rows_html = []
    for row in transactions:
        balance_title = (
            f"Solde: {money(running_balance)}"
            if opening_balance is not None
            else "Solde: non défini"
        )
        rows_html.append(transaction_row(row, period, balance_title))
        amount = float(row["amount"] or 0)
        operations_total += amount
        running_balance += amount
    rows = "".join(rows_html)
    current_balance = (
        f"Solde actuel : {money(running_balance)} - Total opérations : {money(operations_total)}"
        if opening_balance is not None
        else f"Solde actuel : non défini - Total opérations : {money(operations_total)}"
    )
    labels_json = json.dumps([row["name"] for row in labels], ensure_ascii=False)
    opening_data = "" if opening_balance is None else format_number(opening_balance)
    return f"""<script>window.BUDGET_LABELS = {labels_json};</script>
<section class="panel sheet-panel">
  <div class="section-head">
    <h2>{esc(account["name"])}</h2>
    <span class="save-state" data-save-state></span>
  </div>
  <table class="sheet-table transaction-sheet-table" data-transaction-table data-period-id="{period_id}" data-account-id="{account["id"]}" data-opening-balance="{esc(opening_data)}" data-number-decimals="{NUMBER_DECIMALS}">
    <colgroup>
      <col class="transaction-index-col">
      <col class="transaction-date-col">
      <col class="transaction-label-col">
      <col class="transaction-amount-col">
      <col class="transaction-comment-col">
      <col class="transaction-actions-col">
    </colgroup>
    <thead><tr><th class="row-index-head">#</th><th>Date</th><th>Intitulé</th><th class="num">Montant</th><th>Commentaire</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
    <tfoot>
      <tr class="transaction-balance-row">
        <td colspan="6" data-current-balance-text>{esc(current_balance)}</td>
      </tr>
      <tr class="table-actions-row">
        <td colspan="5"></td>
        <td class="row-actions table-footer-actions">
          <button type="button" class="row-confirm icon-button" data-add-row title="Ajouter une ligne" aria-label="Ajouter une ligne">{icon("plus")}</button>
          <button type="button" class="row-delete icon-button" data-remove-all title="Supprimer toutes les lignes" aria-label="Supprimer toutes les lignes">{icon("clear-list")}</button>
          <a class="button ghost import-button icon-button" href="/period/{period_id}/import?account={account["id"]}" title="Importer CSV" aria-label="Importer CSV">{icon("upload")}</a>
        </td>
      </tr>
    </tfoot>
  </table>
</section>"""


def transaction_row(row: sqlite3.Row, period: sqlite3.Row, balance_title: str) -> str:
    warning_html = transaction_period_warning(row, period)
    return f"""<tr class="{transaction_amount_class(row["amount"])}" data-transaction-id="{row["id"]}" data-sort-date="{esc(row["date"] or "")}">
  <td class="row-index-cell"><button type="button" class="drag-handle" draggable="true" data-drag-handle title="Déplacer">↕</button><span class="row-index-value" data-field="sort_index" data-original="{esc(row["sort_index"])}" title="{esc(balance_title)}" aria-label="{esc(balance_title)}">{esc(row["sort_index"])}</span></td>
  <td class="editable" contenteditable="true" data-save="transaction" data-field="date" data-original="{esc(format_date(row["date"]))}">{esc(format_date(row["date"]))}</td>
  <td>{label_picker(row["label"], 'data-save="transaction" data-field="label"')}</td>
  <td class="editable num" contenteditable="true" data-save="transaction" data-field="amount" data-original="{esc(format_number(row["amount"]))}">{esc(format_number(row["amount"]))}</td>
  <td class="editable" contenteditable="true" data-save="transaction" data-field="comment" data-original="{esc(row["comment"])}">{esc(row["comment"])}</td>
  <td class="row-actions">
    {warning_html}
    {row_action_buttons("row")}
  </td>
</tr>"""


def transaction_amount_class(amount: float) -> str:
    if amount > 0:
        return "amount-positive"
    if amount < 0:
        return "amount-negative"
    return ""


def transaction_period_warning(row: sqlite3.Row, period: sqlite3.Row) -> str:
    reason = transaction_period_warning_reason(row, period)
    if not reason:
        return ""
    return (
        f'<span class="transaction-warning-icon icon-button" title="{esc(reason)}" '
        f'aria-label="{esc(reason)}">{icon("warning")}</span>'
    )


def transaction_period_warning_reason(row: sqlite3.Row, period: sqlite3.Row) -> str:
    tx_date_raw = row["date"]
    if not tx_date_raw:
        return ""
    try:
        tx_date = datetime.strptime(str(tx_date_raw), "%Y-%m-%d").date()
        start_date = datetime.strptime(str(period["start_date"]), "%Y-%m-%d").date() if period["start_date"] else None
        end_date = datetime.strptime(str(period["end_date"]), "%Y-%m-%d").date() if period["end_date"] else None
    except ValueError:
        return "La date de cette transaction n'est pas reconnue."
    if start_date and tx_date < start_date:
        return f"Date hors période: {format_date(tx_date_raw)} est avant le début {format_date(period['start_date'])}."
    if end_date and tx_date > end_date:
        return f"Date hors période: {format_date(tx_date_raw)} est après la fin {format_date(period['end_date'])}."
    return ""
