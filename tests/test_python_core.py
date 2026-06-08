from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import database
from i18n import frontend_messages, preferred_language, translate, use_language
from user_preferences import UserPreferences, defaults_for_language, use_preferences
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


class DatabaseConfigurationTests(unittest.TestCase):
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
