from __future__ import annotations

import sqlite3
import calendar
import locale
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    text as sql_text,
)
from sqlalchemy.engine import Connection, Engine, URL, make_url
from sqlalchemy.exc import DBAPIError, IntegrityError as SQLAlchemyIntegrityError, ResourceClosedError

from backend_messages import invalid_mysql_name
from config import get_language, parse_simple_yaml

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("BUDGET_SQLITE_PATH", str(ROOT / "data" / "budget.sqlite3"))).expanduser()
INITIAL_DATA_PATH = ROOT / "initial-data.yaml"
INITIAL_DATA_SEED_KEY = "initial-data"
MIGRATIONS_DIR = ROOT / "migrations"
LATEST_SCHEMA_VERSION = 3
MIGRATION_FILENAME_RE = re.compile(r"^migration_(\d+)_(\d+)\.sql$")
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


metadata = MetaData()

users_table = Table(
    "users",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("hashed_password", String(1024), nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    Column("is_superuser", Boolean, nullable=False, server_default="0"),
    Column("is_verified", Boolean, nullable=False, server_default="0"),
    Column("last_login", String(32)),
    Column("created_at", DateTime, server_default=sql_text("CURRENT_TIMESTAMP")),
)

Table(
    "user_profiles",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("locale", String(64), nullable=False, server_default="fr_FR.UTF-8"),
    Column("date_format", String(16), nullable=False, server_default="dmy"),
    Column("number_decimals", Integer, nullable=False, server_default="2"),
    sqlite_autoincrement=True,
)

Table(
    "profile_seeded",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("seed_key", String(64), nullable=False),
    Column("seeded_at", DateTime, nullable=False, server_default=sql_text("CURRENT_TIMESTAMP")),
    UniqueConstraint("user_id", "seed_key", name="uniq_profile_seeded_user_key"),
    sqlite_autoincrement=True,
)

period_table = Table(
    "period",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", String(36), nullable=False),
    Column("name", String(255), nullable=False),
    Column("start_date", String(10)),
    Column("end_date", String(10)),
    UniqueConstraint("user_id", "name", name="uniq_period_user_name"),
    sqlite_autoincrement=True,
)

accounts_table = Table(
    "accounts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", String(36), nullable=False),
    Column("name", String(255), nullable=False),
    Column("sort_index", Integer, nullable=False, server_default="1"),
    Column("show_in_summary", Integer, nullable=False, server_default="1"),
    Column("visible_if_empty", Integer, nullable=False, server_default="1"),
    UniqueConstraint("user_id", "name", name="uniq_accounts_user_name"),
    sqlite_autoincrement=True,
)

Table(
    "transaction_labels",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", String(36), nullable=False),
    Column("name", String(255), nullable=False),
    UniqueConstraint("user_id", "name", name="uniq_labels_user_name"),
    sqlite_autoincrement=True,
)

transactions_table = Table(
    "transactions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", String(36), nullable=False),
    Column("period_id", Integer, ForeignKey("period.id", ondelete="CASCADE"), nullable=False),
    Column("account_id", Integer, ForeignKey("accounts.id"), nullable=False),
    Column("date", String(10)),
    Column("label", String(255), nullable=False),
    Column("amount", Float, nullable=False, server_default="0"),
    Column("sort_index", Integer, nullable=False, server_default="1"),
    Column("comment", Text),
    Column("created_at", DateTime, nullable=False, server_default=sql_text("CURRENT_TIMESTAMP")),
    Column("updated_at", DateTime, nullable=False, server_default=sql_text("CURRENT_TIMESTAMP")),
    sqlite_autoincrement=True,
)

Table(
    "account_balances",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", String(36), nullable=False),
    Column("period_id", Integer, ForeignKey("period.id", ondelete="CASCADE"), nullable=False),
    Column("account_id", Integer, ForeignKey("accounts.id"), nullable=False),
    Column("opening", Float),
    UniqueConstraint("user_id", "period_id", "account_id", name="uniq_account_balances_user_period_account"),
    sqlite_autoincrement=True,
)

