from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from database import db
from endpoints import api, imports, parameters, period, periods, static_files, transactions


application = FastAPI(title="Budget")


@application.on_event("startup")
def startup() -> None:
    with db():
        pass


@application.head("/{path:path}")
def head(_path: str = "") -> Response:
    return Response(status_code=HTTPStatus.OK)


@application.get("/", response_class=HTMLResponse)
def periods_page() -> HTMLResponse:
    return html(periods.page())


@application.get("/period/{period_id}/import", response_class=HTMLResponse)
def import_page(period_id: int, request: Request) -> HTMLResponse:
    return html(imports.page(period_id, query_string(request)))


@application.get("/period/{period_id}", response_class=HTMLResponse)
def period_page(period_id: int, request: Request) -> HTMLResponse:
    return html(period.page(period_id, query_string(request)))


@application.get("/parameters", response_class=HTMLResponse)
def parameters_page() -> HTMLResponse:
    return html(parameters.page())


@application.get("/transactions", response_class=HTMLResponse)
def transactions_page(request: Request) -> HTMLResponse:
    return html(transactions.page(query_string(request)))


@application.post("/api/{path:path}", response_model=None)
async def api_update(path: str, request: Request) -> JSONResponse:
    result = api.update(f"/api/{path}", await json_data(request))
    status = HTTPStatus.OK if result.pop("ok", False) else HTTPStatus(result.pop("status", 400))
    return JSONResponse({"ok": status == HTTPStatus.OK, **result}, status_code=status)


@application.post("/periods/create", response_model=None)
async def create_period(request: Request) -> RedirectResponse:
    return redirect(periods.create(await form_data(request)))


@application.post("/parameters/accounts/create", response_model=None)
async def create_account(request: Request) -> RedirectResponse:
    return redirect(parameters.create_account(await form_data(request)))


@application.post("/parameters/labels/create", response_model=None)
async def create_label(request: Request) -> RedirectResponse:
    return redirect(parameters.create_label(await form_data(request)))


@application.post("/transactions/create", response_model=None)
async def create_transaction(request: Request) -> RedirectResponse:
    return redirect(transactions.create(await form_data(request)))


@application.post("/period/{period_id}/import", response_model=None)
async def import_submit(period_id: int, request: Request) -> Response:
    result = imports.submit(period_id, await form_data(request))
    if isinstance(result, bytes):
        return html(result)
    return redirect(result)


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
