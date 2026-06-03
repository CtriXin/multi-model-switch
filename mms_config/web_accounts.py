# -*- coding: utf-8 -*-
"""Account summary and draft helpers for the MMS config WebUI."""

from __future__ import annotations

import copy
from typing import Any


def _backend():
    from mms_config import web

    return web


def _call_backend(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(_backend(), name)(*args, **kwargs)


def _safe_text(value: Any) -> str:
    return _call_backend("_safe_text", value)


def _truthy(value: Any, default: bool = False) -> bool:
    return _call_backend("_truthy", value, default)


def _normalize_priority(value: Any, default: int = 100) -> int:
    return _call_backend("_normalize_priority", value, default)


def _normalize_family_priority_overrides(value: Any) -> dict[str, int]:
    return _call_backend("_normalize_family_priority_overrides", value)


def _usage_summary(runtime_kind: str, runtime_id: str) -> dict[str, Any]:
    return _call_backend("_usage_summary", runtime_kind, runtime_id)


def _runtime_usage_rows(runtime_kind: str, runtime_id: str) -> list[dict[str, Any]]:
    return _call_backend("_runtime_usage_rows", runtime_kind, runtime_id)


def _mapping_digest(payload: Any) -> str:
    return _call_backend("_mapping_digest", payload)


def _allowed_clis() -> tuple[str, ...]:
    return tuple(getattr(_backend(), "_ALLOWED_CLIS"))


def _account_summary(account: dict[str, Any], *, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    account = account if isinstance(account, dict) else {}
    defaults = defaults if isinstance(defaults, dict) else {}
    account_id = _safe_text(account.get("id"))
    cli_name = _safe_text(account.get("cli"))
    is_default = bool(cli_name and defaults.get(cli_name) == account_id)
    auth_mode = _safe_text(account.get("auth_mode") or account.get("mode") or "oauth")
    is_claude = cli_name == "claude"
    return {
        "id": account_id,
        "name": _safe_text(account.get("name") or account_id),
        "cli": cli_name,
        "enabled": account.get("enabled", True) is not False,
        "priority": _normalize_priority(account.get("priority", 100)),
        "family_priority_overrides": _normalize_family_priority_overrides(account.get("family_priority_overrides")),
        "claude_1m_mode": _safe_text(account.get("claude_1m_mode") or "auto") or "auto",
        "auth_mode": auth_mode,
        "is_default": is_default,
        "default_label": cli_name.upper() if is_default else "备选",
        "home_dir_configured": bool(_safe_text(account.get("home_dir"))),
        "proxy_configured": bool(_safe_text(account.get("proxy"))),
        "no_proxy_configured": bool(_safe_text(account.get("no_proxy"))),
        "timezone": _safe_text(account.get("timezone")),
        "note": _safe_text(account.get("note")),
        "status": "configured",
        "is_claude_human_only": is_claude,
        "webui_write_policy": "claude_human_only_locked" if is_claude else "draft_review_confirmed_save",
        "usage": _usage_summary("account", account_id),
        "usage_rows": _runtime_usage_rows("account", account_id),
    }


def _account_defaults(cfg: dict[str, Any]) -> dict[str, str]:
    account_cfg = cfg.get("account") if isinstance(cfg.get("account"), dict) else {}
    raw_defaults = account_cfg.get("defaults") if isinstance(account_cfg.get("defaults"), dict) else account_cfg
    result: dict[str, str] = {}
    if isinstance(raw_defaults, dict):
        for cli, account_id in raw_defaults.items():
            cli_name = _safe_text(cli).lower()
            value = _safe_text(account_id)
            if cli_name and value:
                result[cli_name] = value
    return result


def _account_summaries(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = _account_defaults(cfg)
    rows = []
    for account in cfg.get("accounts") if isinstance(cfg.get("accounts"), list) else []:
        if isinstance(account, dict):
            rows.append(_account_summary(account, defaults=defaults))
    return sorted(
        rows,
        key=lambda item: (
            0 if item.get("is_default") else 1,
            item.get("cli") or "",
            item.get("name") or item.get("id") or "",
        ),
    )


def _account_by_id(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    accounts = cfg.get("accounts") if isinstance(cfg.get("accounts"), list) else []
    return {
        _safe_text(account.get("id")): account
        for account in accounts
        if isinstance(account, dict) and _safe_text(account.get("id"))
    }


def _account_review_fields(account: dict[str, Any] | None) -> dict[str, Any]:
    account = account if isinstance(account, dict) else {}
    return {
        "name": _safe_text(account.get("name")),
        "enabled": account.get("enabled", True) is not False,
        "priority": _normalize_priority(account.get("priority", 100)),
        "family_priority_overrides": _normalize_family_priority_overrides(account.get("family_priority_overrides")),
        "claude_1m_mode": _safe_text(account.get("claude_1m_mode") or "auto") or "auto",
        "timezone": _safe_text(account.get("timezone")),
        "note": _safe_text(account.get("note")),
    }


def _copy_existing_account(existing: dict[str, Any], account_payload: dict[str, Any]) -> dict[str, Any]:
    account = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    if "name" in account_payload:
        name = _safe_text(account_payload.get("name"))
        current_name = _safe_text(account.get("name") or account.get("id"))
        if name and name != current_name:
            account["name"] = name
    if "enabled" in account_payload:
        enabled = _truthy(account_payload.get("enabled"), True)
        if enabled != (account.get("enabled", True) is not False):
            account["enabled"] = enabled
    if "priority" in account_payload:
        priority = _normalize_priority(account_payload.get("priority"), _normalize_priority(account.get("priority", 100)))
        if priority != _normalize_priority(account.get("priority", 100)):
            account["priority"] = priority
    if "family_priority_overrides" in account_payload:
        overrides = _normalize_family_priority_overrides(account_payload.get("family_priority_overrides"))
        if overrides:
            account["family_priority_overrides"] = overrides
        else:
            account.pop("family_priority_overrides", None)
    if "claude_1m_mode" in account_payload:
        mode = _safe_text(account_payload.get("claude_1m_mode") or "auto")
        normalized = mode if mode in {"auto", "enable", "disable"} else "auto"
        if normalized != "auto" or "claude_1m_mode" in account:
            account["claude_1m_mode"] = normalized
        else:
            account.pop("claude_1m_mode", None)
    if "timezone" in account_payload:
        timezone_name = _safe_text(account_payload.get("timezone"))
        if timezone_name:
            account["timezone"] = timezone_name
        else:
            account.pop("timezone", None)
    if "note" in account_payload:
        note = _safe_text(account_payload.get("note"))
        if note:
            account["note"] = note
        else:
            account.pop("note", None)
    return account


def _apply_account_draft(
    *,
    current_cfg: dict[str, Any],
    next_cfg: dict[str, Any],
    draft: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    has_accounts_payload = isinstance(draft.get("accounts"), list)
    has_defaults_payload = isinstance(draft.get("account_defaults"), dict)
    if not has_accounts_payload and not has_defaults_payload:
        return

    current_accounts = current_cfg.get("accounts") if isinstance(current_cfg.get("accounts"), list) else []
    existing_by_id = _account_by_id(current_cfg)
    next_accounts = copy.deepcopy(current_accounts)
    next_by_id = _account_by_id({"accounts": next_accounts})

    if has_accounts_payload:
        seen_payload_ids: set[str] = set()
        for item in draft.get("accounts") or []:
            if not isinstance(item, dict):
                continue
            account_id = _safe_text(item.get("original_id") or item.get("id"))
            if not account_id:
                continue
            if account_id in seen_payload_ids:
                errors.append(f"账号 ID 重复: {account_id}")
                continue
            seen_payload_ids.add(account_id)
            existing = existing_by_id.get(account_id)
            if not existing:
                errors.append(f"账号 {account_id} 不在当前配置中；WebUI 当前不创建新账号。")
                continue
            updated = _copy_existing_account(existing, item)
            if _safe_text(existing.get("cli")).lower() == "claude" and _mapping_digest(_account_review_fields(existing)) != _mapping_digest(_account_review_fields(updated)):
                errors.append(f"Claude account `{account_id}` 是 human-only；WebUI 当前只允许查看和生成 review，不会保存 Claude account 编辑。")
                continue
            next_by_id[account_id] = updated

        next_accounts = [next_by_id.get(_safe_text(account.get("id")), account) for account in next_accounts if isinstance(account, dict)]
        next_cfg["accounts"] = next_accounts

    if has_defaults_payload:
        defaults = _account_defaults(current_cfg)
        payload_defaults = draft.get("account_defaults") if isinstance(draft.get("account_defaults"), dict) else {}
        accounts_after = _account_by_id({"accounts": next_cfg.get("accounts") if isinstance(next_cfg.get("accounts"), list) else current_accounts})
        for cli, raw_account_id in payload_defaults.items():
            cli_name = _safe_text(cli).lower()
            if cli_name not in _allowed_clis():
                warnings.append(f"账号默认 CLI 不支持: {cli_name}")
                continue
            account_id = _safe_text(raw_account_id)
            before_default = defaults.get(cli_name, "")
            if cli_name == "claude" and before_default != account_id:
                errors.append("Claude 默认账号是 human-only；WebUI 当前不会保存 Claude account default 变化。")
                continue
            if not account_id:
                defaults.pop(cli_name, None)
                continue
            account = accounts_after.get(account_id)
            if not account:
                errors.append(f"默认账号 {cli_name} -> {account_id} 不存在。")
                continue
            if _safe_text(account.get("cli")).lower() != cli_name:
                errors.append(f"默认账号 {cli_name} -> {account_id} 的 CLI 不匹配。")
                continue
            defaults[cli_name] = account_id
        if defaults:
            next_cfg["account"] = {"defaults": defaults}
        else:
            next_cfg.pop("account", None)