Table(
    "monthly_budget",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", String(36), nullable=False),
    Column("day", Integer, nullable=False),
    Column("label", String(255), nullable=False),
    Column("amount", Float, nullable=False, server_default="0"),
    CheckConstraint("day BETWEEN 1 AND 31", name="check_monthly_budget_day"),
    sqlite_autoincrement=True,
)

budget_schedule_table = Table(
    "budget_schedule",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", String(36), nullable=False),
    Column("period_id", Integer, ForeignKey("period.id", ondelete="CASCADE"), nullable=False),
    Column("date", String(10)),
    Column("label", String(255), nullable=False),
    Column("amount", Float, nullable=False, server_default="0"),
    Column("status", String(20), nullable=False, server_default="scheduled"),
    CheckConstraint("status IN ('scheduled', 'found', 'cancel')", name="check_budget_schedule_status"),
    sqlite_autoincrement=True,
)

Index("idx_transactions_period", transactions_table.c.period_id)
Index("idx_transactions_account", transactions_table.c.account_id)
Index("idx_transactions_date", transactions_table.c.date)
Index("idx_transactions_user", transactions_table.c.user_id)
Index("idx_budget_schedule_period", budget_schedule_table.c.period_id)
Index("idx_budget_schedule_match", budget_schedule_table.c.period_id, budget_schedule_table.c.label, budget_schedule_table.c.amount, budget_schedule_table.c.status)
Index("idx_budget_schedule_user", budget_schedule_table.c.user_id)


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


class SQLAlchemyCursor:
    def __init__(self, result: Any):
        self._result = result
        self.rowcount = result.rowcount
        self.lastrowid = getattr(result, "lastrowid", None)
        self._columns = list(result.keys()) if result.returns_rows else []

    def fetchone(self) -> DictRow | None:
        try:
            row = self._result.fetchone()
        except ResourceClosedError:
            return None
        return self._dict_row(row) if row is not None else None

    def fetchall(self) -> list[DictRow]:
        try:
            rows = self._result.fetchall()
        except ResourceClosedError:
            return []
        return [self._dict_row(row) for row in rows]

    def _dict_row(self, row: Any) -> DictRow:
        columns = self._columns or list(row._mapping.keys())
        values = {column: row._mapping[column] for column in columns}
        return DictRow(values, columns)


class SQLAlchemyConnection:
    def __init__(self, engine: Engine):
        self._engine = engine
        self._conn: Connection = engine.connect()
        self._lastrowid = 0
        self.backend = engine.dialect.name
        self.paramstyle = engine.dialect.paramstyle

    def __enter__(self) -> "SQLAlchemyConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()

    def execute(self, sql: str, parameters: tuple[object, ...] | list[object] = ()) -> SQLAlchemyCursor | ResultCursor:
        normalized = sql.strip()
        if normalized.upper().startswith("PRAGMA ") and self.backend != "sqlite":
            return ResultCursor([], [])
        if normalized.upper() == "SELECT LAST_INSERT_ROWID()":
            return ResultCursor([(self._lastrowid,)], ["last_insert_rowid()"])
        if normalized.upper().startswith("DELETE FROM SQLITE_SEQUENCE") and self.backend != "sqlite":
            return ResultCursor([], [])
        converted_sql = driver_sql(sql, self.backend, self.paramstyle)
        try:
            result = self._conn.exec_driver_sql(converted_sql, tuple(parameters))
        except DBAPIError as error:
            if ignorable_database_error(error):
                return ResultCursor([], [])
            raise
        self._lastrowid = getattr(result, "lastrowid", None) or self._lastrowid
        return SQLAlchemyCursor(result)

    def executemany(self, sql: str, parameters: list[tuple[object, ...]]) -> SQLAlchemyCursor:
        result = self._conn.exec_driver_sql(driver_sql(sql, self.backend, self.paramstyle), parameters)
        self._lastrowid = getattr(result, "lastrowid", None) or self._lastrowid
        return SQLAlchemyCursor(result)

    def executescript(self, sql: str) -> None:
        if self.backend == "mysql":
            for statement in mysql_schema_statements():
                self.execute(statement)
            return
        for statement in split_sql_script(sql):
            self.execute(statement)

    def create_all(self) -> None:
        metadata.create_all(self._conn)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()
        self._engine.dispose()


MySQLConnection = SQLAlchemyConnection


