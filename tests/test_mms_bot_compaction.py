from __future__ import annotations

import pytest

from mms_web.bot_executor import PiBotExecutor, _context_percent
from mms_web.errors import WebError


class _Sessions:
    def __init__(self, usage, compact_error=None):
        self.usage = usage
        self.compact_error = compact_error
        self.controls = []

    def runtime_view(self, _session_id):
        return {"stats": {"contextUsage": self.usage}}

    def control(self, session_id, payload):
        self.controls.append((session_id, payload))
        if self.compact_error:
            raise self.compact_error


def _run_compact(usage, *, error=None):
    sessions = _Sessions(usage, error)
    executor = PiBotExecutor(sessions, None)
    executor._maybe_compact(
        "session-1",
        {"autoCompact": True, "compactAtPercent": 70},
        {"id": "task-1"},
    )
    return sessions.controls


def test_pi_percent_is_already_percentage_points():
    assert _context_percent({"percent": 0.8781}) == pytest.approx(0.8781)
    assert _context_percent({"percent": 70.1}) == pytest.approx(70.1)
    assert _context_percent({"usage": {"percent": 0.8781}}) == pytest.approx(0.8781)


def test_short_session_usage_does_not_trigger_compaction():
    assert _run_compact({"tokens": 8781, "contextWindow": 1_000_000, "percent": 0.8781}) == []


def test_compaction_still_triggers_above_bot_threshold():
    controls = _run_compact({"percent": 70.1})
    assert len(controls) == 1
    assert controls[0][1]["action"] == "compact"


def test_short_session_compaction_error_is_a_noop():
    controls = _run_compact(
        {"percent": 70.1},
        error=WebError("COMMAND_FAILED", "Nothing to compact (session too small)", 409),
    )
    assert len(controls) == 1


def test_unrelated_compaction_error_is_not_hidden():
    error = WebError("COMMAND_FAILED", "provider unavailable", 409)
    with pytest.raises(WebError, match="provider unavailable"):
        _run_compact({"percent": 70.1}, error=error)
