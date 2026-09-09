"""Explicit model changes in one Web conversation, preserving Pi native history."""
import copy
import json
import shutil
import threading
from pathlib import Path

from .errors import WebError
from .drivers.base import DriverClosedError, RpcTimeoutError
from .runtime import private_json, require_private_root


class DeferredSink:
    """A candidate process cannot publish state before the switch commits."""
    def __init__(self):
        self.lock = threading.RLock()
        self.active = True
        self.target = None
        self.pending = []

    def __getattr__(self, method):
        if method not in {"upsert_event", "set_proto_state", "set_activity", "approval_pending", "approval_resolved", "process_exited"}:
            raise AttributeError(method)
        def forward(*args, **kwargs):
            with self.lock:
                if not self.active:
                    return
                if self.target:
                    getattr(self.target, method)(*args, **kwargs)
                else:
                    self.pending.append((method, args, kwargs))
        return forward

    def activate(self, target):
        with self.lock:
            self.target = target
            for method, args, kwargs in self.pending:
                getattr(target, method)(*args, **kwargs)
            self.pending.clear()


def rpc(driver, command):
    result = driver.request(command, timeout=8)
    if not result.get("success"):
        # Provider/runtime responses can contain credentials. Only return a
        # stable public message; raw diagnostics stay inside the private runtime.
        raise WebError("MODEL_SWITCH_FAILED", "Pi 未能切换到所选模型，原选择已保留。", 409)
    return result.get("data") or {}


def route_identity(runtime):
    return {k: v for k, v in runtime.items() if not k.startswith("_web") and
            (k in {"id", "mode"} or any(part in k.lower() for part in
             ("key", "url", "header", "auth", "provider", "protocol", "profile", "affinity")))}


def verify(driver, target, effort):
    state = rpc(driver, {"type": "get_state"})
    model = state.get("model") or {}
    if model.get("id") != target["modelId"] or model.get("provider") != target["provider"]:
        raise WebError("MODEL_NOT_APPLIED", "执行进程未采用所选模型，切换没有完成。", 409)
    if effort and state.get("thinkingLevel") != effort:
        raise WebError("EFFORT_NOT_APPLIED", "执行进程未采用新模型的 effort，切换没有完成。", 409)
    return state


def apply_native(driver, target, effort):
    previous = rpc(driver, {"type": "get_state"})
    try:
        rpc(driver, {"type": "set_model", **target})
        if effort:
            rpc(driver, {"type": "set_thinking_level", "level": effort})
        return verify(driver, target, effort)
    except Exception:
        old = previous.get("model") or {}
        try:
            original = {"provider": old["provider"], "modelId": old["id"]}
            rpc(driver, {"type": "set_model", **original})
            rpc(driver, {"type": "set_thinking_level", "level": previous["thinkingLevel"]})
            verify(driver, original, previous["thinkingLevel"])
        except Exception:
            driver.close(graceful_timeout=0.5)
        raise


