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
  a budgeted, redacted context snapshot (state plus the last few user and
  assistant turns already mirrored into ``session.events``; never tool
  output bodies, never files, never the driver) plus a cancel event, and must never
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
from .drivers.base import RpcTimeoutError

BTW_FINAL_STATES = {"completed", "failed", "cancelled", "uncertain"}
BTW_SOURCES = {"state", "completion"}
BTW_RUNNERS = {"host", "pi-extension"}
# Row-mapping semantics exist only for these extension events; "history" is
# a listing reply the host consumes elsewhere, and unknown kinds carry none.
_BTW_ROW_EVENTS = {"accepted", "running", "delta", "completed", "failed", "cancelled"}

_MAX_QUESTION = 2000
_MAX_ANSWER = 20000
_MAX_CONTEXT_TEXT = 500
_MAX_CONTEXT_ITEMS = 8
# Recent-turn excerpt budget. The rows come from the session's own redacted
# event mirror, so no file, config or driver is read to build it. Small on
# purpose: this is an excerpt the side model is told is an excerpt.
_MAX_TURNS = 6
_MAX_TURN_TEXT = 1200
_MAX_TURNS_CHARS = 5000
# How long the /btw prompt itself may take to be accepted. The answer window
# is the ordinary btw timeout, applied to the terminal event instead.
_BTW_PROMPT_TIMEOUT = 10.0
_MAX_FALLBACK_REASON = 300
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


def _clip_text(text: str, limit: int = _MAX_FALLBACK_REASON) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + "…"


def _btw_event_context(value: Any) -> dict:
    """Whitelist the contract's context fields; anything else is dropped."""
    if not isinstance(value, dict):
        return {}
    scope: dict = {}
    if isinstance(value.get("mode"), str):
        scope["mode"] = str(value["mode"])[:40]
    for key in ("entries", "chars"):
        if isinstance(value.get(key), int) and value[key] >= 0:
            scope[key] = value[key]
    if isinstance(value.get("truncated"), bool):
        scope["truncated"] = value["truncated"]
    if isinstance(value.get("leafId"), str):
        scope["leafId"] = str(value["leafId"])[:128]
    return scope


def _btw_event_usage(value: Any) -> dict | None:
    """Same whitelist for usage; a malformed usage is ignored, not stored."""
    if not isinstance(value, dict):
        return None
    usage: dict = {}
    for key in ("input", "output", "cacheRead", "cacheWrite"):
        item = value.get(key)
        if isinstance(item, int) and item >= 0:
            usage[key] = item
    cost = value.get("cost")
    if cost is None or isinstance(cost, (int, float)):
        usage["cost"] = cost
    return usage or None


