"""Pilot ``/btw`` side-question backend (session-owned, read-only).

A side question never becomes a main turn. Rows are stored beside the
transcript, not inside it: asking one does not append main events, does not
enter the follow-up queue, does not call the driver, and does not change
model, channel or effort. Two answer sources exist:

- ``state``: a deterministic answer built from the session snapshot (phase,
  duration, recent tools, queue, approvals, errors). Always available, even
  after the main process exited, and authoritative about *observed* state.
- ``completion``: one read-only request on the session's own route, or a
  runner the host injected as ``sidecar_runner``. Either way it receives only
  a budgeted, redacted context snapshot plus a cancel event, and must never
  touch the workspace, the main transcript, approvals or the driver. When no
  route and no runner can answer, the capability fails closed: the question is
  recorded as ``failed`` with a visible reason, and the main task is
  untouched.

Lifecycle: ``prepared -> accepted -> running -> completed | failed |
cancelled | uncertain``. ``accepted`` means recorded, not answered; updates
arrive through the side-question API, not the main event stream. A service
restart marks rows that were in flight ``cancelled`` (the worker is provably
gone); ``close()`` marks them ``uncertain`` because the sidecar outcome was
never recorded. Finished rows survive stop, resume, refresh and upgrade.
"""

from __future__ import annotations

import copy
import re
import threading
import uuid
from datetime import datetime
from typing import Any

from .errors import WebError

BTW_FINAL_STATES = {"completed", "failed", "cancelled", "uncertain"}
BTW_SOURCES = {"state", "completion"}

_MAX_QUESTION = 2000
_MAX_ANSWER = 20000
_MAX_CONTEXT_TEXT = 500
_MAX_CONTEXT_ITEMS = 8
_IDEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MASK = "[已隐藏密钥]"

# Questions about observed state are answered from the snapshot, not the model.
_STATE_HINTS = (
    "进度", "状态", "哪一步", "进行到哪", "在做什么", "在干什", "多久",
    "运行了", "还在跑", "审批", "等待", "队列", "为什么还没", "卡住",
)

_STATE_LABELS = {
    "running": "正在运行",
    "idle": "空闲",
    "waiting": "正在等待审批",
    "completed": "已完成",
    "stopped": "已停止",
    "error": "出错停止",
}


def _redact_counted(value: Any, secrets: list[str]) -> tuple[Any, int]:
    """redact() with a replacement count for the redaction summary."""
    count = 0

    def walk(item: Any) -> Any:
        nonlocal count
        if isinstance(item, str):
            for secret in secrets or []:
                hits = item.count(secret)
                if hits:
                    count += hits
                    item = item.replace(secret, _MASK)
            return item
        if isinstance(item, list):
            return [walk(entry) for entry in item]
        if isinstance(item, dict):
            return {key: walk(entry) for key, entry in item.items()}
        return item

    return walk(value), count


def public_side_question(row: dict) -> dict:
    """The API view: internal bookkeeping and idempotency keys stay inside."""
    return {
        key: copy.deepcopy(value)
        for key, value in row.items()
        if not str(key).startswith("_") and key != "idempotencyKey"
    }


def _looks_like_state(question: str) -> bool:
    return any(hint in question for hint in _STATE_HINTS)


def _route_snapshot(session) -> dict:
    meta = session.meta
    controls = meta.get("controlSettings") or {}
    return {
        "modelName": meta.get("modelName") or "",
        "providerName": meta.get("providerName") or "",
        "channel": meta.get("channel") or "",
        "thinking": str(controls.get("thinking") or ""),
    }


