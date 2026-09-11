"""Minimal behavior contract fixture for Pilot ``/btw`` side questions.

This module is a TEST FIXTURE, not production code. The real Pilot backend
implements side questions in ``mms_web/side_questions.py`` (plus server
routes); this fixture remains as the pinned minimal behavior contract from
MESSAGE-CONTROL-SPEC.md that the real implementation must keep satisfying,
expressed as an independent reference so the contract tests can compare
semantics without touching production code:

- A side question is a bypass answer. It never touches the main driver, the
  main transcript, the follow-up queue, or the event sequence.
- State answers read only the session view (activity, approvals, queue).
  Completion answers go through an independent read-only sidecar that
  receives an allowlisted context summary, never the transcript.
- A pending approval can be OBSERVED by a side question but never resolved
  by one. Side questions carry no approval owner identity.
- Unfinished side questions become ``uncertain`` after a reload; completed
  records survive verbatim. Nothing fabricates success.
- Missing capabilities fail closed with ``CAPABILITY_UNAVAILABLE`` and a
  reason; ``supported`` is never reported as true without a real source.
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mms_web.errors import WebError

BTW_SCHEMA = "btw-fixture-1"
_FINAL_MAIN_STATES = {"completed", "stopped", "error"}
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_QUESTION = 4000

# MESSAGE-CONTROL-SPEC.md §4: prepared → accepted → running → terminal.
BTW_FINAL_STATES = {"completed", "failed", "cancelled", "uncertain"}
BTW_TRANSITIONS = {
    "prepared": {"accepted", "cancelled", "uncertain"},
    "accepted": {"running", "failed", "cancelled", "uncertain"},
    "running": {"completed", "failed", "cancelled", "uncertain"},
}

# Questions a pure state answer may handle when no sidecar exists. Fixture
# heuristic only; the real implementation may classify differently. Kept
# narrow on purpose: an analytic question must fail closed, not get a fake
# state answer.
STATE_QUESTION_MARKERS = (
    "哪一步", "进度", "状态", "审批", "等待", "为什么还没", "还在", "多久", "队列",
    "progress", "status", "waiting", "approval", "queue", "how long",
    "still running", "which step",
)

# The sidecar context is allowlisted: only these keys may leave the session.
SIDECAR_CONTEXT_FIELDS = (
    "mainState", "phase", "approvalMethod", "queueLength",
    "lastToolTitle", "contextRevision", "modelName",
)


class BtwSidecarError(Exception):
    """The sidecar failed visibly; never silently swallowed."""


class BtwSidecarTimeout(BtwSidecarError):
    """The sidecar exceeded its budget."""


class BtwPending(Exception):
    """Internal marker: the sidecar will never finish (hang mode)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def context_revision(detail: dict) -> int:
    events = detail.get("events") or []
    return max((int(e.get("sequence") or 0) for e in events), default=0)


def build_sidecar_context(detail: dict) -> dict:
    """Build the allowlisted context summary a sidecar may receive.

    Deliberately excludes event bodies, thinking, secrets, full local paths
    and cross-harness traces: none of those are inputs to a side question.
    ``queue`` is optional; it comes from the session's queue truth
    (queue_update), never from transcript event bodies.
    """
    view = detail["session"]
    activity = view.get("activity") or {}
    events = detail.get("events") or []
    tools = [e for e in events if e.get("kind") == "tool"]
    queue = [str(item) for item in (detail.get("queue") or []) if isinstance(item, str)]
    return {
        "mainState": str(view.get("state") or ""),
        "phase": str(activity.get("phase") or ""),
        "approvalMethod": str(activity.get("method") or "") if view.get("state") == "waiting" else "",
        "queueLength": len(queue),
        "lastToolTitle": str(tools[-1].get("title") or "") if tools else "",
        "contextRevision": context_revision(detail),
        "modelName": str(view.get("modelName") or ""),
    }


def state_answer(detail: dict) -> str:
    """Answer from session state evidence only. No model involved."""
    view = detail["session"]
    state = str(view.get("state") or "")
    if state == "waiting":
        method = str((view.get("activity") or {}).get("method") or "confirm")
        return (
            f"主任务正在等待审批（{method}）。BTW 只能查看状态，"
            "不能代替你批准或拒绝。"
        )
    parts: list[str] = []
    phase = str((view.get("activity") or {}).get("phase") or "")
    parts.append(f"主任务{'运行中（阶段：' + phase + '）' if phase else '运行中'}")
    tools = [e for e in detail.get("events") or [] if e.get("kind") == "tool"]
    if tools:
        parts.append(f"最近一次工具调用：{tools[-1].get('title') or '工具调用'}")
    queue = [str(item) for item in (detail.get("queue") or []) if isinstance(item, str)]
    if queue:
        parts.append(f"待发送队列还有 {len(queue)} 条补充消息等待执行")
    return "。".join(parts) + "。"


def is_state_question(question: str) -> bool:
    lowered = str(question).lower()
    return any(marker in lowered for marker in STATE_QUESTION_MARKERS)


