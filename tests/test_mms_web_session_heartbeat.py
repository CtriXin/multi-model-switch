"""Session liveness markers: `lastEventAt` and `heartbeatAt`.

Both are timestamps of things that actually happened. `lastEventAt` moves on
every transcript write, `heartbeatAt` only when the Pi process delivered a
callback through the driver. Neither is a percentage, an estimate, or a clock
that ticks on its own, and both survive a restart as recorded.
"""

from __future__ import annotations

from test_mms_web_sessions_service import launch_ok, make_service  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.tick = 0

    def __call__(self) -> str:
        self.tick += 1
        return f"2026-09-14T00:00:{self.tick:02d}+08:00"


def test_markers_come_from_writes_and_native_callbacks_only(tmp_path, monkeypatch):
    clock = Clock()
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, now=clock)
    session_id = launch_ok(service)["session"]["id"]
    live = service._get(session_id)
    view = live.session_view()
    # Launch wrote the transcript (notice + user) but the fake process has
    # said nothing yet: no heartbeat is claimed for it.
    assert view["lastEventAt"] == view["updatedAt"]
    assert view["lastEventAt"] >= live.events[-1]["updatedAt"]
    assert view["heartbeatAt"] is None
    assert not any("percent" in key.lower() or "progress" in key.lower() for key in view)

    # A native activity callback is a heartbeat, but not a transcript event.
    last_event = view["lastEventAt"]
    service._apply_activity(live, "thinking", {})
    view = live.session_view()
    assert view["heartbeatAt"] is not None and view["heartbeatAt"] > last_event
    assert view["lastEventAt"] == last_event

    # A streamed assistant delta is both.
    beat_before = view["heartbeatAt"]
    drivers[0]._sink.upsert_event({"id": "m-1", "kind": "assistant", "text": "正在读"})
    view = live.session_view()
    assert view["lastEventAt"] > last_event
    assert view["heartbeatAt"] > beat_before

    # A host-side notice moves the transcript marker and leaves the heartbeat.
    beat = view["heartbeatAt"]
    with live.lock:
        live.append_event({"kind": "notice", "text": "设置已更新"}, service._now)
    view = live.session_view()
    assert view["lastEventAt"] > beat
    assert view["heartbeatAt"] == beat
    service.close()


def test_markers_survive_restart_as_recorded(tmp_path, monkeypatch):
    clock = Clock()
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, now=clock)
    session_id = launch_ok(service)["session"]["id"]
    live = service._get(session_id)
    service._apply_activity(live, "thinking", {})
    drivers[0]._sink.upsert_event({"id": "m-1", "kind": "assistant", "text": "正在读"})
    with live.lock:
        live.persist(service._state_dir)
    before = live.session_view()
    service.close()

    reloaded, _ = make_service(tmp_path, monkeypatch=monkeypatch, now=Clock())
    after = reloaded.get_session(session_id)["session"]
    assert after["lastEventAt"] == before["lastEventAt"]
    assert after["heartbeatAt"] == before["heartbeatAt"]
    reloaded.close()
