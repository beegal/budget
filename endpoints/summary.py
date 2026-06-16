from __future__ import annotations

import sqlite3
from urllib.parse import parse_qs
from urllib.parse import urlencode

from components.period import balance_tone, is_transfer_group, money_or_empty
from database import db
from endpoints.filters import parse_period_ids, period_selector_view
from i18n import translate
from web_helpers import money, render_template, transaction_filter_url, user_layout


def page(query: str, user_id: str) -> bytes:
    params = parse_qs(query)
    active_tab = params.get("tab", ["table"])[0]
    if active_tab not in {"table", "chart"}:
        active_tab = "table"
    with db() as conn:
        periods = conn.execute(
            "SELECT id, name FROM period WHERE user_id = ? ORDER BY COALESCE(start_date, ''), id",
            (user_id,),
        ).fetchall()
        selected_period_ids, all_periods = parse_period_ids(params, periods)
        rows = summary_rows(conn, selected_period_ids, user_id) if selected_period_ids else []
        visible_rows = [row for row in rows if not is_transfer_group(str(row["label_group"]))]
        label_groups = [str(row["label_group"]) for row in visible_rows]
        selected_label_groups, all_labels = parse_label_groups(params, label_groups)
        chart_rows = chart_summary_rows(conn, selected_period_ids, user_id) if selected_period_ids else []

    total_income = sum(float(row["income"] or 0) for row in visible_rows)
    total_expense = sum(float(row["expense"] or 0) for row in visible_rows)
    total_net = sum(float(row["net"] or 0) for row in visible_rows)
    body = render_template(
        "summary.html",
        active_tab=active_tab,
        table_tab_url=summary_tab_url(selected_period_ids, selected_label_groups, "table", all_periods, all_labels),
        chart_tab_url=summary_tab_url(selected_period_ids, selected_label_groups, "chart", all_periods, all_labels),
        period_selector=period_selector_view(periods, selected_period_ids, all_periods),
        label_selector=label_selector_view(label_groups, selected_label_groups, all_labels),
        rows=[summary_row_view(row, selected_period_ids) for row in visible_rows],
        totals={
            "income": money(total_income),
            "expense": money(total_expense),
            "net": money(total_net),
            "net_class": balance_tone(total_net),
        },
        chart=summary_chart_view(periods, selected_period_ids, selected_label_groups, chart_rows),
    )
    return user_layout(translate("summary.title"), body, user_id)


def summary_rows(conn: sqlite3.Connection, period_ids: list[int], user_id: str) -> list[sqlite3.Row]:
    placeholders = ", ".join("?" for _ in period_ids)
    return conn.execute(
        f"""
        WITH grouped AS (
            SELECT
                CASE
                    WHEN INSTR(t.label, '-') > 0 THEN TRIM(SUBSTR(t.label, 1, INSTR(t.label, '-') - 1))
                    ELSE TRIM(t.label)
                END AS label_group,
                t.amount
            FROM transactions t
            WHERE t.user_id = ? AND t.period_id IN ({placeholders})
            UNION ALL
            SELECT ? AS label_group,
                   bs.amount
            FROM budget_schedule bs
            WHERE bs.user_id = ? AND bs.period_id IN ({placeholders}) AND bs.status = 'scheduled'
        )
        SELECT grouped.label_group,
               COALESCE(SUM(CASE WHEN grouped.amount > 0 THEN grouped.amount END), 0) AS income,
               COALESCE(SUM(CASE WHEN grouped.amount < 0 THEN grouped.amount END), 0) AS expense,
               COALESCE(SUM(grouped.amount), 0) AS net
        FROM grouped
        GROUP BY grouped.label_group
        ORDER BY grouped.label_group
        """,
        [user_id, *period_ids, translate("summary.planned-budget"), user_id, *period_ids],
    ).fetchall()


def summary_row_view(row: sqlite3.Row, period_ids: list[int]) -> dict[str, object]:
    return {
        "label_group": row["label_group"],
        "href": transaction_filter_url(period_ids, row["label_group"]),
        "income": money_or_empty(row["income"]),
        "expense": money_or_empty(row["expense"]),
        "net": money_or_empty(row["net"]),
        "net_class": balance_tone(row["net"]),
    }


def parse_label_groups(params: dict[str, list[str]], label_groups: list[str]) -> tuple[list[str], bool]:
    raw = params.get("labels", [""])[0].strip()
    if raw == "none":
        return [], False
    if not raw or raw == "all":
        return label_groups, True
    by_name = {label.casefold(): label for label in label_groups}
    selected: list[str] = []
    for part in raw.split(","):
        value = part.strip()
        if not value:
            continue
        label = by_name.get(value.casefold())
        if label and label not in selected:
            selected.append(label)
    if not selected:
        return label_groups, True
    return selected, False


