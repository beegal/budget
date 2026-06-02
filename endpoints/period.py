from __future__ import annotations

import json
import sqlite3
from urllib.parse import parse_qs

from database import db
from web_helpers import esc, layout, money, period_label


def page(period_id: int, query: str) -> bytes:
    params = parse_qs(query)
    active = params.get("account", ["overview"])[0]
    with db() as conn:
        period = conn.execute("SELECT * FROM months WHERE id = ?", (period_id,)).fetchone()
        if period is None:
            return layout("Introuvable", "<section class='panel'><h1>Période introuvable</h1></section>")
        accounts = conn.execute("SELECT id, name FROM accounts ORDER BY sort_index, name").fetchall()
        labels = conn.execute("SELECT id, name FROM transaction_labels ORDER BY name").fetchall()

        summary_rows = conn.execute(
            """
            WITH grouped AS (
                SELECT
                    CASE
                        WHEN INSTR(t.label, '-') > 0 THEN TRIM(SUBSTR(t.label, 1, INSTR(t.label, '-') - 1))
                        ELSE TRIM(t.label)
                    END AS label_group,
                    t.amount
                FROM transactions t
                WHERE t.month_id = ?
            )
            SELECT grouped.label_group,
                   COALESCE(SUM(CASE WHEN grouped.amount > 0 THEN grouped.amount END), 0) AS income,
                   COALESCE(SUM(CASE WHEN grouped.amount < 0 THEN grouped.amount END), 0) AS expense,
                   COALESCE(SUM(grouped.amount), 0) AS net
            FROM grouped
            GROUP BY grouped.label_group
            ORDER BY grouped.label_group
            """,
            (period_id,),
        ).fetchall()
        balance_rows = conn.execute(
            """
            SELECT a.id AS account_id, a.name, ab.opening, ab.current
            FROM account_balances ab
            JOIN accounts a ON a.id = ab.account_id
            WHERE ab.month_id = ? AND a.show_in_summary = 1
            ORDER BY a.sort_index, a.name
            """,
            (period_id,),
        ).fetchall()
        selected_account = None
        account_transactions: list[sqlite3.Row] = []
        budget_rows = []
        if active == "budget":
            budget_rows = conn.execute(
                """
                SELECT *
                FROM budget_schedule
                WHERE month_id = ?
                ORDER BY id
                """,
                (period_id,),
            ).fetchall()
        elif active != "overview":
            selected_account = conn.execute("SELECT * FROM accounts WHERE id = ?", (active,)).fetchone()
            account_transactions = conn.execute(
                """
                SELECT t.*, a.name AS account_name
                FROM transactions t
                JOIN accounts a ON a.id = t.account_id
                WHERE t.month_id = ? AND t.account_id = ?
                ORDER BY COALESCE(t.date, '9999-12-31'), t.sort_index, t.id
                """,
                (period_id, active),
            ).fetchall()

    tabs = [f'<a class="tab {"active" if active == "overview" else ""}" href="/period/{period_id}">Synthèse</a>']
    tabs.append(f'<a class="tab {"active" if active == "budget" else ""}" href="/period/{period_id}?account=budget">Budget</a>')
    tabs.extend(
        f'<a class="tab {"active" if active == str(account["id"]) else ""}" href="/period/{period_id}?account={account["id"]}">{esc(account["name"])}</a>'
        for account in accounts
    )
    if active == "overview":
        content = overview(period_id, summary_rows, balance_rows)
    elif active == "budget":
        content = budget_tab(period_id, budget_rows, accounts)
    else:
        content = account_tab(period_id, selected_account, account_transactions, labels)
    body = f"""<section class="page-title">
  <div>
    <p class="eyebrow">{esc(period_label(period))}</p>
    <h1>{esc(period["name"])}</h1>
  </div>
  <a class="button ghost" href="/">Toutes les périodes</a>
</section>
<nav class="tabs">{"".join(tabs)}</nav>
{content}"""
    return layout(str(period["name"]), body)


