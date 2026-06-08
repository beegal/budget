from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
STATIC_ROOT = ROOT / "static"


CONTENT_TYPES_BY_SUFFIX = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".svg": "image/svg+xml",
}


def resolve(path: str) -> tuple[Path, str] | None:
    if not path.startswith("/static/"):
        return None
    relative = path.removeprefix("/static/")
    file_path = (STATIC_ROOT / relative).resolve()
    if STATIC_ROOT.resolve() not in file_path.parents and file_path != STATIC_ROOT.resolve():
        return None
    content_type = CONTENT_TYPES_BY_SUFFIX.get(file_path.suffix)
    if not content_type or not file_path.is_file():
        return None
    return file_path, content_type
