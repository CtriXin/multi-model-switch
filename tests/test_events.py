"""Tests for mms_events module."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def signal_dir(tmp_path):
    pytest.importorskip("gbrain_memory_hook", reason="optional local GBrain hook is not shipped")
    d = tmp_path / "gbrain"
    d.mkdir()
    with patch("gbrain_memory_hook.PROFILE_DIR", d), \
         patch("gbrain_memory_hook.MMS_SIGNAL_PATH", d / "mms-signals.json"), \
         patch("gbrain_memory_hook.USER_PROFILE_PATH", d / "user-profile.json"):
        yield d


@pytest.fixture
def event_dir(tmp_path):
    d = tmp_path / "events"
    d.mkdir()
    with patch("mms_runtime.events.EVENT_DIR", d), \
         patch("mms_runtime.events.LATEST_PATH", d / "latest.json"):
        yield d


# ── emit_event ──

class TestEmitEvent:
    def test_basic_emit(self, event_dir):
        from mms_runtime.events import emit_event
        ev = emit_event("started", "kimi-k2.5")
        assert ev["type"] == "started"
        assert ev["model"] == "kimi-k2.5"
        assert ev["at"]  # ISO timestamp
        assert ev["run_id"] is None
        assert ev["task_id"] is None
        assert ev["note"] is None

    def test_emit_with_optional_fields(self, event_dir):
        from mms_runtime.events import emit_event
        ev = emit_event("done", "glm-4", run_id="r1", task_id="t1", note="ok")
        assert ev["run_id"] == "r1"
        assert ev["task_id"] == "t1"
        assert ev["note"] == "ok"

    def test_invalid_type_raises(self, event_dir):
        from mms_runtime.events import emit_event
        with pytest.raises(ValueError, match="Unknown event type"):
            emit_event("invalid_type", "model")

    def test_all_valid_types(self, event_dir):
        from mms_runtime.events import emit_event, EventType
        for t in EventType:
            ev = emit_event(t.value, "test-model")
            assert ev["type"] == t.value

    def test_writes_latest_json(self, event_dir):
        from mms_runtime.events import emit_event
        emit_event("queued", "kimi-k2.5")
        latest = event_dir / "latest.json"
        assert latest.exists()
        data = json.loads(latest.read_text())
        assert data["type"] == "queued"
        assert data["model"] == "kimi-k2.5"

    def test_appends_to_daily_jsonl(self, event_dir):
        from mms_runtime.events import emit_event
        emit_event("started", "m1")
        emit_event("done", "m1")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily = event_dir / f"{today}.jsonl"
        assert daily.exists()
        lines = [l for l in daily.read_text().strip().split("\n") if l.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["type"] == "started"
        assert json.loads(lines[1])["type"] == "done"

    def test_writes_gbrain_signals_for_relevant_events(self, event_dir, signal_dir):
        from mms_runtime.events import emit_event
        emit_event("done", "glm-4", run_id="r1", task_id="t1", note="ok")
        for _ in range(50):
            signal_path = signal_dir / "mms-signals.json"
            if signal_path.exists():
                break
            import time
            time.sleep(0.01)
        data = json.loads((signal_dir / "mms-signals.json").read_text())
        assert len(data["signals"]) == 1
        assert data["signals"][0]["type"] == "done"
        assert data["signals"][0]["model"] == "glm-4"

    def test_skips_gbrain_signals_for_irrelevant_events(self, event_dir, signal_dir):
        from mms_runtime.events import emit_event
        emit_event("started", "glm-4")
        import time
        time.sleep(0.02)
        assert not (signal_dir / "mms-signals.json").exists()

    def test_writes_user_profile_for_explicit_preference_note(self, event_dir, signal_dir):
        from mms_runtime.events import emit_event
        emit_event("done", "glm-4", run_id="r1", task_id="planner", note="user prefers terse responses and worktree flow")
        for _ in range(50):
            profile_path = signal_dir / "user-profile.json"
            if profile_path.exists():
                break
            import time
            time.sleep(0.01)
        data = json.loads((signal_dir / "user-profile.json").read_text())
        summaries = [entry["summary"] for entry in data["entries"]]
        assert "prefers terse responses" in summaries
        assert "prefers worktree workflow" in summaries

    def test_merges_duplicate_profile_evidence(self, event_dir, signal_dir):
        from mms_runtime.events import emit_event
        emit_event("done", "glm-4", run_id="r1", task_id="planner", note="user prefers terse responses")
        emit_event("done", "glm-4", run_id="r2", task_id="planner", note="user prefers terse responses")
        for _ in range(50):
            profile_path = signal_dir / "user-profile.json"
            if profile_path.exists():
                break
            import time
            time.sleep(0.01)
        data = json.loads((signal_dir / "user-profile.json").read_text())
        terse = [entry for entry in data["entries"] if entry["summary"] == "prefers terse responses"]
        assert len(terse) == 1
        assert len(terse[0]["evidence"]) == 2


# ── get_latest_event ──

class TestGetLatestEvent:
    def test_returns_none_when_no_file(self, event_dir):
        from mms_runtime.events import get_latest_event
        assert get_latest_event() is None

    def test_returns_latest(self, event_dir):
        from mms_runtime.events import emit_event, get_latest_event
        emit_event("started", "m1")
        emit_event("done", "m2")
        latest = get_latest_event()
        assert latest["type"] == "done"
        assert latest["model"] == "m2"


# ── get_recent_events ──

class TestGetRecentEvents:
    def test_empty_when_no_file(self, event_dir):
        from mms_runtime.events import get_recent_events
        assert get_recent_events() == []

    def test_returns_in_order(self, event_dir):
        from mms_runtime.events import emit_event, get_recent_events
        emit_event("queued", "m1")
        emit_event("started", "m1")
        emit_event("streaming", "m1")
        events = get_recent_events()
        assert len(events) == 3
        assert events[0]["type"] == "queued"
        assert events[2]["type"] == "streaming"

    def test_limit(self, event_dir):
        from mms_runtime.events import emit_event, get_recent_events
        for i in range(10):
            emit_event("started", f"m{i}")
        events = get_recent_events(limit=3)
        assert len(events) == 3
        # Should be last 3
        assert events[0]["model"] == "m7"


# ── cleanup ──

class TestCleanup:
    def test_removes_old_jsonl(self, event_dir):
        # Create an old JSONL file (8 days ago)
        old_date = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")
        old_file = event_dir / f"{old_date}.jsonl"
        old_file.write_text('{"type":"done"}\n')

        from mms_runtime.events import emit_event
        emit_event("started", "m1")  # triggers cleanup

        assert not old_file.exists()

    def test_keeps_recent_jsonl(self, event_dir):
        # Create a recent JSONL file (2 days ago)
        recent_date = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
        recent_file = event_dir / f"{recent_date}.jsonl"
        recent_file.write_text('{"type":"done"}\n')

        from mms_runtime.events import emit_event
        emit_event("started", "m1")

        assert recent_file.exists()