def _parse_iso(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _duration_text(now_iso: str, started_iso: Any) -> str:
    start, end = _parse_iso(started_iso), _parse_iso(now_iso)
    if start is None or end is None:
        return ""
    seconds = max(0, int((end - start).total_seconds()))
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds // 60} 分钟"
    return f"{seconds // 3600} 小时 {seconds % 3600 // 60} 分钟"


class SessionSideQuestions:
    """SessionService mixin implementing the /btw side-question contract.

    Expects the host to provide ``_get``, ``_require_open``, ``_now``,
    ``_state_dir``, ``_object_payload``, ``_sidecar_runner_for`` and
    per-session locks, and to initialise ``self._sidecar_runner``,
    ``self._btw_timeout``, ``self._btw_timers`` and ``self._btw_cancel``.
    """

    # -- reads ------------------------------------------------------

    def list_side_questions(self, session_id: str) -> list[dict]:
        session = self._get(session_id)
        with session.lock:
            rows = sorted(
                session.side_questions.values(), key=lambda row: row.get("createdAt") or ""
            )
            return [public_side_question(row) for row in rows]

    def get_side_question(self, session_id: str, btw_id: str) -> dict:
        session = self._get(session_id)
        with session.lock:
            row = session.side_questions.get(str(btw_id or ""))
            if row is None:
                raise WebError("BTW_NOT_FOUND", "这条旁问不存在。", 404)
            return public_side_question(row)

    # -- create -----------------------------------------------------

    def ask_side_question(self, session_id: str, payload: dict) -> dict:
        self._require_open()
        session = self._get(session_id)
        payload = self._object_payload(payload)
        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            raise WebError("INVALID_REQUEST", "请输入旁问内容。", 400)
        question, masked_question = _redact_counted(question.strip()[:_MAX_QUESTION], session.secrets)
        hint = payload.get("sourceHint")
        if hint is not None and hint not in BTW_SOURCES:
            raise WebError("INVALID_PARAMETER", "sourceHint 必须是 state 或 completion。", 400)
        key = str(payload.get("idempotencyKey") or "").strip()
        if key and not _IDEM_RE.match(key):
            raise WebError("INVALID_REQUEST", "idempotencyKey 格式无效。", 400)
        with session.lock:
            if key and key in session.btw_idem:
                # Idempotent replay: the same key returns the original row.
                return public_side_question(session.side_questions[session.btw_idem[key]])
            now = self._now()
            row = {
                "btwId": f"btw-{uuid.uuid4().hex[:12]}",
                "mainSessionId": session.meta["id"],
                "owner": "sidecar",
                "question": question,
                "status": "accepted",
                "answer": None,
                "source": hint or ("state" if _looks_like_state(question) else "completion"),
                "contextRevision": f"r-{session.last_sequence}",
                "routeSnapshot": _route_snapshot(session),
                "usage": None,
                "redactionSummary": {"secretsMasked": masked_question},
                "error": None,
                "createdAt": now,
                "acceptedAt": now,
                "startedAt": None,
                "completedAt": None,
            }
            session.side_questions[row["btwId"]] = row
            if key:
                session.btw_idem[key] = row["btwId"]
            session.persist(self._state_dir)
        if row["source"] == "state":
            self._answer_from_state(session, row)
        else:
            self._answer_from_completion(session, row)
        return self.get_side_question(session.meta["id"], row["btwId"])

    # -- cancel -------------------------------------------------------

    def cancel_side_question(self, session_id: str, btw_id: str) -> dict:
        self._require_open()
        session = self._get(session_id)
        with session.lock:
            row = session.side_questions.get(str(btw_id or ""))
            if row is None:
                raise WebError("BTW_NOT_FOUND", "这条旁问不存在。", 404)
            if row["status"] in BTW_FINAL_STATES:
                # Already settled: cancel is an idempotent no-op, not an error.
                return public_side_question(row)
        cancel = self._btw_cancel.get(row["btwId"])
        if cancel is not None:
            cancel.set()
        self._btw_finish(session, row, "cancelled", error="旁问已取消。")
        return self.get_side_question(session.meta["id"], row["btwId"])

    # -- state source -------------------------------------------------

    def _answer_from_state(self, session, row: dict) -> None:
        try:
            with session.lock:
                row["status"] = "running"
                row["startedAt"] = self._now()
                answer = self._state_answer(session, row["question"], row["contextRevision"])
        except Exception:
            self._btw_finish(session, row, "failed", error="读取会话状态失败，主任务不受影响。")
            return
        answer, masked = _redact_counted(answer, session.secrets)
        self._btw_finish(session, row, "completed", answer=answer[:_MAX_ANSWER], extra_masked=masked)

    def _state_answer(self, session, question: str, revision: str) -> str:
        """Deterministic answer from the session snapshot. Holds session.lock."""
        parts = [f"当前状态：{_STATE_LABELS.get(session.state, session.state)}。"]
        if session.state in {"running", "waiting"} and session.turn_started_at:
            duration = _duration_text(self._now(), session.turn_started_at)
            if duration:
                parts.append(f"本轮已进行 {duration}。")
        activity = session.activity_view()
        if session.state == "waiting":
            pending = next(iter(session.approvals.values()), {})
            method = pending.get("method", "confirm")
            title = pending.get("title") or ""
            parts.append(
                f"正在等待审批：{method}" + (f"「{title}」。" if title else "。")
                + "旁问只能查看，不能代替批准或拒绝；请在主任务中处理。"
            )
        elif activity:
            phase = activity.get("phase", "")
            tool = activity.get("toolName")
            parts.append(f"当前动作：{phase}" + (f"（工具 {tool}）。" if tool else "。"))
        queued = len(session.pending_prompts) + len(session.meta.get("queue") or [])
        if queued:
            parts.append(f"待发送队列：{queued} 条。")
        tools = [event for event in session.events if event.get("kind") == "tool"]
        if tools:
            recent = "、".join(
                f"{event.get('title') or '工具'}（{event.get('status') or '未知'}）"
                for event in tools[-3:]
            )
            parts.append(f"最近工具：{recent}。")
        errors = [
            event for event in session.events
            if event.get("kind") == "notice" and event.get("status") == "error"
        ]
        if session.state == "error" and errors:
            parts.append(f"最近错误：{str(errors[-1].get('text') or '')[:200]}")
        snapshot = _route_snapshot(session)
        route = " · ".join(part for part in (snapshot["modelName"], snapshot["providerName"], snapshot["channel"]) if part)
        if route:
            parts.append(f"模型：{route}。")
        parts.append(f"这是基于会话状态快照（{revision}）的回答，旁问没有读取主任务的全部上下文。")
        return "".join(parts)

    # -- completion source --------------------------------------------

    def _answer_from_completion(self, session, row: dict) -> None:
        # Per session, not per service: the read-only answer runs on the route
        # this session already launched with, so a host that injects nothing
        # still gets the session's own model rather than no model at all.
        runner = self._sidecar_runner_for(session)
        if not callable(runner):
            # Fail closed: the capability is absent, so the row records a
            # visible failure instead of silently degrading to a state answer
            # or touching the main agent loop.
            self._btw_finish(
                session, row, "failed",
                error="这条会话没有可用于只读旁问模型的路由或凭据，未发送任何请求。主任务不受影响。",
            )
            return
        with session.lock:
            row["status"] = "running"
            row["startedAt"] = self._now()
            context, masked = _redact_counted(self._completion_context(session, row), session.secrets)
            row["redactionSummary"]["secretsMasked"] += masked
            session.persist(self._state_dir)
        cancel = threading.Event()
        self._btw_cancel[row["btwId"]] = cancel
        timer = threading.Timer(
            self._btw_timeout, self._btw_timeout_reached, args=(session, row["btwId"])
        )
        timer.daemon = True
        self._btw_timers[row["btwId"]] = timer
        timer.start()
        worker = threading.Thread(
            target=self._btw_worker,
            args=(session, row["btwId"], runner, context, cancel),
            daemon=True,
            name=f"mms-btw-{row['btwId']}",
        )
        worker.start()

    def _completion_context(self, session, row: dict) -> dict:
        """The only data a sidecar may see: budgeted and later redacted."""
        tools = [event for event in session.events if event.get("kind") == "tool"]
        errors = [
            event for event in session.events
            if event.get("kind") == "notice" and event.get("status") == "error"
        ]
        clip = lambda text: str(text or "")[:_MAX_CONTEXT_TEXT]
        return {
            "kind": "mms-web-btw-context/v1",
            "question": row["question"],
            "contextRevision": row["contextRevision"],
            "state": session.state,
            "activity": session.activity_view(),
            "turnDuration": _duration_text(self._now(), session.turn_started_at),
            "queue": [clip(text) for text in (session.meta.get("queue") or [])][:_MAX_CONTEXT_ITEMS],
            "approvals": [
                {"method": clip(a.get("method")), "title": clip(a.get("title"))}
                for a in list(session.approvals.values())[:_MAX_CONTEXT_ITEMS]
            ],
            "recentTools": [
                {"title": clip(event.get("title")), "status": clip(event.get("status"))}
                for event in tools[-_MAX_CONTEXT_ITEMS:]
            ],
            "recentErrors": [clip(event.get("text")) for event in errors[-4:]],
            "route": _route_snapshot(session),
        }

    def _btw_worker(self, session, btw_id: str, runner, context: dict, cancel: threading.Event) -> None:
        try:
            result = runner(copy.deepcopy(context), cancel_event=cancel, timeout=self._btw_timeout)
        except Exception as exc:
            detail = str(exc)[:200]
            message, masked = _redact_counted(f"旁问模型执行失败：{detail}", session.secrets)
            row = session.side_questions.get(btw_id)
            if row is not None:
                self._btw_finish(session, row, "failed", error=message, extra_masked=masked)
            return
        with session.lock:
            row = session.side_questions.get(btw_id)
            if row is None or row["status"] != "running":
                # Timed out or cancelled while the sidecar was still working;
                # a late answer is discarded, never recorded as success.
                return
            if cancel.is_set():
                pass  # cancel wins over a late answer; finished below
            else:
                answer = str((result or {}).get("answer") or "")
                if not answer.strip():
                    self._btw_finish(session, row, "failed", error="旁问模型没有返回内容。")
                    return
                answer, masked = _redact_counted(answer, session.secrets)
                usage = result.get("usage") if isinstance(result, dict) and isinstance(result.get("usage"), dict) else None
                self._btw_finish(
                    session, row, "completed",
                    answer=answer[:_MAX_ANSWER], usage=usage, extra_masked=masked,
                )
                return
        self._btw_finish(session, row, "cancelled", error="旁问已取消。")

    def _btw_timeout_reached(self, session, btw_id: str) -> None:
        cancel = self._btw_cancel.get(btw_id)
        if cancel is not None:
            cancel.set()
        with session.lock:
            row = session.side_questions.get(btw_id)
            if row is None or row["status"] in BTW_FINAL_STATES:
                return
        self._btw_finish(
            session, row, "failed",
            error=f"旁问超时（{int(self._btw_timeout)} 秒内未返回）。主任务不受影响。",
        )

    def _btw_finish(self, session, row: dict, status: str, *, answer=None, error=None,
                    usage=None, extra_masked: int = 0) -> None:
        with session.lock:
            if row["status"] in BTW_FINAL_STATES:
                return
            if answer is not None:
                row["answer"] = answer
            if usage is not None:
                row["usage"] = usage
            if error is not None:
                row["error"] = error
            row["status"] = status
            row["completedAt"] = self._now()
            row["redactionSummary"]["secretsMasked"] += extra_masked
            session.persist(self._state_dir)
        timer = self._btw_timers.pop(row["btwId"], None)
        if timer is not None:
            timer.cancel()
        self._btw_cancel.pop(row["btwId"], None)

    def _close_side_questions(self, session) -> None:
        """Service shutdown: in-flight rows are uncertain, never faked done."""
        with session.lock:
            rows = [
                row for row in session.side_questions.values()
                if row["status"] not in BTW_FINAL_STATES
            ]
            for row in rows:
                row["status"] = "uncertain"
                row["error"] = "服务停止时旁问仍在进行，结果未记录。"
                row["completedAt"] = self._now()
        for row in rows:
            cancel = self._btw_cancel.pop(row["btwId"], None)
            if cancel is not None:
                cancel.set()
            timer = self._btw_timers.pop(row["btwId"], None)
            if timer is not None:
                timer.cancel()
