from __future__ import annotations

import csv
import sqlite3
from io import StringIO
from urllib.parse import parse_qs

from database import db
from endpoints import api
from web_helpers import esc, layout, period_label


def page(period_id: int, query: str) -> bytes:
    params = parse_qs(query)
    account_id = params.get("account", [""])[0]
    with db() as conn:
        period = conn.execute("SELECT * FROM months WHERE id = ?", (period_id,)).fetchone()
        account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone() if account_id else None
    if period is None or account is None:
        return layout("Import introuvable", "<section class='panel'><h1>Import introuvable</h1></section>")
    return page_html(period, account, "")


def page_html(
    period: sqlite3.Row,
    account: sqlite3.Row,
    raw_csv: str,
    validation: dict[str, object] | None = None,
) -> bytes:
    period_id = period["id"]
    validation_html = render_validation(validation) if validation else ""
    import_disabled = " disabled" if not validation or validation["problem_count"] else ""
    import_button = (
        f'<button name="action" value="import"{import_disabled}>Importation</button>'
        if validation
        else ""
    )
    body = f"""<section class="page-title">
  <div>
    <p class="eyebrow">{esc(period_label(period))}</p>
    <h1>Import CSV</h1>
  </div>
  <a class="button ghost" href="/period/{period_id}?account={account["id"]}">Retour au compte</a>
</section>
<section class="panel narrow">
  <dl class="import-context">
    <div><dt>Compte</dt><dd>{esc(account["name"])}</dd></div>
    <div><dt>Période</dt><dd>{esc(period["name"])}</dd></div>
    <div><dt>Dates valides</dt><dd>{esc(period["start_date"])} &lt;= date{f" &lt; {esc(period['end_date'])}" if period["end_date"] else ""}</dd></div>
  </dl>
  <form method="post" action="/period/{period_id}/import" class="import-form">
    <input type="hidden" name="account_id" value="{account["id"]}">
    <label>CSV import
      <textarea name="csv_import" rows="12" placeholder="Date,Intitulé,Montant,commentaire&#10;2026-03-26,Course - Exemple,-12.50,Note">{esc(raw_csv)}</textarea>
    </label>
    <div class="form-actions">
      <button name="action" value="validate">Validation</button>
      {import_button}
    </div>
  </form>
  {validation_html}
</section>"""
    return layout("Import CSV", body)


def submit(period_id: int, data: dict[str, list[str]]) -> str | bytes:
    account_id = (data.get("account_id") or [""])[0]
    raw_csv = (data.get("csv_import") or [""])[0]
    action = (data.get("action") or ["validate"])[0]
    with db() as conn:
        period = conn.execute("SELECT * FROM months WHERE id = ?", (period_id,)).fetchone()
        account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone() if account_id else None
    if period is None or account is None:
        return "/"
    validation = validate_csv(period_id, raw_csv)
    if action != "import" or validation["problem_count"]:
        return page_html(period, account, raw_csv, validation)
    for row in validation["rows"]:
        result = api.update(
            "/api/transaction-row",
            {
                "month_id": period_id,
                "account_id": account_id,
                "date": row["date"],
                "label": row["label"],
                "amount": row["amount"],
                "comment": row["comment"],
            },
        )
        if not result.get("ok"):
            break
    return f"/period/{period_id}?account={account_id}"


def csv_rows(raw_csv: str) -> list[list[str]]:
    reader = csv.reader(StringIO(raw_csv))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if rows and [cell.strip().lower() for cell in rows[0][:4]] == ["date", "intitulé", "montant", "commentaire"]:
        rows = rows[1:]
    return rows


def validate_csv(period_id: int, raw_csv: str) -> dict[str, object]:
    parsed_rows = []
    labels_to_create = set()
    with db() as conn:
        existing_labels = {
            row["name"].strip().lower()
            for row in conn.execute("SELECT name FROM transaction_labels").fetchall()
        }
        for line_number, row in enumerate(csv_rows(raw_csv), start=1):
            padded = [*row, "", "", "", ""]
            date_value = padded[0].strip()
            label = padded[1].strip()
            amount_value = padded[2].strip()
            comment = padded[3].strip()
            errors = []
            normalized_date = date_value
            try:
                normalized_date = api.normalize_date(date_value) or ""
                api.validate_transaction_date(conn, period_id, normalized_date)
            except ValueError as error:
                errors.append(str(error))
            try:
                float(amount_value.replace(",", "."))
            except ValueError:
                errors.append("Montant invalide")
            if not label:
                errors.append("Intitulé obligatoire")
            elif label.lower() not in existing_labels:
                labels_to_create.add(label.lower())
            parsed_rows.append(
                {
                    "line": line_number,
                    "date": normalized_date,
                    "label": label,
                    "amount": amount_value,
                    "comment": comment,
                    "errors": errors,
                }
            )
    problem_count = sum(1 for row in parsed_rows if row["errors"])
    correct_count = len(parsed_rows) - problem_count
    existing_count = len({row["label"].lower() for row in parsed_rows if row["label"] and row["label"].lower() in existing_labels})
    return {
        "rows": parsed_rows,
        "correct_count": correct_count,
        "problem_count": problem_count,
        "existing_label_count": existing_count,
        "create_label_count": len(labels_to_create),
    }


def render_validation(validation: dict[str, object]) -> str:
    row_html = "".join(
        f"""<tr class="{"import-row-error" if row["errors"] else ""}">
  <td>{row["line"]}</td>
  <td>{esc(row["date"])}</td>
  <td>{esc(row["label"])}</td>
  <td>{esc(row["amount"])}</td>
  <td>{esc(row["comment"])}</td>
  <td>{esc("; ".join(row["errors"]))}</td>
</tr>"""
        for row in validation["rows"]
    )
    return f"""<div class="import-validation">
  <h2>Fichier à importer</h2>
  <table>
    <thead><tr><th>#</th><th>Date</th><th>Intitulé</th><th>Montant</th><th>Commentaire</th><th>Erreur</th></tr></thead>
    <tbody>{row_html or "<tr><td colspan='6'>Aucune ligne à valider.</td></tr>"}</tbody>
  </table>
  <div class="import-result">
    <div><span>Records corrects</span><strong>{validation["correct_count"]}</strong></div>
    <div><span>Records problématiques</span><strong class="{"negative" if validation["problem_count"] else "positive"}">{validation["problem_count"]}</strong></div>
    <div><span>Intitulés existants</span><strong>{validation["existing_label_count"]}</strong></div>
    <div><span>Intitulés à créer</span><strong>{validation["create_label_count"]}</strong></div>
  </div>
</div>"""