def label_selector_view(label_groups: list[str], selected_groups: list[str], all_selected: bool) -> dict[str, object]:
    selected_set = {label.casefold() for label in selected_groups}
    selected_rows = label_groups if all_selected else [label for label in label_groups if label.casefold() in selected_set]
    return {
        "value": "all" if all_selected else "none" if not selected_groups else ",".join(selected_groups),
        "all_selected": all_selected,
        "placeholder": translate("summary.label-filter"),
        "search_placeholder": translate("summary.filter-list"),
        "toggle_label": translate("common.labels"),
        "all_label": translate("common.all"),
        "none_label": translate("common.none-selection"),
        "remove_label": translate("common.remove"),
        "options": [
            {
                "id": label,
                "name": label,
                "checked": all_selected or label.casefold() in selected_set,
            }
            for label in label_groups
        ],
        "tags": [{"id": label, "name": label} for label in selected_rows],
    }


def summary_tab_url(
    period_ids: list[int],
    label_groups: list[str],
    tab: str,
    all_periods: bool,
    all_labels: bool,
) -> str:
    query = {"tab": tab}
    if not all_periods:
        query["periods"] = ",".join(str(period_id) for period_id in period_ids)
    if tab == "chart" and not all_labels:
        query["labels"] = ",".join(label_groups)
    return f"/summary?{urlencode(query)}"


def chart_summary_rows(conn: sqlite3.Connection, period_ids: list[int], user_id: str) -> list[sqlite3.Row]:
    placeholders = ", ".join("?" for _ in period_ids)
    return conn.execute(
        f"""
        WITH grouped AS (
            SELECT
                t.period_id,
                CASE
                    WHEN INSTR(t.label, '-') > 0 THEN TRIM(SUBSTR(t.label, 1, INSTR(t.label, '-') - 1))
                    ELSE TRIM(t.label)
                END AS label_group,
                t.amount
            FROM transactions t
            WHERE t.user_id = ? AND t.period_id IN ({placeholders})
            UNION ALL
            SELECT bs.period_id,
                   ? AS label_group,
                   bs.amount
            FROM budget_schedule bs
            WHERE bs.user_id = ? AND bs.period_id IN ({placeholders}) AND bs.status = 'scheduled'
        )
        SELECT grouped.period_id,
               grouped.label_group,
               COALESCE(SUM(CASE WHEN grouped.amount > 0 THEN grouped.amount END), 0) AS income,
               COALESCE(SUM(CASE WHEN grouped.amount < 0 THEN grouped.amount END), 0) AS expense,
               COALESCE(SUM(grouped.amount), 0) AS net
        FROM grouped
        GROUP BY grouped.period_id, grouped.label_group
        ORDER BY grouped.period_id, grouped.label_group
        """,
        [user_id, *period_ids, translate("summary.planned-budget"), user_id, *period_ids],
    ).fetchall()


def summary_chart_view(
    periods: list[sqlite3.Row],
    selected_period_ids: list[int],
    selected_label_groups: list[str],
    rows: list[sqlite3.Row],
) -> dict[str, object]:
    selected_period_set = set(selected_period_ids)
    chart_periods = [row for row in periods if int(row["id"]) in selected_period_set]
    label_set = set(selected_label_groups)
    period_index = {int(row["id"]): index for index, row in enumerate(chart_periods)}
    points_by_label = {label: [chart_empty_point() for _ in chart_periods] for label in selected_label_groups}
    total_points = [chart_empty_point() for _ in chart_periods]

    for row in rows:
        label = str(row["label_group"])
        if is_transfer_group(label) or label not in label_set:
            continue
        index = period_index.get(int(row["period_id"]))
        if index is None:
            continue
        apply_chart_row(points_by_label[label][index], row)
        apply_chart_row(total_points[index], row)

    income_series = [{"name": translate("common.total"), "label": "", "points": total_points, "metric": "income_plot"}]
    income_series.extend({"name": label, "label": label, "points": points_by_label[label], "metric": "income_plot"} for label in selected_label_groups)
    expense_series = [{"name": translate("common.total"), "label": "", "points": total_points, "metric": "expense_plot"}]
    expense_series.extend({"name": label, "label": label, "points": points_by_label[label], "metric": "expense_plot"} for label in selected_label_groups)
    return {
        "has_data": bool(chart_periods and selected_label_groups),
        "graphs": [
            {
                "title": translate("common.income"),
                "view": line_chart_view(chart_periods, income_series),
            },
            {
                "title": translate("common.expense"),
                "view": line_chart_view(chart_periods, expense_series),
            },
        ],
    }


