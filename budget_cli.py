from __future__ import annotations

import os
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from fastapi_users.password import PasswordHelper
from rich import box
from rich.console import Console
from rich.table import Table
import typer

import database
from user_preferences import ensure_user_preferences


ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = ROOT / "data" / "budget.sqlite3"
Backend = str
console = Console(width=160)
app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
    rich_markup_mode="rich",
    help="Administration et imports/exports Budget.",
)
db_app = typer.Typer(help="Gestion de la base de données.")
export_app = typer.Typer(help="Exports XLSX.")
import_app = typer.Typer(help="Imports XLSX.")
users_app = typer.Typer(help="Administration des utilisateurs.")
app.add_typer(db_app, name="db")
app.add_typer(export_app, name="export")
app.add_typer(import_app, name="import")
app.add_typer(users_app, name="users")
XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
FULL_EXPORT_VERSION = "4"
FULL_EXPORT_TABLES = [
    ("users", ["id", "email", "hashed_password", "is_active", "is_superuser", "is_verified", "last_login"]),
    ("user_profiles", ["id", "user_id", "locale", "date_format", "number_decimals"]),
    ("profile_seeded", ["id", "user_id", "seed_key", "seeded_at"]),
    ("period", ["id", "user_id", "name", "start_date", "end_date"]),
    ("accounts", ["id", "user_id", "name", "sort_index", "show_in_summary", "visible_if_empty"]),
    ("transaction_labels", ["id", "user_id", "name"]),
    ("monthly_budget", ["id", "user_id", "day", "label", "amount"]),
    ("account_balances", ["id", "user_id", "period_id", "account_id", "opening"]),
    ("budget_schedule", ["id", "user_id", "period_id", "label", "amount", "status"]),
    (
        "transactions",
        ["id", "user_id", "period_id", "account_id", "date", "label", "amount", "sort_index", "comment", "created_at", "updated_at"],
    ),
]
USER_EXPORT_VERSION = "3"
USER_EXPORT_TABLES = [
    ("user_profiles", ["id", "locale", "date_format", "number_decimals"]),
    ("profile_seeded", ["id", "seed_key", "seeded_at"]),
    ("period", ["id", "name", "start_date", "end_date"]),
    ("accounts", ["id", "name", "sort_index", "show_in_summary", "visible_if_empty"]),
    ("transaction_labels", ["id", "name"]),
    ("monthly_budget", ["id", "day", "label", "amount"]),
    ("account_balances", ["id", "period_id", "account_id", "opening"]),
    ("budget_schedule", ["id", "period_id", "label", "amount", "status"]),
    (
        "transactions",
        ["id", "period_id", "account_id", "date", "label", "amount", "sort_index", "comment", "created_at", "updated_at"],
    ),
]
INTEGER_COLUMNS = {
    "id",
    "period_id",
    "account_id",
    "sort_index",
    "show_in_summary",
    "visible_if_empty",
    "day",
    "number_decimals",
}
FLOAT_COLUMNS = {"amount", "opening"}


@dataclass
class WorkbookSheet:
    name: str
    rows: dict[int, dict[int, str]]


@app.callback()
def main(
    ctx: typer.Context,
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="Chemin vers la base SQLite."),
    db_backend: Backend = typer.Option(
        os.environ.get("BUDGET_DB_BACKEND", "sqlite"),
        "--db-backend",
        help="Backend de base de données historique: sqlite ou mysql.",
    ),
    database_url: str | None = typer.Option(
        os.environ.get("BUDGET_DATABASE_URL"),
        "--database-url",
        help="URL SQLAlchemy complète, par exemple sqlite:////tmp/budget.db ou mysql+pymysql://user:pass@host/db.",
    ),
) -> None:
    if database_url:
        os.environ["BUDGET_DATABASE_URL"] = database_url
        db_backend = database.database_backend()
    else:
        db_backend = db_backend.strip().lower()
        os.environ["BUDGET_DB_BACKEND"] = db_backend
    ctx.obj = {"db_path": db_path.expanduser(), "db_backend": db_backend}


