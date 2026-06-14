from __future__ import annotations

from datetime import date, datetime

from database import db, ensure_internal_transfer_labels, integrity_errors
from i18n import translate
from transfer_labels import (
    internal_transfer_mirror_label,
    internal_transfer_target_name,
    is_internal_transfer_label,
    normalized_text,
)
from web_helpers import format_date, format_number, normalize_date


def update(path: str, payload: dict[str, object], user_id: str) -> dict[str, object]:
    try:
        if path == "/api/transaction":
            return {"ok": True, **update_transaction(payload, user_id)}
        elif path == "/api/transaction-row":
            return {"ok": True, **save_transaction_row(payload, user_id)}
        elif path == "/api/transaction-delete":
            return {"ok": True, **delete_transaction(payload, user_id)}
        elif path == "/api/transaction-clear":
            return {"ok": True, **clear_transactions(payload, user_id)}
        elif path == "/api/transaction-reorder":
            return {"ok": True, **reorder_transaction(payload, user_id)}
        elif path == "/api/label-from-text":
            return {"ok": True, **create_label_from_text(payload, user_id)}
        elif path == "/api/account-row":
            return {"ok": True, **save_named_row("accounts", payload, user_id)}
        elif path == "/api/account-reorder":
            return {"ok": True, **reorder_account(payload, user_id)}
        elif path == "/api/account-summary":
            update_account_summary(payload, user_id)
        elif path == "/api/account-visible-if-empty":
            update_account_visible_if_empty(payload, user_id)
        elif path == "/api/period-range":
            return {"ok": True, **update_period_range(payload, user_id)}
        elif path == "/api/period-name":
            return {"ok": True, **update_period_name(payload, user_id)}
        elif path == "/api/period-delete":
            return {"ok": True, **delete_period(payload, user_id)}
        elif path == "/api/period-date":
            return {"ok": True, **update_period_date(payload, user_id)}
        elif path == "/api/account-balance":
            return {"ok": True, **update_account_balance(payload, user_id)}
        elif path == "/api/account-delete":
            return {"ok": True, **delete_account(payload, user_id)}
        elif path == "/api/account-merge":
            return {"ok": True, **merge_account(payload, user_id)}
        elif path == "/api/label-row":
            return {"ok": True, **save_label_row(payload, user_id)}
        elif path == "/api/label-delete":
            delete_label(payload, user_id)
        elif path == "/api/monthly-budget-row":
            return {"ok": True, **save_monthly_budget_row(payload, user_id)}
        elif path == "/api/monthly-budget-delete":
            delete_named_row("monthly_budget", payload, user_id)
        elif path == "/api/budget-schedule-cancel":
            return {"ok": True, **cancel_budget_schedule(payload, user_id)}
        elif path == "/api/budget-schedule-row":
            return {"ok": True, **save_budget_schedule_row(payload, user_id)}
        elif path == "/api/budget-schedule-clear":
            return {"ok": True, **clear_budget_schedule(payload, user_id)}
        elif path == "/api/budget-schedule-instantiate":
            return {"ok": True, **instantiate_budget_schedule(payload, user_id)}
        elif path == "/api/account":
            update_simple("accounts", payload, user_id)
        elif path == "/api/label":
            update_label(payload, user_id)
        else:
            return {"ok": False, "status": 404, "error": translate("errors.endpoint-not-found")}
    except (*integrity_errors(), ValueError, KeyError) as error:
        return {"ok": False, "status": 400, "error": str(error)}
    return {"ok": True}


