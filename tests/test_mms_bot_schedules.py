"""Timing and validation rules for Bot schedules, independent of the scheduler."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from mms_web import bot_schedules
from mms_web.bot_schedules import (MAX_SCHEDULES_PER_BOT, MIN_INTERVAL_SECONDS, advance, apply_update,
                                   build_schedule, defer_once, is_due, local_timezone_name, normalize_rule,
                                   normalize_timezone, parse_every, parse_weekday, sanitize_schedules)
from mms_web.errors import WebError

UTC = timezone.utc


def at(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def local(value: datetime, name: str) -> str:
    return value.astimezone(ZoneInfo(name)).strftime("%Y-%m-%d %H:%M %a")


# ------------------------------------------------------------------ the rules
def test_once_runs_only_at_its_time():
    rule = {"kind": "once", "at": "2026-09-17T09:00:00+08:00"}
    assert bot_schedules.next_run_at(rule, "Asia/Singapore", after=at(2026, 9, 17, 0, 59)) == at(2026, 9, 17, 1, 0)
    assert bot_schedules.next_run_at(rule, "Asia/Singapore", after=at(2026, 9, 17, 1, 0)) is None


def test_interval_starts_one_period_after_now_and_keeps_its_cadence():
    rule = {"kind": "interval", "everySeconds": 10800}
    assert bot_schedules.next_run_at(rule, "UTC", after=at(2026, 9, 17, 0, 0)) == at(2026, 9, 17, 3, 0)
    # The next run is previous + interval, not now + interval: 7 seconds of
    # scheduler latency must not accumulate into drift.
    due = at(2026, 9, 17, 0, 0)
    assert bot_schedules.next_run_at(rule, "UTC", after=at(2026, 9, 17, 0, 0, 7), previous=due) == at(2026, 9, 17, 3, 0)


def test_daily_uses_the_target_timezone_and_never_returns_the_current_instant():
    rule = {"kind": "daily", "atLocalTime": "09:00"}
    assert bot_schedules.next_run_at(rule, "Asia/Singapore", after=at(2026, 9, 16, 22, 0)) == at(2026, 9, 17, 1, 0)
    assert bot_schedules.next_run_at(rule, "Asia/Singapore", after=at(2026, 9, 17, 1, 0)) == at(2026, 9, 18, 1, 0)


def test_weekly_crosses_the_sunday_to_monday_boundary():
    rule = {"kind": "weekly", "weekday": 0, "atLocalTime": "09:00"}  # 0 = Monday
    sunday = at(2026, 9, 20, 4, 0)  # 12:00 Sunday in Singapore
    nxt = bot_schedules.next_run_at(rule, "Asia/Singapore", after=sunday)
    assert local(nxt, "Asia/Singapore") == "2026-09-21 09:00 Mon"
    assert bot_schedules.next_run_at(rule, "Asia/Singapore", after=nxt) == at(2026, 9, 28, 1, 0)


def test_daily_nine_stays_local_nine_across_a_dst_change():
    rule = {"kind": "daily", "atLocalTime": "09:00"}
    nxt = bot_schedules.next_run_at(rule, "America/New_York", after=at(2026, 3, 7, 14, 0))  # 09:00 EST
    assert nxt == at(2026, 3, 8, 13, 0)  # still 09:00, now EDT
    assert local(nxt, "America/New_York").endswith("09:00 Sun")
    assert bot_schedules.next_run_at(rule, "America/New_York", after=nxt) == at(2026, 3, 9, 13, 0)


def test_spring_forward_gap_uses_the_first_valid_local_instant():
    rule = {"kind": "daily", "atLocalTime": "02:30"}
    nxt = bot_schedules.next_run_at(rule, "America/New_York", after=at(2026, 3, 8, 6, 0))  # 01:00 EST
    assert nxt == at(2026, 3, 8, 7, 0)  # 03:00 EDT: the first valid moment after the gap
    assert local(nxt, "America/New_York").endswith("03:00 Sun")


def test_fall_back_repeat_uses_the_first_occurrence():
    rule = {"kind": "daily", "atLocalTime": "01:30"}
    nxt = bot_schedules.next_run_at(rule, "America/New_York", after=at(2026, 11, 1, 4, 0))  # 00:00 EDT
    assert nxt == at(2026, 11, 1, 5, 30)  # first 01:30, still EDT; the EST repeat is 06:30
    assert bot_schedules.next_run_at(rule, "America/New_York", after=at(2026, 11, 1, 12, 0)) == at(2026, 11, 2, 6, 30)


# ----------------------------------------------------------------- advancing
def test_advance_catches_up_a_single_missed_interval_run():
    schedule = {"rule": {"kind": "interval", "everySeconds": 10800}, "timezone": "UTC",
                "nextRunAt": "2026-09-17T00:00:00+00:00"}
    before = deepcopy(schedule)
    updated, skipped = advance(schedule, now=at(2026, 9, 17, 0, 0, 7))
    assert skipped == 0 and updated["nextRunAt"] == "2026-09-17T03:00:00+00:00"
    assert schedule == before, "advance must not mutate the stored row"


def test_advance_drops_a_backlog_instead_of_replaying_it():
    schedule = {"rule": {"kind": "interval", "everySeconds": 10800}, "timezone": "UTC",
                "nextRunAt": "2026-09-14T00:00:00+00:00"}
    updated, skipped = advance(schedule, now=at(2026, 9, 17, 0, 0))
    assert skipped == 24  # three days of three-hour runs
    assert updated["nextRunAt"] == "2026-09-17T03:00:00+00:00"


def test_advance_counts_missed_daily_runs_and_clears_a_spent_once():
    schedule = {"rule": {"kind": "daily", "atLocalTime": "09:00"}, "timezone": "Asia/Singapore",
                "nextRunAt": "2026-09-14T01:00:00+00:00"}
    updated, skipped = advance(schedule, now=at(2026, 9, 17, 2, 0))
    assert skipped == 3 and updated["nextRunAt"] == "2026-09-18T01:00:00+00:00"
    once = {"rule": {"kind": "once", "at": "2026-09-17T00:00:00+00:00"}, "timezone": "UTC",
            "nextRunAt": "2026-09-17T00:00:00+00:00"}
    updated, skipped = advance(once, now=at(2026, 9, 18, 0, 0))
    assert updated["nextRunAt"] is None and skipped == 0
    assert advance({"rule": {"kind": "once", "at": "2026-09-17T00:00:00+00:00"}, "timezone": "UTC",
                    "nextRunAt": None}, now=at(2026, 9, 18, 0, 0))[1] == 0


# ---------------------------------------------------------------- validation
@pytest.mark.parametrize(("every", "expected"), [
    (299, "SCHEDULE_INTERVAL_TOO_SHORT"),
    (300, None),
    (301, None),
])
def test_minimum_interval(every, expected):
    if expected:
        with pytest.raises(WebError) as failure:
            normalize_rule({"kind": "interval", "everySeconds": every})
        assert failure.value.code == expected and failure.value.status == 400
    else:
        assert normalize_rule({"kind": "interval", "everySeconds": every}) == {"kind": "interval", "everySeconds": every}


@pytest.mark.parametrize(("count", "expected"), [(19, None), (20, "SCHEDULE_LIMIT"), (21, "SCHEDULE_LIMIT")])
def test_schedule_count_limit(count, expected):
    payload = {"prompt": "查机票", "rule": {"kind": "interval", "everySeconds": MIN_INTERVAL_SECONDS}}
    if expected:
        with pytest.raises(WebError) as failure:
            build_schedule("bot_1", payload, existing_count=count, now=at(2026, 9, 17))
        assert failure.value.code == expected and failure.value.status == 409
    else:
        assert build_schedule("bot_1", payload, existing_count=count, now=at(2026, 9, 17))["nextRunAt"]


def test_unknown_rule_kind_is_rejected_never_silently_once():
    with pytest.raises(WebError) as failure:
        normalize_rule({"kind": "cron", "expression": "0 */3 * * *"})
    assert failure.value.code == "INVALID_SCHEDULE_RULE"
    with pytest.raises(WebError):
        normalize_rule({"kind": "once", "at": "2026-09-17T09:00:00"})  # naive time
    with pytest.raises(WebError):
        normalize_rule({"kind": "daily", "atLocalTime": "9:00"})
    with pytest.raises(WebError):
        normalize_rule({"kind": "weekly", "weekday": 7, "atLocalTime": "09:00"})


@pytest.mark.parametrize(("text", "expected"), [
    ("3h", 10800), ("180m", 10800), ("10800s", 10800), ("10800", 10800),
])
def test_every_accepts_the_human_spellings(text, expected):
    assert parse_every(text) == expected


@pytest.mark.parametrize("text", ["", "3 hours", "abc", "-3h", "3.5h", "1d"])
def test_every_rejects_anything_else(text):
    with pytest.raises(WebError) as failure:
        parse_every(text)
    assert failure.value.code == "INVALID_SCHEDULE_RULE"


def test_weekday_names():
    assert [parse_weekday(item) for item in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")] == list(range(7))
    assert parse_weekday("周一") == 0 and parse_weekday("周日") == 6
    with pytest.raises(WebError):
        parse_weekday("monday")


def test_timezone_defaults_to_the_machine_and_rejects_unknown_names():
    assert local_timezone_name()
    assert normalize_timezone(None) == local_timezone_name()
    assert normalize_timezone("  ") == local_timezone_name()
    assert normalize_timezone("Asia/Singapore") == "Asia/Singapore"
    with pytest.raises(WebError) as failure:
        normalize_timezone("Mars/Olympus")
    assert failure.value.code == "INVALID_TIMEZONE" and failure.value.status == 400


def test_build_and_update_keep_the_contract_shape():
    schedule = build_schedule("bot_1", {"prompt": " 查机票 ", "rule": {"kind": "daily", "atLocalTime": "09:00"},
                                        "overlapPolicy": "queue"}, existing_count=0, now=at(2026, 9, 17),
                               created_by="bot")
    assert schedule["id"].startswith("sch_") and schedule["botId"] == "bot_1"
    assert schedule["prompt"] == "查机票" and schedule["createdBy"] == "bot"
    assert schedule["timezone"] and schedule["enabled"] is True
    assert schedule["lastRunAt"] is None and schedule["lastTaskId"] is None
    assert schedule["recentTaskIds"] == [] and schedule["lastSkip"] is None

    updated = apply_update(schedule, {"prompt": "新说明", "rule": {"kind": "weekly", "weekday": 2, "atLocalTime": "08:00"},
                                      "timezone": "America/New_York", "botId": "bot_2"},
                           now=at(2026, 9, 18))
    assert updated["prompt"] == "新说明" and updated["rule"]["weekday"] == 2
    assert updated["timezone"] == "America/New_York"
    assert updated["enabled"] is True and updated["botId"] == "bot_1", "an edit may not move or disable a schedule"
    assert updated["nextRunAt"].endswith("+00:00")
    with pytest.raises(WebError):
        apply_update(schedule, {"overlapPolicy": "sometimes"}, now=at(2026, 9, 18))
    # Pausing has exactly one entry point: /enable and /disable, never an edit.
    with pytest.raises(WebError) as failure:
        apply_update(schedule, {"enabled": False}, now=at(2026, 9, 18))
    assert failure.value.code == "INVALID_REQUEST"
    with pytest.raises(WebError):
        build_schedule("bot_1", {"prompt": "查机票", "enabled": False,
                                  "rule": {"kind": "interval", "everySeconds": 300}},
                       existing_count=0, now=at(2026, 9, 18))


def test_defer_once_parks_a_due_one_shot_without_consuming_it():
    schedule = build_schedule("bot_1", {"prompt": "提醒", "rule": {"kind": "once", "at": "2026-09-17T00:00:00+00:00"}},
                              existing_count=0, now=at(2026, 9, 16))
    parked = defer_once(schedule, stamp="2026-09-17T00:00:01.000+00:00", reason="paused")
    assert parked["nextRunAt"] == schedule["nextRunAt"]
    assert parked["lastSkip"] == {"at": "2026-09-17T00:00:01.000+00:00", "reason": "paused", "skipped": 0}
    assert parked["updatedAt"] == "2026-09-17T00:00:01.000+00:00"
    # Already parked for the same reason: no rewrite on every tick.
    assert defer_once(parked, stamp="2026-09-17T00:00:02.000+00:00", reason="paused") is None
    assert defer_once(parked, stamp="2026-09-17T00:00:03.000+00:00", reason="busy")["lastSkip"]["reason"] == "busy"


def test_stored_rows_are_parked_instead_of_bricking_the_loop():
    good = build_schedule("bot_1", {"prompt": "查机票", "rule": {"kind": "interval", "everySeconds": 300}},
                          existing_count=0, now=at(2026, 9, 17))
    clean = sanitize_schedules({
        good["id"]: good,
        "sch_bad_rule": {"botId": "bot_1", "rule": {"kind": "cron"}, "timezone": "UTC", "nextRunAt": None,
                         "recentTaskIds": [], "enabled": True},
        "sch_bad_tz": {"botId": "bot_1", "rule": {"kind": "daily", "atLocalTime": "09:00"},
                       "timezone": "Mars/Olympus", "nextRunAt": "2026-09-17T01:00:00+00:00", "enabled": True},
        "not-a-row": "nope",
    })
    assert set(clean) == {good["id"], "sch_bad_rule", "sch_bad_tz"}
    assert clean["sch_bad_rule"]["enabled"] is False and clean["sch_bad_rule"]["lastSkip"]["reason"] == "invalid"
    assert clean["sch_bad_tz"]["enabled"] is False and clean["sch_bad_tz"]["nextRunAt"] is None
    assert is_due(clean["sch_bad_tz"], at(2100, 1, 1)) is False
    assert sanitize_schedules(None) == {}
    assert is_due(good, at(2100, 1, 1)) and not is_due(good, at(2000, 1, 1))
    assert not is_due({**good, "nextRunAt": None}, at(2100, 1, 1))
    assert not is_due({**good, "nextRunAt": "not-a-time"}, at(2100, 1, 1))
