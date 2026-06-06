from __future__ import annotations

import sqlite3


def parse_period_ids(params: dict[str, list[str]], periods: list[sqlite3.Row]) -> tuple[list[int], bool]:
    raw = params.get("periods", params.get("period", [""]))[0].strip()
    return parse_row_ids(raw, periods)


def parse_account_ids(params: dict[str, list[str]], accounts: list[sqlite3.Row]) -> tuple[list[int], bool]:
    raw = params.get("accounts", params.get("account", [""]))[0].strip()
    return parse_row_ids(raw, accounts)


def parse_row_ids(raw: str, rows: list[sqlite3.Row]) -> tuple[list[int], bool]:
    all_ids = [int(row["id"]) for row in rows]
    if not raw or raw in {"all", "none"}:
        return all_ids, True
    by_name = {str(row["name"]).casefold(): int(row["id"]) for row in rows}
    selected: list[int] = []
    for part in raw.split(","):
        value = part.strip()
        if not value:
            continue
        period_id = int(value) if value.isdigit() else by_name.get(value.casefold())
        if period_id in all_ids and period_id not in selected:
            selected.append(period_id)
    if not selected:
        return all_ids, True
    return selected, False


def period_selector_view(periods: list[sqlite3.Row], selected_ids: list[int], all_selected: bool) -> dict[str, object]:
    return row_selector_view(periods, selected_ids, all_selected)


def account_selector_view(accounts: list[sqlite3.Row], selected_ids: list[int], all_selected: bool) -> dict[str, object]:
    return row_selector_view(accounts, selected_ids, all_selected)


def row_selector_view(rows: list[sqlite3.Row], selected_ids: list[int], all_selected: bool) -> dict[str, object]:
    selected_set = set(selected_ids)
    selected_rows = rows if all_selected else [row for row in rows if int(row["id"]) in selected_set]
    return {
        "value": "all" if all_selected else ",".join(str(period_id) for period_id in selected_ids),
        "all_selected": all_selected,
        "periods": [
            {
                "id": row["id"],
                "name": row["name"],
                "checked": all_selected or int(row["id"]) in selected_set,
            }
            for row in rows
        ],
        "tags": [{"id": row["id"], "name": row["name"]} for row in selected_rows],
    }
