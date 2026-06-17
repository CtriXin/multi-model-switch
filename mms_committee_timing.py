"""Committee member elapsed-time calibration.

Issue #64. The committee host previously reported member timing using the
outer dispatch wall-clock window (or "not_captured"), which masked real
per-member latency differences. The real data is in opencode session logs
as a pair of events per member session:

  start:  service=session.processor session.id=<id> ... process
  end:    service=session.prompt    session.id=<id> ... exiting loop

This module parses those event pairs, computes per-member elapsed time,
enforces same-batch same-tier comparison, and appends a structured record
to ~/.config/mms-next/committee-timing.jsonl (or the resolved config root
equivalent) for later tuning of member selection / convergence strategy.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Mapping

from mms_state_io import (
    resolve_mms_config_dir,
    resolve_real_user_home,
)


# Issue #64: timing data lives under the mms-next (preview) config root.
# When the active config root is already the preview/mms-next root (e.g. when
# MMS_CONFIG_ROOT points at ~/.config/mms-next or MMS_PREVIEW_MODE is set),
# write directly there; otherwise write under ~/.config/mms-next so the data
# stays in the preview lane regardless of the caller's stable/preview mode.
_TIMING_FILENAME = "committee-timing.jsonl"


# Regexes aligned to observed opencode session log lines (UTC ISO-8601).
# Example: "INFO  2026-06-17T01:36:29 +0ms service=session.processor session.id=ses_xxx ... process"
_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?\s*[+-]\d+ms")
_SESSION_ID_RE = re.compile(r"session\.id=(ses_[A-Za-z0-9]+)")
_PROCESSOR_PROCESS_RE = re.compile(r"service=session\.processor\b.*\bprocess\b")
_PROMPT_EXITING_RE = re.compile(r"service=session\.prompt\b.*\bexiting loop\b")
_SESSION_CREATED_RE = re.compile(r"service=session\b.*\bcreated\b")
_TITLE_MEMBER_RE = re.compile(
    # matches "(@committee-<member> subagent)" in the session.created title line;
    # the parenthesised form is what opencode actually emits.
    r"\(@committee-([A-Za-z0-9\-]+)\s+subagent\)"
)
_TIME_CREATED_JSON_RE = re.compile(r'"time":\{[^}]*"created":(\d+)[^}]*\}')


@dataclass
class MemberTiming:
    """One member's timing within a single dispatch batch."""

    member: str
    model_id: str | None
    session_id: str
    process_start_ts: str | None  # ISO-8601 UTC, from session.processor process event
    exiting_loop_ts: str | None  # ISO-8601 UTC, from session.prompt exiting loop event
    elapsed_s: float | None
    speed_ratio: float | None  # elapsed / fastest_elapsed in same batch; 1.0 for fastest
    notes: list[str] = field(default_factory=list)

    def to_record(self) -> dict:
        return asdict(self)


@dataclass
class BatchTiming:
    """All members' timing in one dispatch batch, same-tier comparable."""

    mission_id: str
    dispatch_at: str  # ISO-8601 UTC
    task_kind: str
    tier: str  # e.g. "member"
    members: list[MemberTiming]
    fastest_member: str | None
    fastest_elapsed_s: float | None


def parse_iso_utc(ts: str) -> datetime:
    """Parse the trimmed UTC ISO-8601 form used in session logs."""
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def iso_now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iter_log_lines(log_path: str) -> Iterable[str]:
    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            yield line


def _extract_member_from_title(line: str) -> str | None:
    """From a session.created line, pull 'committee-<name>' if it's a member session."""
    m = _TITLE_MEMBER_RE.search(line)
    if not m:
        return None
    return "committee-" + m.group(1)


