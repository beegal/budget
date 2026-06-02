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
