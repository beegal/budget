from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime
from http import HTTPStatus
from typing import Iterator
from urllib.parse import parse_qs, quote
from zipfile import BadZipFile

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

import auth
import budget_cli
import database
from database import db
from endpoints import admin, api, imports, parameters, period, periods, profile, static_files, summary, tools, transactions
from i18n import preferred_language, translate, use_language
from security import max_upload_bytes, only_https, validate_same_origin
from user_preferences import ensure_user_preferences, use_preferences
from version import APP_VERSION, current_commit_id


logger = logging.getLogger("uvicorn.error")
application = FastAPI(title="Personal Finance")
application.include_router(
    auth.fastapi_users.get_auth_router(auth.auth_backend),
    prefix="/auth/cookie",
    tags=["auth"],
)
application.include_router(
    auth.fastapi_users.get_register_router(auth.UserRead, auth.UserCreate),
    prefix="/auth",
    tags=["auth"],
)


@application.middleware("http")
async def security_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_upload_bytes():
                return Response("Payload too large", status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        except ValueError:
            return Response("Invalid Content-Length", status_code=HTTPStatus.BAD_REQUEST)
    try:
        validate_same_origin(request)
    except HTTPException as error:
        status_code = getattr(error, "status_code", HTTPStatus.FORBIDDEN)
        detail = getattr(error, "detail", "Forbidden")
        return Response(str(detail), status_code=status_code)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
    )
    if only_https():
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@application.on_event("startup")
async def startup() -> None:
    await auth.create_auth_tables()
    with db() as conn:
        db_schema_version = database.schema_version(conn)
        db_backend = getattr(conn, "backend", "sqlite")
    logger.info(
        "Personal Finance started app_version=%s app_commit=%s db_schema_version=%s latest_schema_version=%s db_backend=%s",
        APP_VERSION,
        current_commit_id(),
        db_schema_version,
        database.LATEST_SCHEMA_VERSION,
        db_backend,
    )


@application.head("/{path:path}")
def head(_path: str = "") -> Response:
    return Response(status_code=HTTPStatus.OK)


@application.get("/", response_class=HTMLResponse, response_model=None)
def periods_page(request: Request, user: auth.User | None = Depends(auth.optional_current_user)) -> Response:
    if user is None:
        return redirect("/login")
    uid = user_id(user)
    with request_context(uid, request):
        return html(periods.page(uid))


@application.get("/period/{period_id}/import", response_class=HTMLResponse, response_model=None)
def import_page(
    period_id: int,
    request: Request,
    user: auth.User | None = Depends(auth.optional_current_user),
) -> Response:
    if user is None:
        return redirect("/login")
    uid = user_id(user)
    with request_context(uid, request):
        return html(imports.page(period_id, query_string(request), uid))


@application.get("/period/{period_id}", response_class=HTMLResponse, response_model=None)
def period_page(
    period_id: int,
    request: Request,
    user: auth.User | None = Depends(auth.optional_current_user),
) -> Response:
    if user is None:
        return redirect("/login")
    uid = user_id(user)
    with request_context(uid, request):
        return html(period.page(period_id, query_string(request), uid))


@application.get("/parameters", response_class=HTMLResponse, response_model=None)
def parameters_page(request: Request, user: auth.User | None = Depends(auth.optional_current_user)) -> Response:
    if user is None:
        return redirect("/login")
    uid = user_id(user)
    with request_context(uid, request):
        return html(parameters.page(uid))


@application.get("/profile", response_class=HTMLResponse, response_model=None)
def profile_page(request: Request, user: auth.User | None = Depends(auth.optional_current_user)) -> Response:
    if user is None:
        return redirect("/login")
    uid = user_id(user)
    with request_context(uid, request):
        return html(profile.page(uid))


@application.get("/tools", response_class=HTMLResponse, response_model=None)
def tools_page(request: Request, user: auth.User | None = Depends(auth.optional_current_user)) -> Response:
    if user is None:
        return redirect("/login")
    uid = user_id(user)
    with request_context(uid, request):
        return html(tools.page(uid, query_string(request)))


@application.get("/tools/labels/defined", response_model=None)
def tools_defined_labels(user: auth.User = Depends(auth.current_active_user)) -> JSONResponse:
    with db() as conn:
        labels = tools.labels_payload(tools.defined_labels(conn, user_id(user)))
    return JSONResponse({"labels": labels})


