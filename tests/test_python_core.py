from __future__ import annotations

import os
import sqlite3
import unittest
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

import budget_cli
import database
import security
from app import user_export_filename
from endpoints.api import delete_label, delete_unused_labels, ensure_transaction_label, save_label_row, save_transaction_row, sync_internal_transfer
from endpoints.filters import parse_period_ids
from endpoints.imports import export_csv
from endpoints.period import period_summary_rows
from endpoints.periods import period_overview_totals
from endpoints.parameters import recurring_payment_candidates
from endpoints.summary import chart_summary_rows, parse_label_groups, summary_chart_view, summary_rows
from endpoints.transactions import planned_budget_rows, should_show_planned_budget_rows
from endpoints.tools import defined_labels, encode_label, labels_payload, merge_labels, used_labels
from i18n import frontend_messages, preferred_language, translate, use_language
from transfer_labels import is_internal_transfer_label, is_internal_transfer_group
from user_preferences import UserPreferences, defaults_for_language, use_preferences
from version import current_commit_id
from web_helpers import current_template_variant, format_date, normalize_date, parse_month, preferred_template_variant, use_template_variant


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


class TemplateVariantTests(unittest.TestCase):
    def test_template_variant_defaults_to_desktop(self) -> None:
        self.assertEqual(current_template_variant(), "desktop")

    def test_mobile_user_agent_selects_mobile_templates(self) -> None:
        self.assertEqual(preferred_template_variant("Mozilla/5.0 (iPhone) Mobile"), "mobile")
        self.assertEqual(preferred_template_variant("Mozilla/5.0 (Macintosh)"), "desktop")

    def test_template_variant_context_is_scoped(self) -> None:
        self.assertEqual(current_template_variant(), "desktop")
        with use_template_variant("mobile"):
            self.assertEqual(current_template_variant(), "mobile")
        self.assertEqual(current_template_variant(), "desktop")


class SummaryTests(unittest.TestCase):
    def test_period_summary_splits_scheduled_budget_by_income_and_expense(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "summary-user"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "s@example.test", "x"))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Jan"))
        conn.execute("INSERT INTO accounts(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Cash"))
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-02", "Food - Shop", -12),
        )
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Rent - Home", -100, "scheduled"),
        )
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Refund - Expected", 25, "scheduled"),
        )
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Salary - Main", 200, "found"),
        )

        rows = {row["label_group"]: row for row in period_summary_rows(conn, 1, user_id)}

        self.assertNotIn("Budget planifié", rows)
        self.assertEqual(rows["Futur entrée"]["income"], 25)
        self.assertEqual(rows["Futur entrée"]["expense"], 0)
        self.assertEqual(rows["Futur entrée"]["net"], 25)
        self.assertEqual(rows["Futur sortie"]["income"], 0)
        self.assertEqual(rows["Futur sortie"]["expense"], -100)
        self.assertEqual(rows["Futur sortie"]["net"], -100)
        self.assertNotIn("Salary", rows)

    def test_period_card_totals_match_period_overview_totals(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "summary-user"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "s@example.test", "x"))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Jan"))
        conn.execute("INSERT INTO accounts(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Cash"))
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-02", "Salary - Main", 200),
        )
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-03", "Virement interne - Savings", -50),
        )
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Rent - Home", -100, "scheduled"),
        )
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Refund - Expected", 25, "scheduled"),
        )
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Ignored - Found", 500, "found"),
        )

        totals = period_overview_totals(conn, 1, user_id)

        self.assertEqual(totals["actual_income"], 200)
        self.assertEqual(totals["actual_expense"], 0)
        self.assertEqual(totals["planned_income"], 25)
        self.assertEqual(totals["planned_expense"], -100)
        self.assertEqual(totals["income"], 225)
        self.assertEqual(totals["expense"], -100)
        self.assertEqual(totals["net"], 125)

    def test_global_summary_and_chart_include_only_scheduled_budget(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "summary-user"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "s@example.test", "x"))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Jan"))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (2, user_id, "Feb"))
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Rent - Home", -100, "scheduled"),
        )
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 2, "Salary - Main", 250, "scheduled"),
        )
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 2, "Food - Shop", -20, "cancel"),
        )
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 2, "Found - Bonus", 500, "found"),
        )

        table_rows = {row["label_group"]: row for row in summary_rows(conn, [1, 2], user_id)}
        chart_rows_by_period = {
            (int(row["period_id"]), row["label_group"]): row
            for row in chart_summary_rows(conn, [1, 2], user_id)
        }

        self.assertNotIn("Budget planifié", table_rows)
        self.assertEqual(table_rows["Futur entrée"]["income"], 250)
        self.assertEqual(table_rows["Futur entrée"]["expense"], 0)
        self.assertEqual(table_rows["Futur entrée"]["net"], 250)
        self.assertEqual(table_rows["Futur sortie"]["income"], 0)
        self.assertEqual(table_rows["Futur sortie"]["expense"], -100)
        self.assertEqual(table_rows["Futur sortie"]["net"], -100)
        self.assertEqual(chart_rows_by_period[(1, "Futur sortie")]["expense"], -100)
        self.assertEqual(chart_rows_by_period[(2, "Futur entrée")]["income"], 250)
        self.assertNotIn((2, "Found"), chart_rows_by_period)

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

    def test_planned_budget_transaction_rows_are_available_for_summary_link(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "summary-user"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "s@example.test", "x"))
        conn.execute("INSERT INTO period(id, user_id, name, start_date) VALUES (?, ?, ?, ?)", (1, user_id, "Jan", "2026-01-01"))
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Rent - Home", -100, "scheduled"),
        )
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Refund - Expected", 25, "scheduled"),
        )
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Salary - Main", 200, "found"),
        )

        rows = planned_budget_rows(conn, [1], user_id)
        income_rows = planned_budget_rows(conn, [1], user_id, "income")
        expense_rows = planned_budget_rows(conn, [1], user_id, "expense")

        self.assertTrue(should_show_planned_budget_rows("Budget planifié", True))
        self.assertTrue(should_show_planned_budget_rows("Futur entrée", True))
        self.assertTrue(should_show_planned_budget_rows("Futur sortie", True))
        self.assertFalse(should_show_planned_budget_rows("Budget planifié", False))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["label"], "Budget planifié")
        self.assertEqual(rows[0]["comment"], "Rent - Home")
        self.assertEqual(rows[0]["account_name"], "Budget")
        self.assertEqual(rows[0]["amount"], -100)
        self.assertEqual(len(income_rows), 1)
        self.assertEqual(income_rows[0]["label"], "Futur entrée")
        self.assertEqual(income_rows[0]["amount"], 25)
        self.assertEqual(len(expense_rows), 1)
        self.assertEqual(expense_rows[0]["label"], "Futur sortie")
        self.assertEqual(expense_rows[0]["amount"], -100)


