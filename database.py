from __future__ import annotations

import sqlite3
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from config import MONTH_NAMES, parse_simple_yaml

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("BUDGET_SQLITE_PATH", str(ROOT / "data" / "budget.sqlite3"))).expanduser()
INITIAL_DATA_PATH = ROOT / "initial-data.yaml"
LEGACY_USER_ID = "00000000-0000-0000-0000-000000000001"
USER_SCOPED_TABLES = (
    "period",
    "accounts",
    "transaction_labels",
    "transactions",
    "account_balances",
    "monthly_budget",
    "budget_schedule",
)


class DictRow(dict):
    def __init__(self, values: dict[str, Any], columns: list[str]):
        super().__init__(values)
        self._columns = columns

    def __getitem__(self, key: object) -> Any:
        if isinstance(key, int):
            return super().__getitem__(self._columns[key])
        return super().__getitem__(key)


class ResultCursor:
    def __init__(self, rows: list[tuple[Any, ...]], columns: list[str]):
        self._rows = [DictRow(dict(zip(columns, row)), columns) for row in rows]
        self._index = 0
        self.rowcount = len(rows)
        self.lastrowid = None

    def fetchone(self) -> DictRow | None:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self) -> list[DictRow]:
        rows = self._rows[self._index :]
        self._index = len(self._rows)
        return rows


class MySQLCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor
        self.rowcount = cursor.rowcount
        self.lastrowid = cursor.lastrowid
        self._columns = [column[0] for column in cursor.description or []]

    def fetchone(self) -> DictRow | None:
        row = self._cursor.fetchone()
        return DictRow(row, self._columns) if row is not None else None

    def fetchall(self) -> list[DictRow]:
        return [DictRow(row, self._columns) for row in self._cursor.fetchall()]


class MySQLConnection:
    backend = "mysql"

    def __init__(self, conn: Any):
        self._conn = conn
        self._lastrowid = 0

    def __enter__(self) -> "MySQLConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()

    def execute(self, sql: str, parameters: tuple[object, ...] | list[object] = ()) -> MySQLCursor | ResultCursor:
        normalized = sql.strip()
        if normalized.upper().startswith("PRAGMA "):
            return ResultCursor([], [])
        if normalized.upper() == "SELECT LAST_INSERT_ROWID()":
            return ResultCursor([(self._lastrowid,)], ["last_insert_rowid()"])
        if normalized.upper().startswith("DELETE FROM SQLITE_SEQUENCE"):
            return ResultCursor([], [])
        cursor = self._conn.cursor()
        try:
            cursor.execute(mysql_sql(sql), tuple(parameters))
        except Exception as error:
            if getattr(error, "args", [None])[0] in (1060, 1061):
                return ResultCursor([], [])
            raise
        self._lastrowid = cursor.lastrowid or self._lastrowid
        return MySQLCursor(cursor)

    def executemany(self, sql: str, parameters: list[tuple[object, ...]]) -> MySQLCursor:
        cursor = self._conn.cursor()
        cursor.executemany(mysql_sql(sql), parameters)
        self._lastrowid = cursor.lastrowid or self._lastrowid
        return MySQLCursor(cursor)

    def executescript(self, sql: str) -> None:
        for statement in mysql_schema_statements():
            self.execute(statement)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def db() -> sqlite3.Connection | MySQLConnection:
    if database_backend() == "mysql":
        conn = mysql_connect()
        ensure_schema(conn)
        return conn
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    return conn


def database_backend() -> str:
    return os.environ.get("BUDGET_DB_BACKEND", "sqlite").strip().lower()


def integrity_errors() -> tuple[type[BaseException], ...]:
    errors: list[type[BaseException]] = [sqlite3.IntegrityError]
    try:
        import pymysql

        errors.append(pymysql.err.IntegrityError)
    except ImportError:
        pass
    return tuple(errors)


def mysql_connect(database_name: str | None = None) -> MySQLConnection:
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as error:
        raise RuntimeError("Le backend MySQL demande la dépendance PyMySQL.") from error

    return MySQLConnection(
        pymysql.connect(
            host=os.environ.get("BUDGET_MYSQL_HOST", "127.0.0.1"),
            port=int(os.environ.get("BUDGET_MYSQL_PORT", "3306")),
            user=os.environ.get("BUDGET_MYSQL_USER", "budget"),
            password=os.environ.get("BUDGET_MYSQL_PASSWORD", ""),
            database=database_name or os.environ.get("BUDGET_MYSQL_DATABASE", "budget"),
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
        )
    )


