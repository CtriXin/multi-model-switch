"""Tests for mms_committee_timing (issue #64).

Covers: log event-pair extraction, elapsed computation, same-batch same-tier
speed_ratio, JSONL append under tmp config root, and the render contract that
forbids cross-batch comparison.
"""

from __future__ import annotations

import json
import os

import pytest

from mms_committee_timing import (
    BatchTiming,
    append_batch_record,
    compute_batch_timing,
    extract_member_sessions,
    parse_iso_utc,
    render_timing_table,
    timing_log_path,
)


# ─── Fixtures: synthetic opencode session log lines (UTC) ───────────────────

SAMPLE_LOG_LINES = [
    # gpt-5.5 member session
    'INFO  2026-06-17T01:36:28 +1ms service=session id=ses_gpt session.id=ses_gpt '
    'title=评估 (@committee-gpt-5-5-14 subagent) time={"created":1781660188971} created',
    'INFO  2026-06-17T01:36:29 +0ms service=session.processor session.id=ses_gpt '
    'messageID=msg_gpt process',
    'INFO  2026-06-17T01:36:53 +1ms service=session.prompt session.id=ses_gpt '
    'step=1 loop',
    'INFO  2026-06-17T01:36:53 +1ms service=session.prompt session.id=ses_gpt '
    'exiting loop',
    # deepseek member session (slower)
    'INFO  2026-06-17T01:36:49 +2ms service=session id=ses_ds session.id=ses_ds '
    'title=评估 (@committee-deepseek-v4-pro-20 subagent) time={"created":1781660209702} created',
    'INFO  2026-06-17T01:36:49 +1ms service=session.processor session.id=ses_ds '
    'messageID=msg_ds process',
    'INFO  2026-06-17T01:37:43 +0ms service=session.prompt session.id=ses_ds '
    'exiting loop',
    # kimi member session (fastest)
    'INFO  2026-06-17T01:36:49 +1ms service=session id=ses_kimi session.id=ses_kimi '
    'title=评估 (@committee-kimi-k2-7-code-20 subagent) time={"created":1781660209716} created',
    'INFO  2026-06-17T01:36:50 +0ms service=session.processor session.id=ses_kimi '
    'messageID=msg_kimi process',
    'INFO  2026-06-17T01:37:02 +0ms service=session.prompt session.id=ses_kimi '
    'exiting loop',
    # A non-member host session (should be excluded from member tier)
    'INFO  2026-06-17T01:36:00 +0ms service=session id=ses_host session.id=ses_host '
    'title=host created',
    'INFO  2026-06-17T01:36:00 +0ms service=session.processor session.id=ses_host process',
    'INFO  2026-06-17T01:38:00 +0ms service=session.prompt session.id=ses_host exiting loop',
]


# Production-format log lines: the created line uses 'service=session id=ses_xxx'
# (NOT 'session.id='), while processor/prompt lines use 'session.id='. This is
# the actual opencode emit form; the extractor must match BOTH to reach the
# title (where the member name lives) on the created line.
PRODUCTION_FORMAT_LINES = [
    'INFO  2026-06-17T03:51:29 +1ms service=session id=ses_prod_gpt '
    'slug=stellar-rocket version=1.15.10 '
    'title=审议 PR #65 (@committee-gpt-5-5-14 subagent) '
    'time={"created":1781668289522,"updated":1781668289522} created',
    'INFO  2026-06-17T03:51:29 +0ms service=session.processor session.id=ses_prod_gpt '
    'messageID=msg_pg process',
    'INFO  2026-06-17T03:54:59 +0ms service=session.prompt session.id=ses_prod_gpt '
    'exiting loop',
    'INFO  2026-06-17T03:51:29 +1ms service=session id=ses_prod_ds '
    'slug=happy-garden '
    'title=审议 PR #65 (@committee-deepseek-v4-pro-20 subagent) '
    'time={"created":1781668289536} created',
    'INFO  2026-06-17T03:51:29 +0ms service=session.processor session.id=ses_prod_ds '
    'messageID=msg_pd process',
    'INFO  2026-06-17T03:53:18 +0ms service=session.prompt session.id=ses_prod_ds '
    'exiting loop',
]


def test_parse_iso_utc_roundtrip():
    dt = parse_iso_utc("2026-06-17T01:36:29")
    assert dt.year == 2026 and dt.month == 6 and dt.day == 17
    assert dt.hour == 1 and dt.minute == 36 and dt.second == 29


def test_extract_member_sessions_finds_three_members():
    sessions = extract_member_sessions(SAMPLE_LOG_LINES)
    members = {e["member"] for e in sessions.values() if e["member"]}
    assert members == {
        "committee-gpt-5-5-14",
        "committee-deepseek-v4-pro-20",
        "committee-kimi-k2-7-code-20",
    }


