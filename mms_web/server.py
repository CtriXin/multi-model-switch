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
from urllib.parse import unquote, urlsplit, parse_qs

from mms_version import VERSION
from mms_platform import capability_snapshot

from . import remote_access as access
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
    def __init__(self, *, state_root: Path, config_root: Path | None = None,
                 listen: str = "loopback", hostnames: tuple[str, ...] = ()):
        from .runtime import require_private_root
        state_root = require_private_root(state_root)
        # Loopback-only is the default and needs no token, so nothing changes
        # for a browser on this machine.
        self.access = access.RemoteAccess(state_root, listen, hostnames)
        # Set by create_server, which owns the handler class the extra sockets
        # need. Absent in tests that drive the application without a server.
        self.listeners = None
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

    def bootstrap(self, include_cli: bool = False) -> dict:
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
            # The probe knows what is missing — an absent pi, a Node too old to
            # run it. Repeating "not ready" instead leaves the reader with
            # nothing to act on, which is what a whole machine of greyed-out
            # models looked like.
            blocker = str(capabilities.get("launchReason") or "").strip() or "Web 会话接入尚未就绪。"
            snapshot = {
                **snapshot,
                "models": [{**model, "available": False,
                            "reason": model.get("reason") or blocker}
                           for model in snapshot.get("models", [])],
                "presets": [{**preset, "available": False,
                             "reason": preset.get("reason") or blocker}
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
            **capability_snapshot(),
            "sessions": self.all_sessions(include_cli),
        }

    def _cli_sessions(self) -> list[dict]:
        """Sessions started from the command line, read from Pi's own files.

        Read-only and best-effort: a missing directory or an unreadable file
        must never take the session list down with it.
        """
        if not self.config_root:
            return []
        try:
            from .cli_sessions import index, session_dir_for
            return index(session_dir_for(self.config_root),
                         workspaces=self._known_workspaces())
        except Exception:
            return []

    def _known_workspaces(self) -> list[dict]:
        """The registered folders, for placing command-line sessions."""
        if not self.catalog:
            return []
        try:
            return self.catalog.workspaces()
        except Exception:
            return []

    def all_sessions(self, include_cli: bool = False) -> list[dict]:
        """Pilot's own sessions, and the command-line ones when asked for.

        The caller decides, so the page's own switch takes effect on its next
        read with no restart and no server-side preference to keep in sync.
        """
        own = self._sessions().list_sessions() if self.sessions else []
        if not include_cli:
            return own
        # A session resumed here owns its Pi session, so drop the read-only
        # row for it rather than showing the same conversation twice.
        claimed = {str(s.get("piSessionId") or "") for s in own}
        claimed.discard("")
        merged = own + [s for s in self._cli_sessions()
                        if s["piSessionId"] not in claimed]
        merged.sort(key=lambda view: view.get("updatedAt") or "", reverse=True)
        # Transcript source paths remain server-internal; detail lookup resolves
        # the id again from the scoped session directory.
        return [{k: v for k, v in row.items() if k != "path"} for row in merged]

    def cli_session_detail(self, session_id: str) -> dict:
        """A read-only transcript for one command-line session."""
        from .cli_sessions import index, session_dir_for, transcript
        wanted = session_id[len("cli:"):]
        if not self.config_root or not wanted:
            raise WebError("NOT_FOUND", "找不到这个会话。", 404)
        row = next((s for s in index(session_dir_for(self.config_root), limit=2000,
                                     workspaces=self._known_workspaces())
                    if s["piSessionId"] == wanted), None)
        if row is None:
            raise WebError("NOT_FOUND", "找不到这个会话。", 404)
        return {"session": {k: v for k, v in row.items() if k != "path"},
                # The transcript path is server-only and never crosses the API.
                "events": transcript(row["path"]),
                # Present and empty, not absent: the view reads these without
                # checking, and an absent array is what blanked the page.
                "artifacts": [], "artifactNotice": "", "approvals": [], "runtime": {},
                "note": "这个会话是在命令行里开始的，这里只读。"}

    def remote_access_state(self) -> dict:
        """The switch, the ways in, and which of them are actually listening."""
        port = self.listeners._port if self.listeners else 0
        self.access.refresh()
        if self.listeners:
            # Addresses change with the network, so bring the sockets in line
            # with what the machine has now before reporting them.
            self.listeners.sync(self.access.extra_binds())
        state = self.access.state(port)
        state["listening"] = self.listeners.active if self.listeners else []
        state["unavailable"] = self.listeners.failed if self.listeners else {}
        # Only reachable entries are offered; a bind that failed leads nowhere.
        if state["mode"] == "lan":
            reachable = set(state["listening"])
            state["links"] = [entry for entry in state["links"]
                              if entry["kind"] != "address" or entry["host"] in reachable]
        return state

    def set_remote_access(self, payload: dict) -> dict:
        """Turn remote access on or off, manage tunnel names, or roll the token."""
        payload = dict(payload or {})
        if payload.get("hostname"):
            if self.access.mode == "loopback":
                raise WebError("REMOTE_ACCESS_OFF", "先打开远程访问，再加隧道域名。", 409)
            if not self.access.add_hostname(str(payload["hostname"])):
                raise WebError("INVALID_HOSTNAME",
                               "这不像一个域名。把隧道给你的地址整条粘进来就行。", 400)
            return self.remote_access_state()
        if payload.get("removeHostname"):
            self.access.remove_hostname(str(payload["removeHostname"]))
            return self.remote_access_state()
        if payload.get("regenerate") is True:
            if self.access.mode == "loopback":
                raise WebError("REMOTE_ACCESS_OFF", "先打开远程访问，再换 token。", 409)
            self.access.regenerate()
            return self.remote_access_state()
        if "enabled" not in payload:
            raise WebError("INVALID_REQUEST", "缺少 enabled。", 400)
        # isinstance, not `in (True, False)`: 1 == True in Python, and a
        # stray 1 must be refused rather than quietly read as "off".
        if not isinstance(payload["enabled"], bool):
            raise WebError("INVALID_PARAMETER", "enabled 必须是 true 或 false。", 400)
        wanted = "lan" if payload["enabled"] else "loopback"
        # "all" is a deliberate command-line choice; the switch never widens
        # past the machine's own addresses on its own, and it must not narrow
        # it either: the wildcard socket stays bound for the life of the
        # process, so dropping to loopback would only clear the token gate
        # while the network can still reach every endpoint.
        if self.access.mode == "all":
            return self.remote_access_state()
        self.access.set_mode(wanted)
        if self.listeners:
            self.listeners.sync(self.access.extra_binds())
        return self.remote_access_state()

    def adopt_cli_session(self, session_id: str, payload: dict) -> dict:
        """Continue a terminal-started session in Pilot from here on.

        The transcript path is resolved from the read-only index, never taken
        from the request, so a caller cannot point this at another file.
        """
        from .cli_sessions import index, session_dir_for
        wanted = session_id[len("cli:"):] if session_id.startswith("cli:") else ""
        if not self.config_root or not wanted:
            raise WebError("NOT_FOUND", "只有终端里开始的会话需要接入。", 404)
        service = self._sessions()
        already = next((s for s in service.list_sessions()
                        if str(s.get("piSessionId") or "") == wanted), None)
        if already is not None:
            # Idempotent: a second click opens the session the first one made.
            return service.get_session(already["id"])
        row = next((s for s in index(session_dir_for(self.config_root), limit=2000,
                                     workspaces=self._known_workspaces())
                    if s["piSessionId"] == wanted), None)
        if row is None:
            raise WebError("NOT_FOUND", "找不到这个会话。", 404)
        payload = dict(payload or {})
        workspace_id = str(payload.get("workspaceId") or "") or str(row.get("workspaceId") or "")
        if not workspace_id:
            # The folder it ran in is not registered. Register it, so the
            # adopted session has the working folder its files come from.
            if not self.catalog:
                raise WebError("CAPABILITY_UNAVAILABLE", "本地服务尚未连接。", 409)
            folder = str(row.get("cwd") or "")
            if not folder or not Path(folder).is_dir():
                raise WebError("WORKSPACE_REQUIRED",
                               "这个会话原来的目录已经不在了，请选择一个工作文件夹。", 409)
            workspace_id = str(self.catalog.add_workspace({"path": folder})["id"])
        payload["workspaceId"] = workspace_id
        return service.adopt(row, payload)

    def get(self, parts: list[str], query: dict[str, list[str]] | None = None) -> dict:
        include_cli = (query or {}).get("cli", ["0"])[0] == "1"
        if parts == ["update", "identity"]:
            from .update_handoff import path_identity, session_inventory
            return {"version": VERSION, "processId": os.getpid(), "instance": self.instance, "identity": path_identity(Path(__file__).resolve().parent.parent, self.state_root, self.config_root, Path.cwd()), "sessions": session_inventory(self.sessions)}
        if parts == ["update"]:
            return self.updates.status()
        if parts == ["remote-access"]:
            return self.remote_access_state()
        if parts == ["model-settings"]:
            return self._model_settings().read()
        if parts == ["skill-preferences"]:
            return self._sessions().skills.preferences()
        if parts == ["ui-preferences"]:
            from .ui_preferences import UiPreferences
            return UiPreferences(self.state_root).read(seed_version=VERSION)
        if parts == ["sessions"]:
            return {"sessions": self.all_sessions(include_cli)}
        if len(parts) == 2 and parts[0] == "attachments":
            return self._sessions().files.preview_attachment(parts[1])
        if len(parts) == 3 and parts[0] == "sessions":
            if parts[2] == "diagnostics":
                return self._sessions().diagnostics(parts[1])
            if parts[2] == "runtime":
                return self._sessions().runtime_view(parts[1])
            if parts[2] == "commands":
                return self._sessions().command_catalog(parts[1])
            if parts[2] == "side-questions":
                return {"sideQuestions": self._sessions().list_side_questions(parts[1])}
        if len(parts) == 4 and parts[0] == "sessions" and parts[2] == "side-questions":
            return self._sessions().get_side_question(parts[1], parts[3])
        if parts == ["bootstrap"]:
            return self.bootstrap(include_cli)
        if len(parts) == 2 and parts[0] == "sessions":
            if parts[1].startswith("cli:"):
                return self.cli_session_detail(parts[1])
            return self._sessions().get_session(parts[1])
        raise WebError("NOT_FOUND", "找不到这个接口。", 404)

    # POSTs that change nothing and can take seconds: a native folder dialog the
    # user may leave open, and two filesystem sweeps. Holding the mutation lock
    # through those would stop every other POST — sending a message, stopping a
    # session, confirming an update — for as long as they run. They only read
    # state that is written by atomic replace, so a concurrent write is seen
    # whole or not at all.
    _UNLOCKED_POSTS = (["workspaces", "choose"], ["workspaces", "search"], ["workspaces", "locate"])

    def _post_readonly(self, parts: list[str], payload: dict) -> dict:
        if parts == ["workspaces", "choose"]:
            import subprocess
            import sys
            if sys.platform != "darwin":
                raise WebError("FOLDER_PICKER_UNAVAILABLE", "请直接填写电脑上的文件夹路径。", 409)
            result = subprocess.run(["osascript", "-e", 'POSIX path of (choose folder with prompt "选择 MMS 的工作文件夹")'], capture_output=True, text=True, timeout=120)
            return {"path": result.stdout.strip() if result.returncode == 0 else ""}
        if not self.catalog:
            raise WebError("CAPABILITY_UNAVAILABLE", "本地服务尚未连接。", 409)
        if parts == ["workspaces", "search"]:
            from .workspace_search import search_workspaces
            return search_workspaces(self.catalog, payload)
        from .workspace_search import locate_folder
        return locate_folder(self.catalog, payload)

    def post(self, parts: list[str], payload: dict) -> dict:
        if parts in self._UNLOCKED_POSTS:
            return self._post_readonly(parts, payload)
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
        if parts == ["remote-access"]:
            return self.set_remote_access(payload)
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
        if parts == ["skill-preferences"]:
            return self._sessions().skills.set_preferences(payload)
        if parts == ["ui-preferences"]:
            from .ui_preferences import UiPreferences
            return UiPreferences(self.state_root).update(payload)
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
        if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "adopt":
            return self.adopt_cli_session(parts[1], payload)
        if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "side-questions":
            return self._sessions().ask_side_question(parts[1], payload)
        if (len(parts) == 5 and parts[0] == "sessions" and parts[2] == "side-questions"
                and parts[4] == "cancel"):
            return self._sessions().cancel_side_question(parts[1], parts[3])
        if len(parts) == 3 and parts[0] == "sessions":
            methods = {"messages": "send", "stop": "stop", "control": "control", "manage": "manage", "fork": "fork", "model": "switch_model", "artifacts": "artifact", "queue": "queue"}
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
        if self.listeners:
            self.listeners.close()
        if self.sessions:
            self.sessions.close()


def create_server(app: WebApplication, static_root: Path, port: int = 8765):
    root = static_root.resolve()
    import hashlib
    from mms_version import VERSION
    identity = hashlib.sha256((str(Path(__file__).resolve().parent.parent) + "|" +
                               str(app.config_root.resolve()) + "|" + VERSION).encode()).hexdigest()
    # `mms web status|url|stop|restart` decides "is this one mine" from this
    # fingerprint instead of re-parsing the server's command line, which is not
    # recoverable on Windows. It is a hash, so no local path is published.
    from .service import state_identity
    state_fingerprint = state_identity(app.state_root)

    class Handler(BaseHTTPRequestHandler):
        server_version = "MMSWeb/1"

        def log_message(self, _format, *args):
            # Request paths/bodies can contain private task data. No access log.
            return

        def _presented_token(self):
            """The token this request carries, from the cookie or the query."""
            from http.cookies import SimpleCookie
            query = parse_qs(urlsplit(self.path).query)
            if query.get(access.QUERY):
                return query[access.QUERY][0], True
            jar = SimpleCookie(self.headers.get("Cookie", ""))
            morsel = jar.get(access.COOKIE)
            return (morsel.value if morsel else ""), False

        def _check_origin(self, *, mutation=False):
            expected_port = self.server.server_address[1]
            if not app.access.accepts(self.headers.get("Host"), expected_port):
                raise WebError("INVALID_HOST", "只允许访问本机服务地址。", 403)
            origin = self.headers.get("Origin")
            if origin is not None:
                # The page that issued this request must live on a host this
                # server answers to, judged by the same rule as the Host
                # header so "--listen all" accepts every interface it serves.
                parts = urlsplit(origin)
                if parts.scheme not in ("http", "https") or not app.access.accepts(parts.netloc, expected_port):
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
            self.send_header("X-MMS-Web-Version", VERSION)
            self.send_header("X-MMS-Web-State", state_fingerprint)
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

        def _gate(self):
            """Return True when the request may proceed.

            A valid token in the query is exchanged for a cookie and the URL
            is redirected without it, so the token does not sit in history,
            in the address bar, or in a Referer header on the way out.
            """
            # A tunnel can reach this socket over loopback without forwarding
            # headers. Remote mode therefore authenticates every connection.
            if not app.access.required:
                return True
            presented, from_query = self._presented_token()
            if not app.access.valid(presented):
                self._send(401, b"401", "text/plain; charset=utf-8")
                return False
            if from_query and self.command == "GET":
                split = urlsplit(self.path)
                query = "&".join(part for part in split.query.split("&")
                                 if not part.startswith(f"{access.QUERY}="))
                secure = self.headers.get("X-Forwarded-Proto", "").lower() == "https"
                self.send_response(302)
                self.send_header("Location", split.path + (f"?{query}" if query else ""))
                self.send_header("Set-Cookie",
                                 f"{access.COOKIE}={presented}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000"
                                 + ("; Secure" if secure else ""))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return False
            return True

        def do_GET(self):
            try:
                self._check_origin()
                if not self._gate():
                    return
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
                    return self._json(200, app.get(parts, parse_qs(urlsplit(self.path).query)))
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
                if not self._gate():
                    return
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

    server = ThreadingHTTPServer((app.access.bind_address(), port), Handler)
    server.daemon_threads = True
    app.listeners = RemoteListeners(Handler, server.server_address[1])
    app.listeners.sync(app.access.extra_binds())
    return server


class RemoteListeners:
    """The sockets that exist only while remote access is switched on.

    One per address rather than the wildcard, for two reasons. The always-on
    loopback socket already holds this port, and a second wildcard bind on it
    would collide. And closing these leaves nothing listening on the network,
    which is what "off" has to mean: a port that accepts a connection is
    visible whatever it answers.
    """

    def __init__(self, handler, port: int) -> None:
        self._handler = handler
        self._port = port
        self._servers: dict[str, ThreadingHTTPServer] = {}
        self.failed: dict[str, str] = {}

    @property
    def active(self) -> list[str]:
        return sorted(self._servers)

    def sync(self, addresses: list[str]) -> None:
        """Listen on exactly these addresses, opening and closing as needed."""
        wanted = list(dict.fromkeys(addresses))
        for address in list(self._servers):
            if address not in wanted:
                self._close(address)
        self.failed = {}
        for address in wanted:
            if address in self._servers:
                continue
            try:
                extra = ThreadingHTTPServer((address, self._port), self._handler)
            except OSError as error:
                # A point-to-point tunnel endpoint may refuse a bind. Skip it
                # and say so rather than failing the whole switch.
                self.failed[address] = str(error)
                continue
            extra.daemon_threads = True
            self._servers[address] = extra
            threading.Thread(target=extra.serve_forever, name=f"mms-web-{address}",
                             daemon=True).start()

    def _close(self, address: str) -> None:
        extra = self._servers.pop(address, None)
        if extra is None:
            return
        extra.shutdown()
        extra.server_close()

    def close(self) -> None:
        for address in list(self._servers):
            self._close(address)