def _btw_event_at(payload: dict, fallback: str) -> str:
    at = payload.get("at")
    if isinstance(at, str) and _parse_iso(at) is not None:
        return at
    return fallback


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
        if session.meta.get("harness") == "grok":
            raise WebError("CAPABILITY_UNAVAILABLE", "Grok 会话不支持 /btw 旁问。", 409)
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
                "runner": "host",
                "contextRevision": f"r-{session.last_sequence}",
                "routeSnapshot": _route_snapshot(session),
                "usage": None,
                "redactionSummary": {"secretsMasked": masked_question},
                # What the answer was allowed to see. Filled in for
                # ``completion`` rows once the excerpt is built; a ``state``
                # answer reads the live snapshot instead and leaves it None.
                "contextScope": None,
                "fallbackReason": None,
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

    # -- extension events ----------------------------------------------

    def _apply_side_question_event(self, session, payload: dict) -> None:
        """Map one extension ``BTW_EVENT`` onto the side-question rows.

        Only ``session.side_questions`` is touched: whatever the extension
        reports, the main transcript, the queue and the model stay exactly as
        they were. Rows this path creates or updates carry
        ``runner="pi-extension"`` so the API can tell extension answers from
        host-sidecar answers. Events for unknown ids are ignored unless they
        are the row-creating ``accepted``; duplicate, late or out-of-order
        events never move a row backwards and never reopen a settled one.
        """
        if not isinstance(payload, dict):
            return
        kind = str(payload.get("event") or "")
        if kind not in _BTW_ROW_EVENTS:
            return
        btw_id = str(payload.get("id") or "")
        if not btw_id or not _IDEM_RE.match(btw_id):
            return
        at = _btw_event_at(payload, self._now())
        with session.lock:
            # Events for questions this host asked natively carry the
            # extension's own id: route them to the host row via the map that
            # the accepted event established.
            row = session.side_questions.get(session.btw_native_map.get(btw_id, btw_id))
            if row is None and kind == "accepted":
                host_id = self._match_native_pending(session, payload)
                if host_id is not None:
                    session.btw_native_map[btw_id] = host_id
                    row = session.side_questions.get(host_id)
            if row is None:
                if kind != "accepted":
                    return
                # A finalized or exited session accepts no new rows: the
                # extension is provably gone, so a late accepted would only
                # dangle. Terminal updates for existing rows still land.
                if session.finalized or not session.alive():
                    return
                question, masked = _redact_counted(
                    str(payload.get("question") or "").strip()[:_MAX_QUESTION] or "（扩展未提供问题）",
                    session.secrets,
                )
                session.side_questions[btw_id] = {
                    "btwId": btw_id,
                    "mainSessionId": session.meta["id"],
                    "owner": "sidecar",
                    "question": question,
                    "status": "accepted",
                    "answer": None,
                    "source": "completion",
                    "runner": "pi-extension",
                    "contextRevision": f"r-{session.last_sequence}",
                    "routeSnapshot": _route_snapshot(session),
                    "usage": _btw_event_usage(payload.get("usage")),
                    "redactionSummary": {"secretsMasked": masked},
                    "contextScope": _btw_event_context(payload.get("context")),
                    "error": None,
                    "createdAt": at,
                    "acceptedAt": at,
                    "startedAt": None,
                    "completedAt": None,
                }
                session.persist(self._state_dir)
                return
            if row["status"] in BTW_FINAL_STATES:
                return
            row["runner"] = "pi-extension"
            context = _btw_event_context(payload.get("context"))
            if context:
                row["contextScope"] = context
            if kind == "accepted":
                pass  # idempotent: an existing row never moves backwards
            elif kind == "running":
                if row["status"] == "accepted":
                    row["status"] = "running"
                    row["startedAt"] = at
            elif kind == "delta":
                text = str(payload.get("text") or "")
                if text:
                    tail = session.btw_stream_tails.pop(btw_id, "")
                    value, masked = self._btw_redact_stream(session, str(row.get("answer") or "") + tail + text)
                    keep = max(
                        (
                            n
                            for secret in session.secrets
                            if secret
                            for n in range(1, min(len(secret), len(value) + 1))
                            if value.endswith(secret[:n])
                        ),
                        default=0,
                    )
                    if keep:
                        session.btw_stream_tails[btw_id] = value[-keep:]
                        value = value[:-keep]
                    row["answer"] = value[:_MAX_ANSWER]
                    row["redactionSummary"]["secretsMasked"] += masked
            else:
                if row.get("startedAt") is None:
                    row["startedAt"] = str(row.get("acceptedAt") or at)
                if kind == "completed":
                    answer = str(payload.get("text") or "")
                    if not answer.strip():
                        # No final text: keep whatever the deltas accumulated.
                        answer = str(row.get("answer") or "") + session.btw_stream_tails.pop(btw_id, "")
                    answer, masked = _redact_counted(answer, session.secrets)
                    if answer.strip():
                        row["answer"] = answer[:_MAX_ANSWER]
                        row["redactionSummary"]["secretsMasked"] += masked
                    usage = _btw_event_usage(payload.get("usage"))
                    if usage is not None:
                        row["usage"] = usage
                    row["error"] = None
                else:
                    default = "旁问已取消。" if kind == "cancelled" else "扩展未说明失败原因。"
                    error, masked = _redact_counted(str(payload.get("error") or "")[:500] or default, session.secrets)
                    row["error"] = error
                    row["redactionSummary"]["secretsMasked"] += masked
                row["status"] = kind
                row["completedAt"] = at
                timer = self._btw_timers.pop(row["btwId"], None)
                if timer is not None:
                    timer.cancel()
            session.persist(self._state_dir)

    def _match_native_pending(self, session, payload: dict) -> str | None:
        """Bind an accepted event to the host row whose /btw prompt it answers.

        Called with the session lock held. The extension echoes the question
        it received; the host sent the row's already-redacted question, so the
        same normalisation on both sides makes the match exact. First match
        wins, which keeps duplicate identical questions from pairing twice.
        """
        question, _ = _redact_counted(
            " ".join(str(payload.get("question") or "").split())[:_MAX_QUESTION],
            session.secrets,
        )
        if not question:
            return None
        for host_id, pending in list(session.btw_native_pending.items()):
            if pending.get("question") == question:
                session.btw_native_pending.pop(host_id, None)
                return host_id
        return None

    @staticmethod
    def _btw_redact_stream(session, value: str) -> tuple[str, int]:
        masked = 0
        for secret in session.secrets or []:
            if secret:
                hits = value.count(secret)
                if hits:
                    masked += hits
                    value = value.replace(secret, _MASK)
        return value, masked

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
            native_id = next(
                (nid for nid, hid in session.btw_native_map.items() if hid == row["btwId"]),
                None,
            )
        if native_id is not None:
            # Best effort: tell the extension to stop spending tokens. The
            # row settles below regardless, so a lost command can at worst
            # leave the extension finishing a turn nobody reads.
            try:
                session.driver.request(
                    {"type": "prompt", "message": f"/btw:cancel {native_id}"},
                    timeout=_BTW_PROMPT_TIMEOUT,
                )
            except Exception:
                pass
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
        """Answer a completion question, native extension first.

        When the session carries the fork's ``/btw`` extension
        (``meta.btwNative``), the question is handed to it through a single
        ``/btw`` prompt: the extension answers inside the Pi process with the
        session's own context and reports back through BTW_EVENT notifies.
        It falls back to the host sidecar exactly once per question — when
        the extension refuses the prompt, the driver fails to deliver it, or
        no terminal event arrives before the timeout — never in a loop, and
        never silently: the reason is recorded on the row.
        """
        if self._native_ready(session):
            reason = self._try_native_answer(session, row)
            if reason is None:
                return  # accepted by the extension; events drive the row now
            self._btw_fallback_to_host(session, row, reason)
            return
        # No native extension was detected for this session: the host
        # sidecar is the ordinary path, not a fallback, so nothing is recorded.
        self._answer_from_completion_host(session, row)

    def _native_ready(self, session) -> bool:
        driver = session.driver
        return bool(session.meta.get("btwNative")) and callable(getattr(driver, "request", None))

    def _try_native_answer(self, session, row: dict) -> str | None:
        """Hand one question to the native extension. None means accepted.

        Pi answers an extension-command ``prompt`` only after the command's
        handler finishes, so waiting for that response would block the ask
        for the whole answer. The prompt is therefore sent by a worker
        thread; the ask returns as soon as the question is recorded, and the
        row advances through BTW_EVENT. The worker uses the response only to
        learn about a pre-acceptance rejection; the fallback clock starts
        once the extension is known to have taken the question.
        """
        driver = session.driver
        if driver is None:
            return "native unavailable: no driver"
        question = " ".join(str(row["question"]).split())  # one line, one command
        with session.lock:
            session.btw_native_pending[row["btwId"]] = {
                "question": question,
                "sentAt": self._now(),
            }
        worker = threading.Thread(
            target=self._btw_native_prompt_worker, args=(session, row),
            daemon=True, name=f"mms-btw-native-{row['btwId']}",
        )
        worker.start()
        return None

    def _btw_native_prompt_worker(self, session, row: dict) -> None:
        driver = session.driver
        message = f"/btw {' '.join(str(row['question']).split())}".rstrip()
        optimistic = False
        try:
            response = driver.request({"type": "prompt", "message": message}, timeout=_BTW_PROMPT_TIMEOUT)
        except RpcTimeoutError:
            # The handler outlived the wait: pi has taken the command (its
            # pre-acceptance refusals answer fast). Treat it as accepted and
            # let the events, and then the fallback clock, decide the rest.
            optimistic = True
        except Exception as exc:  # driver refused or died before acceptance
            self._btw_native_rejected(session, row, f"native prompt failed: {exc.__class__.__name__}")
            return
        if not optimistic:
            if not isinstance(response, dict) or response.get("success") is not True:
                error = str((response or {}).get("error") or "")[:120] if isinstance(response, dict) else "malformed response"
                self._btw_native_rejected(session, row, f"extension rejected: {error}" if error else "extension rejected")
                return
        # The extension has (or provably will) take(n) the question. The row
        # advances through BTW_EVENT only; this timer is the fallback trigger
        # when no terminal event lands.
        with session.lock:
            if session.side_questions.get(row["btwId"]) is not row or row["status"] in BTW_FINAL_STATES:
                return
            timer = threading.Timer(
                self._btw_timeout, self._btw_native_timeout, args=(session, row["btwId"])
            )
            timer.daemon = True
            self._btw_timers[row["btwId"]] = timer
        timer.start()

    def _btw_native_rejected(self, session, row: dict, reason: str) -> None:
        with session.lock:
            session.btw_native_pending.pop(row["btwId"], None)
            alive = session.side_questions.get(row["btwId"]) is row
        if alive:
            self._btw_fallback_to_host(session, row, reason)

    def _btw_native_timeout(self, session, btw_id: str) -> None:
        with session.lock:
            session.btw_native_pending.pop(btw_id, None)
            row = session.side_questions.get(btw_id)
            if row is None or row["status"] in BTW_FINAL_STATES:
                return
        self._btw_fallback_to_host(
            session, row,
            f"native 超时（{int(self._btw_timeout)} 秒内无终态事件），已改由 Pilot 旁路回答。",
        )

    def _btw_fallback_to_host(self, session, row: dict, reason: str) -> None:
        """One host-sidecar retry per question, never a loop."""
        with session.lock:
            session.btw_native_pending.pop(row["btwId"], None)
            if row.get("_native_fallback_done"):
                return
            row["_native_fallback_done"] = True
            row["fallbackReason"] = _clip_text(reason)
            # Whatever the extension reported about scope belongs to the
            # extension's answer; the host sidecar sets its own when it runs.
            row["runner"] = "host"
            row["contextScope"] = None
            session.persist(self._state_dir)
        timer = self._btw_timers.pop(row["btwId"], None)
        if timer is not None:
            timer.cancel()
        self._answer_from_completion_host(session, row)

    def _answer_from_completion_host(self, session, row: dict) -> None:
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
            row["contextScope"] = dict(context.get("contextScope") or {})
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

    def _recent_turns(self, session) -> tuple[list[dict], dict]:
        """The last few user/assistant texts, newest last, within budget.

        Reads only ``session.events``, which the driver already filled and
        redacted; tool output bodies, thinking and attachments stay out. The
        scope says how much of the transcript this is, so neither the row nor
        the model can mistake an excerpt for the whole conversation.
        """
        candidates = [
            event for event in session.events
            if event.get("kind") in {"user", "assistant"} and str(event.get("text") or "").strip()
        ]
        turns: list[dict] = []
        used = 0
        clipped = False
        for event in reversed(candidates):
            if len(turns) >= _MAX_TURNS or used >= _MAX_TURNS_CHARS:
                break
            text = str(event.get("text") or "").strip()
            if len(text) > _MAX_TURN_TEXT:
                text = text[:_MAX_TURN_TEXT] + "…"
                clipped = True
            turns.append({"role": event["kind"], "text": text})
            used += len(text)
        turns.reverse()
        scope = {
            "recentTurns": len(turns),
            "totalTurns": len(candidates),
            "truncated": clipped or len(turns) < len(candidates),
        }
        return turns, scope

    def _completion_context(self, session, row: dict) -> dict:
        """The only data a sidecar may see: budgeted and later redacted."""
        turns, scope = self._recent_turns(session)
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
            "recentTurns": turns,
            "contextScope": scope,
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