class TransactionBudgetScheduleTests(unittest.TestCase):
    def test_saving_matching_transaction_reports_newly_found_budget(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "transaction-user"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "t@example.test", "x"))
        conn.execute(
            "INSERT INTO period(id, user_id, name, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
            (1, user_id, "Jan", "2026-01-01", "2026-01-31"),
        )
        conn.execute("INSERT INTO accounts(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Cash"))
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Rent - Home", -100, "scheduled"),
        )

        with patched_api_db(conn):
            result = save_transaction_row(
                {
                    "period_id": 1,
                    "account_id": 1,
                    "date": "2026-01-10",
                    "label": "Rent - Home",
                    "amount": "-100",
                    "comment": "",
                },
                user_id,
            )
            repeated = save_transaction_row(
                {
                    "period_id": 1,
                    "account_id": 1,
                    "date": "2026-01-11",
                    "label": "Rent - Home",
                    "amount": "-100",
                    "comment": "",
                },
                user_id,
            )

        self.assertEqual(
            result["budget_message"],
            "Budget trouvé: Rent - Home (-100,00). Statut passé en trouvé.",
        )
        self.assertNotIn("budget_message", repeated)
        status = conn.execute("SELECT status FROM budget_schedule").fetchone()["status"]
        self.assertEqual(status, "found")


