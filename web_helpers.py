from __future__ import annotations

import html
import sqlite3


def money(value: float | int | None) -> str:
    value = float(value or 0)
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value):,.2f} EUR".replace(",", " ").replace(".", ",")


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def one(data: dict[str, list[str]], key: str, default: str = "") -> str:
    return data.get(key, [default])[0].strip()


def period_label(row: sqlite3.Row) -> str:
    start = row["start_date"] if "start_date" in row.keys() else None
    end = row["end_date"] if "end_date" in row.keys() else None
    legacy = row["period"] if "period" in row.keys() else None
    if start and end:
        return f"du {start} -> {end}"
    if start:
        return f"du {start} -> en cours"
    return legacy or "Période libre"


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
        "hourglass": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h14M5 20h14M7 4c0 5 5 6 5 8s-5 3-5 8M17 4c0 5-5 6-5 8s5 3 5 8"/></svg>',
        "x": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>',
        "check": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 5 5L20 7"/></svg>',
    }
    return icons[name]


def layout(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} - Budget</title>
  <link rel="stylesheet" href="/static/style.css">
  <script defer src="/static/app.js"></script>
</head>
<body>
  <header class="topbar">
    <a class="brand" href="/">Budget</a>
    <nav>
      <a href="/">Périodes</a>
      <a href="/parameters">Paramètres</a>
      <a href="/transactions">Transactions</a>
    </nav>
  </header>
  <main>{body}</main>
</body>
</html>""".encode("utf-8")
