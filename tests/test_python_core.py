from __future__ import annotations

import os
import sqlite3
import unittest
from unittest.mock import patch

import database
from endpoints.api import ensure_transaction_label, sync_internal_transfer
from i18n import frontend_messages, preferred_language, translate, use_language
from transfer_labels import is_internal_transfer_label, is_internal_transfer_group
from user_preferences import UserPreferences, defaults_for_language, use_preferences
from version import current_commit_id
from web_helpers import format_date, normalize_date, parse_month


class DateParsingTests(unittest.TestCase):
    def test_dmy_parsing_with_two_digit_year(self) -> None:
        with use_preferences(UserPreferences(date_format="dmy")):
            self.assertEqual(normalize_date("1/12/25"), "2025-12-01")

    def test_mdy_parsing_when_day_and_month_are_ambiguous(self) -> None:
        with use_preferences(UserPreferences(date_format="mdy")):
            self.assertEqual(normalize_date("1/12/25"), "2025-01-12")

    def test_year_first_format(self) -> None:
        with use_preferences(UserPreferences(date_format="ymd")):
            self.assertEqual(normalize_date("2025-12-01"), "2025-12-01")

    def test_day_month_without_year_uses_current_year(self) -> None:
        with use_preferences(UserPreferences(date_format="dmy")):
            parsed = normalize_date("27/05")
        self.assertRegex(parsed or "", r"^\d{4}-05-27$")

    def test_month_parsing_ignores_accents(self) -> None:
        with patch("web_helpers.current_month_lookup", return_value={"mai": 5, "fevrier": 2}):
            self.assertEqual(parse_month("mai"), 5)
            self.assertEqual(parse_month("février"), 2)

    def test_display_date_uses_user_preference(self) -> None:
        with use_preferences(UserPreferences(date_format="dmy")):
            self.assertEqual(format_date("2026-05-27"), "27/05/2026")
        with use_preferences(UserPreferences(date_format="mdy")):
            self.assertEqual(format_date("2026-05-27"), "05/27/2026")
        with use_preferences(UserPreferences(date_format="ymd")):
            self.assertEqual(format_date("2026-05-27"), "2026-05-27")


class MultilingualTests(unittest.TestCase):
    def test_accept_language_prefers_supported_language_by_quality(self) -> None:
        self.assertEqual(preferred_language("es;q=0.9,nl-BE;q=0.8,en;q=0.7"), "nl")
        self.assertEqual(preferred_language("es;q=0.9,en-US;q=0.8"), "en")

    def test_unknown_accept_language_falls_back_to_default(self) -> None:
        self.assertEqual(preferred_language("es-MX,pt-BR;q=0.9"), "fr")

    def test_translation_uses_current_language_and_fallback(self) -> None:
        with use_language("en"):
            self.assertEqual(translate("periods.open"), "Open")
            self.assertIn("js.saved", frontend_messages())
        with use_language("unknown"):
            self.assertEqual(translate("periods.open"), "Ouvrir")

    def test_language_defaults_drive_user_profile_defaults(self) -> None:
        self.assertEqual(defaults_for_language("en").date_format, "mdy")
        self.assertEqual(defaults_for_language("fr").date_format, "dmy")

    def test_internal_transfer_labels_are_detected_in_supported_languages(self) -> None:
        self.assertTrue(is_internal_transfer_label("Virement Interne - Cash"))
        self.assertTrue(is_internal_transfer_label("Internal transfer - Cash"))
        self.assertTrue(is_internal_transfer_label("Interne Überweisung - Cash"))
        self.assertTrue(is_internal_transfer_label("Interne overschrijving - Cash"))
        self.assertTrue(is_internal_transfer_group("Interne Uberweisung"))
        self.assertFalse(is_internal_transfer_label("Internet"))


