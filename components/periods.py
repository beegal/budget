from __future__ import annotations

import sqlite3

from components.common import icon
from web_helpers import esc, format_date, money, period_label


def period_card(row: sqlite3.Row, warning: str | None) -> str:
    warning_html = (
        f'<span class="period-warning-icon" title="{esc(warning)}" aria-label="{esc(warning)}">i</span>'
        if warning
        else ""
    )
    transaction_count = int(row["transaction_count"] or 0)
    budget_count = int(row["budget_count"] or 0)
    can_delete = transaction_count == 0 and budget_count == 0
    delete_title = (
        "Supprimer la période"
        if can_delete
        else f"Supprimer {transaction_count} transaction(s) et {budget_count} entrée(s) de budget avant de supprimer cette période."
    )
    delete_attrs = (
        f'data-delete-period data-id="{row["id"]}"'
        if can_delete
        else "disabled aria-disabled=\"true\""
    )
    delete_html = (
        f'<button type="button" class="period-delete-button" {delete_attrs} title="{esc(delete_title)}" aria-label="{esc(delete_title)}">{icon("trash")}</button>'
    )
    warning_class = " period-overlap" if warning else ""
    start_display = format_date(row["start_date"] or "")
    end_date = format_date(row["end_date"]) if row["end_date"] else "en cours"
    return f"""<article class="card period-card{warning_class}">
  <div class="period-card-head">
    <div class="period-range" data-period-range data-id="{row["id"]}">
      <button type="button" class="period-range-display muted" data-period-range-display title="Modifier les dates">{esc(period_label(row))}</button>
      <div class="period-range-edit" data-period-range-edit hidden>
        <span>du</span>
        <input value="{esc(start_display)}" data-period-start data-original="{esc(start_display)}" placeholder="26/03/2026">
        <span>-&gt;</span>
        <input value="{esc(end_date)}" data-period-end data-original="{esc(end_date)}" placeholder="26/04/2026">
        <button type="button" class="row-confirm" data-confirm-period>V</button>
        <button type="button" class="row-cancel" data-cancel-period>X</button>
      </div>
    </div>
    {warning_html}
    {delete_html}
  </div>
  <div class="period-name" data-period-name data-id="{row["id"]}">
    <button type="button" class="period-name-display" data-period-name-display title="Modifier le nom">{esc(row["name"])}</button>
    <div class="period-name-edit" data-period-name-edit hidden>
      <input value="{esc(row["name"])}" data-period-name-input data-original="{esc(row["name"])}" placeholder="Nom de la période">
      <button type="button" class="row-confirm" data-confirm-period-name>V</button>
      <button type="button" class="row-cancel" data-cancel-period-name>X</button>
    </div>
  </div>
  <dl class="metrics">
    <div><dt>Entrées</dt><dd class="positive">{money(row["income"])}</dd></div>
    <div><dt>Sorties</dt><dd class="negative">{money(row["expense"])}</dd></div>
    <div><dt>Net</dt><dd>{money(row["net"])}</dd></div>
  </dl>
  <a class="button ghost" href="/period/{row["id"]}">Ouvrir</a>
</article>"""
