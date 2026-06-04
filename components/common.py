from __future__ import annotations

import sqlite3

from web_helpers import esc


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


def panel_message(title: str, heading: str | None = None) -> str:
    return f"<section class='panel'><h1>{esc(heading or title)}</h1></section>"


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