class InternalTransferTests(unittest.TestCase):
    def test_internal_transfer_creates_mirror_transaction(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        conn.execute(
            "INSERT INTO period(user_id, name, start_date, end_date) VALUES (?, ?, ?, ?)",
            (user_id, "Jan", "2026-01-01", "2026-01-31"),
        )
        period_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO accounts(user_id, name, sort_index) VALUES (?, ?, ?)", (user_id, "Cash", 1))
        cash_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO accounts(user_id, name, sort_index) VALUES (?, ?, ?)", (user_id, "Savings", 2))
        savings_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO transactions(user_id, period_id, account_id, date, label, amount, sort_index)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, period_id, cash_id, "2026-01-05", "Internal transfer - Savings", -50, 1),
        )
        source_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        sync_internal_transfer(conn, source_id, user_id)

        rows = conn.execute("SELECT * FROM transactions ORDER BY account_id, id").fetchall()
        self.assertEqual(len(rows), 2)
        mirror = conn.execute("SELECT * FROM transactions WHERE account_id = ?", (savings_id,)).fetchone()
        source = conn.execute("SELECT * FROM transactions WHERE id = ?", (source_id,)).fetchone()
        self.assertEqual(mirror["amount"], 50)
        self.assertEqual(mirror["label"], "Internal transfer - Cash")
        self.assertEqual(mirror["transfer_auto"], 1)
        self.assertEqual(mirror["transfer_pair_id"], source_id)
        self.assertEqual(source["transfer_pair_id"], mirror["id"])

    def test_internal_transfer_label_is_not_added_to_visible_labels(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        ensure_transaction_label(conn, "user-1", "Virement interne - Cash")
        ensure_transaction_label(conn, "user-1", "Courses")
        labels = conn.execute("SELECT name FROM transaction_labels ORDER BY name").fetchall()
        self.assertEqual([row["name"] for row in labels], ["Courses"])

    def test_internal_transfer_labels_are_seeded_for_accounts_on_startup(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(database.sqlite_schema())
        conn.execute("INSERT INTO accounts(user_id, name, sort_index) VALUES (?, ?, ?)", ("user-1", "Cash", 1))
        conn.execute("INSERT INTO accounts(user_id, name, sort_index) VALUES (?, ?, ?)", ("user-1", "Savings", 2))

        database.ensure_schema(conn)

        labels = conn.execute("SELECT name FROM transaction_labels ORDER BY name").fetchall()
        self.assertEqual([row["name"] for row in labels], ["Virement Interne - Cash", "Virement Interne - Savings"])


class SchemaMigrationTests(unittest.TestCase):
    def test_new_sqlite_database_runs_migrations_to_latest_version(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        database.ensure_schema(conn)

        self.assertEqual(database.schema_version(conn), database.LATEST_SCHEMA_VERSION)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()}
        self.assertIn("transfer_pair_id", columns)
        self.assertIn("transfer_auto", columns)

    def test_migrations_are_idempotent(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        database.ensure_schema(conn)
        database.ensure_schema(conn)

        self.assertEqual(database.schema_version(conn), database.LATEST_SCHEMA_VERSION)
        transfer_columns = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(transactions)").fetchall()
            if row["name"].startswith("transfer_")
        ]
        self.assertEqual(transfer_columns, ["transfer_pair_id", "transfer_auto"])

    def test_database_without_version_table_is_version_zero(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(database.sqlite_schema())
        conn.execute("ALTER TABLE transactions ADD COLUMN transfer_pair_id INTEGER")
        conn.execute("ALTER TABLE transactions ADD COLUMN transfer_auto INTEGER NOT NULL DEFAULT 0")

        self.assertEqual(database.schema_version(conn), 0)
        database.ensure_schema(conn)

        self.assertEqual(database.schema_version(conn), database.LATEST_SCHEMA_VERSION)


class DatabaseConfigurationTests(unittest.TestCase):
    def test_app_commit_can_be_set_from_environment(self) -> None:
        with patch.dict(os.environ, {"BUDGET_APP_COMMIT": "abc123"}, clear=False):
            self.assertEqual(current_commit_id(), "abc123")

    def test_database_url_takes_precedence_and_switches_async_driver(self) -> None:
        with patch.dict(os.environ, {"BUDGET_DATABASE_URL": "mysql+pymysql://user:pass@example.test:3306/budget"}, clear=False):
            self.assertEqual(database.database_backend(), "mysql")
            self.assertEqual(database.database_url(), "mysql+pymysql://user:pass@example.test:3306/budget")
            self.assertEqual(database.database_url(async_driver=True), "mysql+aiomysql://user:pass@example.test:3306/budget")

    def test_sqlite_url_uses_configured_path(self) -> None:
        with patch.dict(os.environ, {"BUDGET_DB_BACKEND": "sqlite"}, clear=False):
            os.environ.pop("BUDGET_DATABASE_URL", None)
            self.assertTrue(database.database_url().startswith("sqlite:///"))
            self.assertTrue(database.database_url(async_driver=True).startswith("sqlite+aiosqlite:///"))

    def test_driver_sql_adapts_insert_ignore(self) -> None:
        sql = "INSERT OR IGNORE INTO transaction_labels(user_id, name) VALUES (?, ?)"
        self.assertEqual(
            database.driver_sql(sql, "mysql", "format"),
            "INSERT IGNORE INTO transaction_labels(user_id, name) VALUES (%s, %s)",
        )
        self.assertEqual(
            database.driver_sql(sql, "postgresql", "pyformat"),
            "INSERT INTO transaction_labels (user_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        )


if __name__ == "__main__":
    unittest.main()