class FakeBtwSidecar:
    """Read-only completion double.

    Modes:
    - ``answer``: returns the configured answer.
    - ``error``: raises BtwSidecarError (visible failure).
    - ``timeout``: raises BtwSidecarTimeout (visible failure, retryable).
    - ``hang``: never finishes; the record stays ``running``.

    The double has no write primitives at all — that is the contract.
    Every prompt and context it receives is recorded for redaction asserts.
    """

    def __init__(self, mode: str = "answer", answer: str = "（fixture 旁问回答）") -> None:
        if mode not in {"answer", "error", "timeout", "hang"}:
            raise ValueError(f"unknown sidecar mode: {mode}")
        self.mode = mode
        self.answer = answer
        self.calls: list[dict] = []
        self.supported = True
        self.unsupported_reason = ""
        self.route = {"model": "fake-mini", "provider": "Fake Fixture", "protocol": "anthropic_messages"}

    def capability(self) -> dict:
        if self.supported:
            return {"supported": True, "reason": ""}
        return {"supported": False, "reason": self.unsupported_reason or "旁问模型不可用"}

    def complete(self, question: str, context: dict) -> str:
        self.calls.append({"question": question, "context": copy.deepcopy(context)})
        if not self.supported:
            raise BtwSidecarError(self.unsupported_reason or "旁问模型不可用")
        if self.mode == "error":
            raise BtwSidecarError("sidecar 请求失败（fixture）")
        if self.mode == "timeout":
            raise BtwSidecarTimeout("sidecar 超时（fixture）")
        if self.mode == "hang":
            raise BtwPending()
        return self.answer