def overview(period_id: int, summary_rows: list[sqlite3.Row], balance_rows: list[sqlite3.Row]) -> str:
    total_income = sum(float(row["income"] or 0) for row in summary_rows)
    total_expense = sum(float(row["expense"] or 0) for row in summary_rows)
    total_net = sum(float(row["net"] or 0) for row in summary_rows)
    transfer_total = sum(float(row["net"] or 0) for row in summary_rows if is_transfer_group(str(row["label_group"])))
    transfer_class = "negative" if abs(transfer_total) >= 0.005 else "positive"
    balance_html = "".join(
        f"""<tr>
  <td>{esc(row["name"])}</td>
  <td class="editable num" contenteditable="true" data-save="account-balance" data-month-id="{period_id}" data-account-id="{row["account_id"]}" data-field="opening" data-original="{esc(row["opening"])}">{esc(row["opening"])}</td>
  <td class="num">{money(row["current"])}</td>
</tr>"""
        for row in balance_rows
    )
    summary_html = "".join(
        f"""<tr>
  <td>{esc(row["label_group"])}</td>
  <td class="num positive">{money(row["income"])}</td>
  <td class="num negative">{money(row["expense"])}</td>
  <td class="num">{money(row["net"])}</td>
</tr>"""
        for row in summary_rows
    )
    total_html = (
        f"""<tfoot>
  <tr class="total-row">
    <th>Total</th>
    <th class="num positive">{money(total_income)}</th>
    <th class="num negative">{money(total_expense)}</th>
    <th class="num">{money(total_net)}</th>
  </tr>
</tfoot>"""
        if summary_rows
        else ""
    )
    return f"""<section class="two-col">
  <div class="panel">
    <h2>Soldes par compte</h2>
    <table>
      <thead><tr><th>Compte</th><th class="num">Début</th><th class="num">Actuel</th></tr></thead>
      <tbody>{balance_html or "<tr><td colspan='3'>Aucun solde saisi.</td></tr>"}</tbody>
    </table>
    <div class="balance-check">
      <span>Somme des transferts</span>
      <strong class="{transfer_class}">{money(transfer_total)}</strong>
    </div>
  </div>
  <div class="panel">
    <h2>Entrées / sorties par intitulé</h2>
    <table>
      <thead><tr><th>Intitulé</th><th class="num">Entrées</th><th class="num">Sorties</th><th class="num">Net</th></tr></thead>
      <tbody>{summary_html or "<tr><td colspan='4'>Aucune transaction.</td></tr>"}</tbody>
      {total_html}
    </table>
  </div>
</section>"""


def budget_tab(period_id: int, rows: list[sqlite3.Row], accounts: list[sqlite3.Row]) -> str:
    account_buttons = "".join(
        f'<button type="button" class="budget-account-choice" data-budget-account="{account["id"]}">{esc(account["name"])}</button>'
        for account in accounts
    )
    body_rows = "".join(budget_schedule_row(row, account_buttons) for row in rows)
    return f"""<section class="panel sheet-panel">
  <div class="section-head">
    <h2>Budget</h2>
    <span class="muted">Paiements prévus pour cette période</span>
  </div>
  <table class="sheet-table budget-schedule-table" data-budget-schedule-table data-month-id="{period_id}">
    <thead><tr><th>Intitulé</th><th class="num">Montant</th><th>Status</th><th></th></tr></thead>
    <tbody>{body_rows or "<tr><td colspan='4'>Aucune entrée planifiée.</td></tr>"}</tbody>
  </table>
</section>"""