def switch_model(service, session_id, payload):
    service._require_open()
    session = service._get(session_id)
    payload = service._object_payload(payload)
    preset = payload.get("presetId")
    if not isinstance(preset, str) or not preset:
        raise WebError("INVALID_PARAMETER", "请选择模型与通道。", 400)
    request_id = service._validate_request_id(payload.get("requestId"))
    operation = {"op": "switch-model", "sessionId": session_id, "presetId": preset}
    with session.mutation_lock, service._request_scope(request_id, operation, session) as replay:
        if replay is not None:
            return service.get_session(session_id)
        if session.state in {"running", "waiting"}:
            raise WebError("SESSION_BUSY", "请等待本轮完成，或先停止本轮，再切换模型。", 409)
        if session.meta.get("harness") != "pi" or not session.meta.get("runtimeRoot"):
            raise WebError("MODEL_SWITCH_UNAVAILABLE", "该会话不支持切换模型。", 409)
        root = require_private_root(Path(session.meta["runtimeRoot"]))
        if not root.is_relative_to((service._state_root / "runtimes").resolve()):
            raise WebError("INVALID_SESSION", "会话运行目录无效。", 409)
        saved = json.loads((root / "resume.json").read_text())
        resolved = service._catalog.resolve_launch(preset, session.meta["workspaceId"])
        if resolved.get("harness") != "pi" or not resolved.get("piModel"):
            raise WebError("MODEL_SWITCH_UNAVAILABLE", "请选择支持 Pi 的模型通道。", 409)
        target = resolved["piModel"]
        effort = resolved.get("launchOptions", {}).get("defaultThinkingLevel")
        driver = session.driver
        available = rpc(driver, {"type": "get_available_models"}).get("models", []) if session.alive() else []
        native = session.alive() and route_identity(saved["runtime"]) == route_identity(resolved["runtime"]) and any(
            m.get("id") == target["modelId"] and m.get("provider") == target["provider"] for m in available)
        runtime = copy.deepcopy(resolved["runtime"])
        if native:
            next_root = root
            runtime["_webConfigRoot"] = str(next_root)
            # Persist before changing the live process. A disk failure must
            # leave the currently selected model untouched.
            try:
                private_json(root / "resume.json", {"modelInfo": resolved["modelInfo"], "runtime": runtime, "cwd": saved["cwd"]})
                state = apply_native(driver, target, effort)
            except Exception as exc:
                private_json(root / "resume.json", saved)
                if isinstance(exc, WebError):
                    raise
                raise WebError("MODEL_SWITCH_FAILED", "切换没有完成，原模型和上下文已保留。", 409) from exc
        else:
            try:
                driver, sink, state, next_root = prepare_runtime(service, session, resolved, root, target, effort)
                runtime["_webConfigRoot"] = str(next_root)
            except WebError:
                raise
            except Exception as exc:
                raise WebError("MODEL_SWITCH_FAILED", "新模型未就绪，原会话和上下文已保留。", 409) from exc
        if not native:
            old_driver = session.driver
            if old_driver:
                old_sink = getattr(old_driver, "_sink", None)
                if old_sink:
                    old_sink.active = False
                old_driver.close(graceful_timeout=0.5)
            session.driver = driver
        with session.lock:
            for event in session.events:
                if event.get("kind") == "assistant":
                    event.setdefault("modelName", session.meta.get("modelName", ""))
            meta = service._build_meta(session_id, "pi", session.meta["workspaceId"], session.meta["title"], resolved["modelInfo"], runtime)
            session.meta.update({key: meta[key] for key in ("modelName", "providerName", "channel")})
            session.meta.update(presetId=preset, runtimeRoot=str(next_root))
            session.secrets.extend(str(v) for k, v in runtime.items() if "key" in k.lower() and isinstance(v, str) and v)
            session.meta.setdefault("controlSettings", {})["thinking"] = state.get("thinkingLevel")
            session.meta["runtimeView"] = {}
            session.runtime_checked = 0
            session.finalized = False
            session.stop_requested = False
            session.state = "idle"
            session.activity = None
            session.append_event({"kind": "notice", "title": "模型", "text": f"已切换为 {meta['modelName']} · {meta['channel']}，继续使用当前对话。"}, service._now)
            session.persist(service._state_dir)
        if not native:
            from .sessions import _DriverSink
            sink.activate(_DriverSink(service, session))
    return service.get_session(session_id)


def prepare_runtime(service, session, resolved, old_root, target, effort):
    next_root = require_private_root(Path(resolved["runtime"]["_webConfigRoot"]))
    if not next_root.is_relative_to((service._state_root / "runtimes").resolve()):
        raise WebError("INVALID_SESSION", "新运行目录无效。", 409)
    history = old_root / "conversation.jsonl"
    if history.is_file():
        shutil.copyfile(history, next_root / "conversation.jsonl")
        (next_root / "conversation.jsonl").chmod(0o600)
    plan = service._launch_plan_builder("pi", resolved["modelInfo"], resolved["runtime"], session.meta["cwd"])
    sink = DeferredSink()
    driver = service._spawn_driver(plan, sink)
    try:
        # Native session history is loaded first. Explicit set_model ensures a
        # model-change entry is recorded even if Pi restored the old selection.
        state = apply_native(driver, target, effort)
        for key, command in (("autoCompaction", "set_auto_compaction"), ("autoRetry", "set_auto_retry")):
            if key in session.meta.get("controlSettings", {}):
                rpc(driver, {"type": command, "enabled": session.meta["controlSettings"][key]})
        private_json(next_root / "resume.json", {"modelInfo": resolved["modelInfo"], "runtime": resolved["runtime"], "cwd": session.meta["cwd"]})
        if not driver.alive():
            raise DriverClosedError("candidate exited")
        return driver, sink, state, next_root
    except Exception:
        driver.close(graceful_timeout=0.5)
        raise
