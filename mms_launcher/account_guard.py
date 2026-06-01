"""Account guard helpers for MMS launcher sessions."""

from __future__ import annotations

import os
from urllib.parse import urlsplit


def claude_account_guard_entry(state, account_id):
    if not isinstance(state, dict):
        state = {}
    accounts = state.setdefault("accounts", {})
    key = str(account_id or "").strip() or "_anonymous"
    entry = accounts.get(key)
    if not isinstance(entry, dict):
        entry = {}
        accounts[key] = entry
    return accounts, key, entry


def count_live_session_dirs(sessions_dir, *, session_home_is_active_fn):
    if not os.path.isdir(sessions_dir):
        return 0
    alive = 0
    for name in os.listdir(sessions_dir):
        session_home = os.path.join(sessions_dir, str(name))
        if not os.path.isdir(session_home):
            continue
        if session_home_is_active_fn(session_home):
            alive += 1
    return alive


def proxy_fingerprint(proxy_url):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return "direct"
    try:
        parsed = urlsplit(proxy_url)
    except Exception:
        return proxy_url
    scheme = parsed.scheme or "proxy"
    host = parsed.hostname or "unknown"
    port = f":{parsed.port}" if parsed.port else ""
    auth = "+auth" if parsed.username or parsed.password else ""
    return f"{scheme}://{host}{port}{auth}"


def account_guard_profile(runtime, *, runtime_force_ipv4_fn, default_account_timezone):
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    return {
        "proxy_fingerprint": proxy_fingerprint(runtime.get("proxy")),
        "timezone": str(runtime.get("timezone") or default_account_timezone).strip() or default_account_timezone,
        "force_ipv4": bool(runtime_force_ipv4_fn(runtime)),
        "no_proxy": no_proxy,
        "no_proxy_set": bool(no_proxy),
    }


def build_account_guard_report(
    account,
    *,
    read_account_guard_state_fn,
    count_live_session_dirs_fn,
    claude_account_guard_entry_fn,
    account_guard_profile_fn,
):
    account_id = str(account.get("id") or "").strip()
    home_dir = os.path.expanduser(str(account.get("home_dir") or "").strip())
    sessions_dir = os.path.join(home_dir, "s") if home_dir else ""
    active_before = count_live_session_dirs_fn(sessions_dir)
    active_after = active_before + 1 if home_dir else active_before

    state = read_account_guard_state_fn()
    _accounts, _key, entry = claude_account_guard_entry_fn(state, account_id)
    previous_profile = entry.get("last_profile") if isinstance(entry.get("last_profile"), dict) else {}
    current_profile = account_guard_profile_fn(account)

    drift_fields = []
    drift_labels = {
        "proxy_fingerprint": "proxy",
        "timezone": "timezone",
        "force_ipv4": "ipv4",
        "no_proxy": "no_proxy",
    }
    if previous_profile:
        for key, label in drift_labels.items():
            previous_value = previous_profile.get(key)
            current_value = current_profile.get(key)
            if previous_value is None:
                continue
            if previous_value != current_value:
                drift_fields.append(label)

    consecutive_failures = 0
    try:
        consecutive_failures = max(0, int(entry.get("consecutive_failures", 0) or 0))
    except Exception:
        consecutive_failures = 0

    score = 100
    if active_after >= 3:
        score -= 18
    elif active_after >= 2:
        score -= 8
    if "proxy" in drift_fields:
        score -= 22
    if "timezone" in drift_fields:
        score -= 10
    if "ipv4" in drift_fields:
        score -= 8
    if "no_proxy" in drift_fields:
        score -= 5
    score -= min(consecutive_failures, 3) * 12
    score = max(0, min(100, score))

    if active_after > 4:
        status = "blocked"
        blocked_reason = f"该账号当前将达到 {active_after} 个并发会话，已超过安全上限 4"
    elif score >= 85:
        status = "stable"
        blocked_reason = ""
    elif score >= 60:
        status = "watch"
        blocked_reason = ""
    else:
        status = "risky"
        blocked_reason = ""

    return {
        "account_id": account_id,
        "profile": current_profile,
        "drift_fields": drift_fields,
        "active_sessions_before": active_before,
        "active_sessions_after": active_after,
        "consecutive_failures": consecutive_failures,
        "score": score,
        "status": status,
        "blocked_reason": blocked_reason,
        "first_seen": not bool(previous_profile),
        "last_exit_code": entry.get("last_exit_code"),
    }


