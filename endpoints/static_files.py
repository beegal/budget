from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


CONTENT_TYPES = {
    "/static/style.css": ("style.css", "text/css"),
    "/static/app.js": ("app.js", "application/javascript"),
}


def resolve(path: str) -> tuple[Path, str] | None:
    if path not in CONTENT_TYPES:
        return None
    name, content_type = CONTENT_TYPES[path]
    return ROOT / "static" / name, content_type
