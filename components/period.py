from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from components.common import icon, label_picker, row_action_buttons
from i18n import translate
from transfer_labels import is_internal_transfer_group
from web_helpers import format_date, format_number, money, transaction_filter_url
from user_preferences import current_number_decimals


def period_tabs_view(
    period_id: int,
    active: str,
    visible_accounts: list[sqlite3.Row],
    hidden_accounts: list[sqlite3.Row],
) -> dict[str, object]:
    account_tabs = [account_tab_link_view(period_id, active, account) for account in visible_accounts]
    hidden_links = [
        {"href": f"/period/{period_id}?account={account['id']}", "name": account["name"]}
        for account in hidden_accounts
    ]
    return {
        "simple_tabs": [
            {"label": translate("period.overview"), "href": f"/period/{period_id}", "active_class": "active" if active == "overview" else ""},
            {"label": translate("period.budget"), "href": f"/period/{period_id}?account=budget", "active_class": "active" if active == "budget" else ""},
        ],
        "account_tabs": account_tabs,
        "hidden_links": hidden_links,
        "plus_icon": icon("plus"),
    }


def overview_view(
    period_id: int,
    summary_rows: list[sqlite3.Row],
    balance_rows: list[sqlite3.Row],
    transfer_rows: list[sqlite3.Row],
) -> dict[str, object]:
    non_transfer_rows = [row for row in summary_rows if not is_transfer_group(str(row["label_group"]))]
    total_income = sum(float(row["income"] or 0) for row in non_transfer_rows)
    total_expense = sum(float(row["expense"] or 0) for row in non_transfer_rows)
    total_net = sum(float(row["net"] or 0) for row in non_transfer_rows)
    transfer_total = sum(float(row["amount"] or 0) for row in transfer_rows)
    return {
        "type": "overview",
        "balance_rows": [balance_row_view(period_id, row) for row in balance_rows],
        "summary_rows": [summary_row_view(row, [period_id]) for row in non_transfer_rows],
        "transfer_rows": [transfer_row_view(row) for row in transfer_rows],
        "summary_total": {
            "income": money(total_income),
            "expense": money(total_expense),
            "net": money(total_net),
            "net_class": balance_tone(total_net),
        },
        "transfer_total": {
            "amount": money(transfer_total),
            "amount_class": balance_tone(transfer_total),
        },
    }


def account_tab_link_view(period_id: int, active: str, account: sqlite3.Row) -> dict[str, object]:
    transaction_count = int(account["transaction_count"] or 0)
    current_balance = float(account["current"] or 0)
    balance_class = "positive" if current_balance > 0 else "negative" if current_balance < 0 else "neutral"
    can_hide = transaction_count == 0
    hide_title = (
        translate("period.hide-account")
        if can_hide
        else translate("period.hide-account-blocked", transactions=transaction_count)
    )
    tooltip = "\n".join(
        [
            f"{translate('period.balance')}: {money(account['current'])}",
            translate("period.transaction-count", transactions=transaction_count, amount=money(account["transaction_total"])),
        ]
    )
    return {
        "id": account["id"],
        "name": account["name"],
        "href": f"/period/{period_id}?account={account['id']}",
        "selected": "active" if active == str(account["id"]) else "",
        "balance_class": balance_class,
        "tooltip": tooltip,
        "period_id": period_id,
        "can_hide": can_hide,
        "hide_title": hide_title,
        "trash_icon": icon("trash"),
    }


def balance_row_view(period_id: int, row: sqlite3.Row) -> dict[str, object]:
    return {
        "name": row["name"],
        "opening_class": balance_tone(row["opening"]),
        "period_id": period_id,
        "account_id": row["account_id"],
        "opening_raw": balance_raw(row["opening"]),
        "opening_defined_class": balance_defined_class(row["opening"]),
        "opening_display": balance_display(row["opening"]),
        "transaction_total": money(row["transaction_total"]),
        "transaction_total_class": balance_tone(row["transaction_total"]),
        "current_class": balance_tone(row["current"]),
        "current_defined_class": balance_defined_class(row["current"]),
        "current_display": balance_money_display(row["current"]),
    }


def summary_row_view(row: sqlite3.Row, period_ids: list[int] | None = None) -> dict[str, object]:
    period_ids = period_ids or []
    return {
        "label_group": row["label_group"],
        "href": transaction_filter_url(period_ids, row["label_group"]) if period_ids else "",
        "income": money_or_empty(row["income"]),
        "expense": money_or_empty(row["expense"]),
        "net": money_or_empty(row["net"]),
        "net_class": balance_tone(row["net"]),
    }


def transfer_row_view(row: sqlite3.Row) -> dict[str, object]:
    return {
        "date": row["date"],
        "account_name": row["account_name"],
        "label": row["label"],
        "amount": money(row["amount"]),
        "amount_class": balance_tone(row["amount"]),
    }


def balance_raw(value: object) -> str:
    return "" if value is None else format_number(value)


def money_or_empty(value: object) -> str:
    return "" if abs(float(value or 0)) < 0.005 else money(value)


def balance_display(value: object) -> str:
    return translate("period.unknown") if value is None else format_number(value)


def balance_money_display(value: object) -> str:
    return translate("period.unknown") if value is None else money(value)


def balance_defined_class(value: object) -> str:
    return "balance-undefined" if value is None else ""


def balance_tone(value: object) -> str:
    if value is None:
        return ""
    amount = float(value or 0)
    if amount > 0:
        return "positive"
    if amount < 0:
        return "negative"
    return ""


