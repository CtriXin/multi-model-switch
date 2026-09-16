"""Bounded backoff retry for Bot infrastructure failures.

A retry may only replay work that Pi never received. A task that has entered
``starting`` and then keeps failing is retried; anything after real execution
began is reported to the user instead of being replayed, because the first
attempt may already have produced side effects.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

RETRY_DELAYS = (30, 120, 480)
RETRY_LIMIT = len(RETRY_DELAYS)

TRANSIENT_CODES = {
    # Infrastructure is not ready or temporarily occupied. Nothing was sent
    # to Pi yet, so replaying the launch is safe.
    "BOT_EXECUTOR_UNAVAILABLE",
    "BOT_SESSION_BUSY",
    "BOT_ENDPOINT_UNAVAILABLE",
}
# Codes that are only replayable when the transport status says the launch
# seam itself failed; the same code with another status stays permanent.
STATUS_TRANSIENT_CODES = {"LAUNCH_FAILED"}
PERMANENT_CODES = {
    # A user or configuration decision, not a hiccup.
    "BOT_MODEL_REQUIRED",
    "BOT_GLOBAL_WORKSPACE_REQUIRED",
    "BOT_NOT_FOUND",
    "BOT_TASK_CANCELLED",
    "INVALID_REQUEST",
    "LAUNCH_RESOLVE_FAILED",
    # Delivery may or may not have happened; never replay an unconfirmed
    # prompt or send.
    "RPC_UNCONFIRMED",
    "RPC_TIMEOUT",
    "SEND_FAILED",
}
_TRANSIENT_HINTS = (
    "connection refused", "connection reset", "connection aborted", "connection error",
    "timed out", "timeout", "econnrefused", "econnreset", "etimedout", "ehostunreach",
    "temporarily unavailable", "service unavailable", "bad gateway", "gateway timeout",
    "rate limit", "too many requests", "overloaded", "try again",
    "连接被拒绝", "连接重置", "连接超时", "超时", "暂时不可用", "稍后重试", "服务暂不可用",
    "进程未启动", "未启动就退出", "failed to start", "exited before",
)
_PERMANENT_HINTS = (
    "用户取消", "已取消", "cancelled", "canceled",
    "模型拒绝", "拒绝执行", "refused by the model", "not allowed",
    "没有收到结果", "未收到结果", "正常结束但没有结果",
)
_STATUS = re.compile(r"(?<!\d)(429|502|503|504)(?!\d)")


def classify(error_code: str | None, message: str = "", detail: str = "",
             status: int | None = None) -> str:
    """Return ``transient`` or ``permanent`` for a failed launch.

    Unknown failures are permanent: an unrecognized error must not be
    replayed silently.
    """
    code = str(error_code or "").strip().upper()
    if code in PERMANENT_CODES:
        return "permanent"
    if code in TRANSIENT_CODES:
        return "transient"
    text = f"{error_code or ''} {message or ''} {detail or ''}".casefold()
    if any(hint in text for hint in _TRANSIENT_HINTS) or _STATUS.search(text):
        return "transient"
    if (code in STATUS_TRANSIENT_CODES and isinstance(status, int)
            and status in (429, 502, 503, 504) and "不存在" not in text):
        return "transient"
    if any(hint in text for hint in _PERMANENT_HINTS):
        return "permanent"
    return "permanent"


def _short(text, limit=180) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return value[:limit]


def next_delay(count: int) -> int:
    """Backoff in seconds for the given number of already scheduled attempts."""
    return RETRY_DELAYS[min(max(int(count), 0), RETRY_LIMIT - 1)]


def schedule(task: dict, message: str, *, error_code: str = "", detail: str = "",
             moment: datetime | None = None) -> dict | None:
    """Record the next retry on a not-yet-started task.

    Mutates the task back to ``queued`` with ``retry.nextAt`` set and returns
    the retry record, or ``None`` when the three-attempt budget is used up.
    """
    retry = dict(task.get("retry") or {})
    count = int(retry.get("count") or 0)
    if count >= RETRY_LIMIT:
        return None
    attempt = count + 1
    current = moment or datetime.now(timezone.utc)
    delay = next_delay(count)
    record = {
        "count": attempt,
        "nextAt": (current + timedelta(seconds=delay)).isoformat(timespec="seconds"),
        "lastError": _short(message),
        "lastErrorCode": str(error_code or ""),
        "history": list(retry.get("history") or []),
    }
    record["history"].append({
        "attempt": attempt,
        "at": current.isoformat(timespec="seconds"),
        "delaySeconds": delay,
        "error": _short(message),
        "errorCode": str(error_code or ""),
        "detail": _short(detail, 300),
    })
    task["retry"] = record
    task.update(
        status="queued", waitReason=None, token="",
        queueReason=f"等待重试（第 {attempt} 次，原因：{_short(message, 60)}）",
        updatedAt=current.isoformat(timespec="milliseconds"),
    )
    return record


def exhausted_message(task: dict, message: str) -> str:
    """Explain every finished retry attempt in the final failure message."""
    history = list((task.get("retry") or {}).get("history") or [])
    lines = ["三次自动重试均失败："]
    for item in history:
        code = f"[{item.get('errorCode')}] " if item.get("errorCode") else ""
        lines.append(f"{item.get('attempt')}) {item.get('at')} {code}{item.get('error')}")
    lines.append(f"最终失败：{message}")
    return "\n".join(lines)
