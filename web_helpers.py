from __future__ import annotations

import html
import sqlite3
import string
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import DATE_ORDER, MONTH_LOOKUP, NUMBER_DECIMALS, strip_accents

TEMPLATES_DIR = Path(__file__).parent / "templates"
JINJA_TEMPLATES = {"layout.html", "parameters.html", "transactions.html", "imports.html"}
JINJA_ENV = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(("html",)),
)


def render_template(name: str, **context: object) -> str:
    template_path = TEMPLATES_DIR / name
    if not template_path.exists():
        return f"Template {name} not found"
    if name in JINJA_TEMPLATES:
        return JINJA_ENV.get_template(name).render(**context)
    template_content = template_path.read_text(encoding="utf-8")
    return string.Template(template_content).safe_substitute(**context)


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
            raise ValueError("Format de date inconnu")

        return date(year, month, day).isoformat()
    except (ValueError, KeyError, IndexError):
        raise ValueError(f"Date invalide: {value}")


def parse_month(value: str) -> int:
    normalized = strip_accents(value)
    if normalized in MONTH_LOOKUP:
        return MONTH_LOOKUP[normalized]
    return int(value)


def numeric_day_month(first: int, second: int) -> tuple[int, int]:
    if first > 12 and second <= 12:
        return first, second
    if second > 12 and first <= 12:
        return second, first
    if DATE_ORDER == "mdy":
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
    pattern = f"{{:,.{NUMBER_DECIMALS}f}}"
    return f"{sign}{pattern.format(abs(value))}".replace(",", " ").replace(".", ",")


def format_date(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return raw
    if DATE_ORDER == "mdy":
        return parsed.strftime("%m/%d/%Y")
    return parsed.strftime("%d/%m/%Y")


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def one(data: dict[str, list[str]], key: str, default: str = "") -> str:
    return data.get(key, [default])[0].strip()


def period_label(row: sqlite3.Row) -> str:
    start = row["start_date"] if "start_date" in row.keys() else None
    end = row["end_date"] if "end_date" in row.keys() else None
    if start and end:
        return f"du {format_date(start)} -> {format_date(end)}"
    if start:
        return f"du {format_date(start)} -> en cours"
    return "Période libre"


def layout(title: str, body: str) -> bytes:
    return render_template("layout.html", title=title, body=body).encode("utf-8")
