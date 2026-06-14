from __future__ import annotations

from database import db
from i18n import translate
from user_preferences import (
    ensure_user_preferences,
    normalize_date_format,
    normalize_number_decimals,
)
from web_helpers import one, render_template, settings_tabs_context, user_layout


DATE_FORMAT_OPTIONS = [
    {"value": "dmy", "label": "jj/mm/yy"},
    {"value": "mdy", "label": "mm/jj/yy"},
    {"value": "ymd", "label": "yy-mm-jj"},
]


def page(user_id: str) -> bytes:
    with db() as conn:
        preferences = ensure_user_preferences(conn, user_id)
    body = render_template(
        "profile.html",
        number_decimals=preferences.number_decimals,
        date_formats=[
            {
                **option,
                "selected": option["value"] == preferences.date_format,
            }
            for option in DATE_FORMAT_OPTIONS
        ],
        **settings_tabs_context(user_id, "profile"),
    )
    return user_layout(translate("profile.title"), body, user_id)


def save(data: dict[str, list[str]], user_id: str) -> str:
    date_format = normalize_date_format(one(data, "date_format"))
    number_decimals = normalize_number_decimals(one(data, "number_decimals"))
    with db() as conn:
        ensure_user_preferences(conn, user_id)
        conn.execute(
            """
            UPDATE user_profiles
            SET date_format = ?, number_decimals = ?
            WHERE user_id = ?
            """,
            (date_format, number_decimals, user_id),
        )
    return "/profile"
