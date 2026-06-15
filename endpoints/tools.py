from __future__ import annotations

import base64
import json
import sqlite3
from urllib.parse import parse_qs, quote

from components.common import label_picker
from database import db
from i18n import translate
from transfer_labels import is_internal_transfer_label, normalized_text
from web_helpers import one, render_template, settings_tabs_context, user_layout


def page(user_id: str, query: str = "") -> bytes:
    params = parse_qs(query)
    with db() as conn:
        defined = defined_labels(conn, user_id)
        used = used_labels(conn, user_id)
    label_selector = {
        "name": "source_labels",
        "value": "none",
        "empty_mode": "none",
        "tags": [],
        "placeholder": translate("tools.merge-from-placeholder"),
        "toggle_label": translate("common.labels"),
        "search_placeholder": translate("summary.filter-list"),
        "all_label": translate("common.all"),
        "none_label": translate("common.none-selection"),
        "remove_label": translate("common.remove"),
        "options": [
            {
                "id": encode_label(label["name"]),
                "name": label["name"],
                "checked": False,
            }
            for label in used
        ],
    }
    body = render_template(
        "tools.html",
        source_labels=used,
        labels_json=json.dumps([label["name"] for label in defined], ensure_ascii=False),
        destination_label_picker=label_picker("", 'name="destination_label" required'),
        label_selector=label_selector,
        error=params.get("error", [""])[0],
        message=params.get("message", [""])[0],
        title=translate("tools.title"),
        label_merge_title=translate("tools.label-merge-title"),
        merge_from_label=translate("tools.merge-from-label"),
        merge_to_label=translate("tools.merge-to-label"),
        merge_button=translate("tools.merge-button"),
        empty_label_message=translate("tools.empty-label-message"),
        **settings_tabs_context(user_id, "tools"),
    )
    return user_layout(translate("tools.title"), body, user_id)


def defined_labels(conn: sqlite3.Connection, user_id: str) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT id, name FROM transaction_labels WHERE user_id = ? ORDER BY name",
        (user_id,),
    ).fetchall()
    return [row for row in rows if not is_internal_transfer_label(row["name"])]


def used_labels(conn: sqlite3.Connection, user_id: str) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT DISTINCT label AS name
        FROM transactions
        WHERE user_id = ?
          AND label IS NOT NULL
          AND TRIM(label) <> ''
        ORDER BY label
        """,
        (user_id,),
    ).fetchall()
    return [row for row in rows if not is_internal_transfer_label(row["name"])]


def labels_payload(rows: list[sqlite3.Row]) -> list[dict[str, object]]:
    return [{"id": row["id"], "name": row["name"]} if "id" in row.keys() else {"name": row["name"]} for row in rows]


def merge_labels(data: dict[str, list[str]], user_id: str) -> str:
    source_names = parse_source_labels(one(data, "source_labels"))
    destination_name = one(data, "destination_label").strip()
    if not destination_name:
        raise ValueError(translate("errors.label-required"))
    if is_internal_transfer_label(destination_name):
        raise ValueError(translate("errors.label-not-found"))
    if not source_names:
        raise ValueError(translate("tools.source-required"))

    with db() as conn:
        name_placeholders = ",".join("?" for _ in source_names)
        existing_sources = conn.execute(
            f"""
            SELECT DISTINCT label AS name
            FROM transactions
            WHERE user_id = ?
              AND label IN ({name_placeholders})
            """,
            (user_id, *source_names),
        ).fetchall()
        if len(existing_sources) != len(set(source_names)):
            raise ValueError(translate("errors.label-not-found"))
        if any(is_internal_transfer_label(source["name"]) for source in existing_sources):
            raise ValueError(translate("errors.label-not-found"))
        if normalized_text(destination_name) in {normalized_text(name) for name in source_names}:
            raise ValueError(translate("tools.same-label-error"))

        conn.execute(
            "INSERT OR IGNORE INTO transaction_labels(user_id, name) VALUES (?, ?)",
            (user_id, destination_name),
        )
        transaction_count = conn.execute(
            f"SELECT COUNT(*) FROM transactions WHERE user_id = ? AND label IN ({name_placeholders})",
            (user_id, *source_names),
        ).fetchone()[0]
        budget_count = conn.execute(
            f"SELECT COUNT(*) FROM monthly_budget WHERE user_id = ? AND label IN ({name_placeholders})",
            (user_id, *source_names),
        ).fetchone()[0]
        scheduled_count = conn.execute(
            f"SELECT COUNT(*) FROM budget_schedule WHERE user_id = ? AND label IN ({name_placeholders})",
            (user_id, *source_names),
        ).fetchone()[0]
        for source_name in source_names:
            merge_note = f"Move from {source_name}."
            rows = conn.execute(
                """
                SELECT id, comment
                FROM transactions
                WHERE user_id = ?
                  AND label = ?
                """,
                (user_id, source_name),
            ).fetchall()
            for row in rows:
                current_comment = str(row["comment"] or "").strip()
                new_comment = f"{merge_note} {current_comment}".strip()
                conn.execute(
                    "UPDATE transactions SET label = ?, comment = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                    (destination_name, new_comment, row["id"], user_id),
                )
        conn.execute(
            f"UPDATE monthly_budget SET label = ? WHERE user_id = ? AND label IN ({name_placeholders})",
            (destination_name, user_id, *source_names),
        )
        conn.execute(
            f"UPDATE budget_schedule SET label = ? WHERE user_id = ? AND label IN ({name_placeholders})",
            (destination_name, user_id, *source_names),
        )
        conn.execute(
            f"DELETE FROM transaction_labels WHERE user_id = ? AND name IN ({name_placeholders})",
            (user_id, *source_names),
        )

    message = translate(
        "tools.label-merge-done",
        transactions=transaction_count,
        budgets=budget_count,
        scheduled=scheduled_count,
    )
    return f"/tools?message={quote(message)}"


def parse_source_labels(value: str) -> list[str]:
    raw = str(value or "").strip()
    if not raw or raw in {"all", "none"}:
        return []
    labels: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            labels.append(decode_label(part))
    return labels


def encode_label(label: str) -> str:
    encoded = base64.urlsafe_b64encode(label.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def decode_label(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}").decode("utf-8")