def db() -> SQLAlchemyConnection:
    conn = connect()
    ensure_schema(conn)
    return conn


def database_backend() -> str:
    explicit_url = os.environ.get("BUDGET_DATABASE_URL")
    if explicit_url:
        return make_url(explicit_url).get_backend_name()
    return os.environ.get("BUDGET_DB_BACKEND", "sqlite").strip().lower()


def database_url(database_name: str | None = None, admin: bool = False, async_driver: bool = False) -> str:
    explicit_url = os.environ.get("BUDGET_DATABASE_URL")
    if explicit_url and not admin and database_name is None:
        return adapt_database_url(explicit_url, async_driver)
    backend = os.environ.get("BUDGET_DB_BACKEND", "sqlite").strip().lower()
    if backend == "mysql":
        user = os.environ.get("BUDGET_MYSQL_ROOT_USER" if admin else "BUDGET_MYSQL_USER", "root" if admin else "budget")
        password = os.environ.get("BUDGET_MYSQL_ROOT_PASSWORD" if admin else "BUDGET_MYSQL_PASSWORD", "")
        driver = "mysql+aiomysql" if async_driver else "mysql+pymysql"
        return (
            URL.create(
                driver,
                username=user,
                password=password,
                host=os.environ.get("BUDGET_MYSQL_HOST", "127.0.0.1"),
                port=int(os.environ.get("BUDGET_MYSQL_PORT", "3306")),
                database=None if admin else database_name or os.environ.get("BUDGET_MYSQL_DATABASE", "budget"),
            )
            .render_as_string(hide_password=False)
        )
    driver = "sqlite+aiosqlite" if async_driver else "sqlite"
    return f"{driver}:///{DB_PATH}"


def adapt_database_url(url: str, async_driver: bool = False) -> str:
    parsed = make_url(url)
    backend = parsed.get_backend_name()
    if backend == "sqlite":
        driver = "sqlite+aiosqlite" if async_driver else "sqlite"
    elif backend == "mysql":
        driver = "mysql+aiomysql" if async_driver else "mysql+pymysql"
    else:
        driver = parsed.drivername
    return parsed.set(drivername=driver).render_as_string(hide_password=False)


def engine_options(url: str) -> dict[str, object]:
    backend = make_url(url).get_backend_name()
    if backend == "mysql":
        return {"pool_pre_ping": True}
    return {}


def connect(database_name: str | None = None, admin: bool = False) -> SQLAlchemyConnection:
    if database_backend() == "sqlite":
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    url = database_url(database_name, admin)
    engine = create_engine(url, future=True, **engine_options(url))
    conn = SQLAlchemyConnection(engine)
    if conn.backend == "sqlite":
        conn.execute("PRAGMA foreign_keys = ON")
    return conn


def integrity_errors() -> tuple[type[BaseException], ...]:
    errors: list[type[BaseException]] = [sqlite3.IntegrityError, SQLAlchemyIntegrityError]
    try:
        import pymysql

        errors.append(pymysql.err.IntegrityError)
    except ImportError:
        pass
    return tuple(errors)


def mysql_connect(database_name: str | None = None) -> SQLAlchemyConnection:
    return connect(database_name)


def mysql_admin_connect() -> SQLAlchemyConnection:
    return connect(admin=True)


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
        raise ValueError(invalid_mysql_name(label, value))
    return value


def driver_sql(sql: str, backend: str, paramstyle: str) -> str:
    if backend == "mysql":
        return mysql_sql(sql)
    converted = sql
    if backend == "postgresql":
        converted = postgres_sql(converted)
    if paramstyle in {"format", "pyformat"}:
        converted = converted.replace("?", "%s")
    return converted


def mysql_sql(sql: str) -> str:
    converted = sql.replace("INSERT OR IGNORE INTO", "INSERT IGNORE INTO")
    converted = converted.replace("?", "%s")
    converted = converted.replace(
        "ON CONFLICT(user_id, period_id, account_id) DO UPDATE SET opening = excluded.opening",
        "ON DUPLICATE KEY UPDATE opening = VALUES(opening)",
    )
    return converted