@application.get("/tools/labels/used", response_model=None)
def tools_used_labels(user: auth.User = Depends(auth.current_active_user)) -> JSONResponse:
    with db() as conn:
        labels = tools.labels_payload(tools.used_labels(conn, user_id(user)))
    return JSONResponse({"labels": labels})


@application.post("/tools/labels/merge", response_model=None)
async def tools_merge_labels(request: Request, user: auth.User = Depends(auth.current_active_user)) -> RedirectResponse:
    uid = user_id(user)
    with request_context(uid, request):
        try:
            return redirect(tools.merge_labels(await form_data(request), uid))
        except ValueError as error:
            return redirect(f"/tools?error={quote(str(error))}")


@application.post("/profile", response_model=None)
async def profile_save(request: Request, user: auth.User = Depends(auth.current_active_user)) -> RedirectResponse:
    uid = user_id(user)
    with request_context(uid, request):
        return redirect(profile.save(await form_data(request), uid))


@application.get("/parameters/export", response_model=None)
def parameters_export(user: auth.User = Depends(auth.current_active_user)) -> Response:
    with db() as conn:
        data = budget_cli.export_user_database_bytes(conn, user_id(user), user.email)
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="budget-user-export.xlsx"'},
    )


@application.post("/parameters/import", response_model=None)
async def parameters_import(request: Request, user: auth.User = Depends(auth.current_active_user)) -> Response:
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        return Response("Fichier d'import manquant.", status_code=HTTPStatus.BAD_REQUEST)
    try:
        data = await upload.read(max_upload_bytes() + 1)
        if len(data) > max_upload_bytes():
            return Response("Fichier trop volumineux.", status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        with db() as conn:
            budget_cli.import_user_database_bytes(conn, data, user_id(user))
    except (BadZipFile, KeyError, ValueError) as error:
        return Response(str(error), status_code=HTTPStatus.BAD_REQUEST)
    return redirect("/parameters")


@application.get("/transactions", response_class=HTMLResponse, response_model=None)
def transactions_page(
    request: Request,
    user: auth.User | None = Depends(auth.optional_current_user),
) -> Response:
    if user is None:
        return redirect("/login")
    uid = user_id(user)
    with request_context(uid, request):
        return html(transactions.page(query_string(request), uid))


@application.get("/summary", response_class=HTMLResponse, response_model=None)
def summary_page(
    request: Request,
    user: auth.User | None = Depends(auth.optional_current_user),
) -> Response:
    if user is None:
        return redirect("/login")
    uid = user_id(user)
    with request_context(uid, request):
        return html(summary.page(query_string(request), uid))


@application.get("/admin", response_class=HTMLResponse, response_model=None)
def admin_page(request: Request, user: auth.User = Depends(auth.current_admin_user)) -> Response:
    uid = user_id(user)
    with request_context(uid, request):
        return html(admin.page(uid, query_string(request)))


@application.post("/admin/users/create", response_model=None)
async def admin_create_user(request: Request, _user: auth.User = Depends(auth.current_admin_user)) -> RedirectResponse:
    try:
        return redirect(admin.create_user(await form_data(request)))
    except ValueError as error:
        return redirect(f"/admin?error={quote(str(error))}")


@application.post("/admin/users/password", response_model=None)
async def admin_set_password(request: Request, _user: auth.User = Depends(auth.current_admin_user)) -> RedirectResponse:
    try:
        return redirect(admin.set_password(await form_data(request)))
    except ValueError as error:
        return redirect(f"/admin?error={quote(str(error))}")


@application.post("/admin/users/active", response_model=None)
async def admin_set_active(request: Request, user: auth.User = Depends(auth.current_admin_user)) -> RedirectResponse:
    try:
        return redirect(admin.set_active(await form_data(request), user_id(user)))
    except ValueError as error:
        return redirect(f"/admin?error={quote(str(error))}")


@application.post("/admin/users/admin", response_model=None)
async def admin_set_admin(request: Request, user: auth.User = Depends(auth.current_admin_user)) -> RedirectResponse:
    try:
        return redirect(admin.set_admin(await form_data(request), user_id(user)))
    except ValueError as error:
        return redirect(f"/admin?error={quote(str(error))}")


@application.post("/api/{path:path}", response_model=None)
async def api_update(path: str, request: Request, user: auth.User = Depends(auth.current_active_user)) -> JSONResponse:
    uid = user_id(user)
    with request_context(uid, request):
        result = api.update(f"/api/{path}", await json_data(request), uid)
    status = HTTPStatus.OK if result.pop("ok", False) else HTTPStatus(result.pop("status", 400))
    return JSONResponse({"ok": status == HTTPStatus.OK, **result}, status_code=status)


@application.post("/periods/create", response_model=None)
async def create_period(request: Request, user: auth.User = Depends(auth.current_active_user)) -> RedirectResponse:
    uid = user_id(user)
    with request_context(uid, request):
        return redirect(periods.create(await form_data(request), uid))


@application.post("/parameters/accounts/create", response_model=None)
async def create_account(request: Request, user: auth.User = Depends(auth.current_active_user)) -> RedirectResponse:
    return redirect(parameters.create_account(await form_data(request), user_id(user)))


@application.post("/parameters/labels/create", response_model=None)
async def create_label(request: Request, user: auth.User = Depends(auth.current_active_user)) -> RedirectResponse:
    return redirect(parameters.create_label(await form_data(request), user_id(user)))


@application.post("/transactions/create", response_model=None)
async def create_transaction(request: Request, user: auth.User = Depends(auth.current_active_user)) -> RedirectResponse:
    uid = user_id(user)
    with request_context(uid, request):
        return redirect(transactions.create(await form_data(request), uid))


@application.post("/period/{period_id}/import", response_model=None)
async def import_submit(period_id: int, request: Request, user: auth.User = Depends(auth.current_active_user)) -> Response:
    uid = user_id(user)
    with request_context(uid, request):
        result = imports.submit(period_id, await form_data(request), uid)
    if isinstance(result, bytes):
        return html(result)
    return redirect(result)


@application.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return html(render_public_page("login.html", request))


@application.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> HTMLResponse:
    return html(render_public_page("register.html", request))


@application.post("/logout", response_model=None)
def logout() -> RedirectResponse:
    response = redirect("/login")
    response.delete_cookie("budget_auth", path="/")
    return response


@application.get("/{path:path}")
def static_or_not_found(path: str) -> Response:
    static_asset = static_files.resolve(f"/{path}")
    if not static_asset:
        return Response(status_code=HTTPStatus.NOT_FOUND)
    file_path, content_type = static_asset
    if not file_path.exists():
        return Response(status_code=HTTPStatus.NOT_FOUND)
    return Response(file_path.read_bytes(), media_type=content_type)


def html(data: bytes) -> HTMLResponse:
    return HTMLResponse(data.decode("utf-8"))


def redirect(location: str) -> RedirectResponse:
    return RedirectResponse(location, status_code=HTTPStatus.SEE_OTHER)


def query_string(request: Request) -> str:
    return request.url.query


def user_id(user: auth.User) -> str:
    value = str(user.id)
    with db() as conn:
        conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.now().isoformat(timespec="seconds"), value))
    return value


@contextmanager
def request_context(uid: str | None = None, request: Request | None = None) -> Iterator[None]:
    language_id = None
    if request:
        language_id = request.cookies.get("budget_language") or preferred_language(request.headers.get("accept-language"))
    with use_language(language_id):
        if uid is None:
            yield
            return
        with db() as conn:
            preferences = ensure_user_preferences(conn, uid, language_id)
            database.ensure_user_data(conn, uid, language_id)
        with use_preferences(preferences):
            yield


def render_public_page(template_name: str, request: Request | None = None) -> bytes:
    from web_helpers import layout, render_template

    with request_context(request=request):
        return layout(translate("auth.login-title"), render_template(template_name))


async def form_data(request: Request) -> dict[str, list[str]]:
    return parse_qs((await limited_body(request)).decode("utf-8"))


async def json_data(request: Request) -> dict[str, object]:
    data = await limited_body(request)
    if not data:
        return {}
    return json.loads(data)


async def limited_body(request: Request) -> bytes:
    data = await request.body()
    if len(data) > max_upload_bytes():
        raise HTTPException(status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")
    return data


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(application, host=host, port=port)


if __name__ == "__main__":
    run()