def test_extract_handles_production_format_created_line_uses_id_not_session_id():
    # Regression: the created line in real opencode logs uses
    # 'service=session id=ses_xxx' (NOT 'session.id='), while processor/prompt
    # lines use 'session.id='. The extractor must match both so the member
    # name on the created line is reached. This test failed before the fix.
    sessions = extract_member_sessions(PRODUCTION_FORMAT_LINES)
    members = {e["member"] for e in sessions.values() if e["member"]}
    assert members == {
        "committee-gpt-5-5-14",
        "committee-deepseek-v4-pro-20",
    }
    # gpt: 03:51:29 -> 03:54:59 = 210s
    by_member = {e["member"]: e for e in sessions.values() if e["member"]}
    assert by_member["committee-gpt-5-5-14"]["process_at"] == "2026-06-17T03:51:29"
    assert by_member["committee-gpt-5-5-14"]["exiting_at"] == "2026-06-17T03:54:59"


def test_compute_batch_timing_on_production_format():
    sessions = extract_member_sessions(PRODUCTION_FORMAT_LINES)
    batch = compute_batch_timing(
        sessions, mission_id="prod-1", task_kind="pr_review_gate", tier="member"
    )
    by_member = {m.member: m for m in batch.members}
    # gpt 210s, deepseek 109s -> deepseek is fastest here.
    assert by_member["committee-deepseek-v4-pro-20"].elapsed_s == 109.0
    assert by_member["committee-gpt-5-5-14"].elapsed_s == 210.0
    assert batch.fastest_member == "committee-deepseek-v4-pro-20"


def test_extract_captures_process_and_exiting_timestamps():
    sessions = extract_member_sessions(SAMPLE_LOG_LINES)
    by_member = {e["member"]: e for e in sessions.values() if e["member"]}
    gpt = by_member["committee-gpt-5-5-14"]
    assert gpt["process_at"] == "2026-06-17T01:36:29"
    assert gpt["exiting_at"] == "2026-06-17T01:36:53"


def test_compute_batch_timing_elapsed_values():
    sessions = extract_member_sessions(SAMPLE_LOG_LINES)
    batch = compute_batch_timing(
        sessions,
        mission_id="test-mission-1",
        task_kind="gate",
        tier="member",
        dispatch_at="2026-06-17T01:36:00Z",
    )
    by_member = {m.member: m for m in batch.members}
    # gpt 01:36:29 -> 01:36:53 = 24s
    assert by_member["committee-gpt-5-5-14"].elapsed_s == 24.0
    # deepseek 01:36:49 -> 01:37:43 = 54s
    assert by_member["committee-deepseek-v4-pro-20"].elapsed_s == 54.0
    # kimi 01:36:50 -> 01:37:02 = 12s  (fastest)
    assert by_member["committee-kimi-k2-7-code-20"].elapsed_s == 12.0


def test_compute_batch_timing_speed_ratio_and_fastest():
    sessions = extract_member_sessions(SAMPLE_LOG_LINES)
    batch = compute_batch_timing(
        sessions, mission_id="m1", task_kind="gate", tier="member"
    )
    by_member = {m.member: m for m in batch.members}
    # Fastest is kimi (12s), ratio 1.0.
    assert batch.fastest_member == "committee-kimi-k2-7-code-20"
    assert batch.fastest_elapsed_s == 12.0
    assert by_member["committee-kimi-k2-7-code-20"].speed_ratio == 1.0
    # gpt 24/12 = 2.0
    assert by_member["committee-gpt-5-5-14"].speed_ratio == 2.0
    # deepseek 54/12 = 4.5
    assert by_member["committee-deepseek-v4-pro-20"].speed_ratio == 4.5


def test_compute_batch_excludes_non_member_sessions():
    sessions = extract_member_sessions(SAMPLE_LOG_LINES)
    batch = compute_batch_timing(
        sessions, mission_id="m1", task_kind="gate", tier="member"
    )
    # ses_host has no @committee-* member marker, must not appear.
    assert all(m.member.startswith("committee-") for m in batch.members)
    assert len(batch.members) == 3


def test_compute_batch_marks_incomplete_event_pairs():
    # Drop the kimi exiting-loop line so its pair is incomplete.
    lines = [ln for ln in SAMPLE_LOG_LINES if "ses_kimi" not in ln or "exiting loop" not in ln]
    sessions = extract_member_sessions(lines)
    batch = compute_batch_timing(sessions, mission_id="m1", task_kind="gate", tier="member")
    by_member = {m.member: m for m in batch.members}
    kimi = by_member["committee-kimi-k2-7-code-20"]
    assert kimi.elapsed_s is None
    assert "incomplete_event_pair" in kimi.notes
    # Fastest is now gpt (24s); kimi excluded from fastest calc.
    assert batch.fastest_member == "committee-gpt-5-5-14"


