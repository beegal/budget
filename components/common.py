from __future__ import annotations

import sqlite3
from functools import cache
from pathlib import Path

from web_helpers import render_template


ICONS_DIR = Path(__file__).resolve().parent.parent / "static" / "icons"


def row_options(rows: list[sqlite3.Row], selected: object | None, empty_label: str | None = None) -> str:
    chunks = []
    if empty_label is not None:
        chunks.append(render_template("components/select_option.html", value="", label=empty_label, selected=False))
    selected_value = "" if selected is None else str(selected)
    for row in rows:
        value = str(row["id"])
        chunks.append(
            render_template(
                "components/select_option.html",
                value=value,
                label=row["name"],
                selected=value == selected_value,
            )
        )
    return "".join(chunks)


def panel_message(title: str, heading: str | None = None) -> str:
    return render_template("components/panel_message.html", heading=heading or title)


def label_picker(label: str, attrs: str) -> str:
    return render_template("components/label_picker.html", label=label, attrs=attrs)


def row_action_buttons(kind: str, mode: str = "idle") -> str:
    editing = mode == "edit"
    deleting = mode == "delete"
    return render_template(
        "components/row_action_buttons.html",
        kind=kind,
        editing=editing,
        deleting=deleting,
    )


@cache
def icon(name: str) -> str:
    icon_path = ICONS_DIR / f"{name}.svg"
    return icon_path.read_text(encoding="utf-8")
