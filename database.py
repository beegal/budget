from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "budget.sqlite3"
INITIAL_DATA_PATH = ROOT / "initial-data.yaml"
MONTH_NAMES = [
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
]


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS months (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            period TEXT,
            start_date TEXT,
            end_date TEXT
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            sort_index INTEGER NOT NULL DEFAULT 1,
            show_in_summary INTEGER NOT NULL DEFAULT 1,
            visible_if_empty INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS transaction_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month_id INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            date TEXT,
            label TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            sort_index INTEGER NOT NULL DEFAULT 1,
            comment TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS account_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month_id INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            opening REAL,
            current REAL,
            closing REAL,
            difference REAL,
            UNIQUE(month_id, account_id)
        );

        CREATE TABLE IF NOT EXISTS monthly_budget (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 31),
            label TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS budget_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month_id INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN ('scheduled', 'found', 'cancel'))
        );

        CREATE INDEX IF NOT EXISTS idx_transactions_month ON transactions(month_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
        CREATE INDEX IF NOT EXISTS idx_budget_schedule_month ON budget_schedule(month_id);
        CREATE INDEX IF NOT EXISTS idx_budget_schedule_match ON budget_schedule(month_id, label, amount, status);
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO transaction_labels(name)
        SELECT DISTINCT label FROM transactions WHERE label IS NOT NULL AND TRIM(label) <> ''
        """
    )
    seed_empty_database(conn)
    conn.commit()


def seed_empty_database(conn: sqlite3.Connection) -> None:
    has_months = conn.execute("SELECT EXISTS(SELECT 1 FROM months)").fetchone()[0]
    has_accounts = conn.execute("SELECT EXISTS(SELECT 1 FROM accounts)").fetchone()[0]
    if has_months or has_accounts:
        return

    initial_data = load_initial_data()
    today = date.today()
    start_date = today.replace(day=1)
    month_name = f"{MONTH_NAMES[today.month - 1]} {today.year}"
    period = f"{start_date.isoformat()} -> en cours"
    conn.execute(
        "INSERT INTO months(name, period, start_date, end_date) VALUES (?, ?, ?, NULL)",
        (month_name, period, start_date.isoformat()),
    )
    month_id = conn.execute("SELECT id FROM months WHERE name = ?", (month_name,)).fetchone()["id"]

    for index, account in enumerate(initial_accounts(initial_data), start=1):
        account_name = account["name"]
        show_in_summary = 1 if account.get("show_in_summary", True) else 0
        conn.execute(
            "INSERT INTO accounts(name, sort_index, show_in_summary) VALUES (?, ?, ?)",
            (account_name, index, show_in_summary),
        )
        account_id = conn.execute("SELECT id FROM accounts WHERE name = ?", (account_name,)).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO account_balances(month_id, account_id, opening, current, closing, difference)
            VALUES (?, ?, 0, 0, 0, 0)
            """,
            (month_id, account_id),
        )

    for label in initial_labels(initial_data):
        conn.execute("INSERT OR IGNORE INTO transaction_labels(name) VALUES (?)", (label,))


def load_initial_data() -> dict[str, Any]:
    if not INITIAL_DATA_PATH.exists():
        return default_initial_data()
    parsed = parse_simple_yaml(INITIAL_DATA_PATH.read_text(encoding="utf-8"))
    return parsed if parsed else default_initial_data()


def default_initial_data() -> dict[str, Any]:
    return {
        "accounts": [
            {"name": "Compte courant", "show_in_summary": True},
            {"name": "Compte epargne", "show_in_summary": True},
        ],
        "labels": [
            "Salaire",
            "Courses",
            "Loyer",
            "Electricite",
            "Internet",
            "Transport",
            "Virement interne",
        ],
    }


def initial_accounts(initial_data: dict[str, Any]) -> list[dict[str, Any]]:
    accounts = initial_data.get("accounts") or default_initial_data()["accounts"]
    normalized = []
    for account in accounts:
        if isinstance(account, str):
            normalized.append({"name": account, "show_in_summary": True})
        elif isinstance(account, dict) and str(account.get("name") or "").strip():
            normalized.append(
                {
                    "name": str(account["name"]).strip(),
                    "show_in_summary": bool(account.get("show_in_summary", True)),
                }
            )
    return normalized or default_initial_data()["accounts"]


def initial_labels(initial_data: dict[str, Any]) -> list[str]:
    labels = initial_data.get("labels") or default_initial_data()["labels"]
    return [str(label).strip() for label in labels if str(label).strip()]


def parse_simple_yaml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_section: str | None = None
    current_item: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_section = line[:-1].strip()
            data[current_section] = []
            current_item = None
            continue
        if current_section is None:
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if ":" in item:
                key, value = split_yaml_pair(item)
                current_item = {key: parse_yaml_scalar(value)}
                data[current_section].append(current_item)
            else:
                current_item = None
                data[current_section].append(parse_yaml_scalar(item))
            continue
        if current_item is not None and ":" in stripped:
            key, value = split_yaml_pair(stripped)
            current_item[key] = parse_yaml_scalar(value)
    return data


def split_yaml_pair(value: str) -> tuple[str, str]:
    key, raw_value = value.split(":", 1)
    return key.strip(), raw_value.strip()


def parse_yaml_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
