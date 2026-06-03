from __future__ import annotations

import sqlite3
from datetime import date, datetime

from database import db


def update(path: str, payload: dict[str, object]) -> dict[str, object]:
    try:
        if path == "/api/transaction":
            update_transaction(payload)
        elif path == "/api/transaction-row":
            return {"ok": True, **save_transaction_row(payload)}
        elif path == "/api/transaction-delete":
            return {"ok": True, **delete_transaction(payload)}
        elif path == "/api/transaction-clear":
            return {"ok": True, **clear_transactions(payload)}
        elif path == "/api/transaction-reorder":
            return {"ok": True, **reorder_transaction(payload)}
        elif path == "/api/label-from-text":
            return {"ok": True, **create_label_from_text(payload)}
        elif path == "/api/account-row":
            return {"ok": True, **save_named_row("accounts", payload)}
        elif path == "/api/account-reorder":
            return {"ok": True, **reorder_account(payload)}
        elif path == "/api/account-summary":
            update_account_summary(payload)
        elif path == "/api/account-visible-if-empty":
            update_account_visible_if_empty(payload)
        elif path == "/api/account-balance":
            update_account_balance(payload)
        elif path == "/api/account-delete":
            delete_account(payload)
        elif path == "/api/label-row":
            return {"ok": True, **save_label_row(payload)}
        elif path == "/api/label-delete":
            delete_named_row("transaction_labels", payload)
        elif path == "/api/monthly-budget-row":
            return {"ok": True, **save_monthly_budget_row(payload)}
        elif path == "/api/monthly-budget-delete":
            delete_named_row("monthly_budget", payload)
        elif path == "/api/budget-schedule-cancel":
            return {"ok": True, **cancel_budget_schedule(payload)}
        elif path == "/api/budget-schedule-instantiate":
            return {"ok": True, **instantiate_budget_schedule(payload)}
        elif path == "/api/account":
            update_simple("accounts", payload)
        elif path == "/api/label":
            update_label(payload)
        else:
            return {"ok": False, "status": 404, "error": "Endpoint introuvable"}
    except (sqlite3.IntegrityError, ValueError, KeyError) as error:
        return {"ok": False, "status": 400, "error": str(error)}
    return {"ok": True}