def budget_tab_view(period_id: int, rows: list[sqlite3.Row], accounts: list[sqlite3.Row], labels: list[sqlite3.Row]) -> dict[str, object]:
    return {
        "type": "budget",
        "period_id": period_id,
        "labels_json": json.dumps([row["name"] for row in labels], ensure_ascii=False),
        "rows": [budget_schedule_row_view(index, row, accounts) for index, row in enumerate(rows, start=1)],
        "plus_icon": icon("plus"),
        "clear_icon": icon("clear-list"),
    }


def budget_schedule_row_view(index: int, row: sqlite3.Row, accounts: list[sqlite3.Row]) -> dict[str, object]:
    status = str(row["status"])
    status_label = {
        "scheduled": translate("period.status-scheduled"),
        "found": translate("period.status-found"),
        "cancel": translate("period.status-canceled"),
    }.get(status, status)
    return {
        "index": index,
        "id": row["id"],
        "status": status,
        "status_label": status_label,
        "date": format_date(row["date"]) if row["date"] else "",
        "label": row["label"],
        "amount": money(row["amount"]),
        "actions": budget_schedule_actions_view(status),
        "account_choices": [{"id": account["id"], "name": account["name"]} for account in accounts],
    }


def budget_schedule_actions_view(status: str) -> list[dict[str, str]]:
    if status != "scheduled":
        return []
    return [
        {
            "class": "row-cancel",
            "data_attr": "data-budget-schedule-cancel",
            "title": translate("period.cancel-scheduled"),
            "icon": icon("ban"),
        },
        {
            "class": "row-confirm",
            "data_attr": "data-budget-schedule-confirm",
            "title": translate("period.send-to-account"),
            "icon": icon("send"),
        },
    ]


def is_transfer_group(label_group: str) -> bool:
    return is_internal_transfer_group(label_group)


def account_tab_view(
    period_id: int,
    period: sqlite3.Row,
    account: sqlite3.Row | None,
    transactions: list[sqlite3.Row],
    labels: list[sqlite3.Row],
) -> dict[str, object]:
    if account is None:
        return {"type": "missing-account"}
    opening_balance = account["opening"]
    running_balance = float(opening_balance or 0)
    operations_income = 0.0
    operations_expense = 0.0
    operations_total = 0.0
    rows = []
    for row in transactions:
        balance_title = (
            f"{translate('period.balance')}: {money(running_balance)}"
            if opening_balance is not None
            else f"{translate('period.balance')}: {translate('period.unknown')}"
        )
        rows.append(transaction_row_view(row, period, balance_title))
        amount = float(row["amount"] or 0)
        if amount > 0:
            operations_income += amount
        elif amount < 0:
            operations_expense += amount
        operations_total += amount
        running_balance += amount
    total_income_label = f"{translate('common.total')} {translate('common.income').casefold()}"
    total_expense_label = f"{translate('common.total')} {translate('common.expense').casefold()}"
    current_balance = (
        f"{translate('period.current-balance')} : {money(running_balance)} - "
        f"{total_income_label} : {money(operations_income)} - "
        f"{total_expense_label} : {money(operations_expense)} - "
        f"{translate('period.total-operations')} : {money(operations_total)}"
        if opening_balance is not None
        else f"{translate('period.current-balance')} : {translate('period.unknown')} - "
        f"{total_income_label} : {money(operations_income)} - "
        f"{total_expense_label} : {money(operations_expense)} - "
        f"{translate('period.total-operations')} : {money(operations_total)}"
    )
    opening_data = "" if opening_balance is None else format_number(opening_balance)
    return {
        "type": "account",
        "period_id": period_id,
        "account_id": account["id"],
        "account_name": account["name"],
        "labels_json": json.dumps([row["name"] for row in labels], ensure_ascii=False),
        "opening_data": opening_data,
        "number_decimals": current_number_decimals(),
        "rows": rows,
        "current_balance": current_balance,
        "plus_icon": icon("plus"),
        "clear_icon": icon("clear-list"),
        "upload_icon": icon("upload"),
        "download_icon": icon("download"),
    }


def transaction_row_view(row: sqlite3.Row, period: sqlite3.Row, balance_title: str) -> dict[str, object]:
    warning_reason = transaction_period_warning_reason(row, period)
    return {
        "id": row["id"],
        "amount_class": transaction_amount_class(row["amount"]),
        "sort_date": row["date"] or "",
        "sort_index": row["sort_index"],
        "balance_title": balance_title,
        "date": format_date(row["date"]),
        "label_picker": label_picker(row["label"], 'data-save="transaction" data-field="label"'),
        "amount": format_number(row["amount"]),
        "comment": row["comment"] or "",
        "warning_reason": warning_reason,
        "warning_icon": icon("warning") if warning_reason else "",
        "row_actions": row_action_buttons("row"),
    }


def transaction_amount_class(amount: float) -> str:
    if amount > 0:
        return "amount-positive"
    if amount < 0:
        return "amount-negative"
    return ""


def transaction_period_warning_reason(row: sqlite3.Row, period: sqlite3.Row) -> str:
    tx_date_raw = row["date"]
    if not tx_date_raw:
        return ""
    try:
        tx_date = datetime.strptime(str(tx_date_raw), "%Y-%m-%d").date()
        start_date = datetime.strptime(str(period["start_date"]), "%Y-%m-%d").date() if period["start_date"] else None
        end_date = datetime.strptime(str(period["end_date"]), "%Y-%m-%d").date() if period["end_date"] else None
    except ValueError:
        return translate("period.date-not-recognized")
    if start_date and tx_date < start_date:
        return translate("period.date-before-period", date=format_date(tx_date_raw), start=format_date(period["start_date"]))
    if end_date and tx_date > end_date:
        return translate("period.date-after-period", date=format_date(tx_date_raw), end=format_date(period["end_date"]))
    return ""