def cli_context(ctx: typer.Context) -> tuple[Path, Backend]:
    return ctx.obj["db_path"], ctx.obj["db_backend"]


def handle_error(error: Exception) -> None:
    console.print(f"[bold red]Erreur:[/bold red] {error}")
    raise typer.Exit(1) from error


def ensure_database(db_path: Path, backend: Backend) -> None:
    if os.environ.get("BUDGET_DATABASE_URL"):
        with database.db():
            return
    if backend == "sqlite" and not db_path.exists():
        create_database(db_path, backend)
        console.print(f"[green]Base créée:[/green] {db_path}")


@db_app.command("create")
def create_db(ctx: typer.Context) -> None:
    """Recrée une base vide."""
    db_path, backend = cli_context(ctx)
    try:
        create_database(db_path, backend)
        console.print(f"[green]Base créée:[/green] {database_label(db_path, backend)}")
    except Exception as error:
        handle_error(error)


@export_app.command("full")
def export_full_command(ctx: typer.Context, export_path: Path = typer.Argument(..., help="Fichier .xlsx à créer.")) -> None:
    """Exporte toute la base, utilisateurs inclus."""
    db_path, backend = cli_context(ctx)
    try:
        ensure_database(db_path, backend)
        summary = export_full_database(db_path, export_path.expanduser(), backend)
        console.print(f"[green]Export complet terminé:[/green] {export_path}")
        print_count_summary(summary)
    except Exception as error:
        handle_error(error)


@export_app.command("user")
def export_user_command(
    ctx: typer.Context,
    user: str = typer.Argument(..., help="Email ou UUID utilisateur."),
    export_path: Path = typer.Argument(..., help="Fichier .xlsx à créer."),
) -> None:
    """Exporte uniquement les données métier d'un utilisateur."""
    db_path, backend = cli_context(ctx)
    try:
        ensure_database(db_path, backend)
        summary = export_user_database(db_path, export_path.expanduser(), user, backend)
        console.print(f"[green]Export utilisateur terminé:[/green] {export_path}")
        print_count_summary(summary)
    except Exception as error:
        handle_error(error)


@import_app.command("full")
def import_full_command(ctx: typer.Context, import_path: Path = typer.Argument(..., help="Export complet .xlsx.")) -> None:
    """Restaure toute la base depuis un export complet."""
    db_path, backend = cli_context(ctx)
    try:
        ensure_database(db_path, backend)
        resolved_path = resolve_xlsx_path(import_path.expanduser())
        summary = import_full_database(db_path, resolved_path, backend)
        console.print(f"[green]Import complet terminé:[/green] {resolved_path}")
        print_count_summary(summary)
    except Exception as error:
        handle_error(error)


@import_app.command("user")
def import_user_command(
    ctx: typer.Context,
    user: str = typer.Argument(..., help="Email ou UUID utilisateur cible."),
    import_path: Path = typer.Argument(..., help="Export utilisateur .xlsx."),
) -> None:
    """Remplace les données métier d'un utilisateur depuis un export utilisateur."""
    db_path, backend = cli_context(ctx)
    try:
        ensure_database(db_path, backend)
        resolved_path = resolve_xlsx_path(import_path.expanduser())
        summary = import_user_database(db_path, resolved_path, user, backend)
        console.print(f"[green]Import utilisateur terminé:[/green] {resolved_path}")
        print_count_summary(summary)
    except Exception as error:
        handle_error(error)


@users_app.command("list")
def list_users_command(ctx: typer.Context) -> None:
    """Liste les utilisateurs."""
    db_path, backend = cli_context(ctx)
    try:
        ensure_database(db_path, backend)
        print_users_table(list_users(db_path, backend))
    except Exception as error:
        handle_error(error)


