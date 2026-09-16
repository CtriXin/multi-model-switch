"""Periodic Bot schedules: durable entities independent from a task.

A schedule is a small rule (``once`` / ``interval`` / ``daily`` / ``weekly``)
plus the prompt to run.  Every calculation here is a pure function over plain
data so the scheduler thread in :mod:`mms_web.bots` keeps only thin wiring and
the timing rules stay unit-testable.  No cron expressions: users say "every
three hours" or "every day at 9", and those four shapes cover that.

Timezone arithmetic uses the standard library ``zoneinfo`` only.  A schedule
always stores its IANA name, otherwise "daily 09:00" drifts across a daylight
saving change.
"""
from __future__ import annotations

import os
import re
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import WebError

MIN_INTERVAL_SECONDS = 300
MAX_SCHEDULES_PER_BOT = 20
RECENT_TASK_LIMIT = 10
MAX_PROMPT_CHARS = 32000
KINDS = ("once", "interval", "daily", "weekly")
OVERLAP_POLICIES = ("skip", "queue")
CREATORS = ("user", "bot")

_LOCAL_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_EVERY_RE = re.compile(r"^(\d{1,9})([hms]?)$")
_FIXED_OFFSET_RE = re.compile(r"^UTC([+-])(\d{2}):(\d{2})$")
_ZONEINFO_ROOTS = ("/var/db/timezone/zoneinfo", "/usr/share/zoneinfo", "/usr/lib/zoneinfo", "/etc/zoneinfo")
_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
             "周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}


