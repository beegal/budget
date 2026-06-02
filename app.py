from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from database import db
from endpoints import api, imports, parameters, period, periods, static_files, transactions


class BudgetHandler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        static_asset = static_files.resolve(parsed.path)
        if static_asset:
            path, content_type = static_asset
            self.serve_file(path, content_type)
            return
        if parsed.path == "/":
            self.send_html(periods.page())
            return
        if parsed.path.startswith("/period/") and parsed.path.endswith("/import"):
            period_id = int(parsed.path.removeprefix("/period/").split("/")[0])
            self.send_html(imports.page(period_id, parsed.query))
            return
        if parsed.path.startswith("/period/"):
            period_id = int(parsed.path.removeprefix("/period/").split("/")[0])
            self.send_html(period.page(period_id, parsed.query))
            return
        if parsed.path == "/parameters":
            self.send_html(parameters.page())
            return
        if parsed.path == "/transactions":
            self.send_html(transactions.page(parsed.query))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            result = api.update(parsed.path, self.json_data())
            status = HTTPStatus.OK if result.pop("ok", False) else HTTPStatus(result.pop("status", 400))
            self.send_json({"ok": status == HTTPStatus.OK, **result}, status)
            return

        data = self.form_data()
        if parsed.path == "/periods/create":
            self.redirect(periods.create(data))
            return
        if parsed.path == "/parameters/accounts/create":
            self.redirect(parameters.create_account(data))
            return
        if parsed.path == "/parameters/labels/create":
            self.redirect(parameters.create_label(data))
            return
        if parsed.path == "/transactions/create":
            self.redirect(transactions.create(data))
            return
        if parsed.path.startswith("/period/") and parsed.path.endswith("/import"):
            period_id = int(parsed.path.removeprefix("/period/").split("/")[0])
            result = imports.submit(period_id, data)
            if isinstance(result, bytes):
                self.send_html(result)
            else:
                self.redirect(result)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def serve_file(self, path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, data: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def form_data(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", 0))
        return parse_qs(self.rfile.read(length).decode("utf-8"))

    def json_data(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    with db():
        pass
    server = ThreadingHTTPServer((host, port), BudgetHandler)
    print(f"Budget app running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
