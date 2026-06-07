from __future__ import annotations

import csv
import sqlite3
from datetime import date
from io import StringIO
from urllib.parse import parse_qs

from components.common import panel_message
from components.imports import validation_view
from config import normalize_import_name
from database import db
from endpoints import api
from i18n import translate
from user_preferences import current_date_format
from web_helpers import format_date, parse_month, period_label, render_template, user_layout


DATE_FORMAT_LABELS = {
    "dmy": "jj/mm/yy",
    "mdy": "mm/jj/yy",
    "ymd": "yy-mm-jj",
}


def page(period_id: int, query: str, user_id: str) -> bytes:
    params = parse_qs(query)
    account_id = params.get("account", [""])[0]
    with db() as conn:
        period = conn.execute("SELECT * FROM period WHERE id = ? AND user_id = ?", (period_id, user_id)).fetchone()
        account = conn.execute(
            "SELECT * FROM accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        ).fetchone() if account_id else None
    if period is None or account is None:
        return user_layout(translate("imports.title"), panel_message(translate("imports.title")), user_id)
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
    body = render_template(
        "imports.html",
        period_label=period_label(period),
        period_id=period_id,
        account_id=account["id"],
        account_name=account["name"],
        period_name=period["name"],
        period_start_date=format_date(period["start_date"]),
        period_end_date=format_date(period["end_date"]) if period["end_date"] else "",
        raw_csv=raw_csv,
        date_format=date_format,
        format_value=format_value,
        validation=validation_view(validation),
    )
    return user_layout(translate("imports.title"), body, str(period["user_id"]))


def submit(period_id: int, data: dict[str, list[str]], user_id: str) -> str | bytes:
    account_id = (data.get("account_id") or [""])[0]
    raw_csv = (data.get("csv_import") or [""])[0]
    date_format = (data.get("date_format") or [default_date_format()])[0]
    format_value = (data.get("format") or ["csv_header"])[0]
    action = (data.get("action") or ["validate"])[0]
    with db() as conn:
        period = conn.execute("SELECT * FROM period WHERE id = ? AND user_id = ?", (period_id, user_id)).fetchone()
        account = conn.execute(
            "SELECT * FROM accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        ).fetchone() if account_id else None
    if period is None or account is None:
        return "/"
    validation = validate_csv(period_id, raw_csv, date_format, format_value, user_id)
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
            user_id,
        )
        if not result.get("ok"):
            break
    return f"/period/{period_id}?account={account_id}"


def csv_rows(raw_csv: str, format_value: str = "csv_header") -> list[list[str]]:
    delimiter = "\t" if format_value.startswith("tsv") else ","
    reader = csv.reader(StringIO(raw_csv), delimiter=delimiter)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if rows and format_value in {"csv_header", "tsv_header"}:
        rows = rows[1:]
    return rows


def default_date_format() -> str:
    return current_date_format()


def parse_import_year(value: str) -> int:
    year = int(value)
    if len(value) == 2:
        return 2000 + year
    return year


def normalize_import_date(value: object, date_format: str = "dmy", default_year: int | None = None) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(translate("errors.date-required"))
    if date_format not in DATE_FORMAT_LABELS:
        date_format = default_date_format()
    normalized = raw
    for separator in ("-", ".", " "):
        normalized = normalized.replace(separator, "/")
    parts = [part.strip() for part in normalized.split("/") if part.strip()]
    if len(parts) not in {2, 3}:
        raise ValueError(translate("errors.invalid-date-for-format", format=DATE_FORMAT_LABELS[date_format], value=value))
    try:
        if len(parts) == 2:
            year = default_year or date.today().year
            day, month = parse_import_day_month(parts, date_format)
        elif date_format == "ymd":
            year = parse_import_year(parts[0])
            month = parse_month(parts[1])
            day = int(parts[2])
        elif date_format == "mdy":
            month = parse_month(parts[0])
            day = int(parts[1])
            year = parse_import_year(parts[2])
        else:
            day = int(parts[0])
            month = parse_month(parts[1])
            year = parse_import_year(parts[2])
        return date(year, month, day).isoformat()
    except ValueError:
        raise ValueError(translate("errors.invalid-date-for-format", format=DATE_FORMAT_LABELS[date_format], value=value))


def parse_import_day_month(parts: list[str], date_format: str) -> tuple[int, int]:
    try:
        first_month = parse_month(parts[0])
        first_is_month = not parts[0].strip().isdigit() or first_month <= 12
    except ValueError:
        first_month = 0
        first_is_month = False
    try:
        second_month = parse_month(parts[1])
        second_is_month = not parts[1].strip().isdigit() or second_month <= 12
    except ValueError:
        second_month = 0
        second_is_month = False

    if first_is_month and not parts[0].strip().isdigit():
        return int(parts[1]), first_month
    if second_is_month and not parts[1].strip().isdigit():
        return int(parts[0]), second_month
    if date_format == "mdy":
        return int(parts[1]), int(parts[0])
    return int(parts[0]), int(parts[1])


def import_year_candidates(conn: sqlite3.Connection, period_id: int, user_id: str) -> list[int]:
    period = conn.execute("SELECT start_date, end_date FROM period WHERE id = ? AND user_id = ?", (period_id, user_id)).fetchone()
    years = []
    for field in ("start_date", "end_date"):
        raw = period[field] if period else ""
        if raw:
            years.append(date.fromisoformat(raw).year)
    years.append(date.today().year)
    return list(dict.fromkeys(years))


def validate_csv(period_id: int, raw_csv: str, date_format: str = "dmy", format_value: str = "csv_header", user_id: str = "") -> dict[str, object]:
    parsed_rows = []
    labels_to_create = set()
    with db() as conn:
        year_candidates = import_year_candidates(conn, period_id, user_id)
        existing_labels = {
            row["name"].strip().lower()
            for row in conn.execute("SELECT name FROM transaction_labels WHERE user_id = ?", (user_id,)).fetchall()
        }
        for line_number, row in enumerate(csv_rows(raw_csv, format_value), start=1):
            padded = [*row, "", "", "", ""]
            date_value = padded[0].strip()
            label = normalize_import_name(padded[1])
            amount_value = padded[2].strip()
            comment = padded[3].strip()
            errors = []
            normalized_date = date_value
            try:
                last_error = None
                for year in year_candidates:
                    try:
                        normalized_date = normalize_import_date(date_value, date_format, year)
                        api.validate_transaction_date(conn, period_id, normalized_date, user_id)
                        last_error = None
                        break
                    except ValueError as error:
                        last_error = error
                if last_error:
                    raise last_error
            except ValueError as error:
                errors.append(str(error))
            try:
                float(amount_value.replace(",", "."))
            except ValueError:
                errors.append(translate("errors.invalid-amount"))
            if not label:
                errors.append(translate("errors.label-required"))
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
