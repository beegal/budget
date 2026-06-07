from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from config import get_default_language, get_language, get_supported_language_ids, get_supported_languages, parse_simple_yaml


LOCALES_DIR = Path(__file__).resolve().parent / "locales"
DEFAULT_LANGUAGE = "fr"
_CURRENT_LANGUAGE: ContextVar[str] = ContextVar(
    "budget_language",
    default=get_default_language()["id"],
)


def current_language() -> str:
    return _CURRENT_LANGUAGE.get()


def current_language_locale_name() -> str:
    return language_locale_name(current_language())


def current_language_locale_tag() -> str:
    return locale_tag(current_language_locale_name())


def language_locale_name(language_id: str | None) -> str:
    return str(get_language(language_id).get("locale") or "").strip() or "fr_FR.UTF-8"


def locale_tag(locale_name: str) -> str:
    value = str(locale_name or "").split(".", 1)[0].replace("_", "-")
    return value or "fr-FR"


@contextmanager
def use_language(language_id: str | None) -> Iterator[None]:
    token = _CURRENT_LANGUAGE.set(normalize_language(language_id))
    try:
        yield
    finally:
        _CURRENT_LANGUAGE.reset(token)


def normalize_language(language_id: str | None) -> str:
    value = str(language_id or "").strip().lower()
    if value in get_supported_language_ids():
        return value
    return get_default_language()["id"]


def preferred_language(accept_language: str | None) -> str:
    supported = get_supported_language_ids()
    candidates: list[tuple[float, int, str]] = []
    for index, part in enumerate(str(accept_language or "").split(",")):
        raw_language, _separator, raw_quality = part.strip().partition(";q=")
        language = raw_language.split("-", 1)[0].strip().lower()
        if not language:
            continue
        try:
            quality = float(raw_quality) if raw_quality else 1.0
        except ValueError:
            quality = 1.0
        candidates.append((quality, -index, language))
    for _quality, _index, language in sorted(candidates, reverse=True):
        if language in supported:
            return language
    return get_default_language()["id"]


def language_options() -> list[dict[str, object]]:
    current = current_language()
    return [
        {
            **language,
            "selected": language["id"] == current,
        }
        for language in get_supported_languages()
    ]


def translate(key: str, **values: object) -> str:
    text = lookup(key, current_language())
    if values:
        try:
            return text.format(**values)
        except (KeyError, ValueError):
            return text
    return text


def frontend_messages() -> dict[str, str]:
    messages = flatten(load_language(current_language()))
    fallback = flatten(load_language(DEFAULT_LANGUAGE))
    return {**fallback, **messages}


def lookup(key: str, language: str) -> str:
    value = nested_get(load_language(language), key)
    if value is None and language != DEFAULT_LANGUAGE:
        value = nested_get(load_language(DEFAULT_LANGUAGE), key)
    return str(value if value is not None else key)


@cache
def load_language(language: str) -> dict[str, Any]:
    safe_language = "".join(char for char in language.lower() if char.isalnum() or char in {"-", "_"})
    path = LOCALES_DIR / f"{safe_language}.yaml"
    if not path.exists() and safe_language != DEFAULT_LANGUAGE:
        path = LOCALES_DIR / f"{DEFAULT_LANGUAGE}.yaml"
    if not path.exists():
        return {}
    parsed = parse_simple_yaml(path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else {}


def nested_get(values: dict[str, Any], key: str) -> object | None:
    current: object = values
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def flatten(values: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flattened: dict[str, str] = {}
    for key, value in values.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(flatten(value, full_key))
        else:
            flattened[full_key] = str(value)
    return flattened
