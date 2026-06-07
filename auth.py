from __future__ import annotations

import os
import secrets
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, schemas
from fastapi_users.authentication import AuthenticationBackend, CookieTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import DeclarativeBase

import database
from i18n import preferred_language
from user_preferences import ensure_user_preferences


ROOT = Path(__file__).resolve().parent
AUTH_SECRET = os.environ.get("BUDGET_AUTH_SECRET") or secrets.token_urlsafe(48)


class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"
    last_login: Mapped[str | None] = mapped_column(nullable=True)


class UserRead(schemas.BaseUser[uuid.UUID]):
    pass


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass


def auth_database_url() -> str:
    if database.database_backend() == "mysql":
        user = os.environ.get("BUDGET_MYSQL_USER", "budget")
        password = os.environ.get("BUDGET_MYSQL_PASSWORD", "")
        host = os.environ.get("BUDGET_MYSQL_HOST", "127.0.0.1")
        port = os.environ.get("BUDGET_MYSQL_PORT", "3306")
        name = os.environ.get("BUDGET_MYSQL_DATABASE", "budget")
        return f"mysql+aiomysql://{user}:{password}@{host}:{port}/{name}"
    return f"sqlite+aiosqlite:///{database.DB_PATH}"


engine = create_async_engine(auth_database_url())
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def create_auth_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = AUTH_SECRET
    verification_token_secret = AUTH_SECRET

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        language_id = (
            request.cookies.get("budget_language") or preferred_language(request.headers.get("accept-language"))
            if request
            else None
        )
        with database.db() as conn:
            database.adopt_legacy_data(conn, str(user.id))
            ensure_user_preferences(conn, str(user.id), language_id)


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


cookie_transport = CookieTransport(
    cookie_name="budget_auth",
    cookie_max_age=int(os.environ.get("BUDGET_AUTH_COOKIE_MAX_AGE", "2592000")),
    cookie_secure=os.environ.get("BUDGET_AUTH_COOKIE_SECURE", "0") == "1",
    cookie_httponly=True,
    cookie_samesite="lax",
)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=AUTH_SECRET, lifetime_seconds=int(os.environ.get("BUDGET_AUTH_LIFETIME", "2592000")))


auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])
current_active_user = fastapi_users.current_user(active=True)
optional_current_user = fastapi_users.current_user(optional=True, active=True)
current_admin_user = fastapi_users.current_user(active=True, superuser=True)
