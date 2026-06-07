from __future__ import annotations

import calendar
import locale
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cache
from typing import Iterator

from config import get_date_format, get_default_locale, get_language, get_number_decimals, strip_accents
from i18n import current_language


DEFAULT_LOCALE = get_default_locale() or "fr_FR.UTF-8"
DEFAULT_DATE_FORMAT = get_date_format()
DEFAULT_NUMBER_DECIMALS = get_number_decimals()


@dataclass(frozen=True)
class UserPreferences:
    locale_name: str = DEFAULT_LOCALE
    date_format: str = DEFAULT_DATE_FORMAT
    number_decimals: int = DEFAULT_NUMBER_DECIMALS

    @property
    def date_order(self) -> str:
        if self.date_format == "mdy":
            return "mdy"
        if self.date_format == "ymd":
            return "ymd"
        return "dmy"

    def as_frontend_config(self) -> dict[str, object]:
        return {
            "dateFormat": self.date_format,
            "dateOrder": self.date_order,
            "numberDecimals": self.number_decimals,
        }


_CURRENT_PREFERENCES: ContextVar[UserPreferences] = ContextVar(
    "budget_user_preferences",
    default=UserPreferences(),
)


def current_preferences() -> UserPreferences:
    return _CURRENT_PREFERENCES.get()


@contextmanager
def use_preferences(preferences: UserPreferences) -> Iterator[None]:
    token = _CURRENT_PREFERENCES.set(preferences)
    try:
        yield
    finally:
        _CURRENT_PREFERENCES.reset(token)


def ensure_user_preferences(conn, user_id: str, language_id: str | None = None) -> UserPreferences:
    defaults = defaults_for_language(language_id)
    conn.execute(
        """
        INSERT OR IGNORE INTO user_profiles(user_id, locale, date_format, number_decimals)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, defaults.locale_name, defaults.date_format, defaults.number_decimals),
    )
    row = conn.execute(
        "SELECT locale, date_format, number_decimals FROM user_profiles WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return row_preferences(row)


def defaults_for_language(language_id: str | None) -> UserPreferences:
    language = get_language(language_id)
    return UserPreferences(
        locale_name=normalize_locale(language.get("locale")),
        date_format=normalize_date_format(language.get("date-format")),
        number_decimals=DEFAULT_NUMBER_DECIMALS,
    )


def row_preferences(row) -> UserPreferences:
    if row is None:
        return UserPreferences()
    return UserPreferences(
        locale_name=normalize_locale(row["locale"]),
        date_format=normalize_date_format(row["date_format"]),
        number_decimals=normalize_number_decimals(row["number_decimals"]),
    )


def normalize_locale(value: object) -> str:
    value = str(value or "").strip()
    return value or DEFAULT_LOCALE


def normalize_date_format(value: object) -> str:
    value = str(value or "").strip().lower()
    aliases = {
        "dmy": "dmy",
        "dd/mm/yy": "dmy",
        "dd/mm/yyyy": "dmy",
        "jj/mm/yy": "dmy",
        "jj/mm/yyyy": "dmy",
        "mdy": "mdy",
        "mm/dd/yy": "mdy",
        "mm/dd/yyyy": "mdy",
        "mm/jj/yy": "mdy",
        "mm/jj/yyyy": "mdy",
        "ymd": "ymd",
        "yy-mm-dd": "ymd",
        "yyyy-mm-dd": "ymd",
        "yy-mm-jj": "ymd",
        "yyyy-mm-jj": "ymd",
    }
    return aliases.get(value, DEFAULT_DATE_FORMAT)


def normalize_number_decimals(value: object) -> int:
    try:
        decimals = int(value)
    except (TypeError, ValueError):
        return DEFAULT_NUMBER_DECIMALS
    return max(0, min(decimals, 6))


def current_date_order() -> str:
    return current_preferences().date_order


def current_number_decimals() -> int:
    return current_preferences().number_decimals


def current_date_format() -> str:
    return current_preferences().date_format


def current_month_lookup() -> dict[str, int]:
    return month_lookup_for_language(current_language())


def month_lookup_for_language(language_id: str | None) -> dict[str, int]:
    return month_lookup_for_locale(defaults_for_language(language_id).locale_name)


@cache
def month_lookup_for_locale(locale_name: str) -> dict[str, int]:
    previous = locale.setlocale(locale.LC_TIME)
    try:
        for candidate in (locale_name, ""):
            try:
                locale.setlocale(locale.LC_TIME, candidate)
                break
            except locale.Error:
                continue
        return build_month_lookup()
    finally:
        locale.setlocale(locale.LC_TIME, previous)


def build_month_lookup() -> dict[str, int]:
    lookup = {}
    prefixes: dict[str, set[int]] = {}
    for index in range(1, 13):
        name = calendar.month_name[index]
        if name:
            normalized_name = strip_accents(name)
            lookup[normalized_name] = index
            for length in range(3, len(normalized_name)):
                prefixes.setdefault(normalized_name[:length], set()).add(index)
        abbreviation = calendar.month_abbr[index]
        if abbreviation:
            lookup[strip_accents(abbreviation).rstrip(".")] = index
    for prefix, indexes in prefixes.items():
        if len(indexes) == 1:
            lookup.setdefault(prefix, next(iter(indexes)))
    return lookup
