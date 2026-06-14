from __future__ import annotations

import os
import sqlite3
import unittest
from contextlib import contextmanager
from io import BytesIO
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

import budget_cli
import database
import security
from endpoints.api import delete_label, ensure_transaction_label, save_label_row, sync_internal_transfer
from endpoints.filters import parse_period_ids
from endpoints.summary import chart_summary_rows, parse_label_groups, summary_chart_view
from endpoints.tools import defined_labels, encode_label, labels_payload, merge_labels, used_labels
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


class SummaryTests(unittest.TestCase):
    def test_period_filter_none_returns_empty_selection(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        conn.execute("INSERT INTO period(user_id, name) VALUES (?, ?)", ("summary-user", "Jan"))
        periods = conn.execute("SELECT id, name FROM period").fetchall()

        selected, all_selected = parse_period_ids({"periods": ["none"]}, periods)

        self.assertFalse(all_selected)
        self.assertEqual(selected, [])

    def test_label_group_filter_accepts_text_values(self) -> None:
        selected, all_selected = parse_label_groups({"labels": ["Food,Salary"]}, ["Food", "Rent", "Salary"])

        self.assertFalse(all_selected)
        self.assertEqual(selected, ["Food", "Salary"])

    def test_label_group_filter_none_returns_empty_selection(self) -> None:
        selected, all_selected = parse_label_groups({"labels": ["none"]}, ["Food", "Rent"])

        self.assertFalse(all_selected)
        self.assertEqual(selected, [])

    def test_chart_summary_excludes_internal_transfer_groups(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "summary-user"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "s@example.test", "x"))
        conn.execute("INSERT INTO period(id, user_id, name, start_date, end_date) VALUES (?, ?, ?, ?, ?)", (1, user_id, "Jan", "2026-01-01", "2026-01-31"))
        conn.execute("INSERT INTO period(id, user_id, name, start_date, end_date) VALUES (?, ?, ?, ?, ?)", (2, user_id, "Feb", "2026-02-01", "2026-02-28"))
        conn.execute("INSERT INTO accounts(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Cash"))
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-02", "Food - Shop", -12),
        )
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-03", "Food - Refund", 2),
        )
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 2, 1, "2026-02-02", "Food - Shop", -8),
        )
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-04", "Salary - Main", 100),
        )
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 2, 1, "2026-02-03", "Virement Interne - Cash", 100),
        )

        periods = conn.execute("SELECT id, name FROM period WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()
        rows = chart_summary_rows(conn, [1, 2], user_id)
        chart = summary_chart_view(periods, [1, 2], ["Food", "Salary", "Virement Interne"], rows)
        income_graph = chart["graphs"][0]["view"]
        expense_graph = chart["graphs"][1]["view"]

        self.assertEqual([series["name"] for series in income_graph["series"]], ["Total", "Salary"])
        self.assertEqual(income_graph["series"][0]["sum"], "100,00 EUR")
        self.assertEqual(expense_graph["series"][0]["sum"], "18,00 EUR")
        self.assertNotIn("Salary", [series["name"] for series in expense_graph["series"]])
        self.assertEqual(
            expense_graph["series"][1]["point_views"][0]["tooltip"],
            "-10,00 EUR\nEntrées : 2,00 EUR\nSorties : 12,00 EUR",
        )
        self.assertEqual(expense_graph["series"][1]["point_views"][0]["href"], "/transactions?periods=1&q=Food")
        self.assertEqual(expense_graph["series"][1]["href"], "/transactions?periods=1%2C2&q=Food")


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


class LabelIdentifierTests(unittest.TestCase):
    def test_label_update_uses_label_id_and_updates_transactions(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Food - Old"))
        label_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO period(user_id, name, start_date, end_date)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, "Jan", "2026-01-01", "2026-01-31"),
        )
        period_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO accounts(user_id, name, sort_index) VALUES (?, ?, ?)", (user_id, "Cash", 1))
        account_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO transactions(user_id, period_id, account_id, date, label, amount, sort_index)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, period_id, account_id, "2026-01-05", "Food - Old", -10, 1),
        )

        with patched_api_db(conn):
            result = save_label_row({"id": label_id, "value": "Food - New"}, user_id)

        self.assertEqual(result["id"], label_id)
        self.assertEqual(result["value"], "Food - New")
        self.assertEqual(conn.execute("SELECT name FROM transaction_labels WHERE id = ?", (label_id,)).fetchone()["name"], "Food - New")
        self.assertEqual(conn.execute("SELECT label FROM transactions").fetchone()["label"], "Food - New")

    def test_label_delete_uses_label_id(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Food - Old"))
        label_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        with patched_api_db(conn):
            delete_label({"id": label_id}, user_id)

        self.assertIsNone(conn.execute("SELECT id FROM transaction_labels WHERE id = ?", (label_id,)).fetchone())

    def test_label_update_rejects_unknown_id(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)

        with patched_api_db(conn), self.assertRaises(ValueError):
            save_label_row({"id": 999, "value": "Food"}, "user-1")


class ToolsTests(unittest.TestCase):
    def test_tool_label_sources_are_split_between_defined_and_used_labels(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Defined - Only"))
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Food - Old"))
        conn.execute(
            "INSERT INTO period(id, user_id, name, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
            (1, user_id, "Jan", "2026-01-01", "2026-01-31"),
        )
        conn.execute("INSERT INTO accounts(id, user_id, name, sort_index) VALUES (?, ?, ?, ?)", (1, user_id, "Cash", 1))
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-05", "Used - Only", -10),
        )

        self.assertEqual([row["name"] for row in defined_labels(conn, user_id)], ["Defined - Only", "Food - Old"])
        self.assertEqual([row["name"] for row in used_labels(conn, user_id)], ["Used - Only"])
        self.assertEqual(labels_payload(used_labels(conn, user_id)), [{"name": "Used - Only"}])

    def test_label_merge_updates_data_and_deletes_source_label(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Food - Old"))
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Food - New"))
        conn.execute(
            "INSERT INTO period(id, user_id, name, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
            (1, user_id, "Jan", "2026-01-01", "2026-01-31"),
        )
        conn.execute("INSERT INTO accounts(id, user_id, name, sort_index) VALUES (?, ?, ?, ?)", (1, user_id, "Cash", 1))
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-05", "Food - Old", -10),
        )
        conn.execute(
            "INSERT INTO monthly_budget(user_id, day, label, amount) VALUES (?, ?, ?, ?)",
            (user_id, 1, "Food - Old", -100),
        )
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Food - Old", -100, "scheduled"),
        )

        with patched_tools_db(conn):
            redirect = merge_labels(
                {"source_labels": [encode_label("Food - Old")], "destination_label": ["Food - New"]},
                user_id,
            )

        self.assertTrue(redirect.startswith("/tools?message="))
        self.assertEqual(conn.execute("SELECT label FROM transactions").fetchone()["label"], "Food - New")
        self.assertEqual(conn.execute("SELECT label FROM monthly_budget").fetchone()["label"], "Food - New")
        self.assertEqual(conn.execute("SELECT label FROM budget_schedule").fetchone()["label"], "Food - New")
        self.assertIsNone(conn.execute("SELECT id FROM transaction_labels WHERE name = ?", ("Food - Old",)).fetchone())

    def test_label_merge_accepts_multiple_source_labels(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Food - Old"))
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Food - Older"))
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Food - New"))
        conn.execute(
            "INSERT INTO period(id, user_id, name, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
            (1, user_id, "Jan", "2026-01-01", "2026-01-31"),
        )
        conn.execute("INSERT INTO accounts(id, user_id, name, sort_index) VALUES (?, ?, ?, ?)", (1, user_id, "Cash", 1))
        for label in ("Food - Old", "Food - Older"):
            conn.execute(
                "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, 1, 1, "2026-01-05", label, -10),
            )

        with patched_tools_db(conn):
            merge_labels(
                {
                    "source_labels": [f"{encode_label('Food - Old')},{encode_label('Food - Older')}"],
                    "destination_label": ["Food - New"],
                },
                user_id,
            )

        labels = conn.execute("SELECT DISTINCT label FROM transactions").fetchall()
        self.assertEqual([row["label"] for row in labels], ["Food - New"])
        deleted = conn.execute(
            "SELECT id FROM transaction_labels WHERE name IN (?, ?)",
            ("Food - Old", "Food - Older"),
        ).fetchall()
        self.assertEqual(deleted, [])

    def test_label_merge_requires_source_selection(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Food - New"))

        with patched_tools_db(conn), self.assertRaises(ValueError):
            merge_labels({"source_labels": ["none"], "destination_label": ["Food - New"]}, user_id)

    def test_label_merge_can_create_destination_from_picker_text(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Food - Old"))
        conn.execute(
            "INSERT INTO period(id, user_id, name, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
            (1, user_id, "Jan", "2026-01-01", "2026-01-31"),
        )
        conn.execute("INSERT INTO accounts(id, user_id, name, sort_index) VALUES (?, ?, ?, ?)", (1, user_id, "Cash", 1))
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-05", "Food - Old", -10),
        )

        with patched_tools_db(conn):
            merge_labels({"source_labels": [encode_label("Food - Old")], "destination_label": ["Food - New"]}, user_id)

        self.assertEqual(conn.execute("SELECT label FROM transactions").fetchone()["label"], "Food - New")
        self.assertIsNotNone(conn.execute("SELECT id FROM transaction_labels WHERE name = ?", ("Food - New",)).fetchone())

    def test_label_merge_source_can_exist_only_in_transactions(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        conn.execute(
            "INSERT INTO period(id, user_id, name, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
            (1, user_id, "Jan", "2026-01-01", "2026-01-31"),
        )
        conn.execute("INSERT INTO accounts(id, user_id, name, sort_index) VALUES (?, ?, ?, ?)", (1, user_id, "Cash", 1))
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-05", "Historical - Typo", -10),
        )

        with patched_tools_db(conn):
            merge_labels({"source_labels": [encode_label("Historical - Typo")], "destination_label": ["Historical - Fixed"]}, user_id)

        self.assertEqual(conn.execute("SELECT label FROM transactions").fetchone()["label"], "Historical - Fixed")
        self.assertIsNotNone(conn.execute("SELECT id FROM transaction_labels WHERE name = ?", ("Historical - Fixed",)).fetchone())


@contextmanager
def patched_api_db(conn: sqlite3.Connection):
    @contextmanager
    def fake_db():
        yield conn

    with patch("endpoints.api.db", fake_db):
        yield


@contextmanager
def patched_tools_db(conn: sqlite3.Connection):
    @contextmanager
    def fake_db():
        yield conn

    with patch("endpoints.tools.db", fake_db):
        yield


class SchemaMigrationTests(unittest.TestCase):
    def test_new_sqlite_database_runs_migrations_to_latest_version(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        database.ensure_schema(conn)

        self.assertEqual(database.schema_version(conn), database.LATEST_SCHEMA_VERSION)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()}
        self.assertIn("transfer_pair_id", columns)
        self.assertIn("transfer_auto", columns)
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        self.assertIn("created_at", user_columns)

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


class SecurityConfigurationTests(unittest.TestCase):
    def test_security_limits_use_environment_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BUDGET_ONLY_HTTPS": "1",
                "BUDGET_MAX_UPLOAD": "1234",
                "BUDGET_MAX_ACCOUNT": "7",
                "BUDGET_MAX_DAILY_NEW_ACCOUNT": "2",
            },
            clear=False,
        ):
            self.assertTrue(security.only_https())
            self.assertEqual(security.max_upload_bytes(), 1234)
            self.assertEqual(security.max_accounts(), 7)
            self.assertEqual(security.max_daily_new_accounts(), 2)

    def test_security_limits_fall_back_to_yaml_config(self) -> None:
        config = {
            "security": {
                "only-https": True,
                "max-upload": 4567,
                "max-account": 8,
                "max-daily-new-account": 3,
                "zip-max-files": 20,
                "zip-max-uncompressed-factor": 4,
                "zip-max-compression-ratio": 12.5,
            }
        }
        with patch.dict(os.environ, {}, clear=True), patch("security.load_config", return_value=config):
            self.assertTrue(security.only_https())
            self.assertEqual(security.max_upload_bytes(), 4567)
            self.assertEqual(security.max_accounts(), 8)
            self.assertEqual(security.max_daily_new_accounts(), 3)
            self.assertEqual(security.zip_max_files(), 20)
            self.assertEqual(security.zip_max_uncompressed_factor(), 4)
            self.assertEqual(security.zip_max_compression_ratio(), 12.5)

    def test_workbook_zip_bomb_ratio_is_rejected(self) -> None:
        payload = BytesIO()
        with ZipFile(payload, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("xl/worksheets/sheet1.xml", "A" * 1000)

        payload.seek(0)
        with ZipFile(payload) as archive, patch.dict(
            os.environ,
            {
                "BUDGET_MAX_UPLOAD": "1000000",
                "BUDGET_ZIP_MAX_FILES": "20",
                "BUDGET_ZIP_MAX_UNCOMPRESSED_FACTOR": "5",
                "BUDGET_ZIP_MAX_COMPRESSION_RATIO": "1.1",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "compression ratio"):
                budget_cli.validate_xlsx_archive_limits(archive)


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

    def test_mysql_schema_uses_datetime_for_user_created_at(self) -> None:
        schema = "\n".join(database.mysql_schema_statements())
        self.assertIn("created_at DATETIME DEFAULT CURRENT_TIMESTAMP", schema)
        self.assertNotIn("created_at VARCHAR(32) DEFAULT CURRENT_TIMESTAMP", schema)


if __name__ == "__main__":
    unittest.main()