class SideQuestionStore:
    """Session-owned side-question records implementing the minimal contract.

    ``state_reader(session_id) -> detail`` must return the real session
    detail (as ``SessionService.get_session`` does) or raise ``WebError``.
    The store only ever reads that snapshot; it has no handle to the driver,
    the event list, or the approval flow.
    """

    def __init__(self, state_root: Path, *, sidecar: FakeBtwSidecar | None = None,
                 state_reader=None, now=None) -> None:
        self._root = Path(state_root) / "side-questions"
        self._sidecar = sidecar
        self._state_reader = state_reader
        self._now = now or _now_iso
        self._records: dict[str, dict[str, dict]] = {}
        self._idempotency: dict[str, dict[str, str]] = {}
        self._counter = 0
        self._load()

    # -- capability -----------------------------------------------------

    def capability(self) -> dict:
        """Never claim completion support without a real sidecar."""
        if self._sidecar is None:
            return {
                "sideQuestions": {
                    "supported": False,
                    "reason": "未接入旁问 completion；仅状态类问题可由会话状态回答。",
                    "stateOnly": True,
                }
            }
        cap = self._sidecar.capability()
        if cap["supported"]:
            return {"sideQuestions": {"supported": True, "source": "state+completion"}}
        return {
            "sideQuestions": {
                "supported": False,
                "reason": cap["reason"],
                "stateOnly": True,
            }
        }

    # -- public API -----------------------------------------------------

    def ask(self, session_id: str, payload: dict) -> dict:
        payload = payload if isinstance(payload, dict) else {}
        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            raise WebError("INVALID_REQUEST", "旁问内容不能为空。", 400)
        question = question.strip()[:_MAX_QUESTION]
        idem = payload.get("idempotencyKey")
        if idem is not None:
            if not isinstance(idem, str) or not _IDEMPOTENCY_RE.match(idem):
                raise WebError("INVALID_REQUEST", "idempotencyKey 格式无效。", 400)
        source_hint = str(payload.get("sourceHint") or "")

        detail = self._require_detail(session_id)
        main_state = str(detail["session"].get("state") or "")
        if main_state in _FINAL_MAIN_STATES:
            raise WebError(
                "CAPABILITY_UNAVAILABLE",
                "主任务已结束；旁问只在主任务运行或等待审批时可用。",
                409,
            )

        if idem:
            existing = self._idempotency.get(session_id, {}).get(idem)
            if existing:
                record = self._records[session_id][existing]
                if record["question"] != question:
                    raise WebError("REQUEST_ID_CONFLICT", "同一 idempotencyKey 不能携带不同问题。", 409)
                return copy.deepcopy(record)

        sidecap = self._sidecar.capability() if self._sidecar is not None else None
        # MESSAGE-CONTROL-SPEC §2 policy: state questions are answered from
        # session state first (cheap, exact); only questions that need
        # judgment go to the sidecar. sourceHint may force completion, never
        # fabricate it when the sidecar is missing.
        use_state = source_hint != "completion" and (
            source_hint == "state" or is_state_question(question)
        )
        if not use_state and (sidecap is None or not sidecap["supported"]):
            # Fail closed BEFORE creating any record: no fabricated answers.
            raise WebError(
                "CAPABILITY_UNAVAILABLE",
                "当前通道没有可用的旁问模型，且该问题需要模型判断；不能伪造回答。",
                409,
            )

        self._counter += 1
        record = {
            "btwId": f"btw-{uuid.uuid4().hex[:12]}",
            "mainSessionId": session_id,
            "question": question,
            "status": "prepared",
            "answer": "",
            "source": "",
            "contextRevision": context_revision(detail),
            "routeSnapshot": {},
            "usage": {},
            "redactionSummary": {},
            "createdAt": self._now(),
            "seq": self._counter,
            "completedAt": "",
            "error": "",
        }
        self._records.setdefault(session_id, {})[record["btwId"]] = record

        if use_state:
            record["source"] = "state"
            self._transition(record, "accepted")
            self._persist(record)
            self._transition(record, "running")
            self._persist(record)
            record["answer"] = state_answer(detail)
            record["routeSnapshot"] = {"source": "state"}
            record["redactionSummary"] = {"policy": "state-only", "contextFields": []}
            self._transition(record, "completed")
            record["completedAt"] = self._now()
            self._persist(record)
        else:
            record["source"] = "completion"
            context = build_sidecar_context(detail)
            record["redactionSummary"] = {
                "policy": "allowlist",
                "contextFields": sorted(context.keys()),
            }
            self._transition(record, "accepted")
            self._persist(record)
            self._transition(record, "running")
            self._persist(record)
            try:
                answer = self._sidecar.complete(question, context)
            except BtwPending:
                self._persist(record)  # stays running; no fabricated result
            except BtwSidecarTimeout as exc:
                record["error"] = f"{exc}；旁问失败，可重试。"
                self._transition(record, "failed")
                record["completedAt"] = self._now()
                self._persist(record)
            except BtwSidecarError as exc:
                record["error"] = str(exc)
                self._transition(record, "failed")
                record["completedAt"] = self._now()
                self._persist(record)
            else:
                record["answer"] = str(answer)
                record["routeSnapshot"] = dict(self._sidecar.route)
                record["usage"] = {"promptTokens": 12, "completionTokens": 8}
                self._transition(record, "completed")
                record["completedAt"] = self._now()
                self._persist(record)

        if idem:
            self._idempotency.setdefault(session_id, {})[idem] = record["btwId"]
        return copy.deepcopy(record)

    def list(self, session_id: str) -> list[dict]:
        records = list(self._records.get(session_id, {}).values())
        records.sort(key=lambda r: (r.get("createdAt", ""), int(r.get("seq") or 0)))
        return [copy.deepcopy(r) for r in records]

    def get(self, session_id: str, btw_id: str) -> dict:
        record = self._records.get(session_id, {}).get(btw_id)
        if record is None:
            raise WebError("BTW_NOT_FOUND", "这条旁问不存在。", 404)
        return copy.deepcopy(record)

    def cancel(self, session_id: str, btw_id: str) -> dict:
        record = self._records.get(session_id, {}).get(btw_id)
        if record is None:
            raise WebError("BTW_NOT_FOUND", "这条旁问不存在。", 404)
        if record["status"] in BTW_FINAL_STATES:
            raise WebError("BTW_ALREADY_FINISHED", "这条旁问已结束，不能取消。", 409)
        self._transition(record, "cancelled")
        record["completedAt"] = self._now()
        self._persist(record)
        return copy.deepcopy(record)

    # -- internals --------------------------------------------------------

    def _require_detail(self, session_id: str) -> dict:
        if self._state_reader is None:
            raise WebError("CAPABILITY_UNAVAILABLE", "旁问状态来源不可用。", 409)
        return self._state_reader(session_id)

    @staticmethod
    def _transition(record: dict, new_status: str) -> None:
        allowed = BTW_TRANSITIONS.get(record["status"], set())
        if new_status not in allowed:
            raise AssertionError(
                f"非法 BTW 状态转移：{record['status']} -> {new_status}"
            )
        record["status"] = new_status

    def _persist(self, record: dict) -> None:
        directory = self._root / record["mainSessionId"]
        directory.mkdir(parents=True, exist_ok=True)
        payload = dict(record)
        payload["schema"] = BTW_SCHEMA
        (directory / f"{record['btwId']}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _load(self) -> None:
        if not self._root.is_dir():
            return
        for session_dir in sorted(self._root.iterdir()):
            if not session_dir.is_dir():
                continue
            for path in sorted(session_dir.glob("*.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(payload, dict) or payload.get("schema") != BTW_SCHEMA:
                    continue
                if payload.get("status") not in BTW_FINAL_STATES:
                    # Reload cannot confirm an in-flight sidecar result.
                    # Honest mark: uncertain. Never completed, never deleted.
                    payload["recoveredFrom"] = payload.get("status")
                    payload["status"] = "uncertain"
                    if not payload.get("error"):
                        payload["error"] = "服务重启，旁问结果未知。"
                    path.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                record = {k: v for k, v in payload.items() if k != "schema"}
                self._records.setdefault(session_dir.name, {})[record["btwId"]] = record
                self._counter = max(self._counter, int(record.get("seq") or 0))
