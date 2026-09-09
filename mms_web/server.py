"""Loopback HTTP transport. Adapter absence is explicit, never simulated data."""

from __future__ import annotations

import importlib
import json
import mimetypes
import secrets
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from mms_version import VERSION

from .errors import WebError

MAX_BODY = 12 * 1024 * 1024


def _adapter(module: str, name: str, **kwargs):
    try:
        loaded = importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name != module:
            raise
        return None
    return getattr(loaded, name)(**kwargs)


class WebApplication:
    def __init__(self, *, state_root: Path, config_root: Path | None = None):
        from .runtime import require_private_root
        state_root = require_private_root(state_root)
        if config_root is None:
            config_root = state_root / "config"
        self.config_root = config_root
        self.state_root = state_root
        self.csrf_token = secrets.token_urlsafe(32)
        self.mutation_lock = threading.RLock()
        self.probation_token = os.environ.get("MMS_WEB_PROBATION", "")
        self.maintenance = bool(self.probation_token)
        self.pending_handoff = None
        self.instance = os.environ.get("MMS_WEB_INSTANCE") or secrets.token_hex(16)
        from .updates import UpdateService
        self.updates = UpdateService(self)
        self.catalog = _adapter(
            "mms_web.catalog", "CatalogService",
            config_root=config_root, state_root=state_root,
        )
        self.sessions = _adapter(
            "mms_web.sessions", "SessionService",
            config_root=config_root, state_root=state_root, catalog=self.catalog, real_launch=config_root is not None,
        ) if self.catalog else None

    def _model_settings(self):
        if not hasattr(self, "model_settings"):
            from .model_settings import ModelSettings
            if not self.catalog:
                raise WebError("CAPABILITY_UNAVAILABLE", "模型目录不可用。", 409)
            self.model_settings = ModelSettings(self.catalog)
        return self.model_settings

    def bootstrap(self) -> dict:
        snapshot = self.catalog.snapshot() if self.catalog else {
            "models": [], "services": [], "presets": [], "workspaces": [],
            "diagnostics": [{"code": "CATALOG_UNAVAILABLE",
                             "message": "模型目录接入尚未就绪，可以先查看界面预览。"}],
        }
        capabilities = {"catalogRead": False, "configure": False, "launch": False}
        if self.catalog:
            capabilities.update(self.catalog.capabilities())
            capabilities["discoverModels"] = True
            capabilities["modelSettings"] = self._model_settings().available()
        if self.sessions:
            capabilities.update(self.sessions.capabilities())
        if not capabilities["launch"]:
            snapshot = {
                **snapshot,
                "models": [{**model, "available": False,
                            "reason": model.get("reason") or "Web 会话接入尚未就绪。"}
                           for model in snapshot.get("models", [])],
                "presets": [{**preset, "available": False,
                             "reason": preset.get("reason") or "Web 会话接入尚未就绪。"}
                            for preset in snapshot.get("presets", [])],
            }
        if capabilities["launch"]:
            snapshot["models"] = [
                {**m, "harnesses": ["pi"] if "pi" in m.get("harnesses", []) else [],
                 "available": bool(m.get("available") and "pi" in m.get("harnesses", [])),
                 **({"reason": m.get("reason") or "这个模型尚未支持当前网页执行工具。"}
                    if "pi" not in m.get("harnesses", []) else {})}
                for m in snapshot.get("models", [])
            ]
        snapshot["presets"] = [
            {**p, "available": False, "reason": "该执行工具的网页交互正在接入，可先选择 Pi。"}
            if p.get("harness") != "pi" else p for p in snapshot.get("presets", [])
        ]
        return {
            **snapshot, "version": "1", "appVersion": VERSION, "mode": "live",
            "capabilities": capabilities, "csrfToken": self.csrf_token,
            "sessions": self.sessions.list_sessions() if self.sessions else [],
        }

    def get(self, parts: list[str]) -> dict:
        if parts == ["update", "identity"]:
            from .update_handoff import path_identity, session_inventory
            return {"version": VERSION, "processId": os.getpid(), "instance": self.instance, "identity": path_identity(Path(__file__).resolve().parent.parent, self.state_root, self.config_root, Path.cwd()), "sessions": session_inventory(self.sessions)}
        if parts == ["update"]:
            return self.updates.status()
        if parts == ["model-settings"]:
            return self._model_settings().read()
        if parts == ["sessions"]:
            return {"sessions": self._sessions().list_sessions()}
        if len(parts) == 2 and parts[0] == "attachments":
            return self._sessions().files.preview_attachment(parts[1])
        if len(parts) == 3 and parts[0] == "sessions":
            if parts[2] == "diagnostics":
                return self._sessions().diagnostics(parts[1])
            if parts[2] == "runtime":
                return self._sessions().runtime_view(parts[1])
            if parts[2] == "commands":
                return self._sessions().command_catalog(parts[1])
        if parts == ["bootstrap"]:
            return self.bootstrap()
        if len(parts) == 2 and parts[0] == "sessions":
            return self._sessions().get_session(parts[1])
        raise WebError("NOT_FOUND", "找不到这个接口。", 404)

    def post(self, parts: list[str], payload: dict) -> dict:
        with self.mutation_lock:
            if parts == ["update", "commit"]:
                if not self.probation_token or not secrets.compare_digest(str(payload.get("token") or ""), self.probation_token):
                    raise WebError("INVALID_UPDATE_TOKEN", "更新确认无效。", 403)
                from .runtime import private_json
                operation_path = self.state_root / "updates/operation.json"
                from .updates import read_json
                operation = read_json(operation_path)
                private_json(operation_path, {**operation, "phase": "complete", "message": f"已更新到 v{VERSION}，会话历史已保留。", "cancellable": False})
                self.probation_token = ""
                self.maintenance = False
                return {"ok": True}
            if self.maintenance:
                raise WebError("UPDATE_IN_PROGRESS", "正在验证更新，会话已保留，请稍后再试。", 409)
            return self._post(parts, payload)

    def _post(self, parts: list[str], payload: dict) -> dict:
        if parts in (["update", "start"], ["update", "cancel"]):
            coordinator = self.updates.coordinator
            if not coordinator:
                raise WebError("UPDATE_UNAVAILABLE", "当前启动方式尚未启用安全更新。", 409)
            return coordinator.start(payload) if parts[1] == "start" else coordinator.cancel()
        if parts == ["update", "check"]:
            return self.updates.request_check()
        if parts == ["update", "preferences"]:
            return self.updates.preferences(payload)
        if len(parts) == 2 and parts[0] == "model-settings" and parts[1] in {"discover", "check", "refresh", "preview", "apply"}:
            return getattr(self._model_settings(), parts[1])(payload)
        if parts == ["launch-options"]:
            import shutil
            resolved = self.catalog.resolve_launch(str(payload.get("presetId") or ""), str(payload.get("workspaceId") or ""))
            root = Path(resolved["runtime"]["_webConfigRoot"])
            try:
                return resolved.get("launchOptions", {})
            finally:
                if root.parent == self.state_root / "runtimes":
                    shutil.rmtree(root)
        if parts == ["skills"]:
            return self._sessions().skills.snapshot(str(payload.get("workspaceId") or ""))
        if parts == ["project-materials"]:
            return self._sessions().materials.snapshot(str(payload.get("workspaceId") or ""))
        if parts == ["project-materials", "change"]:
            return self._sessions().materials.change(payload)
        if parts == ["attachments"]:
            return self._sessions().files.upload(payload)
        if parts == ["files", "import"]:
            return self._sessions().files.import_to_workspace(payload)
        if parts == ["files", "reference-local"]:
            return self._sessions().files.reference_local(payload)
        if parts == ["files", "choose-local"]:
            return self._sessions().files.choose_local(payload)
        if parts in (["files", "tree"], ["files", "read"], ["files", "git"]):
            return getattr(self._sessions().files, parts[1])(payload)
        if parts == ["workspaces", "choose"]:
            import subprocess
            import sys
            if sys.platform != "darwin":
                raise WebError("FOLDER_PICKER_UNAVAILABLE", "请直接填写电脑上的文件夹路径。", 409)
            result = subprocess.run(["osascript", "-e", 'POSIX path of (choose folder with prompt "选择 MMS 的工作文件夹")'], capture_output=True, text=True, timeout=120)
            return {"path": result.stdout.strip() if result.returncode == 0 else ""}
        if parts == ["workspaces", "search"]:
            if not self.catalog:
                raise WebError("CAPABILITY_UNAVAILABLE", "本地服务尚未连接。", 409)
            from .workspace_search import search_workspaces
            return search_workspaces(self.catalog, payload)
        if parts == ["workspaces"]:
            if not self.catalog:
                raise WebError("CAPABILITY_UNAVAILABLE", "本地服务尚未连接。", 409)
            return self.catalog.add_workspace(payload)
        if len(parts) == 2 and parts[0] == "workspaces" and parts[1] in {"rename", "remove"}:
            if not self.catalog:
                raise WebError("CAPABILITY_UNAVAILABLE", "本地服务尚未连接。", 409)
            return getattr(self.catalog, f"{parts[1]}_workspace")(payload)
        if parts == ["configuration", "preview"]:
            return self._catalog().configuration_preview(payload)
        if parts == ["configuration", "discover"]:
            self._catalog()
            from .connections import discover_models
            return discover_models(payload)
        if parts == ["configuration", "apply"]:
            return self._catalog().configuration_apply(payload)
        if parts == ["configuration", "discard"]:
            return self._catalog().configuration_discard(payload)
        if parts == ["sessions"]:
            service = self._sessions()
            if not service.capabilities().get("launch"):
                raise WebError("CAPABILITY_UNAVAILABLE", "当前会话路径尚未就绪，未启动模型。", 409)
            return service.launch(payload)
        if len(parts) == 3 and parts[0] == "sessions":
            methods = {"messages": "send", "stop": "stop", "control": "control", "manage": "manage", "fork": "fork", "model": "switch_model", "artifacts": "artifact"}
            if parts[2] in methods:
                return getattr(self._sessions(), methods[parts[2]])(parts[1], payload)
        if len(parts) == 4 and parts[0] == "sessions" and parts[2] == "approvals":
            return self._sessions().approve(parts[1], parts[3], payload)
        raise WebError("NOT_FOUND", "找不到这个接口。", 404)

    def _sessions(self):
        if not self.sessions:
            raise WebError("CAPABILITY_UNAVAILABLE", "会话接入尚未就绪，未启动模型。", 409)
        return self.sessions

    def _catalog(self):
        if not self.catalog or not self.catalog.capabilities().get("configure"):
            raise WebError("CAPABILITY_UNAVAILABLE", "配置接入尚未就绪，未修改任何配置。", 409)
        return self.catalog

    def close(self):
        self.updates.close()
        if self.sessions:
            self.sessions.close()


