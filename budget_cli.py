from __future__ import annotations

import argparse
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import database


ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = ROOT / "data" / "budget.sqlite3"
XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
EXCEL_EPOCH = date(1899, 12, 30)
PERIOD_SHEET_SKIP = {"budget", "feuil1"}


@dataclass
class WorkbookSheet:
    name: str
    rows: dict[int, dict[int, str]]


@dataclass
class TransactionImport:
    sheet_name: str
    account: str
    tx_date: str
    label: str
    amount: float
    row_number: int


@dataclass
class ImportProblem:
    sheet_name: str
    row_number: int
    account: str
    label: str
    reason: str


@dataclass
class ImportInconsistency:
    sheet_name: str
    row_number: int
    period_start: str
    period_end: str
    account: str
    tx_date: str
    label: str
    amount: float
    reason: str


@dataclass
class PeriodImport:
    name: str
    start_date: str
    end_date: str | None
    balances: dict[str, float | None]
    transactions: list[TransactionImport]
    problems: list[ImportProblem]


def main() -> int:
    parser = argparse.ArgumentParser(description="Importe le classeur Personnal-Budget dans la base Budget.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Chemin vers la base SQLite.")
    parser.add_argument("--create", action="store_true", help="Recrée une base vide avant l'import.")
    parser.add_argument("--import", dest="import_path", help="Classeur Personnal-Budget .xlsx/.xls à importer.")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    if args.create:
        create_database(db_path)
        print(f"Base créée: {db_path}")
    elif not db_path.exists():
        create_database(db_path)
        print(f"Base créée: {db_path}")

    if args.import_path:
        workbook_path = resolve_workbook_path(Path(args.import_path).expanduser())
        summary = import_workbook(db_path, workbook_path)
        print(f"Import terminé: {workbook_path}")
        print(f"Périodes: {summary['periods']}")
        print(f"Comptes: {summary['accounts']}")
        print(f"Transactions: {summary['transactions']}")
        print(f"Transactions hors période importées: {summary['out_of_range_transactions']}")
        print(f"Lignes non importées: {summary['skipped_transactions']}")
        print(f"Intitulés: {summary['labels']}")
        print(f"Budget mensuel: {summary['monthly_budget']}")
        for inconsistency in summary["inconsistencies"]:
            print(
                f"Incohérence importée - feuille {inconsistency.sheet_name}, ligne {inconsistency.row_number}, "
                f"période {inconsistency.period_start} -> {inconsistency.period_end}, "
                f"date {inconsistency.tx_date}, compte {inconsistency.account}, "
                f"intitulé {inconsistency.label}, montant {inconsistency.amount:g}: {inconsistency.reason}"
            )
        for problem in summary["problems"]:
            print(
                f"Non importé - feuille {problem.sheet_name}, ligne {problem.row_number}, "
                f"compte {problem.account or '-'}, intitulé {problem.label or '-'}: {problem.reason}"
            )

    if not args.create and not args.import_path:
        parser.print_help()
    return 0


def create_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        database.ensure_schema(conn)
        clear_database(conn)


