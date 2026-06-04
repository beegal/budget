from __future__ import annotations

from components.common import label_picker, row_action_buttons
from web_helpers import esc, format_number


def settings_row(kind: str, row_id: int, name: str) -> str:
    if kind == "label":
        group_name, subcategory = split_label_name(name)
        return f"""<tr data-settings-row data-kind="{kind}" data-id="{row_id}">
  <td><input value="{esc(group_name)}" data-setting-value data-setting-part="group" data-original="{esc(group_name)}" autocomplete="off"></td>
  <td><input value="{esc(subcategory)}" data-setting-value data-setting-part="subcategory" data-original="{esc(subcategory)}" autocomplete="off"></td>
  <td class="row-actions">
    {row_action_buttons("setting")}
  </td>
</tr>"""
    return f"""<tr data-settings-row data-kind="{kind}" data-id="{row_id}">
  <td><input value="{esc(name)}" data-setting-value data-original="{esc(name)}" autocomplete="off"></td>
  <td class="row-actions">
    {row_action_buttons("setting")}
  </td>
</tr>"""


def split_label_name(name: str) -> tuple[str, str]:
    group_name, separator, subcategory = name.partition(" - ")
    if not separator:
        return name, ""
    return group_name, subcategory


def account_row(row_id: int, name: str, sort_index: int, show_in_summary: bool, visible_if_empty: bool) -> str:
    summary_checked = " checked" if show_in_summary else ""
    empty_checked = " checked" if visible_if_empty else ""
    return f"""<tr data-settings-row data-kind="account" data-id="{row_id}" draggable="false">
  <td class="row-index-cell"><button type="button" class="drag-handle" draggable="true" data-account-drag-handle title="Déplacer">↕</button><span class="row-index-value" data-account-index>{sort_index}</span></td>
  <td><input value="{esc(name)}" data-setting-value data-original="{esc(name)}" autocomplete="off"></td>
  <td class="center-cell"><input type="checkbox" data-account-summary data-id="{row_id}"{summary_checked}></td>
  <td class="center-cell"><input type="checkbox" data-account-visible-if-empty data-id="{row_id}"{empty_checked}></td>
  <td class="row-actions">
    {row_action_buttons("setting")}
  </td>
</tr>"""


def monthly_budget_row(row_id: int, day: int, label: str, amount: float) -> str:
    amount_class = "amount-positive" if amount > 0 else "amount-negative" if amount < 0 else ""
    amount_display = format_number(amount)
    return f"""<tr class="{amount_class}" data-budget-row data-id="{row_id}">
  <td><input data-budget-field="day" value="{day}" data-original="{day}" inputmode="numeric"></td>
  <td>{label_picker(label, 'data-budget-field="label"')}</td>
  <td><input data-budget-field="amount" value="{esc(amount_display)}" data-original="{esc(amount_display)}" inputmode="decimal"></td>
  <td class="row-actions">
    {row_action_buttons("budget")}
  </td>
</tr>"""


def empty_monthly_budget_row() -> str:
    return """<tr data-empty-budget-row>
  <td colspan="3" class="muted">Aucune entrée.</td>
  <td class="row-actions"></td>
</tr>"""