def claude_guard_runtime(runtime, *, real_user_path_fn):
    guard_runtime = dict(runtime or {})
    auth_mode = str(guard_runtime.get("auth_mode") or "api_key").strip() or "api_key"
    if auth_mode == "api_key" and not str(guard_runtime.get("home_dir") or "").strip():
        guard_runtime["home_dir"] = real_user_path_fn(".config", "mms", "claude-gateway")
    return guard_runtime


def format_account_guard_summary(report):
    if not isinstance(report, dict):
        return ""
    status_labels = {
        "stable": "stable",
        "watch": "watch",
        "risky": "risky",
        "blocked": "blocked",
    }
    drift = report.get("drift_fields") or []
    drift_label = "first run" if report.get("first_seen") else ("stable" if not drift else ",".join(drift))
    parts = [
        f"账号守护 {status_labels.get(report.get('status'), 'unknown')}",
        f"score {report.get('score', 0)}",
        f"sessions {report.get('active_sessions_after', 0)}",
        f"profile {drift_label}",
    ]
    failures = int(report.get("consecutive_failures", 0) or 0)
    if failures:
        parts.append(f"failures {failures}")
    return " | ".join(parts)


def persist_account_guard_launch(
    account_id,
    report,
    *,
    session_home="",
    account_guard_state_path_fn,
    locked_state_file_fn,
    load_json_dict_unlocked_fn,
    claude_account_guard_entry_fn,
    guard_utc_now_fn,
    atomic_write_json_fn,
):
    path = account_guard_state_path_fn()
    with locked_state_file_fn(path):
        state = load_json_dict_unlocked_fn(path)
        _accounts, _key, entry = claude_account_guard_entry_fn(state, account_id)
        launch_count = 0
        try:
            launch_count = int(entry.get("launch_count", 0) or 0)
        except Exception:
            launch_count = 0
        entry.update(
            {
                "launch_count": launch_count + 1,
                "last_launch_at": guard_utc_now_fn(),
                "last_profile": dict((report or {}).get("profile") or {}),
                "last_score": int((report or {}).get("score", 0) or 0),
                "last_status": str((report or {}).get("status") or ""),
                "last_drift_fields": list((report or {}).get("drift_fields") or []),
                "last_active_sessions": int((report or {}).get("active_sessions_after", 0) or 0),
                "last_session_home": str(session_home or ""),
            }
        )
        atomic_write_json_fn(path, state, mode=0o600)


def record_account_guard_finalize(
    account_id,
    *,
    exit_code=None,
    stale_cleanup=False,
    account_guard_state_path_fn,
    locked_state_file_fn,
    load_json_dict_unlocked_fn,
    claude_account_guard_entry_fn,
    guard_utc_now_fn,
    atomic_write_json_fn,
):
    account_id = str(account_id or "").strip()
    if not account_id:
        return
    path = account_guard_state_path_fn()
    with locked_state_file_fn(path):
        state = load_json_dict_unlocked_fn(path)
        _accounts, _key, entry = claude_account_guard_entry_fn(state, account_id)
        entry["last_exit_at"] = guard_utc_now_fn()
        entry["last_exit_code"] = exit_code
        if stale_cleanup or exit_code is None:
            atomic_write_json_fn(path, state, mode=0o600)
            return
        failures = 0
        try:
            failures = int(entry.get("consecutive_failures", 0) or 0)
        except Exception:
            failures = 0
        entry["consecutive_failures"] = 0 if int(exit_code) == 0 else max(0, failures) + 1
        atomic_write_json_fn(path, state, mode=0o600)