def clear_database(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in (
        "transactions",
        "budget_schedule",
        "monthly_budget",
        "account_balances",
        "transaction_labels",
        "accounts",
        "period",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM sqlite_sequence")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def resolve_workbook_path(path: Path) -> Path:
    if path.exists():
        return path
    if path.suffix.lower() == ".xls":
        xlsx_path = path.with_suffix(".xlsx")
        if xlsx_path.exists():
            return xlsx_path
    raise FileNotFoundError(f"Classeur introuvable: {path}")


def import_workbook(db_path: Path, workbook_path: Path) -> dict[str, object]:
    if workbook_path.suffix.lower() == ".xls":
        raise ValueError("Le format .xls binaire n'est pas supporté sans xlrd. Sauve le fichier en .xlsx.")
    sheets = read_xlsx(workbook_path)
    periods = build_periods(sheets)
    budget_rows = monthly_budget_rows(sheets)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        account_ids: dict[str, int] = {}
        label_names: set[str] = set()
        monthly_count = import_monthly_budget(conn, budget_rows)
        transaction_count = 0
        inconsistencies: list[ImportInconsistency] = []
        problems = [problem for period in periods for problem in period.problems]
        for period in periods:
            period_id = insert_period(conn, period)
            period_start = iso_to_date(period.start_date)
            period_end = iso_to_date(period.end_date) if period.end_date else None
            for account_name in period_account_names(period):
                account_id = get_or_create_account(conn, account_ids, account_name)
                opening = period.balances.get(account_name)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO account_balances(period_id, account_id, opening)
                    VALUES (?, ?, ?)
                    """,
                    (period_id, account_id, opening),
                )
            sort_indexes: dict[int, int] = {}
            for tx in sorted(period.transactions, key=lambda item: (item.tx_date, item.row_number, item.account)):
                tx_date = iso_to_date(tx.tx_date)
                if tx_date < period_start or (period_end is not None and tx_date > period_end):
                    inconsistencies.append(
                        ImportInconsistency(
                            sheet_name=tx.sheet_name,
                            row_number=tx.row_number,
                            period_start=period.start_date,
                            period_end=period.end_date or "en cours",
                            account=tx.account,
                            tx_date=tx.tx_date,
                            label=tx.label,
                            amount=tx.amount,
                            reason="date hors période visible dans le classeur",
                        )
                    )
                account_id = get_or_create_account(conn, account_ids, tx.account)
                label_names.add(tx.label)
                conn.execute("INSERT OR IGNORE INTO transaction_labels(name) VALUES (?)", (tx.label,))
                sort_index = sort_indexes.get(account_id, 0) + 1
                sort_indexes[account_id] = sort_index
                conn.execute(
                    """
                    INSERT INTO transactions(period_id, account_id, date, label, amount, sort_index)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (period_id, account_id, tx.tx_date, tx.label, tx.amount, sort_index),
                )
                transaction_count += 1
        conn.commit()
        return {
            "periods": len(periods),
            "accounts": int(conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]),
            "transactions": transaction_count,
            "out_of_range_transactions": len(inconsistencies),
            "inconsistencies": inconsistencies,
            "skipped_transactions": len(problems),
            "problems": problems,
            "labels": int(conn.execute("SELECT COUNT(*) FROM transaction_labels").fetchone()[0]),
            "monthly_budget": monthly_count,
        }


def read_xlsx(path: Path) -> list[WorkbookSheet]:
    with ZipFile(path) as archive:
        shared_strings = read_shared_strings(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        sheets = []
        for sheet in workbook.find("m:sheets", XLSX_NS):
            name = sheet.attrib["name"]
            target = relmap[sheet.attrib[REL_ID]]
            rows = read_sheet_rows(archive, target, shared_strings)
            sheets.append(WorkbookSheet(name, rows))
        return sheets


def read_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall("m:si", XLSX_NS):
        strings.append("".join(node.text or "" for node in item.iter(f"{{{XLSX_NS['m']}}}t")))
    return strings


def read_sheet_rows(archive: ZipFile, target: str, shared_strings: list[str]) -> dict[int, dict[int, str]]:
    path = "xl/" + target if not target.startswith("xl/") else target
    root = ET.fromstring(archive.read(path))
    rows: dict[int, dict[int, str]] = {}
    for row in root.findall(".//m:sheetData/m:row", XLSX_NS):
        row_number = int(row.attrib["r"])
        values: dict[int, str] = {}
        for cell in row.findall("m:c", XLSX_NS):
            value = cell_value(cell, shared_strings).strip()
            if value:
                values[column_index(cell.attrib["r"])] = value
        if values:
            rows[row_number] = values
    return rows


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "s":
        value = cell.find("m:v", XLSX_NS)
        return shared_strings[int(value.text)] if value is not None and value.text else ""
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{XLSX_NS['m']}}}t"))
    value = cell.find("m:v", XLSX_NS)
    return value.text if value is not None and value.text is not None else ""