def save_transaction_row(payload: dict[str, object]) -> dict[str, object]:
    label = str(payload.get("label") or "").strip()
    if not label:
        raise ValueError("Intitulé obligatoire")
    amount = float(str(payload.get("amount") or 0).replace(",", "."))
    tx_date = normalize_date(payload.get("date"))
    requested_index = parse_sort_index(payload.get("sort_index"))
    comment = str(payload.get("comment") or "").strip() or None

    with db() as conn:
        month_id = int(payload["month_id"])
        account_id = int(payload["account_id"])
        validate_transaction_date(conn, month_id, tx_date)
        conn.execute("INSERT OR IGNORE INTO transaction_labels(name) VALUES (?)", (label,))
        tx_id = payload.get("id")
        if tx_id:
            old = conn.execute("SELECT * FROM transactions WHERE id = ?", (int(tx_id),)).fetchone()
            if old is None:
                raise ValueError("Transaction introuvable")
            conn.execute("UPDATE transactions SET sort_index = 0 WHERE id = ?", (int(tx_id),))
            compact_transaction_indexes(conn, int(old["month_id"]), int(old["account_id"]))
            sort_index = requested_index or next_transaction_index(conn, month_id, account_id)
            shift_transaction_indexes(conn, month_id, account_id, sort_index)
            conn.execute(
                """
                UPDATE transactions
                SET date = ?, label = ?, amount = ?, sort_index = ?, comment = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (tx_date, label, amount, sort_index, comment, int(tx_id)),
            )
            saved_id = int(tx_id)
        else:
            sort_index = requested_index or next_transaction_index(conn, month_id, account_id)
            shift_transaction_indexes(conn, month_id, account_id, sort_index)
            conn.execute(
                """
                INSERT INTO transactions(month_id, account_id, date, label, amount, sort_index, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (month_id, account_id, tx_date, label, amount, sort_index, comment),
            )
            saved_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        compact_transaction_indexes(conn, month_id, account_id)
        sort_index = conn.execute("SELECT sort_index FROM transactions WHERE id = ?", (saved_id,)).fetchone()["sort_index"]
        mark_matching_budget_schedule_found(conn, month_id, label, amount)
        rows = transaction_indexes(conn, month_id, account_id)
    return {"id": saved_id, "date": tx_date or "", "sort_index": sort_index, "rows": rows}


def mark_matching_budget_schedule_found(conn: sqlite3.Connection, month_id: int, label: str, amount: float) -> None:
    conn.execute(
        """
        UPDATE budget_schedule
        SET status = 'found'
        WHERE id = (
            SELECT id
            FROM budget_schedule
            WHERE month_id = ?
              AND status = 'scheduled'
              AND label = ?
              AND ABS(amount - ?) < 0.005
            ORDER BY id
            LIMIT 1
        )
        """,
        (month_id, label, amount),
    )


def parse_sort_index(value: object) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = int(raw)
    if parsed < 1:
        raise ValueError("Index invalide")
    return parsed


def normalize_date(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parts = raw.replace("-", "/").split("/")
    if len(parts) == 3 and len(parts[0]) == 4:
        year, month, day = (int(part) for part in parts)
    elif len(parts) == 3:
        day, month, year = (int(part) for part in parts)
    elif len(parts) == 2:
        day, month = (int(part) for part in parts)
        year = date.today().year
    else:
        raise ValueError("Date invalide")
    return date(year, month, day).isoformat()


def validate_transaction_date(conn: sqlite3.Connection, month_id: int, tx_date: str | None) -> None:
    if tx_date is None:
        raise ValueError("Date obligatoire")
    period = conn.execute("SELECT start_date, end_date FROM months WHERE id = ?", (month_id,)).fetchone()
    if period is None:
        raise ValueError("Période introuvable")
    if not period["start_date"]:
        raise ValueError("Début de période manquant")

    parsed_date = datetime.strptime(tx_date, "%Y-%m-%d").date()
    start_date = datetime.strptime(period["start_date"], "%Y-%m-%d").date()
    if parsed_date < start_date:
        raise ValueError(f"La date doit être >= {period['start_date']}")
    if period["end_date"]:
        end_date = datetime.strptime(period["end_date"], "%Y-%m-%d").date()
        if parsed_date >= end_date:
            raise ValueError(f"La date doit être < {period['end_date']}")


def next_transaction_index(conn: sqlite3.Connection, month_id: int, account_id: int) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(MAX(sort_index), 0) + 1 AS next_index
        FROM transactions
        WHERE month_id = ? AND account_id = ?
        """,
        (month_id, account_id),
    ).fetchone()
    return int(row["next_index"])


def shift_transaction_indexes(conn: sqlite3.Connection, month_id: int, account_id: int, start_index: int) -> None:
    conn.execute(
        """
        UPDATE transactions
        SET sort_index = sort_index + 1
        WHERE month_id = ? AND account_id = ? AND sort_index >= ?
        """,
        (month_id, account_id, start_index),
    )


def compact_transaction_indexes(conn: sqlite3.Connection, month_id: int, account_id: int) -> None:
    rows = conn.execute(
        """
        SELECT id
        FROM transactions
        WHERE month_id = ? AND account_id = ? AND sort_index > 0
        ORDER BY COALESCE(date, '9999-12-31'), sort_index, id
        """,
        (month_id, account_id),
    ).fetchall()
    for index, row in enumerate(rows, start=1):
        conn.execute("UPDATE transactions SET sort_index = ? WHERE id = ?", (index, row["id"]))


def transaction_indexes(conn: sqlite3.Connection, month_id: int, account_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT id, date, sort_index
        FROM transactions
        WHERE month_id = ? AND account_id = ?
        ORDER BY COALESCE(date, '9999-12-31'), sort_index, id
        """,
        (month_id, account_id),
    ).fetchall()
    return [{"id": row["id"], "date": row["date"] or "", "sort_index": row["sort_index"]} for row in rows]


def delete_transaction(payload: dict[str, object]) -> dict[str, object]:
    with db() as conn:
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (int(payload["id"]),)).fetchone()
        if row is None:
            raise ValueError("Transaction introuvable")
        conn.execute("DELETE FROM transactions WHERE id = ?", (int(payload["id"]),))
        compact_transaction_indexes(conn, int(row["month_id"]), int(row["account_id"]))
        rows = transaction_indexes(conn, int(row["month_id"]), int(row["account_id"]))
    return {"rows": rows}