def chart_empty_point() -> dict[str, float]:
    return {"income": 0.0, "expense": 0.0, "net": 0.0, "income_plot": 0.0, "expense_plot": 0.0}


def apply_chart_row(point: dict[str, float], row: sqlite3.Row) -> None:
    income = float(row["income"] or 0)
    expense = abs(float(row["expense"] or 0))
    net = float(row["net"] or 0)
    point["income"] += income
    point["expense"] += expense
    point["net"] += net
    if net > 0:
        point["income_plot"] += net
    elif net < 0:
        point["expense_plot"] += abs(net)


def line_chart_view(periods: list[sqlite3.Row], raw_series: list[dict[str, object]]) -> dict[str, object]:
    width = 760
    height = 300
    left = 56
    right = 22
    top = 22
    bottom = 50
    plot_width = width - left - right
    plot_height = height - top - bottom
    all_values = [float(point[str(series["metric"])]) for series in raw_series for point in series["points"]] or [0.0]
    minimum = min(all_values)
    maximum = max(all_values)
    minimum = min(0.0, minimum)
    if minimum == maximum:
        if maximum == 0:
            maximum = 1.0
        else:
            minimum -= 1
            maximum += 1
    span = maximum - minimum
    count = max(len(periods), 1)

    def x_at(index: int) -> float:
        if count == 1:
            return left + plot_width / 2
        return left + (plot_width * index / (count - 1))

    def y_at(value: float) -> float:
        return top + ((maximum - value) / span) * plot_height

    palette = ["#0f5a6d", "#1976a2", "#0b7a44", "#b42318", "#8a5cf6", "#c26a00", "#596579", "#008a8a"]
    period_ids = [int(row["id"]) for row in periods]
    series_views = []
    for index, series in enumerate(raw_series):
        metric = str(series["metric"])
        label = str(series.get("label") or "")
        raw_points = list(series["points"])
        values = [float(point[metric]) for point in raw_points]
        if not any(value != 0 for value in values):
            continue
        line_segments = chart_line_segments(values, x_at, y_at)
        point_views = [
            {
                "x": f"{x_at(point_index):.1f}",
                "y": f"{y_at(value):.1f}",
                "income": money(raw_points[point_index]["income"]),
                "expense": money(raw_points[point_index]["expense"]),
                "net": money(raw_points[point_index]["net"]),
                "period": periods[point_index]["name"] if point_index < len(periods) else "",
                "href": chart_transaction_url([int(periods[point_index]["id"])], label) if point_index < len(periods) else "",
                "tooltip": chart_tooltip(
                    periods[point_index]["name"] if point_index < len(periods) else "",
                    str(series["name"]),
                    raw_points[point_index],
                ),
            }
            for point_index, value in enumerate(values)
            if value != 0
        ]
        series_views.append(
            {
                "name": series["name"],
                "line_segments": line_segments,
                "point_views": point_views,
                "color": palette[index % len(palette)],
                "href": chart_transaction_url(period_ids, label),
                "sum": money(sum(values)),
                "sum_class": balance_tone(sum(values)),
            }
        )

    return {
        "width": width,
        "height": height,
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "zero_y": f"{y_at(0):.1f}",
        "min_label": money(minimum),
        "max_label": money(maximum),
        "periods": [{"name": row["name"], "x": f"{x_at(index):.1f}"} for index, row in enumerate(periods)],
        "series": series_views,
        "has_data": bool(periods and len(raw_series) > 1),
    }


def chart_line_segments(values, x_at, y_at) -> list[str]:
    segments: list[str] = []
    current: list[str] = []
    for point_index, value in enumerate(values):
        if value == 0:
            if len(current) > 1:
                segments.append(" ".join(current))
            current = []
            continue
        current.append(f"{x_at(point_index):.1f},{y_at(value):.1f}")
    if len(current) > 1:
        segments.append(" ".join(current))
    return segments


def chart_tooltip(period: str, series_name: str, point: dict[str, float]) -> str:
    return (
        f"{money(point['net'])}\n"
        f"{translate('common.income')} : {money(point['income'])}\n"
        f"{translate('common.expense')} : {money(point['expense'])}"
    )


def chart_transaction_url(period_ids: list[int], label: str) -> str:
    query = {"periods": ",".join(str(period_id) for period_id in period_ids)}
    if label:
        query["q"] = label
    return f"/transactions?{urlencode(query)}"
