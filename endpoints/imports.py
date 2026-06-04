from __future__ import annotations

import csv
import sqlite3
from datetime import date
from io import StringIO
from urllib.parse import parse_qs

from components.common import panel_message
from components.imports import import_button, render_validation
from config import DATE_FORMAT
from database import db
from endpoints import api
from web_helpers import esc, format_date, layout, period_label, render_template


DATE_FORMAT_LABELS = {
    "dmy": "jj/mm/yy",
    "mdy": "mm/jj/yy",
    "ymd": "yy-mm-jj",
}


def page(period_id: int, query: str) -> bytes:
    params = parse_qs(query)
    account_id = params.get("account", [""])[0]
    with db() as conn:
        period = conn.execute("SELECT * FROM period WHERE id = ?", (period_id,)).fetchone()
        account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone() if account_id else None
    if period is None or account is None:
        return layout("Import introuvable", panel_message("Import introuvable"))
    return page_html(period, account, "", default_date_format(), "csv_header")


def page_html(
    period: sqlite3.Row,
    account: sqlite3.Row,
    raw_csv: str,
    date_format: str = "dmy",
    format_value: str = "csv_header",
    validation: dict[str, object] | None = None,
) -> bytes:
    period_id = period["id"]
    validation_html = render_validation(validation) if validation else ""
    body = render_template(
        "imports.html",
        period_label=esc(period_label(period)),
        period_id=period_id,
        account_id=account["id"],
        account_name=esc(account["name"]),
        period_name=esc(period["name"]),
        period_start_date=esc(format_date(period["start_date"])),
        period_end_date_clause=f" &lt;= {esc(format_date(period['end_date']))}" if period["end_date"] else "",
        raw_csv=esc(raw_csv),
        date_format_dmy_selected="selected" if date_format == "dmy" else "",
        date_format_mdy_selected="selected" if date_format == "mdy" else "",
        date_format_ymd_selected="selected" if date_format == "ymd" else "",
        format_csv_header_selected="selected" if format_value == "csv_header" else "",
        format_csv_no_header_selected="selected" if format_value == "csv_no_header" else "",
        format_tsv_header_selected="selected" if format_value == "tsv_header" else "",
        format_tsv_no_header_selected="selected" if format_value == "tsv_no_header" else "",
        import_button=import_button(validation),
        validation_html=validation_html,
    )
    return layout("Import CSV", body)


def submit(period_id: int, data: dict[str, list[str]]) -> str | bytes:
    account_id = (data.get("account_id") or [""])[0]
    raw_csv = (data.get("csv_import") or [""])[0]
    date_format = (data.get("date_format") or [default_date_format()])[0]
    format_value = (data.get("format") or ["csv_header"])[0]
    action = (data.get("action") or ["validate"])[0]
    with db() as conn:
        period = conn.execute("SELECT * FROM period WHERE id = ?", (period_id,)).fetchone()
        account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone() if account_id else None
    if period is None or account is None:
        return "/"
    validation = validate_csv(period_id, raw_csv, date_format, format_value)
    if action != "import" or validation["problem_count"]:
        return page_html(period, account, raw_csv, date_format, format_value, validation)
    for row in validation["rows"]:
        result = api.update(
            "/api/transaction-row",
            {
                "period_id": period_id,
                "account_id": account_id,
                "date": row["date_iso"],
                "label": row["label"],
                "amount": row["amount"],
                "comment": row["comment"],
            },
        )
        if not result.get("ok"):
            break
    return f"/period/{period_id}?account={account_id}"


def csv_rows(raw_csv: str, format_value: str = "csv_header") -> list[list[str]]:
    delimiter = "\t" if format_value.startswith("tsv") else ","
    reader = csv.reader(StringIO(raw_csv), delimiter=delimiter)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if rows and "header" in format_value:
        rows = rows[1:]
    return rows


def default_date_format() -> str:
    return DATE_FORMAT


def parse_import_year(value: str) -> int:
    year = int(value)
    if len(value) == 2:
        return 2000 + year
    return year


def normalize_import_date(value: object, date_format: str = "dmy") -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Date obligatoire")
    if date_format not in DATE_FORMAT_LABELS:
        date_format = default_date_format()
    normalized = raw
    for separator in ("-", ".", " "):
        normalized = normalized.replace(separator, "/")
    parts = [part.strip() for part in normalized.split("/") if part.strip()]
    if len(parts) != 3:
        raise ValueError(f"Date invalide pour le format {DATE_FORMAT_LABELS[date_format]}: {value}")
    try:
        if date_format == "ymd":
            year = parse_import_year(parts[0])
            month = int(parts[1])
            day = int(parts[2])
        elif date_format == "mdy":
            month = int(parts[0])
            day = int(parts[1])
            year = parse_import_year(parts[2])
        else:
            day = int(parts[0])
            month = int(parts[1])
            year = parse_import_year(parts[2])
        return date(year, month, day).isoformat()
    except ValueError:
        raise ValueError(f"Date invalide pour le format {DATE_FORMAT_LABELS[date_format]}: {value}")


def validate_csv(period_id: int, raw_csv: str, date_format: str = "dmy", format_value: str = "csv_header") -> dict[str, object]:
    parsed_rows = []
    labels_to_create = set()
    with db() as conn:
        existing_labels = {
            row["name"].strip().lower()
            for row in conn.execute("SELECT name FROM transaction_labels").fetchall()
        }
        for line_number, row in enumerate(csv_rows(raw_csv, format_value), start=1):
            padded = [*row, "", "", "", ""]
            date_value = padded[0].strip()
            label = padded[1].strip()
            amount_value = padded[2].strip()
            comment = padded[3].strip()
            errors = []
            normalized_date = date_value
            try:
                normalized_date = normalize_import_date(date_value, date_format)
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
                    "date": format_date(normalized_date),
                    "date_iso": normalized_date,
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
