"""MMS Pilot session service (API v1, Agent B contract).

Owns web-launched rich sessions: session ids, event sequences, thread-safe
snapshots, persistence, requestId idempotency, and process lifecycle for the
first rich driver (Pi ``--mode rpc``). The catalog is injected; tests use a
fake catalog. External/glinter sessions are never adopted and never gain
fabricated send/stop capabilities.

Session state comes from the RPC protocol / child process only. No timers
fabricate success.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .drivers import PiRpcDriver, PipedProcessLauncher, probe_mms_pi_seam
from .drivers.base import DriverClosedError, DriverWriteUnconfirmedError, LaunchSeamUnavailable, RpcTimeoutError
from .errors import WebError
from .context_evidence import consume_prompt, observe_read, prompt_hash
from .session_actions import SessionActions, backfill_history, redact

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_EVENTS = 4000
_MAX_NOTICE = 1000
_MAX_STDERR_NOTICE = 600
_PROTO_STATES = {"running", "idle", "waiting"}
_FINAL_STATES = {"completed", "stopped", "error"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _fingerprint(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def _clip(text: str, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + "…"


class _DriverSink:
    """Bridge from a driver's reader threads into one session's state."""

    def __init__(self, service: "SessionService", session: "_LiveSession") -> None:
        self._service = service
        self._session = session
        self.active = True

    def upsert_event(self, fields: dict) -> None:
        if not self.active:
            return
        self._service._apply_driver_event(self._session, fields)

    def set_proto_state(self, state: str) -> None:
        if not self.active:
            return
        self._service._apply_proto_state(self._session, state)

    def set_activity(self, phase: str, **details) -> None:
        if not self.active:
            return
        self._service._apply_activity(self._session, phase, details)

    def approval_pending(self, approval_id: str, method: str, title: str) -> None:
        if not self.active:
            return
        self._service._apply_approval_pending(self._session, approval_id, method, title)

    def approval_resolved(self, approval_id: str, decision: str) -> None:
        if not self.active:
            return
        self._service._apply_approval_resolved(self._session, approval_id, decision)

    def process_exited(self, exit_code: int, stderr_tail: str) -> None:
        if not self.active:
            return
        self._service._apply_process_exited(self._session, exit_code, stderr_tail)


class _LiveSession:
    def __init__(self, meta: dict, state_root: Path | None = None) -> None:
        self.lock = threading.RLock()
        self.mutation_lock = threading.RLock()
        self.meta = meta
        self.secrets: list[str] = []
        if meta.get("runtimeRoot"):
            try:
                saved = json.loads((Path(meta["runtimeRoot"]) / "resume.json").read_text())
                runtime = saved.get("runtime", {})
                self.secrets = [v for k, v in runtime.items() if isinstance(v, str)
                                and len(v) >= 8 and any(x in k.lower() for x in ("api_key", "token", "secret"))]
            except (OSError, ValueError):
                pass
        self.pending_prompts: dict[str, str] = {}
        self.stream_tails: dict[tuple[str, str], str] = {}
        self.events: list[dict] = []
        self.event_index: dict[str, dict] = {}
        self.last_sequence = 0
        self.state = "running"
        # Transient: never replay an old busy phase after restart.
        self.activity: dict | None = None
        self.turn_started_at: str | None = None
        self.driver: Any = None
        self.approvals: dict[str, dict] = {}
        self.stop_requested = False
        self.request_log: dict[str, str] = {}
        self.finalized = False
        self.updated_at = meta.get("updatedAt") or _now_iso()
        from .artifact_history import ArtifactHistory
        self.artifact_history = ArtifactHistory(state_root, meta, self.secrets) if state_root else None

    # -- events --------------------------------------------------------

    def append_event(self, fields: dict, now: Callable[[], str]) -> dict:
        event_id = str(fields.get("id") or f"e-{uuid.uuid4().hex[:12]}")
        self.last_sequence += 1
        event = {
            "id": event_id,
            "sequence": self.last_sequence,
            "kind": str(fields.get("kind") or "notice"),
            "text": str(fields.get("text") or ""),
            "createdAt": now(),
            "updatedAt": now(),
        }
        for key in ("title", "status", "approvalId", "decision", "arguments", "method", "options", "placeholder", "prefill", "answer", "thinking", "nativeTimestamp", "modelName", "usage", "attachments", "references", "skills", "fileSelections", "contextUsage"):
            if fields.get(key) is not None:
                event[key] = fields[key]
        self.event_index[event_id] = event
        self.events.append(event)
        self._trim_events()
        self.updated_at = now()
        return event

    def upsert_event(self, fields: dict, now: Callable[[], str]) -> dict:
        event_id = str(fields.get("id") or "")
        existing = self.event_index.get(event_id) if event_id else None
        if existing is None:
            return self.append_event(fields, now)
        if fields.get("textAppend") is not None:
            existing["text"] = str(existing.get("text") or "") + str(fields.get("textAppend") or "")
        elif fields.get("text") is not None:
            existing["text"] = str(fields.get("text"))
        for key in ("title", "status", "decision", "arguments", "method", "options", "placeholder", "prefill", "answer", "thinking", "nativeTimestamp", "modelName", "usage", "attachments", "references", "skills"):
            if fields.get(key) is not None:
                existing[key] = fields[key]
        if fields.get("thinkingAppend") is not None:
            existing["thinking"] = str(existing.get("thinking") or "") + str(fields["thinkingAppend"])
        # Last write wins as the event's end time; the reply duration reads it.
        existing["updatedAt"] = now()
        self.updated_at = now()
        return existing

    def _trim_events(self) -> None:
        while len(self.events) > _MAX_EVENTS:
            drop = self.events[0]
            if drop["kind"] in {"user", "approval"}:
                break
            self.events = self.events[1:]
            self.event_index.pop(drop["id"], None)

    # -- snapshots -----------------------------------------------------

    def alive(self) -> bool:
        return self.driver is not None and self.driver.alive()

    def can_resume(self) -> bool:
        root = self.meta.get("runtimeRoot")
        return bool(root and (Path(root) / "resume.json").is_file()
                    and (Path(root) / "conversation.jsonl").is_file())

    def session_caps(self) -> dict:
        alive = self.alive() and not self.finalized
        return {
            "send": bool(alive or self.can_resume()),
            "stop": bool(alive),
            "approve": bool(alive and self.approvals),
        }

    def session_view(self) -> dict:
        view = {
            "id": self.meta["id"],
            "title": self.meta.get("title") or "",
            "workspaceId": self.meta.get("workspaceId") or "",
            "harness": self.meta.get("harness") or "",
            "modelName": self.meta.get("modelName") or "",
            "presetId": self.meta.get("presetId") or "",
            "providerName": self.meta.get("providerName") or "",
            "channel": self.meta.get("channel") or "",
            "state": self.state,
            "activity": self.activity_view(),
            "updatedAt": self.updated_at,
            "owner": "web",
            "archived": bool(self.meta.get("archived")),
            "cwd": self.meta.get("cwd", ""),
            "forkedFrom": self.meta.get("forkedFrom"),
            "capabilities": self.session_caps(),
        }
        if self.meta.get("summary"):
            view["summary"] = self.meta["summary"]
        return view

    def detail_view(self) -> dict:
        from .artifacts import collect_artifacts
        return {
            "session": self.session_view(),
            "events": [copy.deepcopy(event) for event in self.events],
            "artifacts": self.artifact_history.list(self.events) if self.artifact_history else collect_artifacts(self.meta, self.events),
            "artifactNotice": self.artifact_history.note if self.artifact_history else "",
            "runtime": self.meta.get("runtimeView", {}),
        }

    def finish_pending_tools(self) -> None:
        for event in self.events:
            if event.get("kind") == "tool" and event.get("status") == "running":
                event["status"] = "error"
                event["text"] += "\n本轮已结束，未收到此工具的完成回报。"

    def cancel_pending(self):
        with self.lock:
            for event_id in list(self.pending_prompts):
                event = self.event_index.get(event_id)
                if event and event.get("status") == "queued":
                    event["status"] = "cancelled"
            self.pending_prompts.clear()

    def activity_view(self) -> dict | None:
        if self.state == "waiting":
            pending = next(iter(self.approvals.values()), {})
            return {"phase": "waiting", "method": pending.get("method", "confirm")}
        if self.state in _FINAL_STATES:
            return None
        return copy.deepcopy(self.activity)

    def persist(self, state_dir: Path) -> None:
        payload = {
            "schema": 1,
            "session": self.meta,
            "state": self.state,
            "events": self.events,
            "approvals": self.approvals,
            "requestLog": self.request_log,
            "lastSequence": self.last_sequence,
            "stopRequested": self.stop_requested,
            "updatedAt": self.updated_at,
        }
        from .runtime import private_json
        private_json(state_dir / f"{self.meta['id']}.json", payload)



class SessionService(SessionActions):
    """API v1 session adapter. See docs/mms-web/API.md for the contract."""

    def __init__(
        self,
        *,
        config_root: Path | None,
        state_root: Path,
        catalog,
        driver_factory: Callable | None = None,
        launch_plan_builder: Callable | None = None,
        process_launcher: Any = None,
        real_launch: bool = False,
        now: Callable[[], str] | None = None,
    ) -> None:
        self._config_root = Path(config_root) if config_root is not None else None
        self._state_root = Path(state_root)
        self._catalog = catalog
        self._now = now or _now_iso
        self._process_launcher = process_launcher or PipedProcessLauncher()
        from .drivers.launch_bridge import mms_pi_launch_plan_builder

        self._launch_plan_builder = launch_plan_builder or mms_pi_launch_plan_builder(self._config_root)
        self._driver_factory = driver_factory
        self._seam = probe_mms_pi_seam()
        # Real launches stay disabled until the lead integrates the launcher
        # seam; tests enable it explicitly with a task-owned fixture child.
        self._real_launch = bool(real_launch)
        self._lock = threading.RLock()
        self._sessions: dict[str, _LiveSession] = {}
        self._requests: dict[str, dict] = {}
        self._closed = False
        self._state_dir = self._state_root / "sessions"
        from .skills import SkillCatalog
        self.skills = SkillCatalog(catalog, self._state_root)
        self._load_persisted()
        from .files import FileService
        self.files = FileService(catalog, self._state_root)
        from .project_materials import ProjectMaterials
        self.materials = ProjectMaterials(catalog, self._state_root)

    # -- capabilities --------------------------------------------------

    def capabilities(self) -> dict:
        return {
            "launch": bool(
                self._real_launch
                and self._seam.get("available")
                and callable(getattr(self._catalog, "resolve_launch", None))
            )
        }

    def seam_report(self) -> dict:
        """Diagnostics for the lead; not part of the HTTP contract."""
        return copy.deepcopy(self._seam)

    # -- reads ---------------------------------------------------------

    def list_sessions(self) -> list[dict]:
        with self._lock:
            sessions = [session.session_view() for session in self._sessions.values()]
        sessions.sort(key=lambda view: view.get("updatedAt") or "", reverse=True)
        return sessions

    def get_session(self, session_id: str) -> dict:
        session = self._get(session_id)
        runtime = self.runtime_view(session_id) if not session.alive() or hasattr(session.driver, "request") else session.meta.get("runtimeView", {})
        with session.lock:
            backfill_history(session)
            detail = session.detail_view()
            detail["runtime"] = runtime
            return detail

    def artifact(self, session_id: str, payload: dict) -> dict:
        session = self._get(session_id)
        for key in ("revision", "compare"):
            if key in payload and (type(payload[key]) is not int or payload[key] < 0):
                raise WebError("INVALID_REVISION", "成果版本无效。", 400)
        with session.lock:
            return session.artifact_history.read(str(payload.get("id") or ""), session.events,
                                                 payload.get("revision"), payload.get("compare"))

    # -- mutations -----------------------------------------------------

    def launch(self, payload: dict) -> dict:
        self._require_open()
        payload = self._object_payload(payload)
        if payload.get("fileSelections"):
            raise WebError("INVALID_SELECTION", "请在成果所属会话中发送选段修改。", 400)
        request_id = self._validate_request_id(payload.get("requestId"))
        op_payload = {
            "op": "launch",
            "workspaceId": payload.get("workspaceId"),
            "presetId": payload.get("presetId"),
            "title": payload.get("title"),
            "prompt": payload.get("prompt"),
            "attachments": payload.get("attachments", []), "references": payload.get("references", []), "planMode": payload.get("planMode", False), "thinkingLevel": payload.get("thinkingLevel"), "skills": payload.get("skills", []),
        }
        with self._request_scope(request_id, op_payload) as replay:
            if replay is not None:
                with replay.lock:
                    return replay.detail_view()
            detail, live = self._do_launch(payload, request_id, op_payload)
            with self._lock:
                entry = self._requests.get(request_id)
                if entry is not None:
                    entry["sessionId"] = live.meta["id"]
        return detail

    def send(self, session_id: str, payload: dict) -> dict:
        self._require_open()
        session = self._get(session_id)
        payload = self._object_payload(payload)
        request_id = self._validate_request_id(payload.get("requestId"))
        text = payload.get("text") or ("请查看附件。" if payload.get("attachments") else "")
        if not isinstance(text, str) or not text.strip():
            raise WebError("INVALID_REQUEST", "请输入消息内容。", 400)
        op_payload = {"op": "send", "sessionId": session.meta["id"], "text": text, "skills": payload.get("skills", []), "attachments": payload.get("attachments", []), "references": payload.get("references", []), "fileSelections": payload.get("fileSelections", [])}
        with session.mutation_lock, self._request_scope(request_id, op_payload, session) as replay:
            if replay is not None:
                with replay.lock:
                    return replay.detail_view()
            selections = payload.get("fileSelections", [])
            if not isinstance(selections, list) or len(selections) > 4:
                raise WebError("INVALID_SELECTION", "每条消息最多引用 4 个成果选段。", 400)
            selected, selection_text = [], ""
            with session.lock:
                for item in selections:
                    clean, section = session.artifact_history.selection(item, session.events)
                    selected.append(clean)
                    selection_text += section
            images, attachments, suffix = self.files.prepare(payload.get("attachments", []), session.meta["workspaceId"], payload.get("references", []))
            suffix += selection_text
            if not session.alive():
                self._resume(session)
            skill_text, selected_skills = self.skills.prepare(payload.get("skills", []), session.meta["workspaceId"])
            suffix += skill_text
            material_text, materials = self.materials.prepare(session.meta["workspaceId"])
            suffix += material_text
            from .project_materials import usage_record
            context = usage_record(session.meta.get("cwd"), selected_skills, attachments, payload.get("references", []), selected, materials, payload.get("skillInvocation"))
            context["promptSha256"] = prompt_hash(text + suffix)
            self._check_images(session, images)
            with session.lock:
                previous_state = session.state
                session.stop_requested = False
                if session.state not in {"running", "waiting"}:
                    session.state = "running"
                    session.turn_started_at = self._now()
                event = session.append_event({"kind": "user", "text": text, "skills": selected_skills, "attachments": attachments, "references": payload.get("references", []), "fileSelections": selected, "contextUsage": context}, self._now)
                if previous_state in {"running", "waiting"}:
                    event["status"] = "queued"
                    session.pending_prompts[event["id"]] = text + suffix
            try:
                self._send_prompt(session, text + suffix, images=images)
                context["state"] = "submitted" if session.driver else "prepared"
            except WebError as exc:
                with session.lock:
                    context["state"] = "uncertain" if exc.code in {"RPC_TIMEOUT", "RPC_UNCONFIRMED"} else "failed"
                    session.pending_prompts.pop(event["id"], None)
                    event["status"] = "error"
                    if session.last_sequence == event.get("sequence") and session.state == "running":
                        session.state = previous_state
                    session.persist(self._state_dir)
                raise
            with session.lock:
                session.persist(self._state_dir)
                return session.detail_view()

    def _resume(self, session: _LiveSession) -> None:
        if not session.can_resume() or not self.capabilities()["launch"]:
            raise WebError("SESSION_NOT_ACTIVE", "该会话目前无法继续。", 409)
        root = Path(session.meta["runtimeRoot"]).resolve()
        if not root.is_relative_to((self._state_root / "runtimes").resolve()):
            raise WebError("INVALID_SESSION", "会话运行目录无效。", 409)
        saved = json.loads((root / "resume.json").read_text(encoding="utf-8"))
        plan = self._launch_plan_builder("pi", saved["modelInfo"], saved["runtime"], saved["cwd"])
        session.finalized = False
        session.stop_requested = False
        driver = self._spawn_driver(plan, _DriverSink(self, session))
        session.driver = driver
        try:
            state = driver.get_state()
            if not state.get("model"):
                raise DriverClosedError("model unavailable")
        except (DriverClosedError, RpcTimeoutError):
            driver.close(graceful_timeout=0.5)
            raise WebError("RESUME_FAILED", "恢复会话失败，请检查本机运行环境。", 502)
        effort = session.meta.get("controlSettings", {}).get("thinking")
        if effort:
            from .launch_options import set_thinking
            try:
                set_thinking(self, session, effort)
            except WebError:
                driver.close(graceful_timeout=0.5)
                raise
        with session.lock:
            session.state = "idle"
            session.activity = None
            session.turn_started_at = None
            session.approvals.clear()
            for event in session.events:
                if event.get("kind") == "approval" and not event.get("decision"):
                    event["decision"] = "deny"
            session.append_event({"kind": "notice", "text": "已恢复上次的上下文，可以继续工作。"}, self._now)

    def stop(self, session_id: str, payload: dict) -> dict:
        self._require_open()
        session = self._get(session_id)
        payload = self._object_payload(payload)
        request_id = self._validate_request_id(payload.get("requestId"))
        op_payload = {"op": "stop", "sessionId": session.meta["id"]}
        with self._request_scope(request_id, op_payload, session) as replay:
            if replay is not None:
                with replay.lock:
                    return replay.detail_view()
            driver = session.driver
            if driver is None or not driver.alive():
                # Idempotent: the process is already gone; nothing to abort.
                with session.lock:
                    return session.detail_view()
            session.stop_requested = True
            try:
                driver.abort()
                session.cancel_pending()
            except DriverClosedError:
                pass
            except RpcTimeoutError:
                session.append_event(
                    {"kind": "notice", "text": "停止请求未在超时内确认", "title": "stop"}, self._now
                )
            session.append_event(
                {"kind": "notice", "text": "已请求停止当前任务", "title": "stop"}, self._now
            )
            with session.lock:
                session.persist(self._state_dir)
                return session.detail_view()

    def approve(self, session_id: str, approval_id: str, payload: dict) -> dict:
        self._require_open()
        session = self._get(session_id)
        payload = self._object_payload(payload)
        request_id = self._validate_request_id(payload.get("requestId"))
        decision = payload.get("decision")
        if decision not in {"allow", "deny"}:
            raise WebError("INVALID_REQUEST", "decision 必须是 allow 或 deny", status=400)
        approval_id = str(approval_id or "").strip()
        op_payload = {
            "op": "approve",
            "sessionId": session.meta["id"],
            "approvalId": approval_id,
            "decision": decision,
            "value": payload.get("value"),
        }
        with self._request_scope(request_id, op_payload, session) as replay:
            if replay is not None:
                with replay.lock:
                    return replay.detail_view()
            driver = session.driver
            if driver is None or not driver.alive():
                raise WebError("SESSION_NOT_ACTIVE", "会话进程已退出，无法处理审批", status=409)
            with session.lock:
                if approval_id not in session.approvals:
                    raise WebError("APPROVAL_NOT_FOUND", "该审批不存在或已被处理", status=404)
            try:
                if payload.get("value") is not None:
                    driver.respond_ui(approval_id, decision, payload["value"])
                else:
                    driver.respond_ui(approval_id, decision)
            except DriverClosedError as exc:
                raise WebError("SESSION_NOT_ACTIVE", "会话进程已退出，无法处理审批", status=409) from exc
            with session.lock:
                session.persist(self._state_dir)
                return session.detail_view()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            sessions = list(self._sessions.values())
        for session in sessions:
            with session.lock:
                session.stop_requested = True
                driver = session.driver
            if driver is not None:
                try:
                    driver.close()
                except Exception:
                    pass
            with session.lock:
                session.persist(self._state_dir)

    # -- internals: request idempotency --------------------------------

    @contextmanager
    def _request_scope(
        self, request_id: str, op_payload: dict, owner: _LiveSession | None = None
    ) -> Iterator[_LiveSession | None]:
        """Reserve requestId, yield the replayed session (or None), confirm on success.

        A failed mutation releases the reservation so the same requestId can be
        retried after an error. Confirmed requests replay forever (persisted).
        """
        fingerprint = _fingerprint(op_payload)
        with self._lock:
            self._require_open()
            existing = self._requests.get(request_id)
            if existing is not None:
                replay_session = self._sessions.get(existing.get("sessionId") or "")
                registered = existing.get("fingerprint")
                if registered is not None and registered != fingerprint:
                    raise WebError(
                        "REQUEST_ID_CONFLICT",
                        "requestId 已被其他操作使用，请更换 requestId",
                        status=409,
                    )
                if replay_session is None:
                    raise WebError("REQUEST_PENDING", "启动仍在处理中，请稍后重试同一请求。", 425)
                yield replay_session
                return
            self._requests[request_id] = {
                "sessionId": owner.meta["id"] if owner is not None else None,
                "op": op_payload.get("op"),
                "fingerprint": fingerprint,
                "pending": True,
            }
        try:
            yield None
        except BaseException as exc:
            with self._lock:
                entry = self._requests.get(request_id)
                if isinstance(exc, WebError) and exc.code == "RPC_TIMEOUT" and owner is not None:
                    # A timed-out command may already have run. Never send it twice.
                    if entry is not None:
                        entry["pending"] = False
                    with owner.lock:
                        owner.request_log[request_id] = fingerprint
                        owner.persist(self._state_dir)
                elif entry is not None and entry.get("pending"):
                    self._requests.pop(request_id, None)
            raise
        with self._lock:
            entry = self._requests.get(request_id)
            if entry is not None:
                entry["pending"] = False
                session = self._sessions.get(entry.get("sessionId") or "")
                if session is not None:
                    with session.lock:
                        if session.request_log.get(request_id) != fingerprint:
                            session.request_log[request_id] = fingerprint
                            session.persist(self._state_dir)

    # -- internals: launch ----------------------------------------------

    def _do_launch(self, payload: dict, request_id: str, op_payload: dict) -> tuple[dict, _LiveSession]:
        if not self.capabilities()["launch"]:
            raise WebError("CAPABILITY_UNAVAILABLE", "当前环境未启用真实 Pi 会话启动", status=409)
        if payload.get("thinkingLevel") is not None and payload["thinkingLevel"] not in ("off", "minimal", "low", "medium", "high", "xhigh", "max"):
            raise WebError("INVALID_PARAMETER", "请选择有效的 effort。", 400)
        if not isinstance(payload.get("planMode", False), bool):
            raise WebError("INVALID_PARAMETER", "请选择规划或执行模式。", 400)
        workspace_id = str(payload.get("workspaceId") or "").strip()
        preset_id = str(payload.get("presetId") or "").strip()
        if not workspace_id or not preset_id:
            raise WebError("INVALID_REQUEST", "workspaceId 与 presetId 必填", status=400)

        try:
            resolved = self._catalog.resolve_launch(preset_id, workspace_id)
        except WebError:
            raise
        except Exception as exc:
            raise WebError("LAUNCH_RESOLVE_FAILED", "无法解析所选启动组合", status=400) from exc
        if not isinstance(resolved, dict):
            raise WebError("LAUNCH_RESOLVE_FAILED", "无法解析所选启动组合", status=400)
        harness = str(resolved.get("harness") or "").strip()
        if harness != "pi":
            raise WebError(
                "CAPABILITY_UNAVAILABLE",
                f"harness {harness or '?'} 暂不支持 Web rich 会话，当前仅支持 pi",
                status=409,
            )
        model_info = resolved.get("modelInfo") or resolved.get("model_info")
        runtime = resolved.get("runtime") if isinstance(resolved.get("runtime"), dict) else {}
        cwd = str(resolved.get("cwd") or "") or str(self._state_root)
        skill_text, selected_skills = self.skills.prepare(payload.get("skills", []), workspace_id)
        options = resolved.get("launchOptions") or {}
        from .recipe_requirements import validate_requirements
        validate_requirements(payload.get("recipeRequirements"), options.get("model") or {}, selected_skills)
        effort = payload.get("thinkingLevel") or options.get("defaultThinkingLevel")
        if effort and options and effort not in options.get("supportedThinkingLevels", []):
            raise WebError("EFFORT_UNSUPPORTED", "这条通道不支持所选 effort，请重新选择。", 409)

        try:
            plan = self._launch_plan_builder(harness, model_info, runtime, cwd)
        except (LaunchSeamUnavailable, DriverClosedError) as exc:
            raise WebError("CAPABILITY_UNAVAILABLE", f"Pi 启动接缝不可用: {exc}", status=409)
        if plan is None:
            raise WebError("CAPABILITY_UNAVAILABLE", "无法为该组合构建启动计划", status=409)

        title = str(payload.get("title") or "").strip()
        prompt = payload.get("prompt") or ("请查看附件。" if payload.get("attachments") else "")
        if prompt is not None and not isinstance(prompt, str):
            raise WebError("INVALID_REQUEST", "prompt 必须是字符串", status=400)
        images, attachments, suffix = self.files.prepare(payload.get("attachments", []), workspace_id, payload.get("references", []))
        suffix += skill_text
        material_text, materials = self.materials.prepare(workspace_id)
        suffix += material_text
        from .project_materials import usage_record
        context = usage_record(cwd, selected_skills, attachments, payload.get("references", []), [], materials, payload.get("skillInvocation"))
        context["promptSha256"] = prompt_hash(prompt + suffix)
        if not title:
            title = _clip(str(prompt or "").strip() or "Pi 会话", 60)

        session_id = f"s-{uuid.uuid4().hex[:12]}"
        meta = self._build_meta(session_id, harness, workspace_id, title, model_info, runtime)
        meta.update(cwd=cwd, presetId=preset_id)
        if runtime.get("_webConfigRoot"):
            meta["runtimeRoot"] = runtime["_webConfigRoot"]
            from .runtime import private_json
            private_json(Path(runtime["_webConfigRoot"]) / "resume.json",
                         {"modelInfo": model_info, "runtime": runtime, "cwd": cwd})
        live = _LiveSession(meta, self._state_root)
        live.state = "running" if prompt else "idle"

        sink = _DriverSink(self, live)
        try:
            driver = self._spawn_driver(plan, sink)
        except FileNotFoundError as exc:
            raise WebError("LAUNCH_FAILED", "Pi 可执行文件不存在", status=502) from exc
        except (OSError, DriverClosedError) as exc:
            raise WebError("LAUNCH_FAILED", "Pi 子进程无法启动", status=502) from exc
        live.driver = driver
        if runtime.get("_webConfigRoot"):
            try:
                state = driver.get_state()
                if not state.get("model"):
                    raise DriverClosedError("Pi 没有加载所选模型")
            except (DriverClosedError, RpcTimeoutError):
                driver.close(graceful_timeout=0.5)
                diagnostic = str(getattr(driver, "_stderr_tail", ""))
                for secret in live.secrets:
                    diagnostic = diagnostic.replace(secret, "[已隐藏密钥]")
                private_json(Path(runtime["_webConfigRoot"]) / "launch-stderr.json", {"stderr": diagnostic})
                raise WebError("LAUNCH_FAILED", "MMS 未能启动所选模型，请检查本机 Pi 和模型服务。", 502)
        try:
            if effort:
                from .launch_options import set_thinking
                set_thinking(self, live, effort)
            self._check_images(live, images)
            if payload.get("planMode") is True:
                self._require_plan_control(live)
                self._rpc(live, {"type": "prompt", "message": "/mms-web-plan on"})
        except WebError:
            driver.close(graceful_timeout=0.5)
            raise
        with self._lock:
            self._sessions[session_id] = live
            self._requests[request_id]["sessionId"] = session_id
        live.append_event(
            {
                "id": f"n-launch-{session_id}",
                "kind": "notice",
                "text": "会话已通过 MMS 启动路径创建",
                "title": "session",
            },
            self._now,
        )
        if prompt:
            try:
                event = live.append_event({"kind": "user", "text": prompt, "skills": selected_skills, "attachments": attachments, "references": payload.get("references", []), "contextUsage": context}, self._now)
                self._send_prompt(live, prompt + suffix, images=images)
                context["state"] = "submitted" if live.driver else "prepared"
            except WebError as exc:
                context["state"] = "uncertain" if exc.code in {"RPC_TIMEOUT", "RPC_UNCONFIRMED"} else "failed"
                event["status"] = "error"
                live.append_event({"kind": "notice", "text": exc.message, "status": "error"}, self._now)
        with live.lock:
            live.persist(self._state_dir)
            return live.detail_view(), live

    def _spawn_driver(self, plan, sink: _DriverSink):
        if self._driver_factory is not None:
            return self._driver_factory(plan, sink)
        process = self._process_launcher.popen(plan.cmd, env=plan.env, cwd=plan.cwd)
        return PiRpcDriver(process, sink, name=str(plan.harness))

    def _check_images(self, session, images):
        if images and "image" not in (session.driver.get_state().get("model") or {}).get("input", []):
            raise WebError("IMAGE_UNSUPPORTED", "当前模型不支持图片。请切换到支持图片的模型，或移除图片后重试。", 409)

    def _send_prompt(self, session: _LiveSession, text: str, *, images=None) -> None:
        driver = session.driver
        if driver is None:
            return
        try:
            response = driver.send_prompt(text, images=images) if images else driver.send_prompt(text)
        except DriverWriteUnconfirmedError as exc:
            raise WebError("RPC_UNCONFIRMED", "Pi 连接在写入过程中断开，发送结果待确认。请先查看会话记录。", status=502) from exc
        except DriverClosedError as exc:
            raise WebError("SESSION_NOT_ACTIVE", "会话进程已退出，消息未发送", status=409) from exc
        except RpcTimeoutError as exc:
            raise WebError("RPC_TIMEOUT", "Pi 未在超时内确认消息", status=504) from exc
        if response.get("deliveryUnconfirmed") is True:
            raise WebError("RPC_UNCONFIRMED", "Pi 在确认前断开，发送结果待确认。请先查看会话记录。", status=502)
        if response.get("success") is False:
            raise WebError("SEND_FAILED", "Pi 未接受该消息，请检查所选服务连接后重试。", status=502)

    # -- internals: driver callbacks -------------------------------------

    def _apply_driver_event(self, session: _LiveSession, fields: dict) -> None:
        if not isinstance(fields, dict):
            return
        with session.lock:
            if isinstance(fields.get("nativeContext"), dict):
                session.meta["contextEvidence"] = redact(fields["nativeContext"], session.secrets)
                session.persist(self._state_dir)
                return
            if isinstance(fields.get("consumedPrompt"), str):
                prompt = fields["consumedPrompt"]
                event_id = consume_prompt(session, prompt)
                if event_id in session.pending_prompts:
                    session.pending_prompts.pop(event_id, None)
                    event = session.event_index[event_id]
                    event.pop("status", None)
                    session.events.remove(event)
                    session.last_sequence += 1
                    event["sequence"] = session.last_sequence
                    session.events.append(event)
                session.persist(self._state_dir)
                return
            fields = copy.deepcopy(fields)
            event_id = str(fields.get("id") or "")
            existing = session.event_index.get(event_id, {})
            for name in ("text", "thinking"):
                tail_key = (event_id, name)
                if name in fields:
                    session.stream_tails.pop(tail_key, None)
                elif name + "Append" in fields:
                    # Never publish a suffix that could become a known secret
                    # when the next delta arrives. Tails live in memory only.
                    value = str(existing.get(name) or "") + session.stream_tails.pop(tail_key, "") + str(fields.pop(name + "Append"))
                    value = redact(value, session.secrets)
                    keep = max((n for secret in session.secrets for n in range(1, min(len(secret), len(value) + 1))
                                if value.endswith(secret[:n])), default=0)
                    if keep:
                        session.stream_tails[tail_key] = value[-keep:]
                        value = value[:-keep]
                    fields[name] = value
            fields = redact(fields, session.secrets)
            if fields.get("kind") == "assistant":
                fields.setdefault("modelName", session.meta.get("modelName", ""))
            if isinstance(fields.get("planning"), bool):
                session.meta["planning"] = fields["planning"]
                session.persist(self._state_dir)
                return
            media = fields.pop("media", [])
            if media:
                fields["attachments"] = []
                for index, item in enumerate(media[:8]):
                    try:
                        fields["attachments"].append(self.files.upload({"name": f"{fields.get('title', '工具')} 图片 {index + 1}", "data": item.get("data", "")}))
                    except WebError:
                        fields["text"] = fields.get("text", "") + "\n图片超过预览限制或格式不支持。"
            if isinstance(fields.get("queue"), list):
                session.meta["queue"] = fields["queue"]
            event = session.upsert_event(fields, self._now)
            observe_read(session, event)
            if session.artifact_history:
                session.artifact_history.secrets = session.secrets
                session.artifact_history.observe(event, self._now())
            session.persist(self._state_dir)

    def _apply_proto_state(self, session: _LiveSession, state: str) -> None:
        with session.lock:
            if state not in _PROTO_STATES:
                return
            if not session.alive():
                return
            if state in {"idle", "running"} and session.approvals:
                state = "waiting"
            session.state = state
            if state == "idle":
                session.finish_pending_tools()
                session.activity = None
                session.turn_started_at = None
            elif state == "running":
                session.turn_started_at = session.turn_started_at or self._now()
            session.updated_at = self._now()
            session.persist(self._state_dir)

    def _apply_activity(self, session: _LiveSession, phase: str, details: dict) -> None:
        if phase not in {"running", "thinking", "responding", "tool", "compacting", "retrying", "error", "stopped", "idle"}:
            return
        with session.lock:
            if session.finalized or session.state in _FINAL_STATES:
                return
            value = {"phase": phase, **{key: str(details[key])[:120] for key in ("eventId", "toolName") if details.get(key)}}
            value = redact(value, session.secrets)
            if session.activity and all(session.activity.get(k) == value.get(k) for k in ("phase", "eventId", "toolName")):
                return
            session.activity = None if phase == "idle" else {
                **value, "since": self._now(), "turnStartedAt": session.turn_started_at,
            }
            session.updated_at = self._now()
            session.persist(self._state_dir)

    def _apply_approval_pending(self, session: _LiveSession, approval_id: str, method: str, title: str) -> None:
        with session.lock:
            session.approvals[approval_id] = {"method": method, "title": title}
            if session.alive():
                session.state = "waiting"
            session.updated_at = self._now()
            session.persist(self._state_dir)

    def _apply_approval_resolved(self, session: _LiveSession, approval_id: str, decision: str) -> None:
        with session.lock:
            session.approvals.pop(approval_id, None)
            if not session.approvals and session.alive():
                session.state = "running"
            session.updated_at = self._now()
            session.persist(self._state_dir)

    def _apply_process_exited(self, session: _LiveSession, exit_code: int, stderr_tail: str) -> None:
        with session.lock:
            session.approvals.clear()
            session.finalized = True
            if session.stop_requested:
                final_state = "stopped"
            elif exit_code == 0:
                final_state = "completed"
            else:
                final_state = "error"
            session.state = final_state
            session.finish_pending_tools()
            session.activity = None
            session.turn_started_at = None
            notice = f"Pi 进程已退出 (exit {exit_code})"
            lines = [line for line in str(stderr_tail or "").strip().splitlines() if line.strip()]
            if exit_code != 0:
                notice += "，请检查所选模型服务与本机运行环境。"
            session.upsert_event(
                {"id": f"n-exit-{session.meta['id']}", "kind": "notice", "text": notice, "title": "lifecycle"},
                self._now,
            )
            session.persist(self._state_dir)

    # -- internals -------------------------------------------------------

    def _require_open(self) -> None:
        if self._closed:
            raise WebError("SERVICE_CLOSED", "会话服务已关闭", status=503)

    def _get(self, session_id: str) -> _LiveSession:
        with self._lock:
            session = self._sessions.get(str(session_id or ""))
        if session is None:
            raise WebError("SESSION_NOT_FOUND", "会话不存在", status=404)
        return session

    def _object_payload(self, payload) -> dict:
        if not isinstance(payload, dict):
            raise WebError("INVALID_REQUEST", "payload must be an object", status=400)
        return payload

    def _validate_request_id(self, value) -> str:
        request_id = str(value or "").strip()
        if not _REQUEST_ID_RE.match(request_id):
            raise WebError(
                "INVALID_REQUEST", "requestId 必须是 1-128 位的字母数字及 ._-: 字符", status=400
            )
        return request_id

    def _build_meta(
        self,
        session_id: str,
        harness: str,
        workspace_id: str,
        title: str,
        model_info,
        runtime: dict,
    ) -> dict:
        if isinstance(model_info, dict):
            model_name = str(
                model_info.get("model")
                or model_info.get("name")
                or (model_info.get("sonnet") if isinstance(model_info.get("sonnet"), str) else "")
                or runtime.get("model")
                or ""
            )
        elif model_info:
            model_name = str(model_info)
        else:
            model_name = str(runtime.get("model") or "")
        provider_name = str(runtime.get("name") or runtime.get("id") or "")
        channel = str(runtime.get("channel") or runtime.get("mode") or "default")
        return {
            "id": session_id,
            "title": title,
            "workspaceId": workspace_id,
            "harness": harness,
            "modelName": model_name,
            "providerName": provider_name,
            "channel": str(runtime.get("route_provider_id") or runtime.get("id") or channel),
            "owner": "web",
            "createdAt": self._now(),
            "updatedAt": self._now(),
        }

    # -- persistence ------------------------------------------------------

    def _load_persisted(self) -> None:
        if not self._state_dir.is_dir():
            return
        for path in sorted(self._state_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict) or payload.get("schema") != 1:
                continue
            meta = payload.get("session")
            if not isinstance(meta, dict) or not meta.get("id"):
                continue
            live = _LiveSession(dict(meta), self._state_root)
            live.events = [e for e in (payload.get("events") or []) if isinstance(e, dict)]
            for event in live.events:
                if event.get("kind") == "user" and event.get("status") == "queued":
                    event["status"] = "cancelled"
            live.finish_pending_tools()
            live.event_index = {e["id"]: e for e in live.events if e.get("id")}
            live.last_sequence = int(payload.get("lastSequence") or len(live.events) or 0)
            live.approvals = {
                k: v for k, v in dict(payload.get("approvals") or {}).items() if isinstance(v, dict)
            }
            live.stop_requested = bool(payload.get("stopRequested"))
            live.request_log = {
                k: v for k, v in dict(payload.get("requestLog") or {}).items() if isinstance(v, str)
            }
            live.updated_at = str(payload.get("updatedAt") or _now_iso())
            state = str(payload.get("state") or "")
            if state in _FINAL_STATES:
                live.state = state
            else:
                # After a service restart the child is gone; never pretend it runs.
                live.state = "stopped"
            self._sessions[live.meta["id"]] = live
            for request_id, fingerprint in live.request_log.items():
                self._requests[request_id] = {
                    "sessionId": live.meta["id"],
                    "op": None,
                    "fingerprint": fingerprint,
                }