@users_app.command("create")
def create_user_command(
    ctx: typer.Context,
    email: str = typer.Argument(..., help="Email du nouvel utilisateur."),
    password: str = typer.Option(..., "--password", "-p", prompt=True, hide_input=True, confirmation_prompt=True),
) -> None:
    """Crée un utilisateur."""
    db_path, backend = cli_context(ctx)
    try:
        ensure_database(db_path, backend)
        user = create_user(db_path, email, password, backend)
        console.print(f"[green]Utilisateur créé:[/green] {user['email']} ({user['id']})")
    except Exception as error:
        handle_error(error)


@users_app.command("set-password")
def set_password_command(
    ctx: typer.Context,
    user: str = typer.Argument(..., help="Email ou UUID utilisateur."),
    password: str = typer.Option(..., "--password", "-p", prompt=True, hide_input=True, confirmation_prompt=True),
) -> None:
    """Change le mot de passe d'un utilisateur."""
    db_path, backend = cli_context(ctx)
    try:
        ensure_database(db_path, backend)
        set_user_password(db_path, user, password, backend)
        console.print(f"[green]Mot de passe changé:[/green] {user}")
    except Exception as error:
        handle_error(error)


@users_app.command("enable")
def enable_user_command(ctx: typer.Context, user: str = typer.Argument(..., help="Email ou UUID utilisateur.")) -> None:
    """Active un utilisateur."""
    db_path, backend = cli_context(ctx)
    try:
        ensure_database(db_path, backend)
        set_user_active(db_path, user, True, backend)
        console.print(f"[green]Utilisateur activé:[/green] {user}")
    except Exception as error:
        handle_error(error)


@users_app.command("disable")
def disable_user_command(ctx: typer.Context, user: str = typer.Argument(..., help="Email ou UUID utilisateur.")) -> None:
    """Désactive un utilisateur."""
    db_path, backend = cli_context(ctx)
    try:
        ensure_database(db_path, backend)
        set_user_active(db_path, user, False, backend)
        console.print(f"[yellow]Utilisateur désactivé:[/yellow] {user}")
    except Exception as error:
        handle_error(error)


@users_app.command("make-admin")
def make_admin_command(ctx: typer.Context, user: str = typer.Argument(..., help="Email ou UUID utilisateur.")) -> None:
    """Marque un utilisateur comme admin."""
    db_path, backend = cli_context(ctx)
    try:
        ensure_database(db_path, backend)
        set_user_admin(db_path, user, True, backend)
        console.print(f"[green]Utilisateur admin:[/green] {user}")
    except Exception as error:
        handle_error(error)


@users_app.command("revoke-admin")
def revoke_admin_command(ctx: typer.Context, user: str = typer.Argument(..., help="Email ou UUID utilisateur.")) -> None:
    """Retire le rôle admin d'un utilisateur."""
    db_path, backend = cli_context(ctx)
    try:
        ensure_database(db_path, backend)
        set_user_admin(db_path, user, False, backend)
        console.print(f"[yellow]Utilisateur non admin:[/yellow] {user}")
    except Exception as error:
        handle_error(error)


def database_label(db_path: Path, backend: str) -> str:
    if os.environ.get("BUDGET_DATABASE_URL"):
        return os.environ["BUDGET_DATABASE_URL"]
    if backend == "mysql":
        return (
            f"mysql://{os.environ.get('BUDGET_MYSQL_HOST', '127.0.0.1')}:"
            f"{os.environ.get('BUDGET_MYSQL_PORT', '3306')}/"
            f"{os.environ.get('BUDGET_MYSQL_DATABASE', 'budget')}"
        )
    return str(db_path)


def create_database(db_path: Path, backend: str = "sqlite") -> None:
    if os.environ.get("BUDGET_DATABASE_URL"):
        with database.db() as conn:
            database.clear_all_data(conn)
        return
    if backend == "mysql":
        database.create_mysql_database()
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        database.ensure_schema(conn)
        database.clear_all_data(conn)