def mysql_admin_connect() -> MySQLConnection:
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as error:
        raise RuntimeError("Le backend MySQL demande la dépendance PyMySQL.") from error

    return MySQLConnection(
        pymysql.connect(
            host=os.environ.get("BUDGET_MYSQL_HOST", "127.0.0.1"),
            port=int(os.environ.get("BUDGET_MYSQL_PORT", "3306")),
            user=os.environ.get("BUDGET_MYSQL_ROOT_USER", "root"),
            password=os.environ.get("BUDGET_MYSQL_ROOT_PASSWORD", ""),
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
        )
    )


def create_mysql_database() -> None:
    database_name = mysql_identifier(os.environ.get("BUDGET_MYSQL_DATABASE", "budget"), "database")
    user = mysql_identifier(os.environ.get("BUDGET_MYSQL_USER", "budget"), "user")
    password = os.environ.get("BUDGET_MYSQL_PASSWORD", "")
    with mysql_admin_connect() as conn:
        conn.execute(f"CREATE DATABASE IF NOT EXISTS `{database_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin")
        conn.execute(f"ALTER DATABASE `{database_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin")
        conn.execute(f"CREATE USER IF NOT EXISTS `{user}`@'%%' IDENTIFIED BY %s", (password,))
        conn.execute(f"GRANT ALL PRIVILEGES ON `{database_name}`.* TO `{user}`@'%%'")
    with mysql_connect(database_name) as conn:
        ensure_schema(conn)


def mysql_identifier(value: str, label: str) -> str:
    value = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise ValueError(f"Nom MySQL invalide pour {label}: {value}")
    return value


def mysql_sql(sql: str) -> str:
    converted = sql.replace("INSERT OR IGNORE INTO", "INSERT IGNORE INTO")
    converted = converted.replace("?", "%s")
    converted = converted.replace(
        "ON CONFLICT(user_id, period_id, account_id) DO UPDATE SET opening = excluded.opening",
        "ON DUPLICATE KEY UPDATE opening = VALUES(opening)",
    )
    return converted


