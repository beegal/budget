from __future__ import annotations


def validation_view(validation: dict[str, object] | None) -> dict[str, object] | None:
    if not validation:
        return None
    rows = []
    for row in validation["rows"]:
        rows.append(
            {
                "line": row["line"],
                "date": row["date"],
                "label": row["label"],
                "amount": row["amount"],
                "comment": row["comment"] or "",
                "errors": "; ".join(row["errors"]),
                "row_class": "import-row-error" if row["errors"] else "",
            }
        )
    return {
        "rows": rows,
        "correct_count": validation["correct_count"],
        "problem_count": validation["problem_count"],
        "problem_class": "negative" if validation["problem_count"] else "positive",
        "existing_label_count": validation["existing_label_count"],
        "create_label_count": validation["create_label_count"],
    }
