from __future__ import annotations

import html
import sqlite3
import string
from datetime import date
from pathlib import Path

from config import DATE_ORDER, MONTH_LOOKUP, NUMBER_DECIMALS, strip_accents

TEMPLATES_DIR = Path(__file__).parent / "templates"


def render_template(name: str, **context: object) -> str:
    template_path = TEMPLATES_DIR / name
    if not template_path.exists():
        return f"Template {name} not found"
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


def row_options(rows: list[sqlite3.Row], selected: object | None, empty_label: str | None = None) -> str:
    chunks = []
    if empty_label is not None:
        chunks.append(f'<option value="">{esc(empty_label)}</option>')
    selected_value = "" if selected is None else str(selected)
    for row in rows:
        value = str(row["id"])
        mark = " selected" if value == selected_value else ""
        chunks.append(f'<option value="{value}"{mark}>{esc(row["name"])}</option>')
    return "".join(chunks)


def label_picker(label: str, attrs: str) -> str:
    return f"""<div class="label-picker" data-label-picker>
  <div class="label-picker-row">
    <input value="{esc(label)}" data-original="{esc(label)}" autocomplete="off" placeholder="Intitulé" {attrs} data-label-input>
    <button class="label-add" type="button" data-create-label hidden>+</button>
  </div>
  <div class="label-suggestions" data-label-suggestions hidden></div>
</div>"""


def row_action_buttons(kind: str, mode: str = "idle") -> str:
    editing = mode == "edit"
    deleting = mode == "delete"
    edit_hidden = "" if editing else " hidden"
    delete_hidden = "" if deleting else " hidden"
    return f"""<button type="button" class="row-confirm" data-confirm-{kind}{edit_hidden}>V</button>
    <button type="button" class="row-cancel" data-cancel-{kind}{edit_hidden}>X</button>
    <button type="button" class="row-delete" data-delete-{kind}{delete_hidden}>-</button>"""


def icon(name: str) -> str:
    icons = {
        "plus": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
        "clear-list": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h9M4 12h7M4 17h5M15 10l5 5M20 10l-5 5"/></svg>',
        "upload": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M5 20h14"/></svg>',
        "x": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>',
        "check": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 5 5L20 7"/></svg>',
        "trash": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V5h6v2M7 7l1 15h8l1-15M10 11v6M14 11v6"/></svg>',
        "ban": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path d="M7.8 7.8l8.4 8.4"/></svg>',
        "send": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h12M12 7l5 5-5 5M18 5h2v14h-2"/></svg>',
        "warning": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2.5 20h19L12 3z"/><path d="M12 8v6M12 17h.01"/></svg>',
    }
    return icons[name]


def layout(title: str, body: str) -> bytes:
    return render_template("layout.html", title=esc(title), body=body).encode("utf-8")