def column_index(cell_ref: str) -> int:
    letters = "".join(char for char in cell_ref if char.isalpha())
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter.upper()) - 64
    return index - 1


def build_periods(sheets: list[WorkbookSheet]) -> list[PeriodImport]:
    period_sheets = [sheet for sheet in sheets if sheet.name.lower() not in PERIOD_SHEET_SKIP]
    parsed = [parse_period_sheet(sheet) for sheet in period_sheets]
    for index, period in enumerate(parsed):
        next_start = iso_to_date(parsed[index + 1].start_date) if index + 1 < len(parsed) else None
        if period.end_date is None and next_start is not None:
            period.end_date = next_start.isoformat()
    return parsed


def parse_period_sheet(sheet: WorkbookSheet) -> PeriodImport:
    problems: list[ImportProblem] = []
    transactions = parse_transactions(sheet, problems)
    anchor_date = first_transaction_date(sheet) or min((iso_to_date(tx.tx_date) for tx in transactions), default=None)
    raw_period = find_period_text(sheet)
    parsed_range = parse_period_range(raw_period, anchor_date) if raw_period else (None, None)
    start_date = parsed_range[0] or anchor_date or date.today()
    end_date = parsed_range[1]
    return PeriodImport(
        name=sheet.name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat() if end_date else None,
        balances=parse_balances(sheet),
        transactions=transactions,
        problems=problems,
    )


def first_transaction_date(sheet: WorkbookSheet) -> date | None:
    header = sheet.rows.get(3, {})
    date_columns = [column for column, value in sorted(header.items()) if normalize(value) == "date"]
    if not date_columns:
        return None
    first_date_column = date_columns[0]
    for row_number in sorted(sheet.rows):
        if row_number <= 3:
            continue
        value = sheet.rows[row_number].get(first_date_column, "")
        if value:
            return parse_excel_date(value)
    return None


def find_period_text(sheet: WorkbookSheet) -> str:
    for row in sheet.rows.values():
        for value in row.values():
            if value.strip().lower().startswith("du "):
                return value.strip()
    return ""


def parse_period_range(value: str, reference_date: date | None) -> tuple[date | None, date | None]:
    match = re.search(r"du\s+([0-9]{1,2})/([0-9]{1,2})\s*->\s*([0-9]{1,2})/([0-9]{1,2})", value, re.I)
    if not match or reference_date is None:
        return None, None
    start_day, start_month, end_day, end_month = (int(part) for part in match.groups())
    start = date(reference_date.year, start_month, start_day)
    if abs((reference_date - start).days) > 14:
        return None, None
    end_year = reference_date.year + (1 if end_month < start_month else 0)
    end = date(end_year, end_month, end_day)
    return start, end


def parse_balances(sheet: WorkbookSheet) -> dict[str, float | None]:
    header = sheet.rows.get(3, {})
    if normalize(header.get(0)) != "compte" or normalize(header.get(1)) != "debut":
        return {}
    balances: dict[str, float | None] = {}
    for row_number in sorted(sheet.rows):
        if row_number <= 3:
            continue
        row = sheet.rows[row_number]
        account = row.get(0, "").strip()
        if not account or account.lower().startswith("solde "):
            continue
        balances[account] = parse_optional_float(row.get(1, ""))
    return balances