def budget_schedule_row(row: sqlite3.Row, account_buttons: str) -> str:
    status = str(row["status"])
    status_label = {"scheduled": "Planifié", "found": "Trouvé", "cancel": "Annulé"}.get(status, status)
    actions = budget_schedule_actions(status)
    return f"""<tr class="budget-schedule-row budget-status-{esc(status)}" data-budget-schedule-id="{row["id"]}">
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
    return f"""<span class="icon-status" title="Planifié" aria-label="Planifié">{icon("hourglass")}</span>
    <button type="button" class="row-cancel icon-button" data-budget-schedule-cancel title="Annuler" aria-label="Annuler">{icon("x")}</button>
    <button type="button" class="row-confirm icon-button" data-budget-schedule-confirm title="Instancier" aria-label="Instancier">{icon("check")}</button>"""


def is_transfer_group(label_group: str) -> bool:
    normalized = label_group.strip().lower()
    return normalized in {"virement interne", "transfert", "transferts", "transfert interne", "transferts internes"}


def account_tab(
    period_id: int,
    account: sqlite3.Row | None,
    transactions: list[sqlite3.Row],
    labels: list[sqlite3.Row],
) -> str:
    if account is None:
        return "<section class='panel'><h2>Compte introuvable</h2></section>"
    rows = "".join(
        f"""<tr class="{transaction_amount_class(row["amount"])}" data-transaction-id="{row["id"]}">
  <td class="row-index-cell"><button type="button" class="drag-handle" draggable="true" data-drag-handle title="Déplacer">↕</button><span class="row-index-value" data-field="sort_index" data-original="{esc(row["sort_index"])}">{esc(row["sort_index"])}</span></td>
  <td class="editable" contenteditable="true" data-save="transaction" data-field="date" data-original="{esc(row["date"])}">{esc(row["date"])}</td>
  <td>{label_picker(row["label"])}</td>
  <td class="editable num" contenteditable="true" data-save="transaction" data-field="amount" data-original="{esc(row["amount"])}">{esc(row["amount"])}</td>
  <td class="editable" contenteditable="true" data-save="transaction" data-field="comment" data-original="{esc(row["comment"])}">{esc(row["comment"])}</td>
  <td class="row-actions">
    <button type="button" class="row-confirm" data-confirm-row hidden>V</button>
    <button type="button" class="row-cancel" data-cancel-row hidden>X</button>
    <button type="button" class="row-delete" data-delete-row hidden>-</button>
  </td>
</tr>"""
        for row in transactions
    )
    labels_json = json.dumps([row["name"] for row in labels], ensure_ascii=False)
    return f"""<script>window.BUDGET_LABELS = {labels_json};</script>
<section class="panel sheet-panel">
  <div class="section-head">
    <h2>{esc(account["name"])}</h2>
    <span class="save-state" data-save-state>Modifications à valider</span>
  </div>
  <table class="sheet-table" data-transaction-table data-month-id="{period_id}" data-account-id="{account["id"]}">
    <thead><tr><th class="row-index-head">#</th><th>Date</th><th>Intitulé</th><th class="num">Montant</th><th>Commentaire</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
    <tfoot>
      <tr class="table-actions-row">
        <td colspan="5"></td>
        <td class="row-actions table-footer-actions">
          <button type="button" class="row-confirm icon-button" data-add-row title="Ajouter une ligne" aria-label="Ajouter une ligne">{icon("plus")}</button>
          <button type="button" class="row-delete icon-button" data-remove-all title="Supprimer toutes les lignes" aria-label="Supprimer toutes les lignes">{icon("trash")}</button>
          <a class="button ghost import-button icon-button" href="/period/{period_id}/import?account={account["id"]}" title="Importer CSV" aria-label="Importer CSV">{icon("upload")}</a>
        </td>
      </tr>
    </tfoot>
  </table>
</section>"""


def transaction_amount_class(amount: float) -> str:
    if amount > 0:
        return "amount-positive"
    if amount < 0:
        return "amount-negative"
    return ""


def icon(name: str) -> str:
    icons = {
        "plus": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
        "trash": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3"/></svg>',
        "upload": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M5 20h14"/></svg>',
        "hourglass": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h14M5 20h14M7 4c0 5 5 6 5 8s-5 3-5 8M17 4c0 5-5 6-5 8s5 3 5 8"/></svg>',
        "x": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>',
        "check": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 5 5L20 7"/></svg>',
    }
    return icons[name]


def label_picker(label: str, save: bool = True) -> str:
    attrs = 'data-save="transaction" data-field="label"' if save else 'name="label" required'
    return f"""<div class="label-picker" data-label-picker>
  <div class="label-picker-row">
    <input value="{esc(label)}" data-original="{esc(label)}" autocomplete="off" placeholder="Intitulé" {attrs} data-label-input>
    <button class="label-add" type="button" data-create-label hidden>+</button>
  </div>
  <div class="label-suggestions" data-label-suggestions hidden></div>
</div>"""