def test_render_timing_table_contains_same_batch_same_tier_marker():
    sessions = extract_member_sessions(SAMPLE_LOG_LINES)
    batch = compute_batch_timing(sessions, mission_id="m1", task_kind="gate", tier="member")
    rendered = render_timing_table(batch)
    # Header contract: same-batch same-tier must be called out explicitly.
    assert "same-batch same-tier" in rendered
    assert "禁止跨批次横比" in rendered
    assert "committee-kimi-k2-7-code-20" in rendered


def test_render_timing_table_empty_batch_is_safe():
    empty = BatchTiming(
        mission_id="m1",
        dispatch_at="2026-06-17T01:36:00Z",
        task_kind="gate",
        tier="member",
        members=[],
        fastest_member=None,
        fastest_elapsed_s=None,
    )
    rendered = render_timing_table(empty)
    assert "same-batch same-tier" in rendered


def test_append_batch_record_writes_jsonl_under_config_root(tmp_path, monkeypatch):
    # Force the mms-next root under tmp_path via MMS_CONFIG_DIR; clear MMS_CONFIG_ROOT
    # because the real dev env sets it globally and would override MMS_CONFIG_DIR.
    config_dir = tmp_path / ".config" / "mms"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("MMS_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)

    sessions = extract_member_sessions(SAMPLE_LOG_LINES)
    batch = compute_batch_timing(sessions, mission_id="m-jsonl-1", task_kind="gate", tier="member")
    path = append_batch_record(batch)

    assert path.endswith("committee-timing.jsonl")
    assert os.path.basename(path) == "committee-timing.jsonl"
    # Path is under tmp_path
    assert str(tmp_path) in path
    # Three members => three JSONL lines.
    with open(path, "r", encoding="utf-8") as fh:
        lines = [json.loads(ln) for ln in fh if ln.strip()]
    assert len(lines) == 3
    # Each line carries mission_id + task_kind for batch grouping.
    for rec in lines:
        assert rec["mission_id"] == "m-jsonl-1"
        assert rec["task_kind"] == "gate"
        assert rec["tier"] == "member"
        assert rec["member"].startswith("committee-")
        assert "session_id" in rec
        assert "elapsed_s" in rec
        assert "speed_ratio" in rec


def test_append_batch_record_appends_does_not_overwrite(tmp_path, monkeypatch):
    config_dir = tmp_path / ".config" / "mms"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("MMS_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)

    sessions = extract_member_sessions(SAMPLE_LOG_LINES)
    b1 = compute_batch_timing(sessions, mission_id="batch-A", task_kind="gate", tier="member")
    b2 = compute_batch_timing(sessions, mission_id="batch-B", task_kind="gate", tier="member")
    append_batch_record(b1)
    append_batch_record(b2)

    path = timing_log_path()
    with open(path, "r", encoding="utf-8") as fh:
        lines = [json.loads(ln) for ln in fh if ln.strip()]
    # Two batches × 3 members = 6 lines; append semantics preserved.
    assert len(lines) == 6
    missions = {rec["mission_id"] for rec in lines}
    assert missions == {"batch-A", "batch-B"}


def test_timing_log_path_respects_explicit_config_dir(tmp_path, monkeypatch):
    # When caller pins MMS_CONFIG_DIR, the timing file stays self-contained
    # under that dir (test isolation) and is NOT written to the real home.
    config_dir = tmp_path / ".config" / "mms"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("MMS_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    path = timing_log_path()
    assert os.path.basename(path) == "committee-timing.jsonl"
    # Must be under the pinned tmp dir, never under the real home.
    assert str(tmp_path) in path
    assert "/Users/" not in path or str(tmp_path) in path


def test_timing_log_path_defaults_to_mms_next_under_real_home(tmp_path, monkeypatch):
    # No explicit config dir, no preview marker -> default mms root is stable,
    # but issue #64 wants the timing data in the preview (mms-next) lane.
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("MMS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MMS_PREVIEW_MODE", raising=False)
    monkeypatch.delenv("MMS_COMMAND_NAME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MMS_REAL_HOME", str(tmp_path / "home"))
    path = timing_log_path()
    assert os.path.basename(path) == "committee-timing.jsonl"
    # Under <home>/.config/mms-next/
    assert os.path.basename(os.path.dirname(path)) == "mms-next"
    assert str(tmp_path) in path