def clear_transactions(payload: dict[str, object]) -> dict[str, object]:
    with db() as conn:
        month_id = int(payload["month_id"])
        account_id = int(payload["account_id"])
        conn.execute("DELETE FROM transactions WHERE month_id = ? AND account_id = ?", (month_id, account_id))
    return {"rows": []}


def reorder_transaction(payload: dict[str, object]) -> dict[str, object]:
    tx_id = int(payload["id"])
    target_id = int(payload["target_id"])
    position = str(payload.get("position") or "before")
    if position not in {"before", "after"}:
        raise ValueError("Position invalide")
    with db() as conn:
        moved = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        target = conn.execute("SELECT * FROM transactions WHERE id = ?", (target_id,)).fetchone()
        if moved is None or target is None:
            raise ValueError("Transaction introuvable")
        if moved["month_id"] != target["month_id"] or moved["account_id"] != target["account_id"]:
            raise ValueError("Déplacement invalide")

        month_id = int(moved["month_id"])
        account_id = int(moved["account_id"])
        conn.execute("UPDATE transactions SET sort_index = 0 WHERE id = ?", (tx_id,))
        compact_transaction_indexes(conn, month_id, account_id)
        target = conn.execute("SELECT * FROM transactions WHERE id = ?", (target_id,)).fetchone()
        new_date = target["date"]
        validate_transaction_date(conn, month_id, new_date)
        new_index = int(target["sort_index"]) + (1 if position == "after" else 0)
        shift_transaction_indexes(conn, month_id, account_id, new_index)
        conn.execute(
            "UPDATE transactions SET date = ?, sort_index = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_date, new_index, tx_id),
        )
        compact_transaction_indexes(conn, month_id, account_id)
        new_index = conn.execute("SELECT sort_index FROM transactions WHERE id = ?", (tx_id,)).fetchone()["sort_index"]
        rows = transaction_indexes(conn, month_id, account_id)
    return {"date": new_date or "", "sort_index": new_index, "rows": rows}


def create_label_from_text(payload: dict[str, object]) -> dict[str, object]:
    label_name = str(payload.get("value") or "").strip()
    if not label_name:
        raise ValueError("Intitulé obligatoire")

    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO transaction_labels(name) VALUES (?)", (label_name,))
        label = conn.execute("SELECT id, name FROM transaction_labels WHERE name = ?", (label_name,)).fetchone()

    return {
        "label": {"id": label["id"], "name": label["name"]},
    }


def save_monthly_budget_row(payload: dict[str, object]) -> dict[str, object]:
    day = int(str(payload.get("day") or "").strip())
    if day < 1 or day > 31:
        raise ValueError("Jour invalide")
    label = str(payload.get("label") or "").strip()
    if not label:
        raise ValueError("Intitulé obligatoire")
    amount = float(str(payload.get("amount") or 0).replace(",", "."))
    row_id = payload.get("id")
    with db() as conn:
        if row_id:
            conn.execute(
                "UPDATE monthly_budget SET day = ?, label = ?, amount = ? WHERE id = ?",
                (day, label, amount, int(row_id)),
            )
            saved_id = int(row_id)
        else:
            conn.execute(
                "INSERT INTO monthly_budget(day, label, amount) VALUES (?, ?, ?)",
                (day, label, amount),
            )
            saved_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"id": saved_id, "day": day, "label": label, "amount": amount}


def cancel_budget_schedule(payload: dict[str, object]) -> dict[str, object]:
    schedule_id = int(payload["id"])
    with db() as conn:
        row = conn.execute("SELECT * FROM budget_schedule WHERE id = ?", (schedule_id,)).fetchone()
        if row is None:
            raise ValueError("Entrée budget introuvable")
        conn.execute("UPDATE budget_schedule SET status = 'cancel' WHERE id = ?", (schedule_id,))
    return {"id": schedule_id, "status": "cancel", "status_label": "Annulé"}


