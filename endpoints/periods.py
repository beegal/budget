from __future__ import annotations

from datetime import date, datetime, timedelta
import sqlite3

from database import db
from web_helpers import esc, format_date, icon, layout, money, normalize_date, one, period_label, render_template


def page() -> bytes:
    with db() as conn:
        periods = conn.execute(
            """
            SELECT m.*,
                   COALESCE(tx.transaction_count, 0) AS transaction_count,
                   COALESCE(bs.budget_count, 0) AS budget_count,
                   COALESCE(tx.income, 0) AS income,
                   COALESCE(tx.expense, 0) AS expense,
                   COALESCE(tx.net, 0) AS net
            FROM period m
            LEFT JOIN (
                SELECT period_id,
                       COUNT(*) AS transaction_count,
                       COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0) AS income,
                       COALESCE(SUM(CASE WHEN amount < 0 THEN amount END), 0) AS expense,
                       COALESCE(SUM(amount), 0) AS net
                FROM transactions
                GROUP BY period_id
            ) tx ON tx.period_id = m.id
            LEFT JOIN (
                SELECT period_id, COUNT(*) AS budget_count
                FROM budget_schedule
                GROUP BY period_id
            ) bs ON bs.period_id = m.id
            ORDER BY COALESCE(m.start_date, '') DESC, m.id DESC
            """
        ).fetchall()
    overlap_reasons = period_warnings(periods)
    cards = "".join(
        period_card(row, overlap_reasons.get(row["id"]))
        for row in periods
    )
    body = render_template("periods.html", today=format_date(date.today().isoformat()), cards=cards)
    return layout("Périodes", body)


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


def period_warnings(periods: list[sqlite3.Row]) -> dict[int, str]:
    warnings: dict[int, str] = {}
    ranges = []
    for row in periods:
        start = parse_iso_date(row["start_date"])
        end = parse_iso_date(row["end_date"])
        if start and end and end <= start:
            warnings[row["id"]] = "La date de fin doit être après la date de début."
        ranges.append((row, start, end))

    for index, (row, start, end) in enumerate(ranges):
        if not start:
            continue
        for other, other_start, other_end in ranges[index + 1 :]:
            if not other_start:
                continue
            if periods_overlap(start, end, other_start, other_end):
                reason = f"Chevauche la période {other['name']} ({period_label(other)})."
                other_reason = f"Chevauche la période {row['name']} ({period_label(row)})."
                warnings.setdefault(row["id"], reason)
                warnings.setdefault(other["id"], other_reason)
    return warnings


def parse_iso_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def periods_overlap(start: date, end: date | None, other_start: date, other_end: date | None) -> bool:
    return start < (other_end or date.max) and other_start < (end or date.max)


def create(data: dict[str, list[str]]) -> str:
    start_date = datetime.strptime(normalize_date(one(data, "start_date")), "%Y-%m-%d").date()
    end_date = normalize_period_end(one(data, "end_date"))
    previous_end_date = (start_date - timedelta(days=1)).isoformat()
    with db() as conn:
        conn.execute(
            """
            UPDATE period
            SET end_date = ?
            WHERE start_date IS NOT NULL AND end_date IS NULL AND start_date < ?
            """,
            (previous_end_date, start_date.isoformat()),
        )
        conn.execute(
            "INSERT INTO period(name, start_date, end_date) VALUES (?, ?, ?)",
            (one(data, "name"), start_date.isoformat(), end_date),
        )
        period_id = conn.execute("SELECT id FROM period WHERE name = ?", (one(data, "name"),)).fetchone()["id"]
        account_ids = conn.execute("SELECT id FROM accounts").fetchall()
        for account in account_ids:
            conn.execute(
                """
                INSERT OR IGNORE INTO account_balances(period_id, account_id, opening)
                VALUES (?, ?, NULL)
                """,
                (period_id, account["id"]),
            )
        seed_budget_schedule(conn, period_id)
    return "/"


def seed_budget_schedule(conn, period_id: int) -> None:
    conn.execute(
        """
        INSERT INTO budget_schedule(period_id, label, amount, status)
        SELECT ?, label, amount, 'scheduled'
        FROM monthly_budget
        ORDER BY day, id
        """,
        (period_id,),
    )


def normalize_period_end(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw or raw.casefold() == "en cours":
        return None
    return normalize_date(raw)