class ParametersTests(unittest.TestCase):
    def test_recurring_payment_candidates_use_label_group_amount_and_three_distinct_periods(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "parameters-user"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "p@example.test", "x"))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Jan"))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (2, user_id, "Feb"))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (3, user_id, "Mar"))
        conn.execute("INSERT INTO accounts(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Cash"))
        for period_id, tx_date, label in (
            (1, "2026-01-05", "Rent - Home"),
            (2, "2026-02-10", "Rent - Apartment"),
            (3, "2026-03-15", "Rent - House"),
        ):
            conn.execute(
                "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, period_id, 1, tx_date, label, -750),
            )
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-06", "Only once", -20),
        )
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 2, 1, "2026-02-06", "Virement Interne - Cash", -100),
        )

        candidates = recurring_payment_candidates(conn, user_id)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["label"], "Rent - Home")
        self.assertEqual(candidates[0]["day"], 10)
        self.assertEqual(candidates[0]["amount_raw"], "-750.00")

    def test_recurring_payment_candidates_ignore_two_period_matches(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "parameters-user"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "p@example.test", "x"))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Jan"))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (2, user_id, "Feb"))
        conn.execute("INSERT INTO accounts(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Cash"))
        for period_id, tx_date in ((1, "2026-01-05"), (2, "2026-02-05")):
            conn.execute(
                "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, period_id, 1, tx_date, "Rent - Home", -750),
            )

        self.assertEqual(recurring_payment_candidates(conn, user_id), [])

    def test_recurring_payment_candidates_mark_existing_monthly_budget_labels(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "parameters-user"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "p@example.test", "x"))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Jan"))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (2, user_id, "Feb"))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (3, user_id, "Mar"))
        conn.execute("INSERT INTO accounts(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Cash"))
        conn.execute("INSERT INTO monthly_budget(user_id, day, label, amount) VALUES (?, ?, ?, ?)", (user_id, 5, "Rent - Home", -750))
        for period_id, tx_date, label in (
            (1, "2026-01-05", "Rent - Home"),
            (2, "2026-02-05", "Rent - Apartment"),
            (3, "2026-03-05", "Rent - House"),
        ):
            conn.execute(
                "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, period_id, 1, tx_date, label, -750),
            )

        candidates = recurring_payment_candidates(conn, user_id)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["label"], "Rent - Home")
        self.assertTrue(candidates[0]["existing"])

    def test_recurring_payment_candidates_only_use_last_four_periods(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "parameters-user"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "p@example.test", "x"))
        for period_id in range(1, 6):
            conn.execute(
                "INSERT INTO period(id, user_id, name, start_date) VALUES (?, ?, ?, ?)",
                (period_id, user_id, f"P{period_id}", f"2026-0{period_id}-01"),
            )
        conn.execute("INSERT INTO accounts(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Cash"))
        for period_id in (1, 2, 3):
            conn.execute(
                "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, period_id, 1, f"2026-0{period_id}-05", "Old - Match", -50),
            )

        self.assertEqual(recurring_payment_candidates(conn, user_id), [])

    def test_recurring_payment_candidates_are_sorted_by_day(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "parameters-user"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "p@example.test", "x"))
        for period_id in range(1, 4):
            conn.execute("INSERT INTO period(id, user_id, name, start_date) VALUES (?, ?, ?, ?)", (period_id, user_id, f"P{period_id}", f"2026-0{period_id}-01"))
        conn.execute("INSERT INTO accounts(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Cash"))
        for label, day, amount in (("Late - One", 20, -20), ("Early - One", 5, -10)):
            for period_id in range(1, 4):
                conn.execute(
                    "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, period_id, 1, f"2026-0{period_id}-{day:02d}", label, amount),
                )

        candidates = recurring_payment_candidates(conn, user_id)

        self.assertEqual([candidate["label"] for candidate in candidates], ["Early - One", "Late - One"])


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

    def test_delete_unused_labels_keeps_labels_used_by_any_budget_or_transaction(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        labels = ["Unused - Old", "Used - Tx", "Used - Monthly", "Used - Scheduled"]
        for label in labels:
            conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, label))
        conn.execute("INSERT INTO period(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Jan"))
        conn.execute("INSERT INTO accounts(id, user_id, name) VALUES (?, ?, ?)", (1, user_id, "Cash"))
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-01", "Used - Tx", -1),
        )
        conn.execute("INSERT INTO monthly_budget(user_id, day, label, amount) VALUES (?, ?, ?, ?)", (user_id, 1, "Used - Monthly", -2))
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, 1, "Used - Scheduled", -3, "scheduled"),
        )

        with patched_api_db(conn):
            result = delete_unused_labels(user_id)

        remaining = [row["name"] for row in conn.execute("SELECT name FROM transaction_labels ORDER BY name").fetchall()]
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["deleted"], [{"id": 1, "name": "Unused - Old"}])
        self.assertEqual(remaining, ["Used - Monthly", "Used - Scheduled", "Used - Tx"])

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
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount, comment) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-06", "Food - Old", -20, "already checked"),
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
        rows = conn.execute("SELECT label, comment FROM transactions ORDER BY date").fetchall()
        self.assertEqual([row["label"] for row in rows], ["Food - New", "Food - New"])
        self.assertEqual(rows[0]["comment"], "Move from Food - Old.")
        self.assertEqual(rows[1]["comment"], "Move from Food - Old. already checked")
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

    def test_label_merge_rejects_exact_same_label(self) -> None:
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
            (user_id, 1, 1, "2026-01-05", "Food - Old", -10),
        )

        with patched_tools_db(conn), self.assertRaises(ValueError):
            merge_labels({"source_labels": [encode_label("Food - Old")], "destination_label": ["Food - Old"]}, user_id)

    def test_label_merge_allows_case_only_correction(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Sortie - Di"))
        conn.execute("INSERT INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, "Sortie - DI"))
        conn.execute(
            "INSERT INTO period(id, user_id, name, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
            (1, user_id, "Jan", "2026-01-01", "2026-01-31"),
        )
        conn.execute("INSERT INTO accounts(id, user_id, name, sort_index) VALUES (?, ?, ?, ?)", (1, user_id, "Cash", 1))
        conn.execute(
            "INSERT INTO transactions(user_id, period_id, account_id, date, label, amount, comment) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, 1, 1, "2026-01-05", "Sortie - Di", -10, "old note"),
        )

        with patched_tools_db(conn):
            merge_labels({"source_labels": [encode_label("Sortie - Di")], "destination_label": ["Sortie - DI"]}, user_id)

        row = conn.execute("SELECT label, comment FROM transactions").fetchone()
        self.assertEqual(row["label"], "Sortie - DI")
        self.assertEqual(row["comment"], "Move from Sortie - Di. old note")

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


class PersonalBudgetImportTests(unittest.TestCase):
    def test_personal_budget_import_targets_current_user_schema(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "u@example.test", "x"))
        sheet = budget_cli.WorkbookSheet(
            "Jan-Feb",
            {
                1: {0: "du 01/01 -> 31/01"},
                2: {2: "cash"},
                3: {0: "Compte", 1: "Debut", 2: "Date", 3: "Intitulé", 4: "Montant"},
                4: {0: "cash", 1: "10,5", 2: "2026-01-05", 3: "food - old", 4: "-12,3"},
            },
        )

        summary = budget_cli.import_personal_budget_sheets(conn, [sheet], user_id)

        self.assertEqual(summary["periods"], 1)
        self.assertEqual(summary["transactions"], 1)
        period = conn.execute("SELECT user_id, name, start_date, end_date FROM period").fetchone()
        self.assertEqual(
            dict(period),
            {"user_id": user_id, "name": "Jan-Feb", "start_date": "2026-01-01", "end_date": "2026-01-31"},
        )
        account = conn.execute("SELECT user_id, name, visible_if_empty FROM accounts").fetchone()
        self.assertEqual(dict(account), {"user_id": user_id, "name": "Cash", "visible_if_empty": 1})
        labels = {
            (row["user_id"], row["name"])
            for row in conn.execute("SELECT user_id, name FROM transaction_labels").fetchall()
        }
        self.assertIn((user_id, "Food - Old"), labels)
        self.assertIn((user_id, "Virement Interne - Cash"), labels)
        transaction = conn.execute("SELECT user_id, date, label, amount FROM transactions").fetchone()
        self.assertEqual(dict(transaction), {"user_id": user_id, "date": "2026-01-05", "label": "Food - Old", "amount": -12.3})
        balance = conn.execute("SELECT user_id, opening FROM account_balances").fetchone()
        self.assertEqual(dict(balance), {"user_id": user_id, "opening": 10.5})


class CsvExportTests(unittest.TestCase):
    def test_user_export_filename_contains_timestamp(self) -> None:
        self.assertEqual(
            user_export_filename(datetime(2026, 6, 28, 9, 8, 7)),
            "budget-user-export-20260628-090807.xlsx",
        )

    def test_export_csv_uses_import_format_columns(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        database.ensure_schema(conn)
        user_id = "user-1"
        conn.execute("INSERT INTO users(id, email, hashed_password) VALUES (?, ?, ?)", (user_id, "u@example.test", "x"))
        conn.execute(
            "INSERT INTO period(id, user_id, name, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
            (1, user_id, "Jan", "2026-01-01", "2026-01-31"),
        )
        conn.execute("INSERT INTO accounts(id, user_id, name, sort_index) VALUES (?, ?, ?, ?)", (2, user_id, "Cash", 1))
        conn.execute(
            """
            INSERT INTO transactions(user_id, period_id, account_id, date, label, amount, sort_index, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, 1, 2, "2026-01-05", "Food - Old", -12.3, 2, "note"),
        )
        conn.execute(
            """
            INSERT INTO transactions(user_id, period_id, account_id, date, label, amount, sort_index, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, 1, 2, "2026-01-04", "Salary", 100, 1, ""),
        )

        exported = export_csv(conn, 1, 2, "mdy", "csv_header", user_id)

        self.assertEqual(
            exported.splitlines(),
            [
                "Date,Intitulé,Montant,Commentaire",
                "01/04/2026,Salary,100.00,",
                "01/05/2026,Food - Old,-12.30,note",
            ],
        )


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

    def test_mysql_engine_uses_pre_ping_for_stale_connections(self) -> None:
        self.assertEqual(database.engine_options("sqlite:////tmp/budget.sqlite3"), {})
        self.assertEqual(
            database.engine_options("mysql+pymysql://user:pass@example.test:3306/budget"),
            {"pool_pre_ping": True},
        )
        self.assertEqual(
            database.engine_options("mysql+aiomysql://user:pass@example.test:3306/budget"),
            {"pool_pre_ping": True},
        )

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