def _extract_session_created_unix_ms(line: str) -> int | None:
    """Pull the 'created' unix-ms timestamp embedded in session.created JSON blob."""
    m = _TIME_CREATED_JSON_RE.search(line)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def extract_member_sessions(
    log_lines: Iterable[str],
    *,
    member_filter: set[str] | None = None,
) -> dict[str, dict]:
    """Walk log lines and build a per-session dict of timing events.

    Returns: { session_id: {
        "member": str|None, "model_id": str|None,
        "process_at": str|None,   # ISO-8601 UTC
        "exiting_at": str|None,   # ISO-8601 UTC
        "created_at_unix_ms": int|None,
    } }
    """
    sessions: dict[str, dict] = {}

    for line in log_lines:
        sid_m = _SESSION_ID_RE.search(line)
        if not sid_m:
            continue
        sid = sid_m.group(1)
        entry = sessions.setdefault(
            sid,
            {
                "member": None,
                "model_id": None,
                "process_at": None,
                "exiting_at": None,
                "created_at_unix_ms": None,
            },
        )

        if entry["member"] is None:
            member = _extract_member_from_title(line)
            if member:
                entry["member"] = member

        if entry["created_at_unix_ms"] is None and _SESSION_CREATED_RE.search(line):
            entry["created_at_unix_ms"] = _extract_session_created_unix_ms(line)

        ts_m = _TS_RE.search(line)
        ts = ts_m.group(1) if ts_m else None

        if ts and entry["process_at"] is None and _PROCESSOR_PROCESS_RE.search(line):
            entry["process_at"] = ts
        if ts and entry["exiting_at"] is None and _PROMPT_EXITING_RE.search(line):
            entry["exiting_at"] = ts

    # Optional member filter.
    if member_filter:
        sessions = {
            sid: e
            for sid, e in sessions.items()
            if e["member"] in member_filter
        }
    return sessions


def compute_batch_timing(
    sessions: Mapping[str, Mapping],
    *,
    mission_id: str,
    task_kind: str,
    tier: str = "member",
    dispatch_at: str | None = None,
) -> BatchTiming:
    """Build a BatchTiming (same-tier comparable) from extracted sessions.

    Only sessions that look like dispatched members (member is set) and that
    have at least one of process_at / exiting_at are included. Members with
    incomplete pairs are still recorded (with notes) so the host cannot hide
    them behind 'not_captured'.
    """
    member_entries = [
        (sid, e) for sid, e in sessions.items() if e.get("member")
    ]

    raw: list[tuple[str, dict, float | None]] = []
    for sid, e in member_entries:
        proc = e.get("process_at")
        exit_ = e.get("exiting_at")
        elapsed = None
        if proc and exit_:
            try:
                elapsed = (parse_iso_utc(exit_) - parse_iso_utc(proc)).total_seconds()
                if elapsed < 0:
                    elapsed = None
            except (ValueError, TypeError):
                elapsed = None
        raw.append((sid, e, elapsed))

    # Fastest is computed only over members with a usable elapsed value.
    elapsed_values = [el for _, _, el in raw if el is not None]
    fastest_elapsed = min(elapsed_values) if elapsed_values else None

    members: list[MemberTiming] = []
    for sid, e, elapsed in raw:
        notes: list[str] = []
        if elapsed is None:
            notes.append("incomplete_event_pair")
        ratio = None
        if elapsed is not None and fastest_elapsed and fastest_elapsed > 0:
            ratio = round(elapsed / fastest_elapsed, 3)
        members.append(
            MemberTiming(
                member=e["member"],
                model_id=e.get("model_id"),
                session_id=sid,
                process_start_ts=e.get("process_at"),
                exiting_loop_ts=e.get("exiting_at"),
                elapsed_s=elapsed,
                speed_ratio=ratio,
                notes=notes,
            )
        )

    # Sort by elapsed asc (None last) for deterministic ordering.
    members.sort(key=lambda m: (m.elapsed_s is None, m.elapsed_s if m.elapsed_s is not None else 0))

    fastest_member = None
    if fastest_elapsed is not None:
        for m in members:
            if m.elapsed_s == fastest_elapsed:
                fastest_member = m.member
                break

    return BatchTiming(
        mission_id=mission_id,
        dispatch_at=dispatch_at or iso_now_utc(),
        task_kind=task_kind,
        tier=tier,
        members=members,
        fastest_member=fastest_member,
        fastest_elapsed_s=fastest_elapsed,
    )


