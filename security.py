from __future__ import annotations

import os
from http import HTTPStatus
from urllib.parse import urlparse

from fastapi import HTTPException, Request


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def only_https() -> bool:
    return env_bool("BUDGET_ONLY_HTTPS", False)


def max_upload_bytes() -> int:
    return env_int("BUDGET_MAX_UPLOAD", 5 * 1024 * 1024)


def max_accounts() -> int:
    return env_int("BUDGET_MAX_ACCOUNT", 25)


def max_daily_new_accounts() -> int:
    return env_int("BUDGET_MAX_DAILY_NEW_ACCOUNT", 5)


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
