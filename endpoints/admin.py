from __future__ import annotations

from fastapi_users.password import PasswordHelper

from database import db
from web_helpers import layout, one, render_template


password_helper = PasswordHelper()


def page(current_user_id: str) -> bytes:
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
    body = render_template("admin.html", users=users, current_user_id=current_user_id)
    return layout("Administration", body)


def set_password(data: dict[str, list[str]]) -> str:
    user_id = one(data, "user_id")
    password = one(data, "password")
    if len(password) < 8:
        raise ValueError("Le mot de passe doit contenir au moins 8 caractères.")
    with db() as conn:
        conn.execute("UPDATE users SET hashed_password = ? WHERE id = ?", (password_helper.hash(password), user_id))
    return "/admin"


def set_active(data: dict[str, list[str]], current_user_id: str) -> str:
    user_id = one(data, "user_id")
    if user_id == current_user_id:
        raise ValueError("Impossible de désactiver ton propre utilisateur.")
    with db() as conn:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if one(data, "enabled") == "1" else 0, user_id))
    return "/admin"


def set_admin(data: dict[str, list[str]], current_user_id: str) -> str:
    user_id = one(data, "user_id")
    if user_id == current_user_id and one(data, "enabled") != "1":
        raise ValueError("Impossible de retirer ton propre accès admin.")
    with db() as conn:
        conn.execute("UPDATE users SET is_superuser = ? WHERE id = ?", (1 if one(data, "enabled") == "1" else 0, user_id))
    return "/admin"