def create_server(app: WebApplication, static_root: Path, port: int = 8765):
    root = static_root.resolve()
    import hashlib
    from mms_version import VERSION
    identity = hashlib.sha256((str(Path(__file__).resolve().parent.parent) + "|" +
                               str(app.config_root.resolve()) + "|" + VERSION).encode()).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        server_version = "MMSWeb/1"

        def log_message(self, _format, *args):
            # Request paths/bodies can contain private task data. No access log.
            return

        def _check_origin(self, *, mutation=False):
            expected_port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{expected_port}", f"localhost:{expected_port}"}
            if self.headers.get("Host") not in hosts:
                raise WebError("INVALID_HOST", "只允许访问本机服务地址。", 403)
            origin = self.headers.get("Origin")
            if origin is not None and origin not in {f"http://{host}" for host in hosts}:
                raise WebError("INVALID_ORIGIN", "请在 MMS 本地页面中执行此操作。", 403)
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise WebError("INVALID_ORIGIN", "不允许跨站访问本地服务。", 403)
            if mutation and not secrets.compare_digest(
                self.headers.get("X-MMS-CSRF", ""), app.csrf_token
            ):
                raise WebError("INVALID_CSRF", "页面连接已失效，请刷新后重试。", 403)

        def _send(self, status: int, body: bytes, content_type: str, *, preview=False):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-MMS-Web-Identity", identity)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "SAMEORIGIN" if preview else "DENY")
            from .artifact_preview import PREVIEW_CSP
            self.send_header("Content-Security-Policy", PREVIEW_CSP if preview else
                             "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "img-src 'self' data:; connect-src 'self'; "
                             "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status, payload):
            self._send(status, json.dumps(payload, ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")

        def _error(self, exc: Exception):
            if isinstance(exc, WebError):
                self._json(exc.status, {"error": {"code": exc.code, "message": exc.message}})
            else:
                self._json(500, {"error": {"code": "INTERNAL_ERROR",
                                         "message": "本地服务暂时无法完成操作。请检查服务状态。"}})

        def _parts(self):
            path = unquote(urlsplit(self.path).path)
            if not path.startswith("/api/v1/"):
                raise WebError("NOT_FOUND", "找不到这个接口。", 404)
            return path.removeprefix("/api/v1/").split("/")

        def do_GET(self):
            try:
                self._check_origin()
                path = unquote(urlsplit(self.path).path)
                if path.startswith("/api/"):
                    parts = self._parts()
                    if len(parts) == 6 and parts[0] == "sessions" and parts[2] == "artifacts" and parts[4] == "preview":
                        if not parts[5].isdigit():
                            raise WebError("INVALID_REVISION", "成果版本无效。", 400)
                        item = app._sessions().artifact(parts[1], {"id": parts[3], "revision": int(parts[5])})
                        if item["kind"] != "html":
                            raise WebError("PREVIEW_UNAVAILABLE", "这个成果不是 HTML。", 400)
                        from .artifact_preview import offline_html
                        return self._send(200, offline_html(item["content"]), "text/html; charset=utf-8", preview=True)
                    return self._json(200, app.get(parts))
                file = (root / (path.lstrip("/") or "index.html")).resolve()
                if not file.is_relative_to(root) or not file.is_file():
                    raise WebError("NOT_FOUND", "页面资源不存在。请先构建 MMS Pilot。", 404)
                content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                self._send(200, file.read_bytes(), content_type)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                self._error(exc)

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            try:
                self._check_origin(mutation=True)
                if self.headers.get_content_type() != "application/json":
                    raise WebError("INVALID_BODY", "请求必须使用 JSON。", 415)
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    raise WebError("INVALID_BODY", "无效的请求长度。") from None
                if size < 1 or size > MAX_BODY:
                    raise WebError("INVALID_BODY", "请求内容为空或过大。", 413)
                self.connection.settimeout(10)
                try:
                    payload = json.loads(self.rfile.read(size))
                except (ValueError, UnicodeError):
                    raise WebError("INVALID_BODY", "无法读取请求内容。") from None
                if not isinstance(payload, dict):
                    raise WebError("INVALID_BODY", "请求内容必须是一个对象。")
                self._json(200, app.post(self._parts(), payload))
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                self._error(exc)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