def open_database(db_path: Path, backend: str) -> sqlite3.Connection | database.MySQLConnection:
    if os.environ.get("BUDGET_DATABASE_URL") or backend != "sqlite":
        return database.db()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    database.ensure_schema(conn)
    return conn


def export_full_database(db_path: Path, export_path: Path, backend: str = "sqlite") -> dict[str, int]:
    export_path.parent.mkdir(parents=True, exist_ok=True)
    with open_database(db_path, backend) as conn:
        sheets: list[tuple[str, list[list[object]]]] = [
            (
                "_meta",
                [
                    ["key", "value"],
                    ["format", "budget-full-export"],
                    ["version", FULL_EXPORT_VERSION],
                    ["exported_at", datetime.now().isoformat(timespec="seconds")],
                ],
            )
        ]
        summary: dict[str, int] = {}
        for user in conn.execute("SELECT id FROM users").fetchall():
            ensure_user_preferences(conn, user["id"])
        for table_name, columns in FULL_EXPORT_TABLES:
            rows = conn.execute(f"SELECT {', '.join(columns)} FROM {table_name} ORDER BY id").fetchall()
            sheets.append((table_name, [columns, *[[row[column] for column in columns] for row in rows]]))
            summary[table_name] = len(rows)
    write_xlsx(export_path, sheets)
    return summary


def import_full_database(db_path: Path, import_path: Path, backend: str = "sqlite") -> dict[str, int]:
    sheets = {sheet.name: sheet for sheet in read_xlsx(import_path)}
    validate_full_import(sheets)
    with open_database(db_path, backend) as conn:
        database.clear_all_data(conn)
        summary: dict[str, int] = {}
        for table_name, columns in FULL_EXPORT_TABLES:
            if table_name not in sheets:
                summary[table_name] = 0
                continue
            rows = full_import_rows(sheets[table_name], columns)
            if rows:
                placeholders = ", ".join("?" for _ in columns)
                conn.executemany(
                    f"INSERT INTO {table_name}({', '.join(columns)}) VALUES ({placeholders})",
                    rows,
                )
            summary[table_name] = len(rows)
        conn.commit()
        return summary


def export_user_database(db_path: Path, export_path: Path, user_key: str, backend: str = "sqlite") -> dict[str, int]:
    export_path.parent.mkdir(parents=True, exist_ok=True)
    with open_database(db_path, backend) as conn:
        user = find_user(conn, user_key)
        if user is None:
            raise ValueError(f"Utilisateur introuvable: {user_key}")
        sheets, summary = user_export_sheets(conn, user["id"], user["email"])
    write_xlsx(export_path, sheets)
    return summary


def export_user_database_bytes(conn: sqlite3.Connection | database.MySQLConnection, user_id: str, email: str) -> bytes:
    sheets, _summary = user_export_sheets(conn, user_id, email)
    return xlsx_bytes(sheets)