# --------------------------------------------------------------------- helpers
def _parse_iso(value, code: str, message: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise WebError(code, message, 400) from None


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _zone(name: str):
    fixed = _FIXED_OFFSET_RE.fullmatch(str(name or ""))
    if fixed:
        sign = 1 if fixed.group(1) == "+" else -1
        delta = timedelta(hours=int(fixed.group(2)), minutes=int(fixed.group(3)))
        return timezone(sign * delta)
    return ZoneInfo(name)


def _iana_from_path(path: str) -> str | None:
    for root in _ZONEINFO_ROOTS:
        if path.startswith(root + "/"):
            name = path[len(root) + 1:]
            try:
                ZoneInfo(name)
                return name
            except (ZoneInfoNotFoundError, ValueError):
                return None
    return None


def local_timezone_name() -> str:
    """The machine's IANA timezone, or a fixed ``UTC±HH:MM`` fallback.

    There is no stdlib API for "the local IANA name", so try the environment,
    the ``/etc/localtime`` symlink and the platform name before falling back to
    a fixed offset.  The result is always written back into the schedule, so a
    later read on another machine still sees an explicit timezone.
    """
    candidate = os.environ.get("TZ", "").strip()
    if candidate:
        try:
            _zone(candidate)
            return candidate
        except (ZoneInfoNotFoundError, ValueError):
            pass
    try:
        resolved = str(os.path.realpath("/etc/localtime"))
    except OSError:
        resolved = ""
    if resolved and resolved != "/etc/localtime":
        name = _iana_from_path(resolved)
        if name:
            return name
    platform_name = time.tzname[0] if time.tzname else ""
    if platform_name:
        try:
            _zone(platform_name)
            return platform_name
        except (ZoneInfoNotFoundError, ValueError):
            pass
    offset = datetime.now().astimezone().utcoffset() or timedelta(0)
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"UTC{sign}{total // 3600:02d}:{total % 3600 // 60:02d}"


# --------------------------------------------------------------- rule parsing
def normalize_timezone(value: str | None) -> str:
    """Validate an IANA name, defaulting to (and always storing) the machine one."""
    if value in (None, ""):
        return local_timezone_name()
    if not isinstance(value, str) or len(value) > 100:
        raise WebError("INVALID_TIMEZONE", "时区必须是 IANA 名称，例如 Asia/Singapore。", 400)
    name = value.strip()
    if not name:
        return local_timezone_name()
    try:
        _zone(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise WebError("INVALID_TIMEZONE",
                       f"无法识别时区 {name[:40]}，请使用 IANA 名称，例如 Asia/Singapore。", 400) from None
    return name


def parse_every(value) -> int:
    """Parse ``3h`` / ``180m`` / ``10800s`` / a bare second count."""
    match = _EVERY_RE.fullmatch(str(value or "").strip().lower())
    if not match:
        raise WebError("INVALID_SCHEDULE_RULE", "间隔要写成 3h、180m、10800s 或直接的秒数。", 400)
    seconds = int(match.group(1)) * {"h": 3600, "m": 60, "s": 1}[match.group(2) or "s"]
    if seconds <= 0:
        raise WebError("INVALID_SCHEDULE_RULE", "间隔必须大于 0 秒。", 400)
    return seconds


def parse_weekday(value) -> int:
    """Parse ``mon``…``sun`` (also ``周一``…``周日``) into 0=Monday…6=Sunday."""
    text = str(value or "").strip().lower()
    if text in _WEEKDAYS:
        return _WEEKDAYS[text]
    raise WebError("INVALID_SCHEDULE_RULE", "weekday 要写成 mon…sun（0=周一，6=周日）。", 400)


def normalize_rule(rule: dict) -> dict:
    """Validate and normalize one of the four supported rule shapes.

    An unknown ``kind`` is an error, never silently treated as ``once``; adding
    a ``cron`` kind later means extending this function and nothing else.
    """
    if not isinstance(rule, dict):
        raise WebError("INVALID_SCHEDULE_RULE", "定时规则必须是对象。", 400)
    kind = rule.get("kind")
    if kind == "once":
        at = _parse_iso(rule.get("at"), "INVALID_SCHEDULE_RULE", "once 定时需要包含时区的 ISO8601 时间。")
        return {"kind": "once", "at": _iso(at)}
    if kind == "interval":
        every = rule.get("everySeconds")
        if type(every) is not int or every <= 0:
            raise WebError("INVALID_SCHEDULE_RULE", "everySeconds 必须是正整数秒。", 400)
        if every < MIN_INTERVAL_SECONDS:
            raise WebError("SCHEDULE_INTERVAL_TOO_SHORT", "定时间隔最短 5 分钟。", 400)
        return {"kind": "interval", "everySeconds": every}
    if kind in {"daily", "weekly"}:
        at_local = rule.get("atLocalTime")
        local = at_local.strip() if isinstance(at_local, str) else ""
        if not _LOCAL_TIME_RE.fullmatch(local):
            raise WebError("INVALID_SCHEDULE_RULE", "atLocalTime 必须是 HH:MM（24 小时制）。", 400)
        normalized = {"kind": kind, "atLocalTime": local}
        if kind == "weekly":
            weekday = rule.get("weekday")
            if type(weekday) is not int or not 0 <= weekday <= 6:
                raise WebError("INVALID_SCHEDULE_RULE", "weekday 必须是 0（周一）到 6（周日）的整数。", 400)
            normalized["weekday"] = weekday
        return normalized
    raise WebError("INVALID_SCHEDULE_RULE",
                   f"不支持的定时类型 {str(kind)[:40] or '（空）'}；支持 once、interval、daily、weekly。", 400)


# ----------------------------------------------------------------- next times
def _local_instant(wall: datetime, zone) -> datetime:
    """Resolve a naive local wall time to UTC, DST-aware.

    A nonexistent local time (spring forward) resolves to the transition
    instant, i.e. the first valid local time after the gap.  An ambiguous local
    time (fall back) resolves to its first occurrence (``fold=0``).
    """
    candidate = wall.replace(tzinfo=zone)
    first = candidate.astimezone(timezone.utc)
    if first.astimezone(zone).replace(tzinfo=None) == wall:
        return first
    before = wall.replace(tzinfo=zone, fold=0).utcoffset()
    after = wall.replace(tzinfo=zone, fold=1).utcoffset()
    if before == after:
        return first
    low = min(wall.replace(tzinfo=zone, fold=0).astimezone(timezone.utc),
              wall.replace(tzinfo=zone, fold=1).astimezone(timezone.utc))
    high = max(wall.replace(tzinfo=zone, fold=0).astimezone(timezone.utc),
               wall.replace(tzinfo=zone, fold=1).astimezone(timezone.utc))
    while high - low > timedelta(seconds=1):
        middle = low + (high - low) / 2
        if middle.astimezone(zone).utcoffset() == after:
            high = middle
        else:
            low = middle
    return high.replace(microsecond=0)


def next_run_at(rule: dict, timezone_name: str, *, after: datetime,
                previous: datetime | None = None) -> datetime | None:
    """First run strictly after ``after``; ``None`` only for a spent ``once``.

    ``previous`` is the nominal time that was just handled, not the wall clock
    moment it actually ran.  ``interval`` advances from it, so a late tick never
    accumulates drift.
    """
    kind = rule["kind"]
    if kind == "once":
        at = _parse_iso(rule["at"], "INVALID_SCHEDULE_RULE", "once 定时需要包含时区的 ISO8601 时间。")
        return at if at > after else None
    if kind == "interval":
        every = int(rule["everySeconds"])
        base = previous or after
        if base <= after:
            steps = int((after - base).total_seconds() // every) + 1
            base = base + timedelta(seconds=every * steps)
        return base
    if kind not in {"daily", "weekly"}:
        raise WebError("INVALID_SCHEDULE_RULE", "不支持的定时类型。", 400)
    zone = _zone(timezone_name)
    hour, minute = (int(part) for part in rule["atLocalTime"].split(":"))
    local = after.astimezone(zone)
    wall = local.replace(tzinfo=None, second=0, microsecond=0)
    candidate = wall.replace(hour=hour, minute=minute)
    if kind == "weekly":
        candidate += timedelta(days=(int(rule["weekday"]) - wall.weekday()) % 7)
    if candidate <= wall:
        candidate += timedelta(days=1 if kind == "daily" else 7)
    return _local_instant(candidate, zone)


def advance(schedule: dict, *, now: datetime) -> tuple[dict, int]:
    """Move one schedule past ``now`` and report how many runs were skipped.

    The only entry point for both catching up and moving on: a run missed by
    less than one cycle is fired now (the returned schedule keeps the original
    cadence); more than that is dropped and only counted, so an offline Pilot
    never replays a backlog.
    """
    updated = deepcopy(schedule)
    due = _parse_iso(updated.get("nextRunAt"), "INVALID_SCHEDULE_RULE", "nextRunAt 必须是包含时区的 ISO8601 时间。") \
        if updated.get("nextRunAt") else None
    if due is None or due > now:
        return updated, 0
    rule = updated["rule"]
    if rule["kind"] == "once":
        updated["nextRunAt"] = None
        return updated, 0
    if rule["kind"] == "interval":
        every = int(rule["everySeconds"])
        skipped = int((now - due).total_seconds() // every)
        updated["nextRunAt"] = _iso(due + timedelta(seconds=every * (skipped + 1)))
        return updated, skipped
    nxt = next_run_at(rule, updated["timezone"], after=due, previous=due)
    skipped = 0
    while nxt is not None and nxt <= now:
        skipped += 1
        nxt = next_run_at(rule, updated["timezone"], after=nxt, previous=nxt)
    updated["nextRunAt"] = _iso(nxt)
    return updated, skipped


# ------------------------------------------------------------------ lifecycle
def sanitize_schedules(raw) -> dict:
    """Keep stored rows usable without letting one bad row brick the loop.

    A row whose rule or timezone no longer resolves is kept but parked:
    disabled with no next run, so the UI can still show and fix it instead of
    silently losing a user's schedule.
    """
    if not isinstance(raw, dict):
        return {}
    clean = {}
    for key, row in raw.items():
        if not isinstance(row, dict) or not isinstance(row.get("botId"), str):
            continue
        if not isinstance(row.get("recentTaskIds"), list):
            row["recentTaskIds"] = []
        try:
            normalize_rule(row.get("rule"))
            normalize_timezone(row.get("timezone"))
            if row.get("nextRunAt"):
                _parse_iso(row["nextRunAt"], "INVALID_SCHEDULE_RULE", "")
        except (WebError, TypeError, ValueError):
            row.update(enabled=False, nextRunAt=None,
                       lastSkip={"at": row.get("updatedAt"), "reason": "invalid", "skipped": 0})
        clean[str(key)] = row
    return clean


def is_due(schedule: dict, now: datetime) -> bool:
    """Whether a stored ``nextRunAt`` is at or before ``now``."""
    due = str(schedule.get("nextRunAt") or "")
    if not due:
        return False
    try:
        return _parse_iso(due, "INVALID_SCHEDULE_RULE", "") <= now
    except WebError:
        return False


def validate_schedule(payload, existing_count: int) -> None:
    if not isinstance(payload, dict):
        raise WebError("INVALID_REQUEST", "定时内容必须是对象。", 400)
    if int(existing_count) >= MAX_SCHEDULES_PER_BOT:
        raise WebError("SCHEDULE_LIMIT", "一个 Bot 最多 20 条定时。", 409)
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        raise WebError("INVALID_REQUEST", f"prompt 不能为空且长度须在 {MAX_PROMPT_CHARS} 字以内。", 400)
    if payload.get("overlapPolicy", "skip") not in OVERLAP_POLICIES:
        raise WebError("INVALID_REQUEST", "overlapPolicy 必须是 skip 或 queue。", 400)
    normalize_rule(payload.get("rule"))
    normalize_timezone(payload.get("timezone"))


def build_schedule(bot_id: str, payload: dict, *, existing_count: int, now: datetime,
                   created_by: str | None = None, schedule_id: str | None = None) -> dict:
    validate_schedule(payload, existing_count)
    rule = normalize_rule(payload.get("rule"))
    zone = normalize_timezone(payload.get("timezone"))
    creator = created_by or payload.get("createdBy") or "user"
    if creator not in CREATORS:
        raise WebError("INVALID_REQUEST", "createdBy 必须是 user 或 bot。", 400)
    stamp = now.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    return {
        "id": schedule_id or ("sch_" + uuid4().hex[:16]),
        "botId": bot_id,
        "prompt": str(payload["prompt"]).strip(),
        "rule": rule,
        "timezone": zone,
        "enabled": True,
        "overlapPolicy": payload.get("overlapPolicy", "skip"),
        # A once rule that is already in the past still fires on the next tick.
        "nextRunAt": rule["at"] if rule["kind"] == "once" else _iso(next_run_at(rule, zone, after=now)),
        "lastRunAt": None,
        "lastTaskId": None,
        "recentTaskIds": [],
        "lastSkip": None,
        "createdBy": creator,
        "createdAt": stamp,
        "updatedAt": stamp,
    }


def apply_update(schedule: dict, payload: dict, *, now: datetime) -> dict:
    """Validate an edit (prompt / rule / timezone / overlapPolicy)."""
    if not isinstance(payload, dict):
        raise WebError("INVALID_REQUEST", "定时内容必须是对象。", 400)
    updated = deepcopy(schedule)
    if "prompt" in payload:
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
            raise WebError("INVALID_REQUEST", f"prompt 不能为空且长度须在 {MAX_PROMPT_CHARS} 字以内。", 400)
        updated["prompt"] = prompt.strip()
    if "overlapPolicy" in payload:
        if payload["overlapPolicy"] not in OVERLAP_POLICIES:
            raise WebError("INVALID_REQUEST", "overlapPolicy 必须是 skip 或 queue。", 400)
        updated["overlapPolicy"] = payload["overlapPolicy"]
    if "rule" in payload or "timezone" in payload:
        rule = normalize_rule(payload.get("rule") or updated["rule"])
        zone = normalize_timezone(payload.get("timezone", updated["timezone"]))
        updated["rule"], updated["timezone"] = rule, zone
        # An edited rule restarts from now; it never inherits a stale due time.
        updated["nextRunAt"] = rule["at"] if rule["kind"] == "once" else _iso(next_run_at(rule, zone, after=now))
    updated["updatedAt"] = now.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    return updated
