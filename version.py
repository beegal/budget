from __future__ import annotations

import os
import subprocess
from pathlib import Path

APP_VERSION = os.environ.get("BUDGET_APP_VERSION", "0.1.7")


def current_commit_id() -> str:
    explicit_commit = os.environ.get("BUDGET_APP_COMMIT")
    if explicit_commit:
        return explicit_commit
    root = Path(__file__).resolve().parent
    if not (root / ".git").exists():
        return "unknown"
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        commit_id = commit.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if not commit_id:
        return "unknown"
    if status.stdout.strip():
        return f"{commit_id}-dirty"
    return commit_id