def user_export_sheets(
    conn: sqlite3.Connection | database.MySQLConnection,
    user_id: str,
    email: str,
) -> tuple[list[tuple[str, list[list[object]]]], dict[str, int]]:
    sheets: list[tuple[str, list[list[object]]]] = [
        (
            "_meta",
            [
                ["key", "value"],
                ["format", "budget-user-export"],
                ["version", USER_EXPORT_VERSION],
                ["exported_at", datetime.now().isoformat(timespec="seconds")],
                ["email", email],
            ],
        )
    ]
    summary: dict[str, int] = {}
    ensure_user_preferences(conn, user_id)
    for table_name, columns in USER_EXPORT_TABLES:
        rows = conn.execute(
            f"SELECT {', '.join(columns)} FROM {table_name} WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        sheets.append((table_name, [columns, *[[row[column] for column in columns] for row in rows]]))
        summary[table_name] = len(rows)
    return sheets, summary


def import_user_database(db_path: Path, import_path: Path, user_key: str, backend: str = "sqlite") -> dict[str, int]:
    sheets = {sheet.name: sheet for sheet in read_xlsx(import_path)}
    validate_user_import(sheets)
    with open_database(db_path, backend) as conn:
        user = find_user(conn, user_key)
        if user is None:
            raise ValueError(f"Utilisateur introuvable: {user_key}")
        return import_user_sheets(conn, sheets, user["id"])


def import_user_database_bytes(
    conn: sqlite3.Connection | database.MySQLConnection,
    data: bytes,
    user_id: str,
) -> dict[str, int]:
    with ZipFile(BytesIO(data)) as archive:
        # Reuse the normal reader by writing through the same XML helpers on an in-memory archive.
        shared_strings = read_shared_strings(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        sheets = {}
        for sheet in workbook.find("m:sheets", XLSX_NS):
            name = sheet.attrib["name"]
            sheets[name] = WorkbookSheet(name, read_sheet_rows(archive, relmap[sheet.attrib[REL_ID]], shared_strings))
    validate_user_import(sheets)
    return import_user_sheets(conn, sheets, user_id)


def validate_user_import(sheets: dict[str, WorkbookSheet]) -> None:
    required_tables = [
        (table_name, columns)
        for table_name, columns in USER_EXPORT_TABLES
        if table_name != "user_profiles"
    ]
    missing = [table_name for table_name, _columns in required_tables if table_name not in sheets]
    if "_meta" not in sheets:
        missing.insert(0, "_meta")
    if missing:
        raise ValueError(f"Onglet(s) manquant(s) dans l'export utilisateur: {', '.join(missing)}")
    meta = rows_to_records(sheets["_meta"])
    meta_values = {str(row.get("key") or ""): str(row.get("value") or "") for row in meta}
    if meta_values.get("format") != "budget-user-export":
        raise ValueError("Le classeur n'est pas un export utilisateur Budget.")
    if meta_values.get("version") not in {"1", "2", USER_EXPORT_VERSION}:
        raise ValueError(f"Version d'export utilisateur non supportée: {meta_values.get('version') or '-'}")


def import_user_sheets(
    conn: sqlite3.Connection | database.MySQLConnection,
    sheets: dict[str, WorkbookSheet],
    user_id: str,
) -> dict[str, int]:
    clear_user_data(conn, user_id)
    id_maps: dict[str, dict[int, int]] = {"period": {}, "accounts": {}}
    summary: dict[str, int] = {}

    profile_rows = (
        full_import_rows(sheets["user_profiles"], ["id", "locale", "date_format", "number_decimals"])
        if "user_profiles" in sheets
        else []
    )
    for _old_id, locale, date_format, number_decimals in profile_rows[:1]:
        conn.execute(
            """
            INSERT INTO user_profiles(user_id, locale, date_format, number_decimals)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, locale, date_format, number_decimals),
        )
    summary["user_profiles"] = len(profile_rows[:1])

    seeded_rows = (
        full_import_rows(sheets["profile_seeded"], ["id", "seed_key", "seeded_at"])
        if "profile_seeded" in sheets
        else []
    )
    for _old_id, seed_key, seeded_at in seeded_rows:
        conn.execute(
            """
            INSERT OR IGNORE INTO profile_seeded(user_id, seed_key, seeded_at)
            VALUES (?, ?, ?)
            """,
            (user_id, seed_key, seeded_at),
        )
    summary["profile_seeded"] = len(seeded_rows)

    period_rows = full_import_rows(sheets["period"], ["id", "name", "start_date", "end_date"])
    for old_id, name, start_date, end_date in period_rows:
        conn.execute(
            "INSERT INTO period(user_id, name, start_date, end_date) VALUES (?, ?, ?, ?)",
            (user_id, name, start_date, end_date),
        )
        id_maps["period"][int(old_id)] = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    summary["period"] = len(period_rows)

    account_rows = full_import_rows(sheets["accounts"], ["id", "name", "sort_index", "show_in_summary", "visible_if_empty"])
    for old_id, name, sort_index, show_in_summary, visible_if_empty in account_rows:
        conn.execute(
            """
            INSERT INTO accounts(user_id, name, sort_index, show_in_summary, visible_if_empty)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, name, sort_index, show_in_summary, visible_if_empty),
        )
        id_maps["accounts"][int(old_id)] = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    summary["accounts"] = len(account_rows)

    label_rows = full_import_rows(sheets["transaction_labels"], ["id", "name"])
    for _old_id, name in label_rows:
        conn.execute("INSERT OR IGNORE INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, name))
    summary["transaction_labels"] = len(label_rows)

    monthly_rows = full_import_rows(sheets["monthly_budget"], ["id", "day", "label", "amount"])
    for _old_id, day, label, amount in monthly_rows:
        conn.execute(
            "INSERT INTO monthly_budget(user_id, day, label, amount) VALUES (?, ?, ?, ?)",
            (user_id, day, label, amount),
        )
    summary["monthly_budget"] = len(monthly_rows)

    balance_rows = full_import_rows(sheets["account_balances"], ["id", "period_id", "account_id", "opening"])
    for _old_id, period_id, account_id, opening in balance_rows:
        if int(period_id) not in id_maps["period"] or int(account_id) not in id_maps["accounts"]:
            continue
        conn.execute(
            """
            INSERT INTO account_balances(user_id, period_id, account_id, opening)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, id_maps["period"][int(period_id)], id_maps["accounts"][int(account_id)], opening),
        )
    summary["account_balances"] = len(balance_rows)

    schedule_rows = full_import_rows(sheets["budget_schedule"], ["id", "period_id", "label", "amount", "status"])
    for _old_id, period_id, label, amount, status in schedule_rows:
        if int(period_id) not in id_maps["period"]:
            continue
        conn.execute(
            """
            INSERT INTO budget_schedule(user_id, period_id, label, amount, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, id_maps["period"][int(period_id)], label, amount, status),
        )
    summary["budget_schedule"] = len(schedule_rows)

    transaction_rows = full_import_rows(
        sheets["transactions"],
        ["id", "period_id", "account_id", "date", "label", "amount", "sort_index", "comment", "created_at", "updated_at"],
    )
    for _old_id, period_id, account_id, tx_date, label, amount, sort_index, comment, created_at, updated_at in transaction_rows:
        if int(period_id) not in id_maps["period"] or int(account_id) not in id_maps["accounts"]:
            continue
        conn.execute(
            """
            INSERT INTO transactions(user_id, period_id, account_id, date, label, amount, sort_index, comment, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                id_maps["period"][int(period_id)],
                id_maps["accounts"][int(account_id)],
                tx_date,
                label,
                amount,
                sort_index,
                comment,
                created_at,
                updated_at,
            ),
        )
    summary["transactions"] = len(transaction_rows)
    conn.commit()
    return summary


def clear_user_data(conn: sqlite3.Connection | database.MySQLConnection, user_id: str) -> None:
    for table_name in (
        "transactions",
        "budget_schedule",
        "monthly_budget",
        "account_balances",
        "transaction_labels",
        "accounts",
        "period",
        "profile_seeded",
        "user_profiles",
    ):
        conn.execute(f"DELETE FROM {table_name} WHERE user_id = ?", (user_id,))


def find_user(conn: sqlite3.Connection | database.MySQLConnection, user_key: str):
    return conn.execute(
        "SELECT id, email FROM users WHERE id = ? OR LOWER(email) = LOWER(?)",
        (user_key, user_key),
    ).fetchone()


def create_user(db_path: Path, email: str, password: str, backend: str = "sqlite") -> dict[str, str]:
    if len(password) < 8:
        raise ValueError("Le mot de passe doit contenir au moins 8 caractères.")
    user_id = str(uuid.uuid4())
    password_hash = PasswordHelper().hash(password)
    with open_database(db_path, backend) as conn:
        conn.execute(
            """
            INSERT INTO users(id, email, hashed_password, is_active, is_superuser, is_verified, last_login)
            VALUES (?, ?, ?, 1, 0, 0, NULL)
            """,
            (user_id, email.strip().lower(), password_hash),
        )
        conn.commit()
    return {"id": user_id, "email": email.strip().lower()}


def set_user_password(db_path: Path, user_key: str, password: str, backend: str = "sqlite") -> None:
    if len(password) < 8:
        raise ValueError("Le mot de passe doit contenir au moins 8 caractères.")
    with open_database(db_path, backend) as conn:
        user = find_user(conn, user_key)
        if user is None:
            raise ValueError(f"Utilisateur introuvable: {user_key}")
        conn.execute("UPDATE users SET hashed_password = ? WHERE id = ?", (PasswordHelper().hash(password), user["id"]))
        conn.commit()


def set_user_active(db_path: Path, user_key: str, enabled: bool, backend: str = "sqlite") -> None:
    with open_database(db_path, backend) as conn:
        user = find_user(conn, user_key)
        if user is None:
            raise ValueError(f"Utilisateur introuvable: {user_key}")
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if enabled else 0, user["id"]))
        conn.commit()


def set_user_admin(db_path: Path, user_key: str, enabled: bool, backend: str = "sqlite") -> None:
    with open_database(db_path, backend) as conn:
        user = find_user(conn, user_key)
        if user is None:
            raise ValueError(f"Utilisateur introuvable: {user_key}")
        conn.execute("UPDATE users SET is_superuser = ? WHERE id = ?", (1 if enabled else 0, user["id"]))
        conn.commit()


def list_users(db_path: Path, backend: str = "sqlite") -> list[dict[str, object]]:
    with open_database(db_path, backend) as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT u.id AS user,
                       u.email,
                       COALESCE(u.last_login, '-') AS last_connection,
                       COUNT(DISTINCT a.id) AS account_count,
                       COUNT(DISTINCT t.id) AS transaction_count,
                       CASE WHEN u.is_active THEN 'enable' ELSE 'disable' END AS status,
                       CASE WHEN u.is_superuser THEN 'yes' ELSE 'no' END AS admin
                FROM users u
                LEFT JOIN accounts a ON a.user_id = u.id
                LEFT JOIN transactions t ON t.user_id = u.id
                GROUP BY u.id, u.email, u.last_login, u.is_active, u.is_superuser
                ORDER BY LOWER(u.email)
                """
            ).fetchall()
        ]


def print_users_table(rows: list[dict[str, object]]) -> None:
    headers = ["User", "email", "last connection", "number compte", "nombres transaction", "enable/disable", "admin"]
    keys = ["user", "email", "last_connection", "account_count", "transaction_count", "status", "admin"]
    table = Table(box=box.ASCII, show_lines=False)
    for header in headers:
        table.add_column(header, overflow="fold")
    for row in rows:
        table.add_row(*["" if row.get(key) is None else str(row.get(key)) for key in keys])
    console.print(table)


def print_count_summary(summary: dict[str, int]) -> None:
    table = Table(box=box.ASCII, show_header=False)
    table.add_column("Table")
    table.add_column("Lignes", justify="right")
    for table_name, count in summary.items():
        table.add_row(table_name, str(count))
    console.print(table)


def validate_full_import(sheets: dict[str, WorkbookSheet]) -> None:
    required_tables = [
        (table_name, columns)
        for table_name, columns in FULL_EXPORT_TABLES
        if table_name not in {"user_profiles", "profile_seeded"}
    ]
    missing = [table_name for table_name, _columns in required_tables if table_name not in sheets]
    if "_meta" not in sheets:
        missing.insert(0, "_meta")
    if missing:
        raise ValueError(f"Onglet(s) manquant(s) dans l'export complet: {', '.join(missing)}")
    meta = rows_to_records(sheets["_meta"])
    meta_values = {str(row.get("key") or ""): str(row.get("value") or "") for row in meta}
    if meta_values.get("format") != "budget-full-export":
        raise ValueError("Le classeur n'est pas un export complet Budget.")
    if meta_values.get("version") not in {"2", "3", FULL_EXPORT_VERSION}:
        raise ValueError(f"Version d'export non supportée: {meta_values.get('version') or '-'}")


def full_import_rows(sheet: WorkbookSheet, expected_columns: list[str]) -> list[tuple[object, ...]]:
    records = rows_to_records(sheet)
    rows: list[tuple[object, ...]] = []
    for index, record in enumerate(records, start=2):
        missing = [column for column in expected_columns if column not in record]
        if missing:
            raise ValueError(f"Onglet {sheet.name}, ligne {index}: colonne(s) manquante(s): {', '.join(missing)}")
        rows.append(tuple(import_cell_value(column, record[column]) for column in expected_columns))
    return rows


def rows_to_records(sheet: WorkbookSheet) -> list[dict[str, str]]:
    header = [sheet.rows.get(1, {}).get(column, "") for column in sorted(sheet.rows.get(1, {}))]
    if not header:
        return []
    records: list[dict[str, str]] = []
    for row_number in sorted(sheet.rows):
        if row_number == 1:
            continue
        row = sheet.rows[row_number]
        records.append({header[column]: row.get(column, "") for column in range(len(header))})
    return records


def import_cell_value(column: str, value: str) -> object:
    value = str(value or "").strip()
    if value == "":
        return None
    if column in INTEGER_COLUMNS:
        return int(value) if re.fullmatch(r"-?\d+", value) else value
    if column in FLOAT_COLUMNS:
        return float(value)
    return value


def write_xlsx(path: Path, sheets: list[tuple[str, list[list[object]]]]) -> None:
    with ZipFile(path, "w") as archive:
        write_xlsx_archive(archive, sheets)


def xlsx_bytes(sheets: list[tuple[str, list[list[object]]]]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        write_xlsx_archive(archive, sheets)
    return output.getvalue()


def write_xlsx_archive(archive: ZipFile, sheets: list[tuple[str, list[list[object]]]]) -> None:
    archive.writestr("[Content_Types].xml", xlsx_content_types(len(sheets)))
    archive.writestr("_rels/.rels", xlsx_root_rels())
    archive.writestr("xl/workbook.xml", xlsx_workbook(sheets))
    archive.writestr("xl/_rels/workbook.xml.rels", xlsx_workbook_rels(len(sheets)))
    for index, (_name, rows) in enumerate(sheets, start=1):
        archive.writestr(f"xl/worksheets/sheet{index}.xml", xlsx_sheet(rows))


def xlsx_content_types(sheet_count: int) -> str:
    sheet_overrides = "\n".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{sheet_overrides}</Types>"
    )


def xlsx_root_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def xlsx_workbook(sheets: list[tuple[str, list[list[object]]]]) -> str:
    sheet_tags = "\n".join(
        f'<sheet name="{escape(sheet_name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (sheet_name, _rows) in enumerate(sheets, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_tags}</sheets>"
        "</workbook>"
    )


def xlsx_workbook_rels(sheet_count: int) -> str:
    rel_tags = "\n".join(
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{rel_tags}</Relationships>"
    )


def xlsx_sheet(rows: list[list[object]]) -> str:
    row_tags = []
    for row_number, row in enumerate(rows, start=1):
        cells = []
        for column, value in enumerate(row):
            if value is None:
                continue
            cell_ref = f"{column_letters(column)}{row_number}"
            cells.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            )
        row_tags.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_tags)}</sheetData>'
        "</worksheet>"
    )


def column_letters(index: int) -> str:
    index += 1
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def resolve_xlsx_path(path: Path) -> Path:
    if path.exists():
        return path
    if path.suffix.lower() == ".xls":
        xlsx_path = path.with_suffix(".xlsx")
        if xlsx_path.exists():
            return xlsx_path
    raise FileNotFoundError(f"Classeur introuvable: {path}")


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


if __name__ == "__main__":
    app()
