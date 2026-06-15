from __future__ import annotations

import html
import json
import sqlite3
from datetime import date
from functools import cache
from pathlib import Path
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend_messages import template_not_found
from i18n import current_language, current_language_locale_tag, frontend_messages, language_options, translate
from config import strip_accents
from user_preferences import current_date_order, current_month_lookup, current_number_decimals, current_preferences

TEMPLATES_DIR = Path(__file__).parent / "templates"


@cache
def jinja_env(language: str) -> Environment:
    localized_dir = TEMPLATES_DIR / language
    search_paths = [localized_dir, TEMPLATES_DIR] if localized_dir.exists() else [TEMPLATES_DIR]
    env = Environment(
        loader=FileSystemLoader(search_paths),
        autoescape=select_autoescape(("html",)),
    )
    env.globals["t"] = translate
    return env


def render_template(template_name: str, **context: object) -> str:
    language = current_language()
    template_path = TEMPLATES_DIR / language / template_name
    fallback_path = TEMPLATES_DIR / template_name
    if not template_path.exists() and not fallback_path.exists():
        return template_not_found(template_name)
    return jinja_env(language).get_template(template_name).render(**context)


def normalize_date(value: object) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None

    # Replace separators with spaces for easier splitting
    for sep in ("-", "/", ".", ","):
        raw = raw.replace(sep, " ")
    parts = raw.split()

    try:
        if len(parts) == 3:
            if len(parts[0]) == 4:
                year = int(parts[0])
                month = parse_month(parts[1])
                day = int(parts[2])
            else:
                first = int(parts[0])
                second = parse_month(parts[1])
                day, month = numeric_day_month(first, second)
                year = parse_year(parts[2])
        elif len(parts) == 2:
            first = int(parts[0])
            second = parse_month(parts[1])
            day, month = numeric_day_month(first, second)
            year = date.today().year
        else:
            raise ValueError(translate("errors.unknown-date-format"))

        return date(year, month, day).isoformat()
    except (ValueError, KeyError, IndexError):
        raise ValueError(translate("errors.invalid-date", value=value))


def parse_month(value: str) -> int:
    normalized = strip_accents(value)
    month_lookup = current_month_lookup()
    if normalized in month_lookup:
        return month_lookup[normalized]
    return int(value)


def numeric_day_month(first: int, second: int) -> tuple[int, int]:
    if first > 12 and second <= 12:
        return first, second
    if second > 12 and first <= 12:
        return second, first
    if current_date_order() == "mdy":
        return second, first
    return first, second


def parse_year(value: str) -> int:
    year = int(value)
    if len(value) == 2:
        return 2000 + year
    return year


def money(value: float | int | str | None) -> str:
    return f"{format_number(value)} EUR"


def format_number(value: float | int | str | None) -> str:
    value = float(value or 0)
    sign = "-" if value < 0 else ""
    pattern = f"{{:,.{current_number_decimals()}f}}"
    return f"{sign}{pattern.format(abs(value))}".replace(",", " ").replace(".", ",")


def format_date(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return raw
    if current_date_order() == "mdy":
        return parsed.strftime("%m/%d/%Y")
    if current_date_order() == "ymd":
        return parsed.strftime("%Y-%m-%d")
    return parsed.strftime("%d/%m/%Y")


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def one(data: dict[str, list[str]], key: str, default: str = "") -> str:
    return data.get(key, [default])[0].strip()


def period_label(row: sqlite3.Row) -> str:
    start = row["start_date"] if "start_date" in row.keys() else None
    end = row["end_date"] if "end_date" in row.keys() else None
    if start and end:
        return f"{translate('periods.from')} {format_date(start)} -> {format_date(end)}"
    if start:
        return f"{translate('periods.from')} {format_date(start)} -> {translate('periods.current')}"
    return translate("periods.free-period")


def transaction_filter_url(period_ids: list[int], label: str) -> str:
    query = {"periods": ",".join(str(period_id) for period_id in period_ids), "q": label}
    return f"/transactions?{urlencode(query)}"


def layout(title: str, body: str) -> bytes:
    from components.common import icon

    preferences = current_preferences()
    frontend_config = {**preferences.as_frontend_config(), "language": current_language(), "locale": current_language_locale_tag()}
    return render_template(
        "layout.html",
        title=title,
        body=body,
        authenticated=False,
        show_admin=False,
        html_lang=current_language(),
        frontend_config=json.dumps(frontend_config, ensure_ascii=False),
        frontend_i18n=json.dumps(frontend_messages(), ensure_ascii=False),
        languages=language_options(),
        settings_menu_label=translate("nav.parameters-tools"),
        setup_icon=icon("setup"),
        logout_icon=icon("logout"),
    ).encode("utf-8")


def user_layout(title: str, body: str, user_id: str) -> bytes:
    from components.common import icon

    frontend_config = {**current_preferences().as_frontend_config(), "language": current_language(), "locale": current_language_locale_tag()}
    return render_template(
        "layout.html",
        title=title,
        body=body,
        authenticated=True,
        show_admin=user_is_admin(user_id),
        html_lang=current_language(),
        frontend_config=json.dumps(frontend_config, ensure_ascii=False),
        frontend_i18n=json.dumps(frontend_messages(), ensure_ascii=False),
        languages=language_options(),
        settings_menu_label=translate("nav.parameters-tools"),
        setup_icon=icon("setup"),
        logout_icon=icon("logout"),
    ).encode("utf-8")


def user_is_admin(user_id: str) -> bool:
    from database import db

    with db() as conn:
        row = conn.execute("SELECT is_superuser FROM users WHERE id = ?", (user_id,)).fetchone()
    return bool(row and row["is_superuser"])


def settings_tabs_context(user_id: str, active: str) -> dict[str, object]:
    return {
        "settings_active": active,
        "settings_show_admin": user_is_admin(user_id),
        "settings_tabs": {
            "parameters": translate("nav.parameters"),
            "profile": translate("nav.profile"),
            "tools": translate("nav.tools"),
            "admin": translate("nav.admin"),
        },
    }