def save_transaction_row(payload: dict[str, object], user_id: str) -> dict[str, object]:
    label = str(payload.get("label") or "").strip()
    if not label:
        raise ValueError(translate("errors.label-required"))
    amount = parse_amount(payload.get("amount"))
    tx_date = normalize_date(payload.get("date"))
    requested_index = parse_sort_index(payload.get("sort_index"))
    comment = str(payload.get("comment") or "").strip() or None

    with db() as conn:
        period_id = int(payload["period_id"])
        account_id = int(payload["account_id"])
        validate_transaction_date(conn, period_id, tx_date, user_id)
        account = conn.execute("SELECT id FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id)).fetchone()
        if account is None:
            raise ValueError(translate("errors.account-not-found"))
        ensure_transaction_label(conn, user_id, label)
        tx_id = payload.get("id")
        if tx_id:
            old = conn.execute("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (int(tx_id), user_id)).fetchone()
            if old is None:
                raise ValueError(translate("errors.transaction-not-found"))
            conn.execute("UPDATE transactions SET sort_index = 0 WHERE id = ?", (int(tx_id),))
            compact_transaction_indexes(conn, int(old["period_id"]), int(old["account_id"]), user_id)
            sort_index = requested_index or next_transaction_index(conn, period_id, account_id, user_id)
            shift_transaction_indexes(conn, period_id, account_id, sort_index, user_id)
            conn.execute(
                """
                UPDATE transactions
                SET date = ?, label = ?, amount = ?, sort_index = ?, comment = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (tx_date, label, amount, sort_index, comment, int(tx_id), user_id),
            )
            saved_id = int(tx_id)
        else:
            sort_index = requested_index or next_transaction_index(conn, period_id, account_id, user_id)
            shift_transaction_indexes(conn, period_id, account_id, sort_index, user_id)
            conn.execute(
                """
                INSERT INTO transactions(user_id, period_id, account_id, date, label, amount, sort_index, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, period_id, account_id, tx_date, label, amount, sort_index, comment),
            )
            saved_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        compact_transaction_indexes(conn, period_id, account_id, user_id)
        sync_internal_transfer(conn, saved_id, user_id)
        sort_index = conn.execute("SELECT sort_index FROM transactions WHERE id = ? AND user_id = ?", (saved_id, user_id)).fetchone()["sort_index"]
        reconcile_budget_schedule(conn, period_id, user_id)
        rows = transaction_indexes(conn, period_id, account_id, user_id)
    return {
        "id": saved_id,
        "date": format_date(tx_date),
        "date_sort": tx_date or "",
        "label": label,
        "amount": format_number(amount),
        "comment": comment or "",
        "sort_index": sort_index,
        "rows": rows,
    }


def reconcile_budget_schedule(conn: sqlite3.Connection, period_id: int, user_id: str) -> None:
    conn.execute(
        """
        UPDATE budget_schedule
        SET status = 'scheduled'
        WHERE period_id = ? AND user_id = ? AND status = 'found'
        """,
        (period_id, user_id),
    )
    transactions = conn.execute(
        """
        SELECT label, amount
        FROM transactions
        WHERE period_id = ? AND user_id = ?
        ORDER BY COALESCE(date, '9999-12-31'), sort_index, id
        """,
        (period_id, user_id),
    ).fetchall()
    for transaction in transactions:
        conn.execute(
            """
            UPDATE budget_schedule
            SET status = 'found'
            WHERE id = (
                SELECT id
                FROM budget_schedule
                WHERE period_id = ?
                  AND user_id = ?
                  AND status = 'scheduled'
                  AND label = ?
                  AND ABS(amount - ?) < 0.005
                ORDER BY id
                LIMIT 1
            )
            """,
            (period_id, user_id, transaction["label"], float(transaction["amount"] or 0)),
        )


def parse_sort_index(value: object) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = int(raw)
    if parsed < 1:
        raise ValueError(translate("errors.invalid-index"))
    return parsed


def parse_amount(value: object) -> float:
    raw = str(value or "0").strip()
    raw = raw.replace("\xa0", "").replace(" ", "")
    raw = raw.replace("EUR", "").replace("eur", "").replace("euro", "")
    return float(raw.replace(",", ".") or 0)


def ensure_transaction_label(conn, user_id: str, label: str) -> None:
    if is_internal_transfer_label(label):
        return
    conn.execute("INSERT OR IGNORE INTO transaction_labels(user_id, name) VALUES (?, ?)", (user_id, label))


def sync_internal_transfer(conn, tx_id: int, user_id: str) -> None:
    transaction = conn.execute(
        """
        SELECT t.*, a.name AS source_account_name
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE t.id = ? AND t.user_id = ?
        """,
        (tx_id, user_id),
    ).fetchone()
    if transaction is None or int(transaction["transfer_auto"] or 0):
        return

    pair_id = transaction["transfer_pair_id"]
    if not is_internal_transfer_label(transaction["label"]):
        delete_auto_transfer_pair(conn, pair_id, user_id)
        conn.execute("UPDATE transactions SET transfer_pair_id = NULL WHERE id = ? AND user_id = ?", (tx_id, user_id))
        return

    target_name = internal_transfer_target_name(transaction["label"])
    if not target_name:
        raise ValueError(translate("errors.transfer-target-required"))
    target = find_transfer_target_account(conn, target_name, int(transaction["account_id"]), user_id)
    if target is None:
        raise ValueError(translate("errors.transfer-target-not-found", account=target_name))

    mirror_label = internal_transfer_mirror_label(transaction["label"], str(transaction["source_account_name"]))
    mirror_amount = -float(transaction["amount"] or 0)
    mirror_id = None
    old_pair = None
    if pair_id:
        old_pair = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ? AND transfer_auto = 1",
            (int(pair_id), user_id),
        ).fetchone()

    if old_pair is not None and int(old_pair["account_id"]) == int(target["id"]):
        mirror_id = int(old_pair["id"])
        conn.execute(
            """
            UPDATE transactions
            SET period_id = ?, account_id = ?, date = ?, label = ?, amount = ?, comment = ?,
                transfer_pair_id = ?, transfer_auto = 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (
                transaction["period_id"],
                target["id"],
                transaction["date"],
                mirror_label,
                mirror_amount,
                transaction["comment"],
                tx_id,
                mirror_id,
                user_id,
            ),
        )
        compact_transaction_indexes(conn, int(transaction["period_id"]), int(target["id"]), user_id)
    else:
        delete_auto_transfer_pair(conn, pair_id, user_id)
        existing_mirror = find_existing_transfer_mirror(conn, transaction, target["id"], mirror_label, mirror_amount, user_id)
        if existing_mirror is not None:
            mirror_id = int(existing_mirror["id"])
            conn.execute(
                """
                UPDATE transactions
                SET transfer_pair_id = ?, transfer_auto = 1, comment = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (tx_id, transaction["comment"], mirror_id, user_id),
            )
        else:
            sort_index = next_transaction_index(conn, int(transaction["period_id"]), int(target["id"]), user_id)
            shift_transaction_indexes(conn, int(transaction["period_id"]), int(target["id"]), sort_index, user_id)
            conn.execute(
                """
                INSERT INTO transactions(
                    user_id, period_id, account_id, date, label, amount, sort_index, comment,
                    transfer_pair_id, transfer_auto
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    user_id,
                    transaction["period_id"],
                    target["id"],
                    transaction["date"],
                    mirror_label,
                    mirror_amount,
                    sort_index,
                    transaction["comment"],
                    tx_id,
                ),
            )
            mirror_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        compact_transaction_indexes(conn, int(transaction["period_id"]), int(target["id"]), user_id)

    conn.execute(
        "UPDATE transactions SET transfer_pair_id = ?, transfer_auto = 0 WHERE id = ? AND user_id = ?",
        (mirror_id, tx_id, user_id),
    )


def delete_auto_transfer_pair(conn, pair_id: object, user_id: str) -> None:
    if not pair_id:
        return
    pair = conn.execute(
        "SELECT period_id, account_id FROM transactions WHERE id = ? AND user_id = ? AND transfer_auto = 1",
        (int(pair_id), user_id),
    ).fetchone()
    if pair is None:
        return
    conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ? AND transfer_auto = 1", (int(pair_id), user_id))
    compact_transaction_indexes(conn, int(pair["period_id"]), int(pair["account_id"]), user_id)


def find_transfer_target_account(conn, target_name: str, source_account_id: int, user_id: str):
    rows = conn.execute("SELECT id, name FROM accounts WHERE user_id = ?", (user_id,)).fetchall()
    normalized_target = normalized_text(target_name)
    matches = [
        row
        for row in rows
        if int(row["id"]) != source_account_id and normalized_text(row["name"]) == normalized_target
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def find_existing_transfer_mirror(conn, transaction, target_account_id: int, mirror_label: str, mirror_amount: float, user_id: str):
    return conn.execute(
        """
        SELECT *
        FROM transactions
        WHERE user_id = ?
          AND period_id = ?
          AND account_id = ?
          AND COALESCE(date, '') = COALESCE(?, '')
          AND label = ?
          AND ABS(amount - ?) < 0.005
          AND id <> ?
          AND transfer_pair_id IS NULL
        ORDER BY id
        LIMIT 1
        """,
        (
            user_id,
            transaction["period_id"],
            target_account_id,
            transaction["date"],
            mirror_label,
            mirror_amount,
            transaction["id"],
        ),
    ).fetchone()


def validate_transaction_date(conn: sqlite3.Connection, period_id: int, tx_date: str | None, user_id: str) -> None:
    if tx_date is None:
        raise ValueError(translate("errors.date-required"))
    period = conn.execute("SELECT start_date, end_date FROM period WHERE id = ? AND user_id = ?", (period_id, user_id)).fetchone()
    if period is None:
        raise ValueError(translate("errors.period-not-found"))
    if not period["start_date"]:
        raise ValueError(translate("errors.start-date-required"))

    parsed_date = datetime.strptime(tx_date, "%Y-%m-%d").date()
    start_date = datetime.strptime(period["start_date"], "%Y-%m-%d").date()
    if parsed_date < start_date:
        raise ValueError(translate("errors.date-min", date=format_date(period["start_date"])))
    if period["end_date"]:
        end_date = datetime.strptime(period["end_date"], "%Y-%m-%d").date()
        if parsed_date > end_date:
            raise ValueError(translate("errors.date-max", date=format_date(period["end_date"])))


def update_period_date(payload: dict[str, object], user_id: str) -> dict[str, object]:
    period_id = int(payload["id"])
    field = str(payload.get("field") or "")
    if field not in {"start_date", "end_date"}:
        raise ValueError(translate("errors.field-not-allowed"))
    raw_value = str(payload.get("value") or "").strip()
    if field == "start_date" and not raw_value:
        raise ValueError(translate("errors.start-date-value-required"))
    value = normalize_period_end(raw_value) if field == "end_date" else normalize_date(raw_value)
    with db() as conn:
        row = conn.execute("SELECT id FROM period WHERE id = ? AND user_id = ?", (period_id, user_id)).fetchone()
        if row is None:
            raise ValueError(translate("errors.period-not-found"))
        conn.execute(
            f"UPDATE period SET {field} = ? WHERE id = ? AND user_id = ?",
            (value, period_id, user_id),
        )
    return {"value": format_date(value) if value else translate("periods.current")}


def update_period_range(payload: dict[str, object], user_id: str) -> dict[str, object]:
    period_id = int(payload["id"])
    start_raw = str(payload.get("start_date") or "").strip()
    end_raw = str(payload.get("end_date") or "").strip()
    if not start_raw:
        raise ValueError(translate("errors.start-date-value-required"))
    start_date = normalize_date(start_raw)
    end_date = normalize_period_end(end_raw)
    with db() as conn:
        row = conn.execute("SELECT id FROM period WHERE id = ? AND user_id = ?", (period_id, user_id)).fetchone()
        if row is None:
            raise ValueError(translate("errors.period-not-found"))
        conn.execute(
            "UPDATE period SET start_date = ?, end_date = ? WHERE id = ? AND user_id = ?",
            (start_date, end_date, period_id, user_id),
        )
    return {
        "start_date": format_date(start_date),
        "end_date": format_date(end_date) if end_date else translate("periods.current"),
    }


def normalize_period_end(value: object) -> str | None:
    raw = str(value or "").strip()
    current_markers = {"en cours", "current", "laufend", "lopend", translate("periods.current").casefold()}
    if not raw or raw.casefold() in current_markers:
        return None
    return normalize_date(raw)


def update_period_name(payload: dict[str, object], user_id: str) -> dict[str, object]:
    period_id = int(payload["id"])
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError(translate("errors.name-required"))
    with db() as conn:
        row = conn.execute("SELECT id FROM period WHERE id = ? AND user_id = ?", (period_id, user_id)).fetchone()
        if row is None:
            raise ValueError(translate("errors.period-not-found"))
        conn.execute("UPDATE period SET name = ? WHERE id = ? AND user_id = ?", (name, period_id, user_id))
    return {"name": name}


def delete_period(payload: dict[str, object], user_id: str) -> dict[str, object]:
    period_id = int(payload["id"])
    with db() as conn:
        row = conn.execute("SELECT id FROM period WHERE id = ? AND user_id = ?", (period_id, user_id)).fetchone()
        if row is None:
            raise ValueError(translate("errors.period-not-found"))
        transaction_count = int(conn.execute("SELECT COUNT(*) FROM transactions WHERE period_id = ? AND user_id = ?", (period_id, user_id)).fetchone()[0])
        budget_count = int(conn.execute("SELECT COUNT(*) FROM budget_schedule WHERE period_id = ? AND user_id = ?", (period_id, user_id)).fetchone()[0])
        if transaction_count or budget_count:
            raise ValueError(
                translate("errors.delete-period-blocked", transactions=transaction_count, budgets=budget_count)
            )
        conn.execute("DELETE FROM period WHERE id = ? AND user_id = ?", (period_id, user_id))
    return {"id": period_id}


def next_transaction_index(conn: sqlite3.Connection, period_id: int, account_id: int, user_id: str) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(MAX(sort_index), 0) + 1 AS next_index
        FROM transactions
        WHERE period_id = ? AND account_id = ? AND user_id = ?
        """,
        (period_id, account_id, user_id),
    ).fetchone()
    return int(row["next_index"])


def shift_transaction_indexes(conn: sqlite3.Connection, period_id: int, account_id: int, start_index: int, user_id: str) -> None:
    conn.execute(
        """
        UPDATE transactions
        SET sort_index = sort_index + 1
        WHERE period_id = ? AND account_id = ? AND sort_index >= ? AND user_id = ?
        """,
        (period_id, account_id, start_index, user_id),
    )


def compact_transaction_indexes(conn: sqlite3.Connection, period_id: int, account_id: int, user_id: str) -> None:
    rows = conn.execute(
        """
        SELECT id
        FROM transactions
        WHERE period_id = ? AND account_id = ? AND user_id = ? AND sort_index > 0
        ORDER BY COALESCE(date, '9999-12-31'), sort_index, id
        """,
        (period_id, account_id, user_id),
    ).fetchall()
    for index, row in enumerate(rows, start=1):
        conn.execute("UPDATE transactions SET sort_index = ? WHERE id = ?", (index, row["id"]))


def transaction_indexes(conn: sqlite3.Connection, period_id: int, account_id: int, user_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT id, date, sort_index
        FROM transactions
        WHERE period_id = ? AND account_id = ? AND user_id = ?
        ORDER BY COALESCE(date, '9999-12-31'), sort_index, id
        """,
        (period_id, account_id, user_id),
    ).fetchall()
    return [
        {"id": row["id"], "date": format_date(row["date"]), "date_sort": row["date"] or "", "sort_index": row["sort_index"]}
        for row in rows
    ]


def delete_transaction(payload: dict[str, object], user_id: str) -> dict[str, object]:
    with db() as conn:
        row = conn.execute("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (int(payload["id"]), user_id)).fetchone()
        if row is None:
            raise ValueError(translate("errors.transaction-not-found"))
        if int(row["transfer_auto"] or 0):
            conn.execute(
                "UPDATE transactions SET transfer_pair_id = NULL WHERE id = ? AND user_id = ?",
                (row["transfer_pair_id"], user_id),
            )
        else:
            delete_auto_transfer_pair(conn, row["transfer_pair_id"], user_id)
        conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (int(payload["id"]), user_id))
        compact_transaction_indexes(conn, int(row["period_id"]), int(row["account_id"]), user_id)
        reconcile_budget_schedule(conn, int(row["period_id"]), user_id)
        rows = transaction_indexes(conn, int(row["period_id"]), int(row["account_id"]), user_id)
    return {"rows": rows}


def clear_transactions(payload: dict[str, object], user_id: str) -> dict[str, object]:
    with db() as conn:
        period_id = int(payload["period_id"])
        account_id = int(payload["account_id"])
        rows_to_delete = conn.execute(
            "SELECT id, transfer_pair_id, transfer_auto FROM transactions WHERE period_id = ? AND account_id = ? AND user_id = ?",
            (period_id, account_id, user_id),
        ).fetchall()
        for row in rows_to_delete:
            if int(row["transfer_auto"] or 0):
                conn.execute(
                    "UPDATE transactions SET transfer_pair_id = NULL WHERE id = ? AND user_id = ?",
                    (row["transfer_pair_id"], user_id),
                )
            else:
                delete_auto_transfer_pair(conn, row["transfer_pair_id"], user_id)
        conn.execute("DELETE FROM transactions WHERE period_id = ? AND account_id = ? AND user_id = ?", (period_id, account_id, user_id))
        reconcile_budget_schedule(conn, period_id, user_id)
    return {"rows": []}


def reorder_transaction(payload: dict[str, object], user_id: str) -> dict[str, object]:
    tx_id = int(payload["id"])
    target_id = int(payload["target_id"])
    position = str(payload.get("position") or "before")
    if position not in {"before", "after"}:
        raise ValueError(translate("errors.invalid-position"))
    with db() as conn:
        moved = conn.execute("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (tx_id, user_id)).fetchone()
        target = conn.execute("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (target_id, user_id)).fetchone()
        if moved is None or target is None:
            raise ValueError(translate("errors.transaction-not-found"))
        if moved["period_id"] != target["period_id"] or moved["account_id"] != target["account_id"]:
            raise ValueError(translate("errors.invalid-move"))

        period_id = int(moved["period_id"])
        account_id = int(moved["account_id"])
        conn.execute("UPDATE transactions SET sort_index = 0 WHERE id = ?", (tx_id,))
        compact_transaction_indexes(conn, period_id, account_id, user_id)
        target = conn.execute("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (target_id, user_id)).fetchone()
        new_date = target["date"]
        validate_transaction_date(conn, period_id, new_date, user_id)
        new_index = int(target["sort_index"]) + (1 if position == "after" else 0)
        shift_transaction_indexes(conn, period_id, account_id, new_index, user_id)
        conn.execute(
            "UPDATE transactions SET date = ?, sort_index = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (new_date, new_index, tx_id, user_id),
        )
        compact_transaction_indexes(conn, period_id, account_id, user_id)
        new_index = conn.execute("SELECT sort_index FROM transactions WHERE id = ? AND user_id = ?", (tx_id, user_id)).fetchone()["sort_index"]
        rows = transaction_indexes(conn, period_id, account_id, user_id)
    return {"date": new_date or "", "sort_index": new_index, "rows": rows}


def create_label_from_text(payload: dict[str, object], user_id: str) -> dict[str, object]:
    label_name = str(payload.get("value") or "").strip()
    if not label_name:
        raise ValueError(translate("errors.label-required"))

    with db() as conn:
        if is_internal_transfer_label(label_name):
            return {"label": {"id": None, "name": label_name}, "hidden": True}
        ensure_transaction_label(conn, user_id, label_name)
        label = conn.execute(
            "SELECT id, name FROM transaction_labels WHERE user_id = ? AND name = ?",
            (user_id, label_name),
        ).fetchone()

    return {
        "label": {"id": label["id"], "name": label["name"]},
    }


def save_monthly_budget_row(payload: dict[str, object], user_id: str) -> dict[str, object]:
    day = int(str(payload.get("day") or "").strip())
    if day < 1 or day > 31:
        raise ValueError(translate("errors.invalid-day"))
    label = str(payload.get("label") or "").strip()
    if not label:
        raise ValueError(translate("errors.label-required"))
    amount = parse_amount(payload.get("amount"))
    row_id = payload.get("id")
    with db() as conn:
        if row_id:
            conn.execute(
                "UPDATE monthly_budget SET day = ?, label = ?, amount = ? WHERE id = ? AND user_id = ?",
                (day, label, amount, int(row_id), user_id),
            )
            saved_id = int(row_id)
        else:
            conn.execute(
                "INSERT INTO monthly_budget(user_id, day, label, amount) VALUES (?, ?, ?, ?)",
                (user_id, day, label, amount),
            )
            saved_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"id": saved_id, "day": day, "label": label, "amount": format_number(amount)}


def cancel_budget_schedule(payload: dict[str, object], user_id: str) -> dict[str, object]:
    schedule_id = int(payload["id"])
    with db() as conn:
        row = conn.execute("SELECT * FROM budget_schedule WHERE id = ? AND user_id = ?", (schedule_id, user_id)).fetchone()
        if row is None:
            raise ValueError(translate("errors.budget-entry-not-found"))
        conn.execute("UPDATE budget_schedule SET status = 'cancel' WHERE id = ? AND user_id = ?", (schedule_id, user_id))
    return {"id": schedule_id, "status": "cancel", "status_label": translate("period.status-canceled")}


def save_budget_schedule_row(payload: dict[str, object], user_id: str) -> dict[str, object]:
    period_id = int(payload["period_id"])
    label = str(payload.get("label") or "").strip()
    if not label:
        raise ValueError(translate("errors.label-required"))
    amount = parse_amount(payload.get("amount"))
    with db() as conn:
        period = conn.execute("SELECT id FROM period WHERE id = ? AND user_id = ?", (period_id, user_id)).fetchone()
        if period is None:
            raise ValueError(translate("errors.period-not-found"))
        ensure_transaction_label(conn, user_id, label)
        conn.execute(
            "INSERT INTO budget_schedule(user_id, period_id, label, amount, status) VALUES (?, ?, ?, ?, 'scheduled')",
            (user_id, period_id, label, amount),
        )
        schedule_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"id": schedule_id, "label": label, "amount": format_number(amount)}


def clear_budget_schedule(payload: dict[str, object], user_id: str) -> dict[str, object]:
    period_id = int(payload["period_id"])
    with db() as conn:
        conn.execute("DELETE FROM budget_schedule WHERE period_id = ? AND user_id = ?", (period_id, user_id))
    return {"rows": []}


def instantiate_budget_schedule(payload: dict[str, object], user_id: str) -> dict[str, object]:
    schedule_id = int(payload["id"])
    account_id = int(payload["account_id"])
    tx_date = date.today().isoformat()
    with db() as conn:
        scheduled = conn.execute("SELECT * FROM budget_schedule WHERE id = ? AND user_id = ?", (schedule_id, user_id)).fetchone()
        if scheduled is None:
            raise ValueError(translate("errors.budget-entry-not-found"))
        if scheduled["status"] != "scheduled":
            raise ValueError(translate("errors.budget-entry-not-scheduled"))
        account = conn.execute("SELECT id, name FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id)).fetchone()
        if account is None:
            raise ValueError(translate("errors.account-not-found"))
        label = str(scheduled["label"])
        amount = float(scheduled["amount"] or 0)
        period_id = int(scheduled["period_id"])
        ensure_transaction_label(conn, user_id, label)
        sort_index = next_transaction_index(conn, period_id, account_id, user_id)
        shift_transaction_indexes(conn, period_id, account_id, sort_index, user_id)
        conn.execute(
            """
            INSERT INTO transactions(user_id, period_id, account_id, date, label, amount, sort_index, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (user_id, period_id, account_id, tx_date, label, amount, sort_index),
        )
        tx_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        compact_transaction_indexes(conn, period_id, account_id, user_id)
        sync_internal_transfer(conn, int(tx_id), user_id)
        reconcile_budget_schedule(conn, period_id, user_id)
        sort_index = conn.execute("SELECT sort_index FROM transactions WHERE id = ? AND user_id = ?", (tx_id, user_id)).fetchone()["sort_index"]
    return {
        "id": tx_id,
        "account_id": account_id,
        "account_name": account["name"],
        "date": format_date(tx_date),
        "date_sort": tx_date,
        "label": label,
        "amount": amount,
        "sort_index": sort_index,
        "status": "found",
        "status_label": translate("period.status-found"),
    }


def update_transaction(payload: dict[str, object], user_id: str) -> dict[str, object]:
    tx_id = int(payload["id"])
    field = str(payload["field"])
    value = payload.get("value")
    allowed = {"date", "label", "amount", "comment"}
    if field not in allowed:
        raise ValueError(translate("errors.field-not-allowed"))
    if field == "amount":
        value = parse_amount(value)
    if field == "date":
        value = normalize_date(value)
    if field == "label":
        value = str(value).strip()
        if not value:
            raise ValueError(translate("errors.label-required"))
    with db() as conn:
        month_ids: set[int] = set()
        row = conn.execute("SELECT period_id FROM transactions WHERE id = ? AND user_id = ?", (tx_id, user_id)).fetchone()
        if row is None:
            raise ValueError(translate("errors.transaction-not-found"))
        month_ids.add(int(row["period_id"]))
        if field == "date":
            validate_transaction_date(conn, int(row["period_id"]), value, user_id)
        if field == "label":
            ensure_transaction_label(conn, user_id, value)
            conn.execute(
                "UPDATE transactions SET label = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                (value, tx_id, user_id),
            )
        else:
            conn.execute(f"UPDATE transactions SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?", (value, tx_id, user_id))
        sync_internal_transfer(conn, tx_id, user_id)
        for period_id in month_ids:
            reconcile_budget_schedule(conn, period_id, user_id)
    if field == "amount":
        return {"value": format_number(value)}
    if field == "date":
        return {"value": format_date(value), "date_sort": value or ""}
    return {"value": value or ""}


def save_named_row(table: str, payload: dict[str, object], user_id: str) -> dict[str, object]:
    name = str(payload.get("value") or "").strip()
    if not name:
        raise ValueError(translate("errors.value-required"))
    row_id = payload.get("id")
    with db() as conn:
        if row_id:
            conn.execute(f"UPDATE {table} SET name = ? WHERE id = ? AND user_id = ?", (name, int(row_id), user_id))
            saved_id = int(row_id)
            rows = account_indexes(conn, user_id) if table == "accounts" else []
        else:
            if table == "accounts":
                sort_index = next_account_index(conn, user_id)
                conn.execute("INSERT INTO accounts(user_id, name, sort_index) VALUES (?, ?, ?)", (user_id, name, sort_index))
            else:
                conn.execute(f"INSERT INTO {table}(user_id, name) VALUES (?, ?)", (user_id, name))
            saved_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            rows = account_indexes(conn, user_id) if table == "accounts" else []
        if table == "accounts":
            ensure_internal_transfer_labels(conn, user_id)
    return {"id": saved_id, "value": name, "rows": rows}


def next_account_index(conn: sqlite3.Connection, user_id: str) -> int:
    return int(conn.execute("SELECT COALESCE(MAX(sort_index), 0) + 1 FROM accounts WHERE user_id = ?", (user_id,)).fetchone()[0])


def compact_account_indexes(conn: sqlite3.Connection, user_id: str) -> None:
    rows = conn.execute("SELECT id FROM accounts WHERE user_id = ? ORDER BY sort_index, name, id", (user_id,)).fetchall()
    for index, row in enumerate(rows, start=1):
        conn.execute("UPDATE accounts SET sort_index = ? WHERE id = ?", (index, row["id"]))


def account_indexes(conn: sqlite3.Connection, user_id: str) -> list[dict[str, object]]:
    rows = conn.execute("SELECT id, sort_index FROM accounts WHERE user_id = ? ORDER BY sort_index, name, id", (user_id,)).fetchall()
    return [{"id": row["id"], "sort_index": row["sort_index"]} for row in rows]


def reorder_account(payload: dict[str, object], user_id: str) -> dict[str, object]:
    account_id = int(payload["id"])
    target_id = int(payload["target_id"])
    position = str(payload.get("position") or "before")
    if position not in {"before", "after"}:
        raise ValueError(translate("errors.invalid-position"))
    with db() as conn:
        account = conn.execute("SELECT * FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id)).fetchone()
        target = conn.execute("SELECT * FROM accounts WHERE id = ? AND user_id = ?", (target_id, user_id)).fetchone()
        if account is None or target is None:
            raise ValueError(translate("errors.account-not-found"))
        conn.execute("UPDATE accounts SET sort_index = 0 WHERE id = ?", (account_id,))
        compact_account_indexes(conn, user_id)
        target = conn.execute("SELECT * FROM accounts WHERE id = ? AND user_id = ?", (target_id, user_id)).fetchone()
        new_index = int(target["sort_index"]) + (1 if position == "after" else 0)
        conn.execute("UPDATE accounts SET sort_index = sort_index + 1 WHERE sort_index >= ? AND user_id = ?", (new_index, user_id))
        conn.execute("UPDATE accounts SET sort_index = ? WHERE id = ? AND user_id = ?", (new_index, account_id, user_id))
        compact_account_indexes(conn, user_id)
        rows = account_indexes(conn, user_id)
        sort_index = conn.execute("SELECT sort_index FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id)).fetchone()["sort_index"]
    return {"sort_index": sort_index, "rows": rows}


def update_account_summary(payload: dict[str, object], user_id: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE accounts SET show_in_summary = ? WHERE id = ? AND user_id = ?",
            (1 if payload.get("value") else 0, int(payload["id"]), user_id),
        )


def update_account_visible_if_empty(payload: dict[str, object], user_id: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE accounts SET visible_if_empty = ? WHERE id = ? AND user_id = ?",
            (1 if payload.get("value") else 0, int(payload["id"]), user_id),
        )


def update_account_balance(payload: dict[str, object], user_id: str) -> dict[str, object]:
    field = str(payload.get("field") or "")
    if field != "opening":
        raise ValueError(translate("errors.field-not-allowed"))
    raw_value = str(payload.get("value") or "").strip()
    value = None if raw_value == "" else parse_amount(raw_value)
    period_id = int(payload["period_id"])
    account_id = int(payload["account_id"])
    with db() as conn:
        conn.execute(
            """
            INSERT INTO account_balances(user_id, period_id, account_id, opening)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, period_id, account_id) DO UPDATE SET opening = excluded.opening
            """,
            (user_id, period_id, account_id, value),
        )
        transaction_total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE period_id = ? AND account_id = ? AND user_id = ?",
            (period_id, account_id, user_id),
        ).fetchone()[0]
    current = None if value is None else value + float(transaction_total or 0)
    return {
        "value": "" if value is None else format_number(value),
        "display": translate("period.unknown") if value is None else format_number(value),
        "current": "" if current is None else format_number(current),
        "current_display": translate("period.unknown") if current is None else format_number(current),
    }


def save_label_row(payload: dict[str, object], user_id: str) -> dict[str, object]:
    old_name = None
    row_id = payload.get("id")
    if row_id:
        with db() as conn:
            row = conn.execute("SELECT name FROM transaction_labels WHERE id = ? AND user_id = ?", (int(row_id), user_id)).fetchone()
            if row is None:
                raise ValueError(translate("errors.label-not-found"))
            old_name = row["name"]
            if is_internal_transfer_label(old_name):
                raise ValueError(translate("errors.label-not-found"))
    result = save_named_row("transaction_labels", payload, user_id)
    if old_name:
        with db() as conn:
            conn.execute("UPDATE transactions SET label = ? WHERE label = ? AND user_id = ?", (result["value"], old_name, user_id))
    return result


def delete_label(payload: dict[str, object], user_id: str) -> None:
    label_id = int(payload["id"])
    with db() as conn:
        row = conn.execute("SELECT name FROM transaction_labels WHERE id = ? AND user_id = ?", (label_id, user_id)).fetchone()
        if row is None or is_internal_transfer_label(row["name"]):
            raise ValueError(translate("errors.label-not-found"))
        conn.execute("DELETE FROM transaction_labels WHERE id = ? AND user_id = ?", (label_id, user_id))


def delete_named_row(table: str, payload: dict[str, object], user_id: str) -> None:
    with db() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ? AND user_id = ?", (int(payload["id"]), user_id))


def delete_account(payload: dict[str, object], user_id: str) -> dict[str, object]:
    account_id = int(payload["id"])
    with db() as conn:
        transaction_count = int(conn.execute("SELECT COUNT(*) FROM transactions WHERE account_id = ? AND user_id = ?", (account_id, user_id)).fetchone()[0])
        if transaction_count:
            raise ValueError(translate("parameters.delete-account-blocked", transactions=transaction_count))
        conn.execute("DELETE FROM account_balances WHERE account_id = ? AND user_id = ?", (account_id, user_id))
        conn.execute("DELETE FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
        compact_account_indexes(conn, user_id)
        rows = account_indexes(conn, user_id)
    return {"rows": rows}


def merge_account(payload: dict[str, object], user_id: str) -> dict[str, object]:
    source_id = int(payload["id"])
    target_id = int(payload["target_id"])
    if source_id == target_id:
        raise ValueError(translate("errors.different-account-required"))
    with db() as conn:
        source = conn.execute("SELECT id FROM accounts WHERE id = ? AND user_id = ?", (source_id, user_id)).fetchone()
        target = conn.execute("SELECT id FROM accounts WHERE id = ? AND user_id = ?", (target_id, user_id)).fetchone()
        if source is None or target is None:
            raise ValueError(translate("errors.account-not-found"))
        source_balances = conn.execute(
            "SELECT period_id, opening FROM account_balances WHERE account_id = ? AND user_id = ?",
            (source_id, user_id),
        ).fetchall()
        for balance in source_balances:
            existing = conn.execute(
                "SELECT opening FROM account_balances WHERE period_id = ? AND account_id = ? AND user_id = ?",
                (balance["period_id"], target_id, user_id),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO account_balances(user_id, period_id, account_id, opening) VALUES (?, ?, ?, ?)",
                    (user_id, balance["period_id"], target_id, balance["opening"]),
                )
            elif balance["opening"] is not None:
                merged_opening = float(balance["opening"]) + float(existing["opening"] or 0)
                conn.execute(
                    "UPDATE account_balances SET opening = ? WHERE period_id = ? AND account_id = ? AND user_id = ?",
                    (merged_opening, balance["period_id"], target_id, user_id),
                )
        conn.execute("UPDATE transactions SET account_id = ? WHERE account_id = ? AND user_id = ?", (target_id, source_id, user_id))
        conn.execute("DELETE FROM account_balances WHERE account_id = ? AND user_id = ?", (source_id, user_id))
        conn.execute("DELETE FROM accounts WHERE id = ? AND user_id = ?", (source_id, user_id))
        compact_account_indexes(conn, user_id)
        rows = account_indexes(conn, user_id)
    return {"rows": rows}


def update_simple(table: str, payload: dict[str, object], user_id: str) -> None:
    with db() as conn:
        conn.execute(f"UPDATE {table} SET name = ? WHERE id = ? AND user_id = ?", (str(payload.get("value") or "").strip(), int(payload["id"]), user_id))
        if table == "accounts":
            ensure_internal_transfer_labels(conn, user_id)


def update_label(payload: dict[str, object], user_id: str) -> None:
    label_id = int(payload["id"])
    field = str(payload["field"])
    value = payload.get("value")
    if field != "name":
        raise ValueError(translate("errors.field-not-allowed"))
    with db() as conn:
        new_name = str(value).strip()
        if not new_name:
            raise ValueError(translate("errors.label-required"))
        row = conn.execute("SELECT name FROM transaction_labels WHERE id = ? AND user_id = ?", (label_id, user_id)).fetchone()
        if row is None:
            raise ValueError(translate("errors.label-not-found"))
        old_label = row["name"]
        conn.execute("UPDATE transaction_labels SET name = ? WHERE id = ? AND user_id = ?", (new_name, label_id, user_id))
        conn.execute("UPDATE transactions SET label = ? WHERE label = ? AND user_id = ?", (new_name, old_label, user_id))
