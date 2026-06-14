from __future__ import annotations

import uuid
from urllib.parse import parse_qs

from fastapi_users.password import PasswordHelper

import database
from database import db
from i18n import translate
from web_helpers import one, render_template, settings_tabs_context, user_layout


password_helper = PasswordHelper()


def page(current_user_id: str, query: str = "") -> bytes:
    params = parse_qs(query)
    with db() as conn:
        users = conn.execute(
            """
            SELECT u.id,
                   u.email,
                   u.is_active,
                   u.is_superuser,
                   u.last_login,
                   COUNT(DISTINCT a.id) AS account_count,
                   COUNT(DISTINCT t.id) AS transaction_count
            FROM users u
            LEFT JOIN accounts a ON a.user_id = u.id
            LEFT JOIN transactions t ON t.user_id = u.id
            GROUP BY u.id, u.email, u.is_active, u.is_superuser, u.last_login
            ORDER BY LOWER(u.email)
            """
        ).fetchall()
    body = render_template(
        "admin.html",
        users=users,
        current_user_id=current_user_id,
        error=params.get("error", [""])[0],
        **settings_tabs_context(current_user_id, "admin"),
    )
    return user_layout(translate("admin.title"), body, current_user_id)


def create_user(data: dict[str, list[str]]) -> str:
    email = one(data, "email").lower()
    password = one(data, "password")
    if not email:
        raise ValueError(translate("errors.email-required"))
    if len(password) < 8:
        raise ValueError(translate("errors.password-min-length"))
    user_id = str(uuid.uuid4())
    with db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
        if existing is not None:
            raise ValueError(translate("errors.user-already-exists"))
        conn.execute(
            """
            INSERT INTO users(id, email, hashed_password, is_active, is_superuser, is_verified, last_login)
            VALUES (?, ?, ?, ?, ?, 0, NULL)
            """,
            (
                user_id,
                email,
                password_helper.hash(password),
                1 if data.get("is_active", ["0"])[-1] == "1" else 0,
                1 if data.get("is_superuser", ["0"])[-1] == "1" else 0,
            ),
        )
    return "/admin"


def set_password(data: dict[str, list[str]]) -> str:
    user_id = one(data, "user_id")
    password = one(data, "password")
    if len(password) < 8:
        raise ValueError(translate("errors.password-min-length"))
    with db() as conn:
        conn.execute("UPDATE users SET hashed_password = ? WHERE id = ?", (password_helper.hash(password), user_id))
    return "/admin"


def set_active(data: dict[str, list[str]], current_user_id: str) -> str:
    user_id = one(data, "user_id")
    if user_id == current_user_id:
        raise ValueError(translate("admin.self-disable-forbidden"))
    with db() as conn:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if one(data, "enabled") == "1" else 0, user_id))
    return "/admin"


def set_admin(data: dict[str, list[str]], current_user_id: str) -> str:
    user_id = one(data, "user_id")
    if user_id == current_user_id and one(data, "enabled") != "1":
        raise ValueError(translate("admin.self-admin-remove-forbidden"))
    with db() as conn:
        conn.execute("UPDATE users SET is_superuser = ? WHERE id = ?", (1 if one(data, "enabled") == "1" else 0, user_id))
    return "/admin"