def mysql_schema_statements() -> list[str]:
    return [
        """
        CREATE TABLE IF NOT EXISTS users (
            id CHAR(36) NOT NULL PRIMARY KEY,
            email VARCHAR(320) NOT NULL UNIQUE,
            hashed_password VARCHAR(1024) NOT NULL,
            is_active BOOL NOT NULL DEFAULT TRUE,
            is_superuser BOOL NOT NULL DEFAULT FALSE,
            is_verified BOOL NOT NULL DEFAULT FALSE,
            last_login VARCHAR(32)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS period (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            name VARCHAR(255) NOT NULL,
            start_date VARCHAR(10),
            end_date VARCHAR(10),
            UNIQUE KEY uniq_period_user_name (user_id, name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            name VARCHAR(255) NOT NULL,
            sort_index INT NOT NULL DEFAULT 1,
            show_in_summary INT NOT NULL DEFAULT 1,
            visible_if_empty INT NOT NULL DEFAULT 1,
            UNIQUE KEY uniq_accounts_user_name (user_id, name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS transaction_labels (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            name VARCHAR(255) NOT NULL,
            UNIQUE KEY uniq_labels_user_name (user_id, name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            period_id INT NOT NULL,
            account_id INT NOT NULL,
            date VARCHAR(10),
            label VARCHAR(255) NOT NULL,
            amount DOUBLE NOT NULL DEFAULT 0,
            sort_index INT NOT NULL DEFAULT 1,
            comment TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_transactions_period FOREIGN KEY (period_id) REFERENCES period(id) ON DELETE CASCADE,
            CONSTRAINT fk_transactions_account FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS account_balances (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            period_id INT NOT NULL,
            account_id INT NOT NULL,
            opening DOUBLE,
            UNIQUE KEY uniq_account_balances_user_period_account (user_id, period_id, account_id),
            CONSTRAINT fk_account_balances_period FOREIGN KEY (period_id) REFERENCES period(id) ON DELETE CASCADE,
            CONSTRAINT fk_account_balances_account FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS monthly_budget (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            day INT NOT NULL,
            label VARCHAR(255) NOT NULL,
            amount DOUBLE NOT NULL DEFAULT 0,
            CHECK(day BETWEEN 1 AND 31)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS budget_schedule (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            period_id INT NOT NULL,
            label VARCHAR(255) NOT NULL,
            amount DOUBLE NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
            CHECK(status IN ('scheduled', 'found', 'cancel')),
            CONSTRAINT fk_budget_schedule_period FOREIGN KEY (period_id) REFERENCES period(id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX idx_transactions_period ON transactions(period_id)",
        "CREATE INDEX idx_transactions_account ON transactions(account_id)",
        "CREATE INDEX idx_transactions_date ON transactions(date)",
        "CREATE INDEX idx_budget_schedule_period ON budget_schedule(period_id)",
        "CREATE INDEX idx_budget_schedule_match ON budget_schedule(period_id, label, amount, status)",
    ]


def ensure_schema(conn: sqlite3.Connection | MySQLConnection) -> None:
    if not isinstance(conn, MySQLConnection):
        if sqlite_needs_multi_user_migration(conn):
            migrate_sqlite_multi_user(conn)
        else:
            conn.executescript(sqlite_schema())
        ensure_sqlite_user_columns(conn)
    else:
        conn.executescript(sqlite_schema())
        conn.execute("ALTER TABLE users ADD COLUMN last_login VARCHAR(32)")
    conn.execute(
        """
        INSERT OR IGNORE INTO transaction_labels(user_id, name)
        SELECT DISTINCT user_id, label FROM transactions WHERE label IS NOT NULL AND TRIM(label) <> ''
        """
    )
    conn.commit()


def sqlite_schema() -> str:
    return """
        CREATE TABLE IF NOT EXISTS users (
            id CHAR(36) NOT NULL PRIMARY KEY,
            email VARCHAR(320) NOT NULL UNIQUE,
            hashed_password VARCHAR(1024) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            is_superuser BOOLEAN NOT NULL DEFAULT 0,
            is_verified BOOLEAN NOT NULL DEFAULT 0,
            last_login TEXT
        );

        CREATE TABLE IF NOT EXISTS period (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            start_date TEXT,
            end_date TEXT,
            UNIQUE(user_id, name)
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            sort_index INTEGER NOT NULL DEFAULT 1,
            show_in_summary INTEGER NOT NULL DEFAULT 1,
            visible_if_empty INTEGER NOT NULL DEFAULT 1,
            UNIQUE(user_id, name)
        );

        CREATE TABLE IF NOT EXISTS transaction_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(user_id, name)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            period_id INTEGER NOT NULL REFERENCES period(id) ON DELETE CASCADE,
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
            user_id TEXT NOT NULL,
            period_id INTEGER NOT NULL REFERENCES period(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            opening REAL,
            UNIQUE(user_id, period_id, account_id)
        );

        CREATE TABLE IF NOT EXISTS monthly_budget (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 31),
            label TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS budget_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            period_id INTEGER NOT NULL REFERENCES period(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN ('scheduled', 'found', 'cancel'))
        );

        CREATE INDEX IF NOT EXISTS idx_transactions_period ON transactions(period_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
        CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_budget_schedule_period ON budget_schedule(period_id);
        CREATE INDEX IF NOT EXISTS idx_budget_schedule_match ON budget_schedule(period_id, label, amount, status);
        CREATE INDEX IF NOT EXISTS idx_budget_schedule_user ON budget_schedule(user_id);
        """


def sqlite_needs_multi_user_migration(conn: sqlite3.Connection) -> bool:
    has_period = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'period'"
    ).fetchone()
    return bool(has_period) and not table_has_column(conn, "period", "user_id")


def ensure_sqlite_user_columns(conn: sqlite3.Connection) -> None:
    if not table_has_column(conn, "users", "last_login"):
        conn.execute("ALTER TABLE users ADD COLUMN last_login TEXT")


def migrate_sqlite_multi_user(conn: sqlite3.Connection) -> None:
    if table_has_column(conn, "period", "user_id"):
        return
    existing_tables = [
        table
        for table in USER_SCOPED_TABLES
        if conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
    ]
    if not existing_tables:
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    for table in existing_tables:
        conn.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy")
    conn.executescript(sqlite_schema())
    copy_legacy_sqlite_data(conn)
    for table in existing_tables:
        conn.execute(f"DROP TABLE {table}_legacy")
    conn.execute("PRAGMA foreign_keys = ON")


def table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row["name"] == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def copy_legacy_sqlite_data(conn: sqlite3.Connection) -> None:
    legacy = LEGACY_USER_ID
    conn.execute(
        """
        INSERT INTO period(id, user_id, name, start_date, end_date)
        SELECT id, ?, name, start_date, end_date FROM period_legacy
        """,
        (legacy,),
    )
    conn.execute(
        """
        INSERT INTO accounts(id, user_id, name, sort_index, show_in_summary, visible_if_empty)
        SELECT id, ?, name, sort_index, show_in_summary, visible_if_empty FROM accounts_legacy
        """,
        (legacy,),
    )
    conn.execute(
        """
        INSERT INTO transaction_labels(id, user_id, name)
        SELECT id, ?, name FROM transaction_labels_legacy
        """,
        (legacy,),
    )
    conn.execute(
        """
        INSERT INTO monthly_budget(id, user_id, day, label, amount)
        SELECT id, ?, day, label, amount FROM monthly_budget_legacy
        """,
        (legacy,),
    )
    conn.execute(
        """
        INSERT INTO account_balances(id, user_id, period_id, account_id, opening)
        SELECT id, ?, period_id, account_id, opening FROM account_balances_legacy
        """,
        (legacy,),
    )
    conn.execute(
        """
        INSERT INTO budget_schedule(id, user_id, period_id, label, amount, status)
        SELECT id, ?, period_id, label, amount, status FROM budget_schedule_legacy
        """,
        (legacy,),
    )
    conn.execute(
        """
        INSERT INTO transactions(id, user_id, period_id, account_id, date, label, amount, sort_index, comment, created_at, updated_at)
        SELECT id, ?, period_id, account_id, date, label, amount, sort_index, comment, created_at, updated_at FROM transactions_legacy
        """,
        (legacy,),
    )


def adopt_legacy_data(conn: sqlite3.Connection | MySQLConnection, user_id: str) -> None:
    legacy_periods = int(conn.execute("SELECT COUNT(*) FROM period WHERE user_id = ?", (LEGACY_USER_ID,)).fetchone()[0])
    if not legacy_periods:
        return
    owned_periods = int(conn.execute("SELECT COUNT(*) FROM period WHERE user_id = ?", (user_id,)).fetchone()[0])
    if owned_periods:
        return
    for table in USER_SCOPED_TABLES:
        conn.execute(f"UPDATE {table} SET user_id = ? WHERE user_id = ?", (user_id, LEGACY_USER_ID))


def ensure_user_data(conn: sqlite3.Connection | MySQLConnection, user_id: str) -> None:
    has_periods = conn.execute("SELECT EXISTS(SELECT 1 FROM period WHERE user_id = ?)", (user_id,)).fetchone()[0]
    has_accounts = conn.execute("SELECT EXISTS(SELECT 1 FROM accounts WHERE user_id = ?)", (user_id,)).fetchone()[0]
    if has_periods or has_accounts:
        return
    seed_empty_database(conn, user_id)


def clear_all_data(conn: sqlite3.Connection | MySQLConnection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in (
        "transactions",
        "budget_schedule",
        "monthly_budget",
        "account_balances",
        "transaction_labels",
        "accounts",
        "period",
        "users",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM sqlite_sequence")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def seed_empty_database(conn: sqlite3.Connection | MySQLConnection, user_id: str) -> None:
    initial_data = load_initial_data()
    today = date.today()
    start_date = today.replace(day=1)
    default_period_name = f"{MONTH_NAMES[today.month - 1]} {today.year}"
    conn.execute(
        "INSERT INTO period(user_id, name, start_date, end_date) VALUES (?, ?, ?, NULL)",
        (user_id, default_period_name, start_date.isoformat()),
    )
    period_id = conn.execute(
        "SELECT id FROM period WHERE user_id = ? AND name = ?",
        (user_id, default_period_name),
    ).fetchone()["id"]

    for index, account in enumerate(initial_accounts(initial_data), start=1):
        account_name = account["name"]
        show_in_summary = 1 if account.get("show_in_summary", True) else 0
        conn.execute(
            "INSERT INTO accounts(user_id, name, sort_index, show_in_summary) VALUES (?, ?, ?, ?)",
            (user_id, account_name, index, show_in_summary),
        )
        account_id = conn.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND name = ?",
            (user_id, account_name),
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO account_balances(user_id, period_id, account_id, opening)
            VALUES (?, ?, ?, NULL)
            """,
            (user_id, period_id, account_id),
        )

    for label in initial_labels(initial_data):
        conn.execute("INSERT OR IGNORE INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, label))


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
