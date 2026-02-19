from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from cryptobot.engine import BotEngine


class ApiHandler(BaseHTTPRequestHandler):
    engine_provider: Callable[[], BotEngine]
    static_root: Path

    def _send_json(self, payload: dict | list, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, rel_path: str) -> None:
        path = self.static_root / rel_path
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if path.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        else:
            content_type = "application/octet-stream"

        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        engine = self.engine_provider()

        if self.path in {"/", "/index.html"}:
            self._serve_static("index.html")
            return

        if self.path == "/style.css":
            self._serve_static("style.css")
            return

        if self.path == "/app.js":
            self._serve_static("app.js")
            return

        if self.path == "/api/status":
            self._send_json(engine.status())
            return

        if self.path == "/api/trades":
            self._send_json(engine.trades())
            return

        if self.path == "/api/config":
            self._send_json(engine.config_view())
            return

        if self.path == "/api/tick":
            engine.run_once()
            self._send_json(engine.status())
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):  # noqa: N802
        engine = self.engine_provider()

        if self.path == "/api/tick":
            engine.run_once()
            self._send_json(engine.status())
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format, *args):  # noqa: A003
        return


def make_server(engine: BotEngine, host: str, port: int) -> ThreadingHTTPServer:
    static_dir = Path(__file__).resolve().parent / "static"

    class BoundHandler(ApiHandler):
        engine_provider = staticmethod(lambda: engine)
        static_root = static_dir

    return ThreadingHTTPServer((host, port), BoundHandler)
