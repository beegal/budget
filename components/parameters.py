from __future__ import annotations

from components.common import icon, label_picker, row_action_buttons
from i18n import translate
from web_helpers import format_number, render_template


def settings_row(kind: str, row_id: int, name: str) -> str:
    if kind == "label":
        group_name, subcategory = split_label_name(name)
    else:
        group_name, subcategory = "", ""
    return render_template(
        "components/settings_row.html",
        kind=kind,
        row_id=row_id,
        name=name,
        group_name=group_name,
        subcategory=subcategory,
        actions=row_action_buttons("setting"),
    )


def split_label_name(name: str) -> tuple[str, str]:
    group_name, separator, subcategory = name.partition(" - ")
    if not separator:
        return name, ""
    return group_name, subcategory


def account_row(
    row_id: int,
    name: str,
    sort_index: int,
    show_in_summary: bool,
    visible_if_empty: bool,
    transaction_count: int,
    accounts: list[object],
) -> str:
    can_delete = transaction_count == 0
    delete_title = (
        translate("parameters.delete-account")
        if can_delete
        else translate("parameters.delete-account-blocked", transactions=transaction_count)
    )
    merge_choices = [
        {"id": account["id"], "name": account["name"]}
        for account in accounts
        if int(account["id"]) != int(row_id)
    ]
    return render_template(
        "components/account_row.html",
        row_id=row_id,
        name=name,
        sort_index=sort_index,
        show_in_summary=show_in_summary,
        visible_if_empty=visible_if_empty,
        transaction_count=transaction_count,
        can_delete=can_delete,
        delete_title=delete_title,
        merge_choices=merge_choices,
        merge_icon=icon("merge"),
        trash_icon=icon("trash"),
        actions=row_action_buttons("setting"),
    )


def monthly_budget_row(row_id: int, day: int, label: str, amount: float) -> str:
    amount_class = "amount-positive" if amount > 0 else "amount-negative" if amount < 0 else ""
    amount_display = format_number(amount)
    return render_template(
        "components/monthly_budget_row.html",
        row_id=row_id,
        day=day,
        amount_class=amount_class,
        amount_display=amount_display,
        label_picker=label_picker(label, 'data-budget-field="label"'),
        actions=row_action_buttons("budget"),
    )


def empty_monthly_budget_row() -> str:
    return render_template("components/empty_monthly_budget_row.html")


def recurring_budget_candidates_panel(candidates: list[dict[str, object]]) -> str:
    return render_template("components/recurring_budget_candidates.html", candidates=candidates)