def instantiate_budget_schedule(payload: dict[str, object]) -> dict[str, object]:
    schedule_id = int(payload["id"])
    account_id = int(payload["account_id"])
    tx_date = date.today().isoformat()
    with db() as conn:
        scheduled = conn.execute("SELECT * FROM budget_schedule WHERE id = ?", (schedule_id,)).fetchone()
        if scheduled is None:
            raise ValueError("Entrée budget introuvable")
        if scheduled["status"] != "scheduled":
            raise ValueError("Cette entrée n'est plus planifiée")
        account = conn.execute("SELECT id, name FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if account is None:
            raise ValueError("Compte introuvable")
        label = str(scheduled["label"])
        amount = float(scheduled["amount"] or 0)
        month_id = int(scheduled["month_id"])
        conn.execute("INSERT OR IGNORE INTO transaction_labels(name) VALUES (?)", (label,))
        sort_index = next_transaction_index(conn, month_id, account_id)
        shift_transaction_indexes(conn, month_id, account_id, sort_index)
        conn.execute(
            """
            INSERT INTO transactions(month_id, account_id, date, label, amount, sort_index, comment)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (month_id, account_id, tx_date, label, amount, sort_index),
        )
        tx_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        compact_transaction_indexes(conn, month_id, account_id)
        sort_index = conn.execute("SELECT sort_index FROM transactions WHERE id = ?", (tx_id,)).fetchone()["sort_index"]
    return {
        "id": tx_id,
        "account_id": account_id,
        "account_name": account["name"],
        "date": tx_date,
        "label": label,
        "amount": amount,
        "sort_index": sort_index,
    }


def update_transaction(payload: dict[str, object]) -> None:
    tx_id = int(payload["id"])
    field = str(payload["field"])
    value = payload.get("value")
    allowed = {"date", "label", "amount", "comment"}
    if field not in allowed:
        raise ValueError("Champ non autorisé")
    if field == "amount":
        value = float(str(value).replace(",", ".") or 0)
    if field == "date":
        value = normalize_date(value)
    if field == "label":
        value = str(value).strip()
        if not value:
            raise ValueError("Intitulé obligatoire")
    with db() as conn:
        if field == "date":
            row = conn.execute("SELECT month_id FROM transactions WHERE id = ?", (tx_id,)).fetchone()
            if row is None:
                raise ValueError("Transaction introuvable")
            validate_transaction_date(conn, int(row["month_id"]), value)
        if field == "label":
            conn.execute("INSERT OR IGNORE INTO transaction_labels(name) VALUES (?)", (value,))
            conn.execute(
                "UPDATE transactions SET label = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (value, tx_id),
            )
        else:
            conn.execute(f"UPDATE transactions SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (value, tx_id))


def save_named_row(table: str, payload: dict[str, object]) -> dict[str, object]:
    name = str(payload.get("value") or "").strip()
    if not name:
        raise ValueError("Valeur obligatoire")
    row_id = payload.get("id")
    with db() as conn:
        if row_id:
            conn.execute(f"UPDATE {table} SET name = ? WHERE id = ?", (name, int(row_id)))
            saved_id = int(row_id)
            rows = account_indexes(conn) if table == "accounts" else []
        else:
            if table == "accounts":
                sort_index = next_account_index(conn)
                conn.execute("INSERT INTO accounts(name, sort_index) VALUES (?, ?)", (name, sort_index))
            else:
                conn.execute(f"INSERT INTO {table}(name) VALUES (?)", (name,))
            saved_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            rows = account_indexes(conn) if table == "accounts" else []
    return {"id": saved_id, "value": name, "rows": rows}


def next_account_index(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COALESCE(MAX(sort_index), 0) + 1 FROM accounts").fetchone()[0])


def compact_account_indexes(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT id FROM accounts ORDER BY sort_index, name, id").fetchall()
    for index, row in enumerate(rows, start=1):
        conn.execute("UPDATE accounts SET sort_index = ? WHERE id = ?", (index, row["id"]))


def account_indexes(conn: sqlite3.Connection) -> list[dict[str, object]]:
    rows = conn.execute("SELECT id, sort_index FROM accounts ORDER BY sort_index, name, id").fetchall()
    return [{"id": row["id"], "sort_index": row["sort_index"]} for row in rows]


def reorder_account(payload: dict[str, object]) -> dict[str, object]:
    account_id = int(payload["id"])
    target_id = int(payload["target_id"])
    position = str(payload.get("position") or "before")
    if position not in {"before", "after"}:
        raise ValueError("Position invalide")
    with db() as conn:
        account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        target = conn.execute("SELECT * FROM accounts WHERE id = ?", (target_id,)).fetchone()
        if account is None or target is None:
            raise ValueError("Compte introuvable")
        conn.execute("UPDATE accounts SET sort_index = 0 WHERE id = ?", (account_id,))
        compact_account_indexes(conn)
        target = conn.execute("SELECT * FROM accounts WHERE id = ?", (target_id,)).fetchone()
        new_index = int(target["sort_index"]) + (1 if position == "after" else 0)
        conn.execute("UPDATE accounts SET sort_index = sort_index + 1 WHERE sort_index >= ?", (new_index,))
        conn.execute("UPDATE accounts SET sort_index = ? WHERE id = ?", (new_index, account_id))
        compact_account_indexes(conn)
        rows = account_indexes(conn)
        sort_index = conn.execute("SELECT sort_index FROM accounts WHERE id = ?", (account_id,)).fetchone()["sort_index"]
    return {"sort_index": sort_index, "rows": rows}


def update_account_summary(payload: dict[str, object]) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE accounts SET show_in_summary = ? WHERE id = ?",
            (1 if payload.get("value") else 0, int(payload["id"])),
        )


def update_account_visible_if_empty(payload: dict[str, object]) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE accounts SET visible_if_empty = ? WHERE id = ?",
            (1 if payload.get("value") else 0, int(payload["id"])),
        )


def update_account_balance(payload: dict[str, object]) -> None:
    field = str(payload.get("field") or "")
    if field != "opening":
        raise ValueError("Champ non autorisé")
    value = float(str(payload.get("value") or 0).replace(",", "."))
    with db() as conn:
        conn.execute(
            """
            UPDATE account_balances
            SET opening = ?
            WHERE month_id = ? AND account_id = ?
            """,
            (value, int(payload["month_id"]), int(payload["account_id"])),
        )


def save_label_row(payload: dict[str, object]) -> dict[str, object]:
    old_name = None
    row_id = payload.get("id")
    if row_id:
        with db() as conn:
            row = conn.execute("SELECT name FROM transaction_labels WHERE id = ?", (int(row_id),)).fetchone()
            old_name = row["name"] if row else None
    result = save_named_row("transaction_labels", payload)
    if old_name:
        with db() as conn:
            conn.execute("UPDATE transactions SET label = ? WHERE label = ?", (result["value"], old_name))
    return result


def delete_named_row(table: str, payload: dict[str, object]) -> None:
    with db() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (int(payload["id"]),))


def delete_account(payload: dict[str, object]) -> None:
    account_id = int(payload["id"])
    with db() as conn:
        used = conn.execute(
            """
            SELECT
              EXISTS(SELECT 1 FROM transactions WHERE account_id = ?) AS has_transactions,
              EXISTS(SELECT 1 FROM account_balances WHERE account_id = ?) AS has_balances
            """,
            (account_id, account_id),
        ).fetchone()
        if used["has_transactions"] or used["has_balances"]:
            raise ValueError("Compte utilisé: décoche Synthèse au lieu de le supprimer")
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))


def update_simple(table: str, payload: dict[str, object]) -> None:
    with db() as conn:
        conn.execute(f"UPDATE {table} SET name = ? WHERE id = ?", (str(payload.get("value") or "").strip(), int(payload["id"])))


def update_label(payload: dict[str, object]) -> None:
    label_id = int(payload["id"])
    field = str(payload["field"])
    value = payload.get("value")
    if field != "name":
        raise ValueError("Champ non autorisé")
    with db() as conn:
        new_name = str(value).strip()
        if not new_name:
            raise ValueError("Intitulé obligatoire")
        old_label = conn.execute("SELECT name FROM transaction_labels WHERE id = ?", (label_id,)).fetchone()["name"]
        conn.execute("UPDATE transaction_labels SET name = ? WHERE id = ?", (new_name, label_id))
        conn.execute("UPDATE transactions SET label = ? WHERE label = ?", (new_name, old_label))