def timing_log_path(env: Mapping[str, str] | None = None) -> str:
    """Resolve the committee-timing.jsonl path under the mms-next config root.

    Issue #64 requires the timing data to live under the mms-next (preview)
    lane so later member-selection / convergence tuning can read a stable
    preview path. Three cases:

    1. The active config root is already the preview/mms-next root
       (MMS_CONFIG_ROOT ends with 'mms-next', or MMS_PREVIEW_MODE/MMS_COMMAND_NAME
       marks the run as preview): write directly under that root.
    2. The caller pinned an explicit config dir via MMS_CONFIG_DIR / MMS_CONFIG_ROOT
       that is NOT mms-next: respect it but keep the filename, so tests and
       isolated environments stay self-contained.
    3. Default (stable mms root, no preview marker): write under
       <real_home>/.config/mms-next/.
    """
    env_map = dict(env or os.environ)
    config_dir = os.path.normpath(resolve_mms_config_dir(env_map))
    base_name = os.path.basename(config_dir)

    explicit_root = str(env_map.get("MMS_CONFIG_ROOT") or "").strip()
    explicit_dir = str(env_map.get("MMS_CONFIG_DIR") or "").strip()

    # Case 1: active root is already mms-next.
    if base_name == "mms-next":
        return os.path.join(config_dir, _TIMING_FILENAME)

    # Case 2: caller pinned an explicit non-mms-next dir; stay self-contained.
    if explicit_root or explicit_dir:
        return os.path.join(config_dir, _TIMING_FILENAME)

    # Case 3: default stable mode -> issue #64 still wants the preview lane.
    # Redirect from <real_home>/.config/mms to <real_home>/.config/mms-next.
    real_home = resolve_real_user_home(env_map)
    return os.path.join(real_home, ".config", "mms-next", _TIMING_FILENAME)


def append_batch_record(batch: BatchTiming, env: Mapping[str, str] | None = None) -> str:
    """Append one JSONL line per member to the timing log. Returns the path written.

    Each line is self-contained and carries mission_id + task_kind so later
    aggregation can group strictly by same-batch same-tier.
    """
    path = timing_log_path(env)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for m in batch.members:
            record = {
                "mission_id": batch.mission_id,
                "dispatch_at": batch.dispatch_at,
                "task_kind": batch.task_kind,
                "tier": batch.tier,
                "fastest_member": batch.fastest_member,
                "fastest_elapsed_s": batch.fastest_elapsed_s,
                **m.to_record(),
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def render_timing_table(batch: BatchTiming) -> str:
    """Render a markdown table for the host's Model Timing section.

    Same-batch same-tier comparison only; the header says so explicitly to
    stop downstream readers from cross-batch cherry-picking.
    """
    if not batch.members:
        return (
            "_No member timing captured for this batch "
            "(same-batch same-tier comparison)._"
        )
    header = (
        "| 返回顺序 | 成员 | process 开始(UTC) | exiting loop(UTC) | "
        "耗时 | 相对最快 |\n"
        "|---|---|---|---|---|---|\n"
    )
    rows = []
    for idx, m in enumerate(batch.members, 1):
        elapsed = f"{m.elapsed_s:.0f}s" if m.elapsed_s is not None else "n/a"
        ratio = f"{m.speed_ratio:.2f}x" if m.speed_ratio is not None else "n/a"
        rows.append(
            f"| {idx} | {m.member} | {m.process_start_ts or 'n/a'} | "
            f"{m.exiting_loop_ts or 'n/a'} | {elapsed} | {ratio} |"
        )
    note = (
        "\n\n_同次同层比较 (same-batch same-tier): speed_ratio 仅在本批 "
        f"{len(batch.members)} 个成员内有效，禁止跨批次横比。"
        f" 最快={batch.fastest_member} ({batch.fastest_elapsed_s:.0f}s)。_"
        if batch.fastest_elapsed_s is not None
        else "\n\n_本批无完整事件对，elapsed 未计算；需检查 session 日志事件解析。_"
    )
    return header + "\n".join(rows) + note
