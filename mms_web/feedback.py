"""Voluntary product feedback. Usage counters stay on this install.

No transcripts are read. Answers go directly to an external voluntary form.
Local usage never leaves the host; opening the form is not a submission.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .errors import WebError
from .runtime import private_json

DAY = 86400
# Public submit-only form, never a Base read link or owner credential.
DEFAULT_FORM_URL = "https://adsconflux.feishu.cn/share/base/shrcnH5OOt9egb9ebAftt57Kcvd"


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


class FeedbackService:
    def __init__(self, state_root: Path, *, form_url: str | None = None, clock=time.time):
        self.path = Path(state_root) / "feedback-state.json"
        self.form_url = os.environ.get("MMS_FEEDBACK_FORM_URL", DEFAULT_FORM_URL) if form_url is None else form_url
        try:
            parsed = urlsplit(self.form_url)
            self.enabled = bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.fragment)
        except ValueError:
            self.enabled = False
        self.clock = clock
        self.lock = threading.RLock()

    def _read(self) -> dict:
        empty = {"schema": 1, "days": [], "requests": 0, "visits": 0, "seen": [],
                 "firstAt": 0, "lastAt": 0, "invitations": 0, "phase": "new", "nextAt": 0}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            numbers = ("requests", "visits", "firstAt", "lastAt", "invitations", "nextAt")
            if (isinstance(data, dict) and data.get("schema") == 1
                    and all(isinstance(data.get(k), (int, float)) and math.isfinite(data[k]) and data[k] >= 0 for k in numbers)
                    and all(isinstance(data.get(k), list) and all(isinstance(v, str) for v in data[k]) for k in ("days", "seen"))
                    and data.get("phase") in {"new", "later", "shown", "opened", "dismissed", "submitted"}):
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
                    "formUrl": self.form_url if self.enabled else ""}

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
                    state["phase"] = "opened"
            else:
                raise WebError("INVALID_FEEDBACK_ACTION", "反馈提醒状态已变化，请刷新后再试。", 409)
            private_json(self.path, state)
            return {"claimed": action == "claim", **self.status()}
