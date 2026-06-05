from __future__ import annotations

from components.common import label_picker, row_action_buttons
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


def account_row(row_id: int, name: str, sort_index: int, show_in_summary: bool, visible_if_empty: bool) -> str:
    return render_template(
        "components/account_row.html",
        row_id=row_id,
        name=name,
        sort_index=sort_index,
        show_in_summary=show_in_summary,
        visible_if_empty=visible_if_empty,
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