def parse_transactions(sheet: WorkbookSheet, problems: list[ImportProblem] | None = None) -> list[TransactionImport]:
    header = sheet.rows.get(3, {})
    title_row = sheet.rows.get(2, {})
    problems = problems if problems is not None else []
    transactions = []
    date_columns = [column for column, value in header.items() if normalize(value) == "date"]
    for date_col in date_columns:
        account_from_header = title_row.get(date_col, "").strip()
        is_other_accounts = normalize(account_from_header).startswith("other accounts")
        if is_other_accounts:
            account_col, label_col, amount_col = date_col + 1, date_col + 2, date_col + 3
        else:
            account_col, label_col, amount_col = None, date_col + 1, date_col + 2
        for row_number in sorted(sheet.rows):
            if row_number <= 3:
                continue
            row = sheet.rows[row_number]
            raw_date = row.get(date_col, "")
            label = row.get(label_col, "").strip()
            amount_value = row.get(amount_col, "")
            account = row.get(account_col, "").strip() if account_col is not None else account_from_header
            present_count = sum(1 for value in (raw_date, label, amount_value) if str(value).strip())
            if present_count == 0:
                continue
            if present_count < 3:
                problems.append(ImportProblem(sheet.name, row_number, account, label, "date, intitulé ou montant manquant"))
                continue
            if not account:
                problems.append(ImportProblem(sheet.name, row_number, account, label, "compte manquant"))
                continue
            try:
                tx_date = parse_excel_date(raw_date)
                amount = parse_float(amount_value)
            except ValueError as error:
                problems.append(ImportProblem(sheet.name, row_number, account, label, str(error)))
                continue
            transactions.append(
                TransactionImport(
                    sheet_name=sheet.name,
                    account=account,
                    tx_date=tx_date.isoformat(),
                    label=label,
                    amount=amount,
                    row_number=row_number,
                )
            )
    return transactions


def monthly_budget_rows(sheets: list[WorkbookSheet]) -> list[tuple[int, str, float]]:
    budget = next((sheet for sheet in sheets if sheet.name.lower() == "budget"), None)
    if budget is None:
        return []
    rows = []
    for row_number in sorted(budget.rows):
        row = budget.rows[row_number]
        income_label = row.get(1, "").strip()
        income_amount = row.get(5, "").strip()
        expense_label = row.get(6, "").strip()
        expense_amount = row.get(10, "").strip()
        if income_label and income_label.lower() != "total" and income_amount:
            rows.append((1, income_label, abs(parse_float(income_amount))))
        if expense_label and expense_label.lower() != "total" and expense_amount:
            rows.append((1, expense_label, -abs(parse_float(expense_amount))))
    return rows


def import_monthly_budget(conn: sqlite3.Connection, rows: list[tuple[int, str, float]]) -> int:
    conn.execute("DELETE FROM monthly_budget")
    for day, label, amount in rows:
        conn.execute("INSERT INTO monthly_budget(day, label, amount) VALUES (?, ?, ?)", (day, label, amount))
        conn.execute("INSERT OR IGNORE INTO transaction_labels(name) VALUES (?)", (label,))
    return len(rows)


def insert_period(conn: sqlite3.Connection, period: PeriodImport) -> int:
    conn.execute(
        "INSERT INTO period(name, start_date, end_date) VALUES (?, ?, ?)",
        (period.name, period.start_date, period.end_date),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def period_account_names(period: PeriodImport) -> list[str]:
    names = {tx.account for tx in period.transactions}
    names.update(period.balances.keys())
    return sorted(names)


def get_or_create_account(conn: sqlite3.Connection, cache: dict[str, int], name: str) -> int:
    if name in cache:
        return cache[name]
    row = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
    if row:
        account_id = int(row["id"])
    else:
        sort_index = int(conn.execute("SELECT COALESCE(MAX(sort_index), 0) + 1 FROM accounts").fetchone()[0])
        conn.execute("INSERT INTO accounts(name, sort_index) VALUES (?, ?)", (name, sort_index))
        account_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    cache[name] = account_id
    return account_id


def parse_excel_date(value: str) -> date:
    if re.fullmatch(r"\d+(\.\d+)?", value):
        return EXCEL_EPOCH + timedelta(days=int(float(value)))
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            pass
    raise ValueError(f"Date Excel invalide: {value}")


def parse_float(value: str) -> float:
    return float(str(value).replace("\xa0", "").replace(" ", "").replace(",", "."))


def parse_optional_float(value: str) -> float | None:
    value = str(value or "").strip()
    return parse_float(value) if value else None


def iso_to_date(value: str) -> date:
    return date.fromisoformat(value)


def normalize(value: object) -> str:
    return str(value or "").strip().casefold()


if __name__ == "__main__":
    raise SystemExit(main())
