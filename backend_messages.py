from __future__ import annotations


def invalid_mysql_name(label: str, value: str) -> str:
    return f"Nom MySQL invalide pour {label}: {value}"


def template_not_found(template_name: str) -> str:
    return f"Template {template_name} not found"
