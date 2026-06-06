from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from urllib.parse import parse_qs, quote
from zipfile import BadZipFile

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

import auth
import budget_cli
from database import db
from endpoints import admin, api, imports, parameters, period, periods, static_files, summary, transactions


application = FastAPI(title="Budget")
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


@application.on_event("startup")
async def startup() -> None:
    await auth.create_auth_tables()
    with db():
        pass


@application.head("/{path:path}")
def head(_path: str = "") -> Response:
    return Response(status_code=HTTPStatus.OK)


@application.get("/", response_class=HTMLResponse, response_model=None)
def periods_page(user: auth.User | None = Depends(auth.optional_current_user)) -> Response:
    if user is None:
        return redirect("/login")
    return html(periods.page(user_id(user)))


@application.get("/period/{period_id}/import", response_class=HTMLResponse, response_model=None)
def import_page(
    period_id: int,
    request: Request,
    user: auth.User | None = Depends(auth.optional_current_user),
) -> Response:
    if user is None:
        return redirect("/login")
    return html(imports.page(period_id, query_string(request), user_id(user)))


@application.get("/period/{period_id}", response_class=HTMLResponse, response_model=None)
def period_page(
    period_id: int,
    request: Request,
    user: auth.User | None = Depends(auth.optional_current_user),
) -> Response:
    if user is None:
        return redirect("/login")
    return html(period.page(period_id, query_string(request), user_id(user)))


@application.get("/parameters", response_class=HTMLResponse, response_model=None)
def parameters_page(user: auth.User | None = Depends(auth.optional_current_user)) -> Response:
    if user is None:
        return redirect("/login")
    return html(parameters.page(user_id(user)))


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
        data = await upload.read()
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
    return html(transactions.page(query_string(request), user_id(user)))


@application.get("/summary", response_class=HTMLResponse, response_model=None)
def summary_page(
    request: Request,
    user: auth.User | None = Depends(auth.optional_current_user),
) -> Response:
    if user is None:
        return redirect("/login")
    return html(summary.page(query_string(request), user_id(user)))


@application.get("/admin", response_class=HTMLResponse, response_model=None)
def admin_page(request: Request, user: auth.User = Depends(auth.current_admin_user)) -> Response:
    return html(admin.page(user_id(user), query_string(request)))


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
    result = api.update(f"/api/{path}", await json_data(request), user_id(user))
    status = HTTPStatus.OK if result.pop("ok", False) else HTTPStatus(result.pop("status", 400))
    return JSONResponse({"ok": status == HTTPStatus.OK, **result}, status_code=status)


@application.post("/periods/create", response_model=None)
async def create_period(request: Request, user: auth.User = Depends(auth.current_active_user)) -> RedirectResponse:
    return redirect(periods.create(await form_data(request), user_id(user)))


@application.post("/parameters/accounts/create", response_model=None)
async def create_account(request: Request, user: auth.User = Depends(auth.current_active_user)) -> RedirectResponse:
    return redirect(parameters.create_account(await form_data(request), user_id(user)))


@application.post("/parameters/labels/create", response_model=None)
async def create_label(request: Request, user: auth.User = Depends(auth.current_active_user)) -> RedirectResponse:
    return redirect(parameters.create_label(await form_data(request), user_id(user)))


@application.post("/transactions/create", response_model=None)
async def create_transaction(request: Request, user: auth.User = Depends(auth.current_active_user)) -> RedirectResponse:
    return redirect(transactions.create(await form_data(request), user_id(user)))


@application.post("/period/{period_id}/import", response_model=None)
async def import_submit(period_id: int, request: Request, user: auth.User = Depends(auth.current_active_user)) -> Response:
    result = imports.submit(period_id, await form_data(request), user_id(user))
    if isinstance(result, bytes):
        return html(result)
    return redirect(result)


@application.get("/login", response_class=HTMLResponse)
def login_page() -> HTMLResponse:
    return html(render_public_page("login.html"))


@application.get("/register", response_class=HTMLResponse)
def register_page() -> HTMLResponse:
    return html(render_public_page("register.html"))


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


def render_public_page(template_name: str) -> bytes:
    from web_helpers import layout, render_template

    return layout("Connexion", render_template(template_name))


async def form_data(request: Request) -> dict[str, list[str]]:
    return parse_qs((await request.body()).decode("utf-8"))


async def json_data(request: Request) -> dict[str, object]:
    data = await request.body()
    if not data:
        return {}
    return await request.json()


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(application, host=host, port=port)


if __name__ == "__main__":
    run()
