from __future__ import annotations

import calendar
import locale
from pathlib import Path
from typing import Any
import unicodedata

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.yaml"


def parse_simple_yaml(text: str) -> dict[str, Any]:
    lines = yaml_lines(text)
    value, _ = parse_yaml_block(lines, 0, 0)
    return value if isinstance(value, dict) else {}


def yaml_lines(text: str) -> list[tuple[int, str]]:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if line.strip():
            lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    return lines


def parse_yaml_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    is_list = lines[index][1].startswith("- ")
    if is_list:
        values = []
        while index < len(lines):
            current_indent, stripped = lines[index]
            if current_indent < indent or not stripped.startswith("- "):
                break
            if current_indent > indent:
                index += 1
                continue
            item = stripped[2:].strip()
            if ":" in item:
                key, raw_value = split_yaml_pair(item)
                if raw_value:
                    entry = {key: parse_yaml_scalar(raw_value)}
                    index += 1
                else:
                    nested, index = parse_yaml_block(lines, index + 1, indent + 2)
                    entry = {key: nested}
                while index < len(lines):
                    next_indent, next_stripped = lines[index]
                    if next_indent <= indent:
                        break
                    if next_indent == indent + 2 and not next_stripped.startswith("- ") and ":" in next_stripped:
                        child_key, child_value = split_yaml_pair(next_stripped)
                        if child_value:
                            entry[child_key] = parse_yaml_scalar(child_value)
                            index += 1
                        else:
                            nested, index = parse_yaml_block(lines, index + 1, indent + 4)
                            entry[child_key] = nested
                    else:
                        break
                values.append(entry)
            else:
                values.append(parse_yaml_scalar(item))
                index += 1
        return values, index

    values = {}
    while index < len(lines):
        current_indent, stripped = lines[index]
        if current_indent < indent or stripped.startswith("- "):
            break
        if current_indent > indent:
            index += 1
            continue
        key, raw_value = split_yaml_pair(stripped)
        if raw_value:
            values[key] = parse_yaml_scalar(raw_value)
            index += 1
        else:
            values[key], index = parse_yaml_block(lines, index + 1, indent + 2)
    return values, index


def split_yaml_pair(value: str) -> tuple[str, str]:
    if ":" not in value:
        return value.strip(), ""
    key, raw_value = value.split(":", 1)
    return key.strip(), raw_value.strip()


def parse_yaml_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return parse_simple_yaml(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def get_default_locale() -> str:
    config = load_config()
    section = config.get("i18n", config.get("I18n", {}))
    value = section.get("default-locale", "")
    return str(value).strip()


def apply_default_locale() -> None:
    configured_locale = get_default_locale()
    for locale_name in (configured_locale, ""):
        try:
            locale.setlocale(locale.LC_TIME, locale_name)
            return
        except locale.Error:
            continue


def get_month_names() -> list[str]:
    apply_default_locale()
    return [calendar.month_name[index] for index in range(1, 13)]


def get_month_lookup(month_names: list[str]) -> dict[str, int]:
    lookup = {}
    prefixes: dict[str, set[int]] = {}
    for index, name in enumerate(month_names, start=1):
        normalized_name = strip_accents(name)
        lookup[normalized_name] = index
        abbreviation = calendar.month_abbr[index]
        if abbreviation:
            lookup[strip_accents(abbreviation).rstrip(".")] = index
        for length in range(3, len(normalized_name)):
            prefixes.setdefault(normalized_name[:length], set()).add(index)
    for prefix, indexes in prefixes.items():
        if len(indexes) == 1:
            lookup.setdefault(prefix, next(iter(indexes)))
    return lookup


def get_number_decimals() -> int:
    config = load_config()
    section = config.get("display", config.get("Display", {}))
    value = section.get("number-decimals", 2)
    try:
        decimals = int(value)
    except (TypeError, ValueError):
        return 2
    return max(0, min(decimals, 6))


def get_date_order() -> str:
    date_format = get_date_format()
    if date_format == "mdy":
        return "mdy"
    locale_name = get_default_locale().lower()
    if locale_name.startswith(("en_us", "en-ca", "en_ph")):
        return "mdy"
    return "dmy"


def get_date_format() -> str:
    config = load_config()
    section = config.get("i18n", {})
    value = str(section.get("date-format", "")).strip().lower()
    aliases = {
        "dmy": "dmy",
        "dd/mm/yy": "dmy",
        "dd/mm/yyyy": "dmy",
        "jj/mm/yy": "dmy",
        "jj/mm/yyyy": "dmy",
        "mdy": "mdy",
        "mm/dd/yy": "mdy",
        "mm/dd/yyyy": "mdy",
        "mm/jj/yy": "mdy",
        "mm/jj/yyyy": "mdy",
        "ymd": "ymd",
        "yy-mm-dd": "ymd",
        "yyyy-mm-dd": "ymd",
        "yy-mm-jj": "ymd",
        "yyyy-mm-jj": "ymd",
    }
    if value in aliases:
        return aliases[value]
    locale_name = get_default_locale().lower()
    if locale_name.startswith(("en_us", "en-ca", "en_ph")):
        return "mdy"
    return "dmy"


MONTH_NAMES = get_month_names()
MONTH_LOOKUP = get_month_lookup(MONTH_NAMES)
NUMBER_DECIMALS = get_number_decimals()
DATE_FORMAT = get_date_format()
DATE_ORDER = get_date_order()
