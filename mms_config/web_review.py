# -*- coding: utf-8 -*-
"""Save review summary helpers for the MMS config WebUI."""

from __future__ import annotations

import json
from typing import Any


def _backend():
    from mms_config import web

    return web


def _safe_text(value: Any) -> str:
    return _backend()._safe_text(value)


def _sanitize_for_output(value: Any) -> Any:
    return _backend()._sanitize_for_output(value)


def _normalize_priority(value: Any) -> int:
    return _backend()._normalize_priority(value)


def _normalize_family_priority_overrides(value: Any) -> dict[str, int]:
    return _backend()._normalize_family_priority_overrides(value)


def _normalize_model_list(value: Any) -> list[str]:
    return _backend()._normalize_model_list(value)


def _normalize_agent_model_overrides(value: Any) -> dict[str, Any]:
    return _backend()._normalize_agent_model_overrides(value)


def _normalize_opencode_agent_roster(value: Any, *, profile_id: str = "agent") -> dict[str, Any]:
    return _backend()._normalize_opencode_agent_roster(value, profile_id=profile_id)


def _account_by_id(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _backend()._account_by_id(cfg)


def _account_defaults(cfg: dict[str, Any]) -> dict[str, str]:
    return _backend()._account_defaults(cfg)


def _account_review_fields(account: dict[str, Any]) -> dict[str, Any]:
    return _backend()._account_review_fields(account)


def _provider_urls(provider: dict[str, Any] | None) -> dict[str, str]:
    return _backend()._provider_urls(provider)


def _provider_by_id(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _backend()._provider_by_id(cfg)


def _provider_default_id(cfg: dict[str, Any]) -> str:
    return _backend()._provider_default_id(cfg)


def _mapping_digest(payload: Any) -> str:
    return _backend()._mapping_digest(payload)


def build_review_summary(
    current_cfg: dict[str, Any],
    next_cfg: dict[str, Any],
    policy_before: dict[str, Any],
    policy_after: dict[str, Any],
    credential_updates: list[dict[str, str]],
) -> dict[str, Any]:
    """Build a human-readable save review; raw diff remains the audit detail."""
    items: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    before_providers = _provider_by_id(current_cfg)
    after_providers = _provider_by_id(next_cfg)
    before_ids = set(before_providers)
    after_ids = set(after_providers)

    def add_item(kind: str, title: str, detail: str, *, provider_id: str = "", level: str = "info", meta: dict[str, Any] | None = None) -> None:
        items.append({
            "kind": kind,
            "level": level,
            "title": title,
            "detail": detail,
            "provider_id": provider_id,
            "meta": meta or {},
        })

    def add_risk(risk_id: str, title: str, detail: str, *, level: str = "warn", provider_id: str = "") -> None:
        risks.append({
            "id": risk_id,
            "level": level,
            "title": title,
            "detail": detail,
            "provider_id": provider_id,
        })

    def field_changes(before: dict[str, Any], after: dict[str, Any], labels: dict[str, str]) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        for key in labels:
            before_value = before.get(key)
            after_value = after.get(key)
            if _mapping_digest({key: before_value}) == _mapping_digest({key: after_value}):
                continue
            changes.append({"field": key, "label": labels[key], "before": before_value, "after": after_value})
        return changes

    def display_value(value: Any) -> str:
        if value in (None, ""):
            return "-"
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)

    def change_detail(changes: list[dict[str, Any]]) -> str:
        return "；".join(
            f"{item['label']} `{display_value(item.get('before'))}` -> `{display_value(item.get('after'))}`"
            for item in changes
        )

    for provider_id in sorted(after_ids - before_ids):
        add_item("provider_added", "新增通道", f"`{provider_id}` 将被加入配置。", provider_id=provider_id)
    for provider_id in sorted(before_ids - after_ids):
        add_item("provider_removed", "删除通道", f"`{provider_id}` 将从配置里移除。", provider_id=provider_id, level="danger")
        add_risk("provider_removed", "删除通道", f"`{provider_id}` 删除后新 session 不会再使用该通道。", level="danger", provider_id=provider_id)

    before_default = _provider_default_id(current_cfg)
    after_default = _provider_default_id(next_cfg)
    if before_default != after_default:
        add_item("default_provider", "默认通道变化", f"`{before_default or '-'}` -> `{after_default or '-'}`", level="warn")
        add_risk("default_provider_changed", "默认通道变化", "默认 provider 改变会影响后续新 session 的默认路由。", provider_id=after_default)

    before_accounts = _account_by_id(current_cfg)
    after_accounts = _account_by_id(next_cfg)
    before_account_defaults = _account_defaults(current_cfg)
    after_account_defaults = _account_defaults(next_cfg)
    account_change_count = 0
    for cli_name in sorted(set(before_account_defaults) | set(after_account_defaults)):
        before_account = before_account_defaults.get(cli_name, "")
        after_account = after_account_defaults.get(cli_name, "")
        if before_account == after_account:
            continue
        account_change_count += 1
        level = "danger" if cli_name == "claude" else "warn"
        add_item(
            "account_default",
            f"默认账号变化：{cli_name}",
            f"`{before_account or '-'}` -> `{after_account or '-'}`",
            level=level,
            meta={"cli": cli_name, "before": before_account, "after": after_account},
        )
        add_risk(
            "claude_account_human_gate" if cli_name == "claude" else "account_default_changed",
            "默认账号变化",
            "Claude account default 属于 human-only，WebUI 当前不会保存。" if cli_name == "claude" else f"`{cli_name}` 后续新 session 会默认使用 `{after_account or '-'}`。",
            level=level,
        )
    for account_id in sorted(set(before_accounts) & set(after_accounts)):
        before_account = before_accounts.get(account_id, {})
        after_account = after_accounts.get(account_id, {})
        if _mapping_digest(_account_review_fields(before_account)) == _mapping_digest(_account_review_fields(after_account)):
            continue
        account_change_count += 1
        cli_name = _safe_text(after_account.get("cli") or before_account.get("cli")).lower()
        level = "danger" if cli_name == "claude" else "warn"
        add_item(
            "account_metadata",
            f"账号元数据变化：{account_id}",
            f"name/enabled/priority/family/timezone/claude_1m/note 将更新；CLI: `{cli_name or '-'}`。",
            level=level,
            meta={"account_id": account_id, "cli": cli_name},
        )
        if cli_name == "claude":
            add_risk(
                "claude_account_human_gate",
                "Claude account human-only",
                "Claude account metadata 属于 human-only，WebUI 当前不会保存。",
                level="danger",
            )

    hidden_removed_total = 0
    hidden_added_total = 0
    for provider_id in sorted(after_ids):
        before = before_providers.get(provider_id, {})
        after = after_providers[provider_id]
        before_meta = {
            "name": _safe_text(before.get("name") or provider_id),
            "enabled": before.get("enabled", True) is not False,
            "role": _safe_text(before.get("role") or "auto"),
            "priority": _normalize_priority(before.get("priority", 100)),
            "claude_1m_mode": _safe_text(before.get("claude_1m_mode") or "auto") or "auto",
            "timezone": _safe_text(before.get("timezone")),
            "note": _safe_text(before.get("note")),
        }
        after_meta = {
            "name": _safe_text(after.get("name") or provider_id),
            "enabled": after.get("enabled", True) is not False,
            "role": _safe_text(after.get("role") or "auto"),
            "priority": _normalize_priority(after.get("priority", 100)),
            "claude_1m_mode": _safe_text(after.get("claude_1m_mode") or "auto") or "auto",
            "timezone": _safe_text(after.get("timezone")),
            "note": _safe_text(after.get("note")),
        }
        meta_labels = {
            "name": "名称",
            "enabled": "启用",
            "role": "角色",
            "priority": "优先级",
            "claude_1m_mode": "Claude 1M",
            "timezone": "时区",
            "note": "备注",
        }
        meta_changes = field_changes(before_meta, after_meta, meta_labels)
        if provider_id in before_ids and meta_changes:
            important_fields = {item["field"] for item in meta_changes}.intersection({"enabled", "role", "priority", "claude_1m_mode"})
            add_item(
                "provider_metadata",
                f"通道元数据变化：{provider_id}",
                change_detail(meta_changes),
                provider_id=provider_id,
                level="warn" if important_fields else "info",
                meta={"before": before_meta, "after": after_meta, "changes": meta_changes},
            )
        before_family = _normalize_family_priority_overrides(before.get("family_priority_overrides"))
        after_family = _normalize_family_priority_overrides(after.get("family_priority_overrides"))
        if _mapping_digest(before_family) != _mapping_digest(after_family):
            changed = sorted(set(before_family) | set(after_family))
            detail = "；".join(f"{family}: `{before_family.get(family, '-')}` -> `{after_family.get(family, '-')}`" for family in changed)
            add_item(
                "provider_family_priority",
                f"Family 权重变化：{provider_id}",
                detail,
                provider_id=provider_id,
                level="warn",
                meta={"before": before_family, "after": after_family},
            )
        before_urls = _provider_urls(before)
        after_urls = _provider_urls(after)
        if provider_id in before_ids:
            for field, label in (("openai", "OpenAI base URL"), ("anthropic", "Anthropic base URL")):
                if before_urls[field] == after_urls[field]:
                    continue
                add_item(
                    "provider_url",
                    f"通道 URL 变化：{provider_id}",
                    f"{label}: `{before_urls[field] or '-'}` -> `{after_urls[field] or '-'}`",
                    provider_id=provider_id,
                    level="warn",
                    meta={"field": field, "before": before_urls[field], "after": after_urls[field]},
                )
        elif after_urls["openai"] or after_urls["anthropic"]:
            url_parts = []
            if after_urls["openai"]:
                url_parts.append(f"OpenAI: `{after_urls['openai']}`")
            if after_urls["anthropic"]:
                url_parts.append(f"Anthropic: `{after_urls['anthropic']}`")
            add_item("provider_url", f"通道 URL：{provider_id}", "；".join(url_parts), provider_id=provider_id)
        url_changed_by_field: dict[str, bool] = {}
        for field, label in (("openai", "OpenAI base URL"), ("anthropic", "Anthropic base URL")):
            url_changed_by_field[field] = before_urls[field] != after_urls[field]
            url = after_urls[field]
            if url.lower().startswith("http://") and (provider_id not in before_ids or url_changed_by_field[field]):
                add_risk("http_base_url", "HTTP URL", f"`{provider_id}` 的 {label} 使用 `http://`，请确认这是内网/代理预期。", provider_id=provider_id)
        before_enabled = before.get("enabled", True) is not False
        after_enabled = after.get("enabled", True) is not False
        became_empty = bool(before_urls["openai"] or before_urls["anthropic"]) and not after_urls["openai"] and not after_urls["anthropic"]
        became_enabled = not before_enabled and after_enabled
        if after_enabled and not after_urls["openai"] and not after_urls["anthropic"] and (provider_id not in before_ids or became_empty or became_enabled):
            add_risk("empty_provider_url", "启用通道缺少 URL", f"`{provider_id}` 已启用但没有 OpenAI/Anthropic URL。", provider_id=provider_id)
        before_hidden = set(_normalize_model_list(before.get("hidden_models")))
        after_hidden = set(_normalize_model_list(after.get("hidden_models")))
        removed = sorted(before_hidden - after_hidden, key=str.lower)
        added = sorted(after_hidden - before_hidden, key=str.lower)
        hidden_removed_total += len(removed)
        hidden_added_total += len(added)
        if removed:
            preview = ", ".join(removed[:8])
            suffix = f" 等 {len(removed)} 个" if len(removed) > 8 else ""
            add_item("hidden_removed", f"移除隐藏记录：{provider_id}", f"将移除 `{preview}`{suffix}", provider_id=provider_id, meta={"models": removed})
        if added:
            preview = ", ".join(added[:8])
            suffix = f" 等 {len(added)} 个" if len(added) > 8 else ""
            add_item("hidden_added", f"新增隐藏模型：{provider_id}", f"将隐藏 `{preview}`{suffix}", provider_id=provider_id, meta={"models": added})
        before_extra = set(_normalize_model_list(before.get("extra_models")))
        after_extra = set(_normalize_model_list(after.get("extra_models")))
        if before_extra != after_extra:
            add_item(
                "extra_models",
                f"手动模型变化：{provider_id}",
                f"新增 {len(after_extra - before_extra)} 个，移除 {len(before_extra - after_extra)} 个。",
                provider_id=provider_id,
            )

    ui_before = current_cfg.get("ui") if isinstance(current_cfg.get("ui"), dict) else {}
    ui_after = next_cfg.get("ui") if isinstance(next_cfg.get("ui"), dict) else {}
    if _safe_text(ui_before.get("language") or "zh") != _safe_text(ui_after.get("language") or "zh"):
        add_item(
            "ui_language",
            "界面语言变化",
            f"`{_safe_text(ui_before.get('language') or 'zh')}` -> `{_safe_text(ui_after.get('language') or 'zh')}`",
        )

    rescue_before = current_cfg.get("rescue") if isinstance(current_cfg.get("rescue"), dict) else {}
    rescue_after = next_cfg.get("rescue") if isinstance(next_cfg.get("rescue"), dict) else {}
    if _mapping_digest(rescue_before) != _mapping_digest(rescue_after):
        add_item("rescue", "Rescue fallback 变化", f"`{_safe_text(rescue_before.get('fallback_model')) or '-'}` -> `{_safe_text(rescue_after.get('fallback_model')) or '-'}`")

    lb_before = current_cfg.get("load_balance") if isinstance(current_cfg.get("load_balance"), dict) else {}
    lb_after = next_cfg.get("load_balance") if isinstance(next_cfg.get("load_balance"), dict) else {}
    if _mapping_digest(lb_before) != _mapping_digest(lb_after):
        before_profiles = (lb_before.get("profiles") if isinstance(lb_before.get("profiles"), dict) else {}) or {}
        after_profiles = (lb_after.get("profiles") if isinstance(lb_after.get("profiles"), dict) else {}) or {}
        add_item(
            "load_balance",
            "Load balance profile 变化",
            f"default `{_safe_text(lb_before.get('default')) or '-'}` -> `{_safe_text(lb_after.get('default')) or '-'}`；profiles {len(before_profiles)} -> {len(after_profiles)}。",
            level="warn",
        )

    vision_before = current_cfg.get("vision_sidecar") if isinstance(current_cfg.get("vision_sidecar"), dict) else {}
    vision_after = next_cfg.get("vision_sidecar") if isinstance(next_cfg.get("vision_sidecar"), dict) else {}
    if _mapping_digest(vision_before) != _mapping_digest(vision_after):
        before_ref = f"{_safe_text(vision_before.get('provider_id') or vision_before.get('provider')) or '-'}/{_safe_text(vision_before.get('model') or vision_before.get('vision_model')) or '-'}"
        after_ref = f"{_safe_text(vision_after.get('provider_id') or vision_after.get('provider')) or '-'}/{_safe_text(vision_after.get('model') or vision_after.get('vision_model')) or '-'}"
        add_item("vision_sidecar", "Vision sidecar 变化", f"`{before_ref}` -> `{after_ref}`")

    opencode_before = current_cfg.get("opencode") if isinstance(current_cfg.get("opencode"), dict) else {}
    opencode_after = next_cfg.get("opencode") if isinstance(next_cfg.get("opencode"), dict) else {}
    if _safe_text(opencode_before.get("default_profile")) != _safe_text(opencode_after.get("default_profile")):
        add_item("opencode_profile", "OpenCode profile 变化", f"`{_safe_text(opencode_before.get('default_profile')) or '-'}` -> `{_safe_text(opencode_after.get('default_profile')) or '-'}`")
    before_agents = _normalize_agent_model_overrides(opencode_before.get("agent_models") or opencode_before.get("agent_model_overrides"))
    after_agents = _normalize_agent_model_overrides(opencode_after.get("agent_models") or opencode_after.get("agent_model_overrides"))
    if _mapping_digest(before_agents) != _mapping_digest(after_agents):
        added_agents = sorted(set(after_agents) - set(before_agents))
        removed_agents = sorted(set(before_agents) - set(after_agents))
        updated_agents = sorted(
            agent for agent in (set(before_agents) & set(after_agents))
            if _mapping_digest(before_agents.get(agent)) != _mapping_digest(after_agents.get(agent))
        )
        changed_agents = sorted(
            set(added_agents) | set(removed_agents) | set(updated_agents)
        )
        preview = ", ".join(changed_agents[:8])
        suffix = f" 等 {len(changed_agents)} 个" if len(changed_agents) > 8 else ""
        buckets = []
        if added_agents:
            buckets.append(f"新增 {len(added_agents)}")
        if removed_agents:
            buckets.append(f"移除 {len(removed_agents)}")
        if updated_agents:
            buckets.append(f"修改 {len(updated_agents)}")
        add_item(
            "opencode_agent_models",
            "OpenCode agent 模型覆盖变化",
            f"{'，'.join(buckets)}；agent：{preview}{suffix}",
            meta={
                "agents": changed_agents,
                "added_agents": added_agents,
                "removed_agents": removed_agents,
                "updated_agents": updated_agents,
            },
        )
    before_roster = _normalize_opencode_agent_roster(opencode_before.get("agent_roster"), profile_id="agent")
    after_roster = _normalize_opencode_agent_roster(opencode_after.get("agent_roster"), profile_id="agent")
    if _mapping_digest(before_roster) != _mapping_digest(after_roster):
        changed_roster = sorted(
            agent for agent in (set(before_roster) | set(after_roster))
            if _mapping_digest(before_roster.get(agent)) != _mapping_digest(after_roster.get(agent))
        )
        disabled = sorted(agent for agent, entry in after_roster.items() if entry.get("enabled") is False)
        custom = sorted(agent for agent, entry in after_roster.items() if entry.get("custom") is True)
        parts = []
        if disabled:
            parts.append(f"禁用 {len(disabled)}")
        if custom:
            parts.append(f"自定义 {len(custom)}")
        if not parts:
            parts.append(f"更新 {len(changed_roster)}")
        preview = ", ".join(changed_roster[:8])
        suffix = f" 等 {len(changed_roster)} 个" if len(changed_roster) > 8 else ""
        add_item(
            "opencode_agent_roster",
            "OpenCode roster 变化",
            f"{'，'.join(parts)}；agent：{preview}{suffix}",
            meta={"agents": changed_roster, "disabled_agents": disabled, "custom_agents": custom},
        )

    if credential_updates:
        provider_ids = ", ".join(item["provider_id"] for item in credential_updates)
        add_item(
            "credentials",
            "凭据写入",
            f"stable legacy 写 credentials.sh；preview 写 secret backend：{provider_ids}",
            level="warn",
        )
        add_risk(
            "credential_update",
            "凭据写入",
            "只有输入了新 API Key 且勾选更新凭据的通道才会写入；stable legacy 目标是 credentials.sh，preview 目标是 secret backend。",
            level="warn",
        )

    policy_field_labels = {
        "visible": "显示",
        "favorite": "置顶",
        "capabilities.text": "文本",
        "capabilities.vision": "看图",
        "capabilities.tool_use": "工具",
        "capabilities.reasoning": "推理",
        "capabilities.thinking": "Think",
        "capabilities.one_m_context": "1M",
        "capabilities.long_context": "长上下文",
        "capabilities.context_window_tokens": "上下文",
        "capabilities.max_output_tokens": "输出上限",
        "capabilities.cache_sensitive": "缓存",
        "capabilities.cache_sensitive_transport": "缓存传输",
        "capabilities.supports_thinking": "支持 Think",
    }

    def policy_value_display(value: Any) -> str:
        if value is None:
            return "未写入配置"
        if isinstance(value, int) and value >= 1000:
            if value >= 1_000_000 and value % 1_000_000 == 0:
                return f"{value // 1_000_000}M"
            if value >= 100_000 and value % 1000 == 0:
                return f"{value // 1000}K"
        return display_value(value)

    def policy_flat(entry: Any) -> dict[str, Any]:
        if not isinstance(entry, dict):
            return {}
        flat: dict[str, Any] = {}
        for key in ("visible", "favorite"):
            if key in entry:
                flat[key] = entry.get(key)
        caps = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else {}
        for key in sorted(caps):
            flat[f"capabilities.{key}"] = caps.get(key)
        for key in sorted(entry):
            if key in {"visible", "favorite", "capabilities", "capability_sources"}:
                continue
            flat[key] = entry.get(key)
        return flat

    def policy_source_label(source: Any) -> str:
        if not isinstance(source, dict):
            return ""
        name = _safe_text(source.get("source_name"))
        layer = _safe_text(source.get("source_layer")).lower()
        confidence = _safe_text(source.get("confidence")).lower()
        if name:
            return name
        if "openrouter" in confidence:
            return "OpenRouter catalog"
        if layer == "provider_catalog":
            return "Provider catalog"
        if layer == "official":
            return "官方 / 已确认"
        if layer == "manual":
            return "手动调整"
        return layer or ""

    def policy_source_for_field(entry: Any, field: str) -> dict[str, Any]:
        if not isinstance(entry, dict):
            return {}
        sources = entry.get("capability_sources") if isinstance(entry.get("capability_sources"), dict) else {}
        key = field.replace("capabilities.", "", 1)
        source = sources.get(key)
        if source is None and key == "supports_thinking":
            source = sources.get("thinking")
        if source is None and key == "long_context":
            source = sources.get("context_window_tokens") or sources.get("one_m_context")
        if source is None and key == "cache_sensitive_transport":
            source = sources.get("cache_sensitive")
        source = source if isinstance(source, dict) else {}
        label = policy_source_label(source)
        result = _sanitize_for_output(source) if source else {}
        if label:
            result["label"] = label
        return result

    def policy_change_rows(before_entry: Any, after_entry: Any) -> list[dict[str, Any]]:
        before_flat = policy_flat(before_entry)
        after_flat = policy_flat(after_entry)
        rows: list[dict[str, Any]] = []
        for field in sorted(set(before_flat) | set(after_flat)):
            before_value = before_flat.get(field)
            after_value = after_flat.get(field)
            if _mapping_digest({field: before_value}) == _mapping_digest({field: after_value}):
                continue
            source = policy_source_for_field(after_entry, field)
            rows.append(
                {
                    "field": field,
                    "label": policy_field_labels.get(field, field),
                    "before": before_value,
                    "after": after_value,
                    "before_label": policy_value_display(before_value),
                    "after_label": policy_value_display(after_value),
                    "source": source,
                    "source_label": source.get("label", ""),
                }
            )
        return rows

    def build_policy_changes() -> dict[str, Any]:
        policy_before_models = policy_before.get("models") if isinstance(policy_before.get("models"), dict) else {}
        policy_after_models = policy_after.get("models") if isinstance(policy_after.get("models"), dict) else {}
        rows: list[dict[str, Any]] = []
        added = sorted(set(policy_after_models) - set(policy_before_models), key=str.lower)
        removed = sorted(set(policy_before_models) - set(policy_after_models), key=str.lower)
        common = sorted(set(policy_before_models) & set(policy_after_models), key=str.lower)
        for model in added:
            changes = policy_change_rows({}, policy_after_models.get(model))
            rows.append(
                {
                    "model": model,
                    "action": "added",
                    "action_label": "新增",
                    "changed_fields": [item["field"] for item in changes],
                    "changes": changes,
                    "summary": "；".join(f"{item['label']} `{item['after_label']}`" for item in changes[:8]) or "新增条目",
                    "before": {},
                    "after": _sanitize_for_output(policy_after_models.get(model)),
                }
            )
        for model in removed:
            changes = policy_change_rows(policy_before_models.get(model), {})
            rows.append(
                {
                    "model": model,
                    "action": "removed",
                    "action_label": "移除",
                    "changed_fields": [item["field"] for item in changes],
                    "changes": changes,
                    "summary": "将移除该 model-policy 条目",
                    "before": _sanitize_for_output(policy_before_models.get(model)),
                    "after": {},
                }
            )
        for model in common:
            changes = policy_change_rows(policy_before_models.get(model), policy_after_models.get(model))
            if not changes:
                continue
            rows.append(
                {
                    "model": model,
                    "action": "updated",
                    "action_label": "修改",
                    "changed_fields": [item["field"] for item in changes],
                    "changes": changes,
                    "summary": "；".join(f"{item['label']} `{item['before_label']}` -> `{item['after_label']}`" for item in changes[:8]),
                    "before": _sanitize_for_output(policy_before_models.get(model)),
                    "after": _sanitize_for_output(policy_after_models.get(model)),
                }
            )
        rows.sort(key=lambda item: ({"updated": 0, "added": 1, "removed": 2}.get(str(item.get("action")), 9), str(item.get("model") or "").lower()))
        return {
            "schema": "mms.setup_web.model_policy_changes.v1",
            "total": len(rows),
            "added": len(added),
            "removed": len(removed),
            "updated": len([item for item in rows if item.get("action") == "updated"]),
            "items": rows,
        }

    model_policy_changes = build_policy_changes()
    if model_policy_changes["total"]:
        add_item(
            "model_policy",
            "模型能力/偏好策略变化",
            f"将更新 {model_policy_changes['total']} 个 model-policy 条目：修改 {model_policy_changes['updated']}，新增 {model_policy_changes['added']}，移除 {model_policy_changes['removed']}。",
            meta={
                "total": model_policy_changes["total"],
                "updated": model_policy_changes["updated"],
                "added": model_policy_changes["added"],
                "removed": model_policy_changes["removed"],
                "models": [item["model"] for item in model_policy_changes["items"][:80]],
            },
        )

    if not items:
        add_item("no_change", "没有配置变化", "当前草稿与已加载配置一致。")
    return {
        "schema": "mms.setup_web.review_summary.v1",
        "counts": {
            "items": len(items),
            "risks": len(risks),
            "providers_before": len(before_ids),
            "providers_after": len(after_ids),
            "hidden_removed": hidden_removed_total,
            "hidden_added": hidden_added_total,
            "credential_updates": len(credential_updates),
            "account_changes": account_change_count,
            "model_policy_changes": model_policy_changes["total"],
        },
        "items": items,
        "risks": risks,
        "model_policy_changes": model_policy_changes,
    }