def postgres_sql(sql: str) -> str:
    converted = re.sub(
        r"INSERT\s+OR\s+IGNORE\s+INTO\s+([^\s(]+)\s*(\([^)]*\))\s*VALUES\s*(\([^)]*\))",
        r"INSERT INTO \1 \2 VALUES \3 ON CONFLICT DO NOTHING",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return converted


def split_sql_script(sql: str) -> list[str]:
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


def ignorable_database_error(error: DBAPIError) -> bool:
    original = getattr(error, "orig", error)
    args = getattr(original, "args", ())
    code = args[0] if args else getattr(original, "pgcode", None)
    message = str(original).lower()
    return code in (1060, 1061, "42701", "42P07") or "duplicate column" in message or "already exists" in message


def create_core_schema(conn: sqlite3.Connection | SQLAlchemyConnection) -> None:
    if isinstance(conn, SQLAlchemyConnection):
        conn.create_all()
    else:
        conn.executescript(sqlite_schema())


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
            last_login VARCHAR(32),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL UNIQUE,
            locale VARCHAR(64) NOT NULL DEFAULT 'fr_FR.UTF-8',
            date_format VARCHAR(16) NOT NULL DEFAULT 'dmy',
            number_decimals INT NOT NULL DEFAULT 2,
            CONSTRAINT fk_user_profiles_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS profile_seeded (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            seed_key VARCHAR(64) NOT NULL,
            seeded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_profile_seeded_user_key (user_id, seed_key),
            CONSTRAINT fk_profile_seeded_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
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
            date VARCHAR(10),
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


def ensure_schema(conn: sqlite3.Connection | SQLAlchemyConnection) -> None:
    if isinstance(conn, SQLAlchemyConnection):
        if conn.backend == "sqlite":
            if sqlite_needs_multi_user_migration(conn):
                migrate_sqlite_multi_user(conn)
            else:
                create_core_schema(conn)
            ensure_sqlite_user_columns(conn)
        else:
            create_core_schema(conn)
            conn.execute("ALTER TABLE users ADD COLUMN last_login VARCHAR(32)")
    elif sqlite_needs_multi_user_migration(conn):
        migrate_sqlite_multi_user(conn)
        ensure_sqlite_user_columns(conn)
    else:
        conn.executescript(sqlite_schema())
        ensure_sqlite_user_columns(conn)
    run_schema_migrations(conn)
    conn.execute(
        """
        INSERT OR IGNORE INTO transaction_labels(user_id, name)
        SELECT DISTINCT user_id, label FROM transactions WHERE label IS NOT NULL AND TRIM(label) <> ''
        """
    )
    ensure_internal_transfer_labels(conn)
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
            last_login TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            locale TEXT NOT NULL DEFAULT 'fr_FR.UTF-8',
            date_format TEXT NOT NULL DEFAULT 'dmy',
            number_decimals INTEGER NOT NULL DEFAULT 2
        );

        CREATE TABLE IF NOT EXISTS profile_seeded (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            seed_key TEXT NOT NULL,
            seeded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, seed_key)
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
            date TEXT,
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
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            locale TEXT NOT NULL DEFAULT 'fr_FR.UTF-8',
            date_format TEXT NOT NULL DEFAULT 'dmy',
            number_decimals INTEGER NOT NULL DEFAULT 2
        );
        CREATE TABLE IF NOT EXISTS profile_seeded (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            seed_key TEXT NOT NULL,
            seeded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, seed_key)
        );
        """
    )


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


def table_has_column(conn: sqlite3.Connection | SQLAlchemyConnection, table: str, column: str) -> bool:
    if isinstance(conn, SQLAlchemyConnection) and conn.backend == "mysql":
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = ?
              AND column_name = ?
            """,
            (table, column),
        ).fetchone()
        return bool(row and int(row["count"] or 0))
    if isinstance(conn, SQLAlchemyConnection) and conn.backend not in {"sqlite", "mysql"}:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = ?
              AND column_name = ?
            """,
            (table, column),
        ).fetchone()
        return bool(row and int(row["count"] or 0))
    return any(row["name"] == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def table_exists(conn: sqlite3.Connection | SQLAlchemyConnection, table: str) -> bool:
    if isinstance(conn, SQLAlchemyConnection) and conn.backend == "mysql":
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = ?
            """,
            (table,),
        ).fetchone()
        return bool(row and int(row["count"] or 0))
    if isinstance(conn, SQLAlchemyConnection) and conn.backend not in {"sqlite", "mysql"}:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = ?
            """,
            (table,),
        ).fetchone()
        return bool(row and int(row["count"] or 0))
    return bool(
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
    )


def schema_version(conn: sqlite3.Connection | SQLAlchemyConnection) -> int:
    if not table_exists(conn, "schema_version"):
        return 0
    row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
    return int(row["version"] or 0) if row else 0


def migration_files() -> dict[int, tuple[int, Path]]:
    migrations: dict[int, tuple[int, Path]] = {}
    if not MIGRATIONS_DIR.exists():
        return migrations
    for path in MIGRATIONS_DIR.iterdir():
        match = MIGRATION_FILENAME_RE.match(path.name)
        if not match:
            continue
        source_version = int(match.group(1))
        target_version = int(match.group(2))
        if source_version in migrations:
            raise RuntimeError(f"Duplicate migration source version {source_version}: {path.name}")
        migrations[source_version] = (target_version, path)
    return migrations


def run_schema_migrations(conn: sqlite3.Connection | SQLAlchemyConnection) -> None:
    current_version = schema_version(conn)
    migrations = migration_files()
    while current_version < LATEST_SCHEMA_VERSION:
        migration = migrations.get(current_version)
        if migration is None:
            raise RuntimeError(f"Missing migration from schema version {current_version}")
        target_version, path = migration
        if target_version <= current_version:
            raise RuntimeError(f"Invalid migration target in {path.name}")
        execute_migration_file(conn, path)
        migrated_version = schema_version(conn)
        if migrated_version < target_version:
            raise RuntimeError(f"Migration {path.name} did not update schema_version to {target_version}")
        current_version = migrated_version


def execute_migration_file(conn: sqlite3.Connection | SQLAlchemyConnection, path: Path) -> None:
    for statement in split_sql_script(path.read_text(encoding="utf-8")):
        try:
            conn.execute(statement)
        except sqlite3.DatabaseError as error:
            if ignorable_migration_error(error):
                continue
            raise
        except DBAPIError as error:
            if ignorable_migration_error(error):
                continue
            raise


def ignorable_migration_error(error: BaseException) -> bool:
    original = getattr(error, "orig", error)
    message = str(original).lower()
    args = getattr(original, "args", ())
    code = args[0] if args else getattr(original, "pgcode", None)
    return code in (1060, 1061, "42701", "42P07") or "duplicate column" in message or "already exists" in message


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
        INSERT INTO budget_schedule(id, user_id, period_id, date, label, amount, status)
        SELECT id, ?, period_id, NULL, label, amount, status FROM budget_schedule_legacy
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


def ensure_user_data(conn: sqlite3.Connection | MySQLConnection, user_id: str, language_id: str | None = None) -> None:
    if profile_seed_done(conn, user_id, INITIAL_DATA_SEED_KEY):
        return
    seed_empty_database(conn, user_id, language_id)
    mark_profile_seed_done(conn, user_id, INITIAL_DATA_SEED_KEY)


def profile_seed_done(conn: sqlite3.Connection | MySQLConnection, user_id: str, seed_key: str) -> bool:
    """Return whether a one-shot user profile seed already ran.

    `profile_seeded` is intentionally separate from user preferences: it records
    irreversible bootstrap jobs per user. Today the only seed key is
    `initial-data`, used to create the default accounts, labels, budget and first
    period at first login.
    """
    row = conn.execute(
        "SELECT 1 FROM profile_seeded WHERE user_id = ? AND seed_key = ?",
        (user_id, seed_key),
    ).fetchone()
    if row is not None:
        return True
    has_periods = conn.execute("SELECT EXISTS(SELECT 1 FROM period WHERE user_id = ?)", (user_id,)).fetchone()[0]
    has_accounts = conn.execute("SELECT EXISTS(SELECT 1 FROM accounts WHERE user_id = ?)", (user_id,)).fetchone()[0]
    if has_periods or has_accounts:
        mark_profile_seed_done(conn, user_id, seed_key)
        return True
    return False


def mark_profile_seed_done(conn: sqlite3.Connection | MySQLConnection, user_id: str, seed_key: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO profile_seeded(user_id, seed_key) VALUES (?, ?)",
        (user_id, seed_key),
    )


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
        "profile_seeded",
        "user_profiles",
        "users",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM sqlite_sequence")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def seed_empty_database(conn: sqlite3.Connection | MySQLConnection, user_id: str, language_id: str | None = None) -> None:
    initial_data = load_initial_data()
    localized_initial_data = initial_data_for_language(initial_data, language_id)
    today = date.today()
    start_date = today.replace(day=1)
    default_period_name = f"{month_name_for_language(today.month, language_id)} {today.year}"
    conn.execute(
        "INSERT INTO period(user_id, name, start_date, end_date) VALUES (?, ?, ?, NULL)",
        (user_id, default_period_name, start_date.isoformat()),
    )
    period_id = conn.execute(
        "SELECT id FROM period WHERE user_id = ? AND name = ?",
        (user_id, default_period_name),
    ).fetchone()["id"]

    for index, account in enumerate(initial_accounts(localized_initial_data), start=1):
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

    from transfer_labels import is_internal_transfer_label

    for label in initial_labels(localized_initial_data):
        if is_internal_transfer_label(label):
            continue
        conn.execute("INSERT OR IGNORE INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, label))
    ensure_internal_transfer_labels(conn, user_id)


def ensure_internal_transfer_labels(conn: sqlite3.Connection | MySQLConnection, user_id: str | None = None) -> None:
    from transfer_labels import internal_transfer_label_for_account

    if user_id:
        accounts = conn.execute(
            "SELECT user_id, name FROM accounts WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()
    else:
        accounts = conn.execute("SELECT user_id, name FROM accounts ORDER BY user_id, name").fetchall()
    for account in accounts:
        label = internal_transfer_label_for_account(account["name"])
        if label.endswith(" - "):
            continue
        conn.execute(
            "INSERT OR IGNORE INTO transaction_labels(user_id, name) VALUES (?, ?)",
            (account["user_id"], label),
        )


def load_initial_data() -> dict[str, Any]:
    if not INITIAL_DATA_PATH.exists():
        return default_initial_data()
    parsed = parse_simple_yaml(INITIAL_DATA_PATH.read_text(encoding="utf-8"))
    return parsed if parsed else default_initial_data()


def default_initial_data() -> dict[str, Any]:
    return {
        "languages": {
            "fr": {
                "accounts": [
                    {"name": "Compte courant", "show_in_summary": True},
                    {"name": "Compte epargne", "show_in_summary": True},
                ],
                "labels": ["Salaire", "Courses", "Loyer", "Electricite", "Internet", "Transport", "Restaurant"],
            }
        }
    }


def initial_data_for_language(initial_data: dict[str, Any], language_id: str | None) -> dict[str, Any]:
    languages = initial_data.get("languages")
    if not isinstance(languages, dict):
        return initial_data
    requested = str(language_id or "").strip().lower()
    if requested and isinstance(languages.get(requested), dict):
        return languages[requested]
    default_language = next(iter(languages.values()), {})
    return default_language if isinstance(default_language, dict) else {}


def month_name_for_language(month: int, language_id: str | None) -> str:
    language = get_language(language_id)
    previous_locale = locale.setlocale(locale.LC_TIME)
    try:
        for locale_name in (language.get("locale", ""), ""):
            try:
                locale.setlocale(locale.LC_TIME, locale_name)
                return calendar.month_name[month]
            except locale.Error:
                continue
            except IndexError:
                return str(month)
        return calendar.month_name[month]
    finally:
        locale.setlocale(locale.LC_TIME, previous_locale)


def initial_accounts(initial_data: dict[str, Any]) -> list[dict[str, Any]]:
    fallback = initial_data_for_language(default_initial_data(), "fr")
    accounts = initial_data.get("accounts") or fallback["accounts"]
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
    return normalized or fallback["accounts"]


def initial_labels(initial_data: dict[str, Any]) -> list[str]:
    fallback = initial_data_for_language(default_initial_data(), "fr")
    labels = initial_data.get("labels") or fallback["labels"]
    return [str(label).strip() for label in labels if str(label).strip()]
