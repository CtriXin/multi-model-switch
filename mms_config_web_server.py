# -*- coding: utf-8 -*-
"""HTTP serving layer for the MMS config WebUI.

The data/model logic remains in ``mms_config_web``; this module owns only the
stateful app wrapper, request handler, and CLI entrypoint.
"""

from __future__ import annotations

import argparse
import copy
import errno
import json
import threading
import traceback
import webbrowser
from datetime import datetime, timezone
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


def build_migration_export(current_cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().build_migration_export(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def build_migration_import_preview(current_cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().build_migration_import_preview(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def apply_migration_import(current_cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().apply_migration_import(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def build_migration_start_status(current_cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().build_migration_start_status(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def start_migration_work_session(current_cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().start_migration_work_session(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def reveal_local_path(payload: dict[str, Any] | None) -> dict[str, Any]:
    return _backend().reveal_local_path(payload)


def test_provider_models(cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().test_provider_models(cfg, payload, config_path=config_path, command_name=command_name)


def refresh_model_capability_truth(cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().refresh_model_capability_truth(cfg, payload, config_path=config_path, command_name=command_name)


def run_model_smoke(cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, chat: bool = False, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().run_model_smoke(cfg, payload, chat=chat, config_path=config_path, command_name=command_name)


def build_settings_report(cfg: dict[str, Any] | None, payload: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _backend().build_settings_report(cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def build_reference_cards() -> list[dict[str, str]]:
    return _backend().build_reference_cards()


def build_setup_markdown(snapshot: dict[str, Any]) -> str:
    return _backend().build_setup_markdown(snapshot)


def _session_catalog_options(payload: dict[str, Any] | None) -> tuple[str, str, int]:
    payload = payload if isinstance(payload, dict) else {}
    cli = str(payload.get("cli") or "all").strip().lower()
    if cli not in {"all", "claude", "codex"}:
        cli = "all"
    query = " ".join(str(payload.get("query") or "").split())
    try:
        limit = int(payload.get("limit") or 3000)
    except (TypeError, ValueError):
        limit = 3000
    limit = min(max(limit, 1), 5000)
    return cli, query, limit


def _session_preview_options(payload: dict[str, Any] | None) -> tuple[str, str, str, int, int]:
    payload = payload if isinstance(payload, dict) else {}
    cli = str(payload.get("cli") or "all").strip().lower()
    ref = str(payload.get("session_ref") or payload.get("session_id") or payload.get("key") or "").strip()
    if ":" in ref:
        maybe_cli, maybe_ref = ref.split(":", 1)
        if maybe_cli.strip().lower() in {"claude", "codex"}:
            cli = maybe_cli.strip().lower()
            ref = maybe_ref.strip()
    if cli not in {"all", "claude", "codex"}:
        cli = "all"
    query = " ".join(str(payload.get("query") or "").split())
    try:
        limit = int(payload.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    try:
        max_lines = int(payload.get("max_lines") or 20000)
    except (TypeError, ValueError):
        max_lines = 20000
    return cli, ref, query, min(max(limit, 1), 80), min(max(max_lines, 500), 100000)


def _find_session_record(rows: list[dict[str, Any]], session_ref: str, cli: str) -> dict[str, Any] | None:
    ref = str(session_ref or "").strip()
    if not ref:
        return None
    candidates = [
        row for row in rows
        if cli == "all" or str(row.get("cli") or "").strip().lower() == cli
    ]
    exact = [row for row in candidates if str(row.get("session_id") or "") == ref]
    if exact:
        return exact[0]
    prefix = [row for row in candidates if str(row.get("session_id") or "").startswith(ref)]
    return prefix[0] if len(prefix) == 1 else None


def build_session_catalog_from_rows(
    all_rows: list[dict[str, Any]],
    payload: dict[str, Any] | None,
    *,
    command_name: str = "mms",
    generated_at: str | None = None,
) -> dict[str, Any]:
    cli, query, limit = _session_catalog_options(payload)
    rows_for_query = list(all_rows)
    if query:
        tokens = query.lower().split()
        rows_for_query = [
            row for row in rows_for_query
            if all(
                token in " ".join(
                    str(row.get(field) or "").lower()
                    for field in ("cli", "session_id", "project_path", "project_name", "cwd", "title", "model", "source_kind")
                )
                for token in tokens
            )
        ]

    counts = {
        "all": len(rows_for_query),
        "claude": sum(1 for row in rows_for_query if str(row.get("cli") or "") == "claude"),
        "codex": sum(1 for row in rows_for_query if str(row.get("cli") or "") == "codex"),
    }
    rows = rows_for_query if cli == "all" else [row for row in rows_for_query if str(row.get("cli") or "") == cli]
    total_before_limit = len(rows)
    rows = rows[:limit]
    for row in rows:
        row["resume_command"] = f"{command_name} resume {row.get('cli')}:{row.get('session_id')}"
    return {
        "ok": True,
        "schema": "mms.session_catalog.v1",
        "cli": cli,
        "query": query,
        "limit": limit,
        "counts": counts,
        "rows": rows,
        "row_count": len(rows),
        "total_before_limit": total_before_limit,
        "truncated": total_before_limit > len(rows),
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "command_name": command_name,
        "read_only": True,
    }


def build_session_catalog(payload: dict[str, Any] | None, *, command_name: str = "mms") -> dict[str, Any]:
    from mms_session_catalog import list_session_records

    all_rows = list_session_records(cli="all", query="", limit=None)
    return build_session_catalog_from_rows(all_rows, payload, command_name=command_name)


def build_session_preview_from_rows(
    all_rows: list[dict[str, Any]],
    payload: dict[str, Any] | None,
    *,
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_session_catalog import preview_session_record

    cli, session_ref, query, limit, max_lines = _session_preview_options(payload)
    if not session_ref:
        return {
            "ok": False,
            "schema": "mms.session_preview.v1",
            "error": "session id 不能为空",
            "items": [],
            "read_only": True,
        }
    record = _find_session_record(all_rows, session_ref, cli)
    preview = preview_session_record(
        session_ref,
        cli=cli,
        record=copy.deepcopy(record) if isinstance(record, dict) else None,
        query=query,
        limit=limit,
        max_lines=max_lines,
    )
    if isinstance(record, dict):
        row = copy.deepcopy(record)
        row["resume_command"] = f"{command_name} resume {row.get('cli')}:{row.get('session_id')}"
        row["select_model_command"] = f"{command_name} resume --select-model {row.get('cli')}:{row.get('session_id')}"
        preview["record"] = row
    preview.setdefault("schema", "mms.session_preview.v1")
    preview.setdefault("read_only", True)
    preview["command_name"] = command_name
    return preview


def build_session_preview(payload: dict[str, Any] | None, *, command_name: str = "mms") -> dict[str, Any]:
    from mms_session_catalog import list_session_records

    all_rows = list_session_records(cli="all", query="", limit=None)
    return build_session_preview_from_rows(all_rows, payload, command_name=command_name)


def _html_page(_snapshot: dict[str, Any]) -> bytes:
    return read_index_html().encode("utf-8")


class ConfigWebApp:
    def __init__(self, cfg: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> None:
        self.cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
        self.config_path = config_path
        self.preferences_path = preferences_path
        self.command_name = command_name
        self.lock = threading.Lock()
        self._session_catalog_cache: dict[str, Any] | None = None

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

    def migration_export(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return build_migration_export(
                self.cfg,
                payload,
                config_path=self.config_path,
                preferences_path=self.preferences_path,
                command_name=self.command_name,
            )

    def migration_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return build_migration_import_preview(
                self.cfg,
                payload,
                config_path=self.config_path,
                preferences_path=self.preferences_path,
                command_name=self.command_name,
            )

    def migration_apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            result = apply_migration_import(
                self.cfg,
                payload,
                config_path=self.config_path,
                preferences_path=self.preferences_path,
                command_name=self.command_name,
            )
            if result.get("ok"):
                preview = build_migration_import_preview(
                    self.cfg,
                    payload,
                    config_path=self.config_path,
                    preferences_path=self.preferences_path,
                    command_name=self.command_name,
                )
                config_plan = preview.get("config_plan") if isinstance(preview.get("config_plan"), dict) else {}
                self.cfg = config_plan.get("config") if isinstance(config_plan.get("config"), dict) else self.cfg
            return result

    def migration_start_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return build_migration_start_status(
                self.cfg,
                payload,
                config_path=self.config_path,
                preferences_path=self.preferences_path,
                command_name=self.command_name,
            )

    def migration_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return start_migration_work_session(
                self.cfg,
                payload,
                config_path=self.config_path,
                preferences_path=self.preferences_path,
                command_name=self.command_name,
            )

    def reveal_path(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return reveal_local_path(payload)

    def provider_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return test_provider_models(self.cfg, payload, config_path=self.config_path, command_name=self.command_name)

    def capability_truth(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return refresh_model_capability_truth(self.cfg, payload, config_path=self.config_path, command_name=self.command_name)

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

    def _ensure_session_catalog_cache(self) -> None:
        if self._session_catalog_cache is not None:
            return
        result = build_session_catalog({"cli": "all", "query": "", "limit": 5000}, command_name=self.command_name)
        self._session_catalog_cache = {
            "rows": copy.deepcopy(result.get("rows") or []),
            "generated_at": result.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        }

    def session_catalog(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            payload = payload if isinstance(payload, dict) else {}
            force = bool(payload.get("force"))
            if force:
                self._session_catalog_cache = None
            self._ensure_session_catalog_cache()
            return build_session_catalog_from_rows(
                copy.deepcopy(self._session_catalog_cache.get("rows") or []),
                payload,
                command_name=self.command_name,
                generated_at=str(self._session_catalog_cache.get("generated_at") or ""),
            )

    def session_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            payload = payload if isinstance(payload, dict) else {}
            self._ensure_session_catalog_cache()
            return build_session_preview_from_rows(
                copy.deepcopy(self._session_catalog_cache.get("rows") or []),
                payload,
                command_name=self.command_name,
            )


class _SetupWebHandler(BaseHTTPRequestHandler):
    app: ConfigWebApp | None = None

    def log_message(self, *_args: Any) -> None:
        return

    @staticmethod
    def _client_disconnected(exc: BaseException) -> bool:
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return True
        return isinstance(exc, OSError) and exc.errno in {errno.EPIPE, errno.ECONNRESET, errno.ECONNABORTED}

    def _send(self, status: int, body: bytes, content_type: str) -> bool:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return True
        except OSError as exc:
            if self._client_disconnected(exc):
                return False
            raise

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
        if path in {"/", "/index.html"}:
            self._send(200, _html_page({}), "text/html; charset=utf-8")
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
            snapshot = app.snapshot()
            self._send(*_json_response(snapshot))
            return
        if path == "/api/references":
            self._send(*_json_response({"references": build_reference_cards()}))
            return
        if path == "/setup.md":
            snapshot = app.snapshot()
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
            if path == "/api/model-capabilities/refresh":
                self._send(*_json_response(app.capability_truth(payload)))
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
            if path == "/api/session/catalog":
                self._send(*_json_response(app.session_catalog(payload)))
                return
            if path == "/api/session/preview":
                self._send(*_json_response(app.session_preview(payload)))
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
            if path == "/api/migration/export":
                result = app.migration_export(payload)
                self._send(*_json_response(result, status=200 if result.get("ok") else 400))
                return
            if path == "/api/migration/preview":
                result = app.migration_preview(payload)
                self._send(*_json_response(result, status=200 if result.get("ok") else 400))
                return
            if path == "/api/migration/apply":
                result = app.migration_apply(payload)
                self._send(*_json_response(result, status=200 if result.get("ok") else 400))
                return
            if path == "/api/migration/start-status":
                result = app.migration_start_status(payload)
                self._send(*_json_response(result, status=200 if result.get("ok", True) else 400))
                return
            if path == "/api/migration/start":
                result = app.migration_start(payload)
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
    if args.print_summary:
        snapshot = app.snapshot()
        print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.print_markdown:
        snapshot = app.snapshot()
        print(build_setup_markdown(snapshot), end="")
        return 0
    serve_config_web(app, host=args.host, port=args.port, open_browser=not args.no_open)
    return 0
