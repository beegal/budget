from __future__ import annotations

import os
from http import HTTPStatus
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from config import load_config


def security_config() -> dict[str, object]:
    config = load_config()
    section = config.get("security", {})
    return section if isinstance(section, dict) else {}


def config_value(key: str, default: object) -> object:
    return security_config().get(key, default)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        raw = default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: object, fallback: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        raw = default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def env_float(name: str, default: object, fallback: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        raw = default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def only_https() -> bool:
    return env_bool("BUDGET_ONLY_HTTPS", config_value("only-https", False))


def max_upload_bytes() -> int:
    return env_int("BUDGET_MAX_UPLOAD", config_value("max-upload", 5 * 1024 * 1024), 5 * 1024 * 1024)


def max_accounts() -> int:
    return env_int("BUDGET_MAX_ACCOUNT", config_value("max-account", 25), 25)


def max_daily_new_accounts() -> int:
    return env_int("BUDGET_MAX_DAILY_NEW_ACCOUNT", config_value("max-daily-new-account", 5), 5)


def zip_max_files() -> int:
    return env_int("BUDGET_ZIP_MAX_FILES", config_value("zip-max-files", 200), 200)


def zip_max_uncompressed_factor() -> int:
    return env_int("BUDGET_ZIP_MAX_UNCOMPRESSED_FACTOR", config_value("zip-max-uncompressed-factor", 5), 5)


def zip_max_compression_ratio() -> float:
    return env_float("BUDGET_ZIP_MAX_COMPRESSION_RATIO", config_value("zip-max-compression-ratio", 100), 100.0)


def validate_same_origin(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    candidate = origin or referer
    if not candidate:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Missing Origin header")
    parsed_candidate = urlparse(candidate)
    expected_host = request.headers.get("host") or urlparse(str(request.base_url)).netloc
    expected_scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",", 1)[0].strip()
    accepted_schemes = {expected_scheme}
    if only_https():
        accepted_schemes.add("https")
    if parsed_candidate.netloc != expected_host or parsed_candidate.scheme not in accepted_schemes:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Invalid Origin header")
