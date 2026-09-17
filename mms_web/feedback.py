"""Voluntary product feedback. Usage counters stay on this install.

No transcripts are read. A configured HTTPS collector receives only the
allowlisted form after an explicit submit; local usage never leaves the host.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from mms_version import VERSION
from .errors import WebError
from .runtime import private_json

DAY = 86400
CAMPAIGN = "pilot-bot-experience-v1"  # Not tied to releases: upgrades do not re-ask.
# Set only after the maintainer has verified the public collector end to end.
DEFAULT_ENDPOINT = ""
FIELDS = {"requestId", "surface", "job", "outcome", "detail", "recurring", "contact"}


def request_surface(parts: list[str], payload: dict, result: dict) -> str:
    """Only accepted, direct human requests; never schedules or peer dispatch."""
    if parts == ["sessions"] or (len(parts) == 3 and parts[0] == "sessions" and parts[2] == "messages"):
        return "pilot" if (str(payload.get("text") or payload.get("prompt") or "").strip()
                           or payload.get("attachments") or payload.get("references") or payload.get("fileSelections")) else ""
    if len(parts) == 3 and parts[0] == "bots" and parts[2] == "tasks":
        if result.get("kind") == "schedule" or payload.get("runAt") or payload.get("parentTaskId"):
            return ""
        return "bot" if str(payload.get("prompt") or "").strip() else ""
    if len(parts) == 3 and parts[0] == "tasks" and parts[2] == "messages":
        return "bot" if payload.get("role", "user") == "user" and str(payload.get("content") or "").strip() else ""
    return ""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send_feedback(endpoint: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with build_opener(NoRedirect).open(request, timeout=12) as response:
        return json.loads(response.read(32769))


class FeedbackService:
    def __init__(self, state_root: Path, *, endpoint: str | None = None, clock=time.time, sender=send_feedback):
        self.path = Path(state_root) / "feedback-state.json"
        self.endpoint = os.environ.get("MMS_FEEDBACK_ENDPOINT", DEFAULT_ENDPOINT) if endpoint is None else endpoint
        try:
            parsed = urlsplit(self.endpoint)
            self.enabled = bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.fragment)
        except ValueError:
            self.enabled = False
        self.clock, self.sender = clock, sender
        self.lock = threading.RLock()
        self.submit_lock = threading.Lock()

    def _read(self) -> dict:
        empty = {"schema": 1, "days": [], "requests": 0, "visits": 0, "seen": [],
                 "firstAt": 0, "lastAt": 0, "invitations": 0, "phase": "new", "nextAt": 0}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            numbers = ("requests", "visits", "firstAt", "lastAt", "invitations", "nextAt")
            if (isinstance(data, dict) and data.get("schema") == 1
                    and all(isinstance(data.get(k), (int, float)) and math.isfinite(data[k]) and data[k] >= 0 for k in numbers)
                    and all(isinstance(data.get(k), list) and all(isinstance(v, str) for v in data[k]) for k in ("days", "seen"))
                    and data.get("phase") in {"new", "later", "shown", "dismissed", "submitted"}):
                return data
        except FileNotFoundError:
            return empty
        except (OSError, ValueError):
            pass
        # Damaged/unknown preferences must not silently restart invitations.
        return {**empty, "phase": "dismissed"}

    def observe(self, parts: list[str], payload: dict, result: dict) -> None:
        surface = request_surface(parts, payload, result)
        if not surface:
            return
        # Hash request IDs locally; never store task IDs, message text or paths.
        rid = str(payload.get("requestId") or "")
        if not rid:
            return  # Retry-safe counting is preferable to inflating eligibility.
        digest = hashlib.sha256(("/".join(parts) + ":" + rid).encode()).hexdigest()
        with self.lock:
            state = self._read()
            if state["phase"] in {"dismissed", "submitted"} or digest in state["seen"]:
                return
            now = self.clock()
            state["seen"] = (state["seen"] + [digest])[-256:]
            if not state["firstAt"]:
                state["firstAt"] = now
            if not state["lastAt"] or now - state["lastAt"] >= 1800:
                state["visits"] = min(6, state["visits"] + 1)
            state["lastAt"] = now
            state["requests"] = min(12, state["requests"] + 1)
            day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
            state["days"] = sorted(set(state["days"] + [day]))[-3:]
            if surface == "bot":
                state["usedBot"] = True
            private_json(self.path, state)

    def _eligible(self, state: dict) -> bool:
        now = self.clock()
        return bool(self.enabled and state["phase"] in {"new", "later"}
                    and state["invitations"] < 2 and now >= state["nextAt"]
                    and state["firstAt"] and now - state["firstAt"] >= 3 * DAY
                    and len(state["days"]) >= 3 and state["visits"] >= 6
                    and state["requests"] >= 12 and now - state["lastAt"] >= 60)

    def status(self) -> dict:
        with self.lock:
            state = self._read()
            return {"enabled": self.enabled, "eligible": self._eligible(state),
                    "usedBot": bool(state.get("usedBot")), "phase": state["phase"],
                    "metadata": {"version": VERSION, "system": platform.system()},
                    "destination": "MMS 维护者的私有反馈收件箱"}

    def invitation(self, payload: dict) -> dict:
        with self.lock:
            state = self._read()
            action = payload.get("action")
            if action == "claim":
                if not self._eligible(state):
                    return {"claimed": False}
                state.update(phase="shown", invitations=state["invitations"] + 1)
            elif action == "later" and state["phase"] == "shown":
                state.update(phase="later", nextAt=self.clock() + 14 * DAY)
            elif action == "dismiss":
                if state["phase"] != "submitted":
                    state["phase"] = "dismissed"
            elif action == "open":
                if state["phase"] not in {"dismissed", "submitted"}:
                    state["phase"] = "shown"
            else:
                raise WebError("INVALID_FEEDBACK_ACTION", "反馈提醒状态已变化，请刷新后再试。", 409)
            private_json(self.path, state)
            return {"claimed": action == "claim", **self.status()}

    def _payload(self, payload: dict) -> dict:
        if set(payload) - FIELDS:
            raise WebError("INVALID_FEEDBACK", "反馈只接受表单中列出的内容。", 400)
        result = {}
        for key, limit in {"requestId": 128, "surface": 16, "job": 500, "outcome": 16,
                           "detail": 2000, "recurring": 1000, "contact": 200}.items():
            value = payload.get(key, "")
            if not isinstance(value, str) or len(value) > limit:
                raise WebError("INVALID_FEEDBACK", "反馈内容过长或格式不正确。", 400)
            result[key] = value.strip()
        if (not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", result["requestId"])
                or result["surface"] not in {"pilot", "bot", "both"}
                or result["outcome"] not in {"done", "partial", "failed", "exploring"}
                or not result["job"]):
            raise WebError("INVALID_FEEDBACK", "请填写使用场景和完成情况。", 400)
        return {**result, "campaign": CAMPAIGN, "version": VERSION, "system": platform.system()}

    def submit(self, payload: dict) -> dict:
        if not self.enabled:
            raise WebError("FEEDBACK_UNAVAILABLE", "反馈接收暂未开放，请稍后再试。", 503)
        outgoing = self._payload(payload)
        fingerprint = hashlib.sha256(json.dumps(outgoing, sort_keys=True).encode()).hexdigest()
        # Network I/O never holds the app mutation lock or blocks sending a task.
        with self.submit_lock:
            with self.lock:
                state = self._read()
                if state.get("receiptId") == outgoing["requestId"]:
                    if state.get("receiptHash") != fingerprint:
                        raise WebError("FEEDBACK_ID_REUSED", "请关闭反馈窗口后重新填写。", 409)
                    return {"received": True, "receiptId": state["receiptId"]}
            try:
                answer = self.sender(self.endpoint, outgoing)
                if not isinstance(answer, dict) or answer.get("received") is not True or answer.get("receiptId") != outgoing["requestId"]:
                    raise ValueError("missing receipt")
            except (OSError, URLError, ValueError, TimeoutError):
                raise WebError("FEEDBACK_NOT_CONFIRMED", "尚未确认收到，内容已保留在窗口中，请稍后重试。", 502) from None
            with self.lock:
                state = self._read()
                state.update(phase="submitted", receiptId=outgoing["requestId"], receiptHash=fingerprint)
                private_json(self.path, state)
            return {"received": True, "receiptId": outgoing["requestId"]}
