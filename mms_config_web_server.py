# -*- coding: utf-8 -*-
"""HTTP serving layer for the MMS config WebUI.

The data/model logic remains in ``mms_config_web``; this module owns only the
stateful app wrapper, request handler, and CLI entrypoint.
"""

from __future__ import annotations

import argparse
import copy
import json
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from mms_config_web_assets import read_index_html, read_static_asset


def _backend():
    import mms_config_web as web

    return web


def _json_response(payload: Any, *, status: int = 200) -> tuple[int, bytes, str]:
    return _backend()._json_response(payload, status=status)


def build_config_snapshot(cfg: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().build_config_snapshot(cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def build_config_plan(current_cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().build_config_plan(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def apply_config_plan(current_cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "") -> dict[str, Any]:
    return _backend().apply_config_plan(current_cfg, payload, config_path=config_path, preferences_path=preferences_path)


def apply_registry_v2_preview_plan(current_cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "") -> dict[str, Any]:
    return _backend().apply_registry_v2_preview_plan(current_cfg, payload, config_path=config_path, preferences_path=preferences_path)


def build_preferences_plan(payload: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "") -> dict[str, Any]:
    return _backend().build_preferences_plan(payload, config_path=config_path, preferences_path=preferences_path)


def apply_preferences_plan(payload: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "") -> dict[str, Any]:
    return _backend().apply_preferences_plan(payload, config_path=config_path, preferences_path=preferences_path)


def reveal_local_path(payload: dict[str, Any] | None) -> dict[str, Any]:
    return _backend().reveal_local_path(payload)


def test_provider_models(cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().test_provider_models(cfg, payload, config_path=config_path, command_name=command_name)


def run_model_smoke(cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, chat: bool = False, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().run_model_smoke(cfg, payload, chat=chat, config_path=config_path, command_name=command_name)


def build_settings_report(cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().build_settings_report(cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def build_reference_cards() -> list[dict[str, str]]:
    return _backend().build_reference_cards()


def build_setup_markdown(snapshot: dict[str, Any]) -> str:
    return _backend().build_setup_markdown(snapshot)


def _html_page(_snapshot: dict[str, Any]) -> bytes:
    return read_index_html().encode("utf-8")


class ConfigWebApp:
    def __init__(self, cfg: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> None:
        self.cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
        self.config_path = config_path
        self.preferences_path = preferences_path
        self.command_name = command_name
        self.lock = threading.Lock()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return build_config_snapshot(self.cfg, config_path=self.config_path, preferences_path=self.preferences_path, command_name=self.command_name)

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return build_config_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path, command_name=self.command_name)

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            result = apply_config_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path)
            if result.get("ok"):
                plan = build_config_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path, command_name=self.command_name)
                self.cfg = plan.get("config") if isinstance(plan.get("config"), dict) else self.cfg
            return result

    def registry_v2_apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            result = apply_registry_v2_preview_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path)
            if result.get("ok"):
                plan = build_config_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path, command_name=self.command_name)
                self.cfg = plan.get("config") if isinstance(plan.get("config"), dict) else self.cfg
            return result

    def preferences_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return build_preferences_plan(payload, config_path=self.config_path, preferences_path=self.preferences_path)

    def preferences_apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return apply_preferences_plan(payload, config_path=self.config_path, preferences_path=self.preferences_path)

    def reveal_path(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return reveal_local_path(payload)

    def provider_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return test_provider_models(self.cfg, payload, config_path=self.config_path, command_name=self.command_name)

    def model_test(self, payload: dict[str, Any], *, chat: bool = False) -> dict[str, Any]:
        with self.lock:
            return run_model_smoke(self.cfg, payload, chat=chat, config_path=self.config_path, command_name=self.command_name)

    def settings_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return build_settings_report(
                self.cfg,
                payload,
                config_path=self.config_path,
                preferences_path=self.preferences_path,
                command_name=self.command_name,
            )


class _SetupWebHandler(BaseHTTPRequestHandler):
    app: ConfigWebApp | None = None

    def log_message(self, *_args: Any) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid json: {exc}") from exc
        return payload if isinstance(payload, dict) else {}

    def do_GET(self) -> None:
        app = self.app
        if app is None:
            self._send(*_json_response({"error": "app not initialized"}, status=500))
            return
        path = self.path.split("?", 1)[0]
        snapshot = app.snapshot()
        if path in {"/", "/index.html"}:
            self._send(200, _html_page(snapshot), "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            asset_name = path.rsplit("/", 1)[-1]
            try:
                body, content_type = read_static_asset(asset_name)
            except (FileNotFoundError, KeyError):
                self._send(404, b"not found\n", "text/plain; charset=utf-8")
                return
            self._send(200, body, content_type)
            return
        if path in {"/api/state", "/api/snapshot"}:
            self._send(*_json_response(snapshot))
            return
        if path == "/api/references":
            self._send(*_json_response({"references": build_reference_cards()}))
            return
        if path == "/setup.md":
            self._send(200, build_setup_markdown(snapshot).encode("utf-8"), "text/markdown; charset=utf-8")
            return
        self._send(404, b"not found\n", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        app = self.app
        if app is None:
            self._send(*_json_response({"error": "app not initialized"}, status=500))
            return
        path = self.path.split("?", 1)[0]
        try:
            payload = self._read_json()
            if path == "/api/provider/models" or path == "/api/provider/test":
                self._send(*_json_response(app.provider_test(payload)))
                return
            if path == "/api/model/test":
                self._send(*_json_response(app.model_test(payload, chat=False)))
                return
            if path == "/api/chat/test":
                self._send(*_json_response(app.model_test(payload, chat=True)))
                return
            if path == "/api/settings/report":
                self._send(*_json_response(app.settings_report(payload)))
                return
            if path == "/api/plan":
                self._send(*_json_response(app.plan(payload)))
                return
            if path == "/api/save":
                result = app.save(payload)
                self._send(*_json_response(result, status=200 if result.get("ok") else 400))
                return
            if path == "/api/registry-v2/apply":
                result = app.registry_v2_apply(payload)
                self._send(*_json_response(result, status=200 if result.get("ok") else 400))
                return
            if path == "/api/preferences/plan":
                self._send(*_json_response(app.preferences_plan(payload)))
                return
            if path == "/api/preferences/apply":
                result = app.preferences_apply(payload)
                self._send(*_json_response(result, status=200 if result.get("ok") else 400))
                return
            if path == "/api/path/reveal":
                result = app.reveal_path(payload)
                self._send(*_json_response(result, status=200 if result.get("ok") else 400))
                return
            self._send(404, b"not found\n", "text/plain; charset=utf-8")
        except Exception as exc:
            self._send(*_json_response({"ok": False, "error": str(exc), "trace": traceback.format_exc(limit=5)}, status=500))


def serve_config_web(app_or_snapshot: ConfigWebApp | dict[str, Any], *, host: str, port: int, open_browser: bool = True) -> str:
    if isinstance(app_or_snapshot, ConfigWebApp):
        app = app_or_snapshot
    else:
        app = ConfigWebApp({}, command_name="mms")
    handler = type("MMSSetupWebHandler", (_SetupWebHandler,), {"app": app})
    server = ThreadingHTTPServer((host, int(port)), handler)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="mms-setup-web")
    thread.start()
    print(f"MMS 配置 WebUI: {url}")
    print("交互配置页面已启动；保存前会要求 diff + 明确确认。按 Ctrl-C 停止。")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        thread.join()
    except KeyboardInterrupt:
        print("\nStopping MMS setup WebUI.")
    finally:
        server.shutdown()
        server.server_close()
    return url


def run_config_web(
    cfg: dict[str, Any] | None,
    argv: list[str] | None = None,
    *,
    command_name: str = "mms",
    config_path: str = "",
    preferences_path: str = "",
) -> int:
    parser = argparse.ArgumentParser(prog=f"{command_name} config web", description="Start the local interactive MMS configuration WebUI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host; default 127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="Bind port; default 0 chooses a free port")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    parser.add_argument("--print-summary", action="store_true", help="Print redacted setup JSON and exit")
    parser.add_argument("--print-markdown", action="store_true", help="Print setup markdown and exit")
    args = parser.parse_args(argv or [])
    app = ConfigWebApp(cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name)
    snapshot = app.snapshot()
    if args.print_summary:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.print_markdown:
        print(build_setup_markdown(snapshot), end="")
        return 0
    serve_config_web(app, host=args.host, port=args.port, open_browser=not args.no_open)
    return 0
