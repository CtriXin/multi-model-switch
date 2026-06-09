"""Pure state helpers for the launch confirmation TUI."""

from __future__ import annotations

from mms_runtime.i18n import pick as _L


def normalize_caveman_level(value):
    raw = str(value or "").strip().lower().replace("_", "-")
    if raw in {"light", "lite", "low"}:
        return "light"
    if raw in {"standard", "normal", "medium"}:
        return "standard"
    if raw in {"full", "ultra", "high"}:
        return "full"
    return "light"


def caveman_level_text(value):
    value = str(value or "").strip().lower()
    if value == "disable":
        return _L("关闭", "Off")
    if value == "standard":
        return "Standard"
    if value == "full":
        return "Full"
    return "Light"


def agent_pack_text(value):
    value = str(value or "none").strip().lower()
    if value == "ecc":
        return _L("ECC · 工程 workflow / rules / quality hooks", "ECC · engineering workflow / rules / quality hooks")
    if value == "omc":
        return _L("OMC · orchestration runtime / team / verify loop", "OMC · orchestration runtime / team / verify loop")
    return _L("关闭", "Off")


def supports_claude_1m_toggle(info):
    values = []
    if isinstance(info, dict):
        values.extend(str(v or "") for key, v in info.items() if key != "subagent")
    else:
        values.append(str(info or ""))
    for item in values:
        lower = item.strip().lower()
        if lower.startswith("claude-") and "haiku" not in lower and ("opus" in lower or "sonnet" in lower):
            return True
    return False


def confirm_model_display(model_info):
    if isinstance(model_info, dict):
        return ", ".join(f"{key}={value}" for key, value in model_info.items() if key != "subagent")
    return str(model_info)


def confirm_label(label):
    mapping = {
        "CLI": _L("客户端", "CLI"),
        "Model": _L("模型", "Model"),
        "Launch": _L("启动", "Launch"),
        "Bypass": _L("绕过审批", "Bypass"),
        "Caveman": "Caveman",
        "NSR": "NSR",
        "Thinking": _L("思考", "Thinking"),
        "Effort": _L("强度", "Effort"),
        "Agent Pack": _L("能力包", "Agent Pack"),
        "ECC": "ECC",
        "OMC": "OMC",
        "URL": _L("地址", "URL"),
        "Key": _L("密钥", "Key"),
        "Active": _L("激活", "Active"),
        "Preset": _L("预设", "Preset"),
        "CLI source": _L("CLI 来源", "CLI source"),
        "Source": _L("来源", "Source"),
        "Proxy": _L("代理", "Proxy"),
        "TZ": "TZ",
        "IPv4": "IPv4",
        "Slot": _L("槽位", "Slot"),
        "Session": _L("会话", "Session"),
        "Email": _L("邮箱", "Email"),
        "UserID": _L("用户 ID", "User ID"),
        "OrgID": _L("组织 ID", "Org ID"),
        "DNS": "DNS",
        "Check": _L("检查", "Check"),
        "IPv4Egress": _L("IPv4 出口", "IPv4 egress"),
        "IPv6Egress": _L("IPv6 出口", "IPv6 egress"),
        "Reach": _L("目标", "Reach"),
        "Leak": _L("泄漏", "Leak"),
        "Score": _L("评分", "Score"),
        "Sessions": _L("会话数", "Sessions"),
        "Profile": _L("画像", "Profile"),
        "Fake": _L("伪上游", "Fake"),
    }
    return mapping.get(str(label or ""), str(label or ""))


def confirm_panel_title(panel_key):
    mapping = {
        "summary": _L("摘要", "Summary"),
        "mcp": "MCP",
        "skills": _L("技能", "Skills"),
        "hooks": _L("钩子", "Hooks"),
    }
    return mapping.get(str(panel_key or ""), str(panel_key or ""))


def confirm_panel_empty_message(panel_key, preview_catalog=None):
    allow_execution_surfaces = True
    if isinstance(preview_catalog, dict):
        allow_execution_surfaces = bool(preview_catalog.get("allow_execution_surfaces", True))
    if not allow_execution_surfaces:
        mapping = {
            "mcp": _L("当前启动路径不会注入托管 MCP。", "This launch path does not inject managed MCP."),
            "skills": _L("当前启动路径不会注入托管技能。", "This launch path does not inject managed skills."),
            "hooks": _L("当前启动路径不会注入托管钩子。", "This launch path does not inject managed hooks."),
        }
        return mapping.get(str(panel_key or ""), _L("当前面板没有可展示内容。", "No managed content for this panel."))
    mapping = {
        "mcp": _L("当前没有可预览的 MCP。", "No managed MCP to preview."),
        "skills": _L("当前没有可预览的技能。", "No managed skills to preview."),
        "hooks": _L("当前没有可预览的钩子。", "No managed hooks to preview."),
    }
    return mapping.get(str(panel_key or ""), _L("当前面板没有可展示内容。", "Nothing to show on this panel."))


def _normalize_preview_item(item):
    if not isinstance(item, dict):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            return None
        item = {"title": str(item[0]), "summary": str(item[1]), "details": []}
    title = str(item.get("title") or "").strip()
    summary = str(item.get("summary") or "").strip()
    details = []
    for detail in item.get("details") or []:
        if not isinstance(detail, (list, tuple)) or len(detail) < 2:
            continue
        label = str(detail[0] or "").strip()
        value = str(detail[1] or "").strip()
        if label and value:
            details.append((label, value))
    if not title:
        return None
    return {
        "title": title,
        "summary": summary,
        "details": details,
        "disable_key": str(item.get("disable_key") or title).strip(),
    }


def collect_preview_items(
    preview_catalog,
    panel_key,
    *,
    caveman_enabled=False,
    nsr_enabled=False,
    agent_pack="none",
):
    panel_key = str(panel_key or "").strip()
    if not isinstance(preview_catalog, dict):
        return []
    sections = preview_catalog.get(panel_key)
    if not isinstance(sections, dict):
        return []

    scopes = ["always"]
    if caveman_enabled:
        scopes.append("caveman")
    if nsr_enabled:
        scopes.append("nsr")
    pack_key = str(agent_pack or "none").strip().lower()
    if pack_key in {"ecc", "omc"}:
        scopes.append(pack_key)

    items = []
    seen = set()
    for scope in scopes:
        for raw_item in sections.get(scope) or []:
            item = _normalize_preview_item(raw_item)
            if item is None:
                continue
            signature = (item["title"], item["summary"], tuple(item["details"]))
            if signature in seen:
                continue
            seen.add(signature)
            items.append(item)
    return items


def _mask_secret(value):
    value = str(value or "")
    return value[:4] + "****" + value[-4:] if len(value) > 8 else "****"


def build_confirm_detail_lines(env_vars=None, context_lines=None):
    detail_lines = []
    if env_vars:
        preferred_keys = [
            ("ANTHROPIC_BASE_URL", "URL"),
            ("OPENAI_BASE_URL", "URL"),
            ("ANTHROPIC_AUTH_TOKEN", "Key"),
            ("OPENAI_API_KEY", "Key"),
            ("GEMINI_API_KEY", "Key"),
            ("MMS_ACTIVE_MODEL", "Active"),
            ("MMS_ACTIVE_PRESET", "Preset"),
            ("MMS_ACTIVE_CLI", "CLI source"),
        ]
        seen = set()
        for env_key, label in preferred_keys:
            if env_key in env_vars:
                value = str(env_vars.get(env_key, ""))
                if "key" in env_key.lower() or "token" in env_key.lower() or "auth" in env_key.lower():
                    value = _mask_secret(value)
                detail_lines.append((confirm_label(label), value, "detail"))
                seen.add(env_key)
        for env_key, value in env_vars.items():
            if env_key in seen:
                continue
            upper_key = env_key.upper()
            if any(token in upper_key for token in ("BASE_URL", "API_KEY", "AUTH_TOKEN", "ACTIVE_", "MODEL")):
                value = str(value or "")
                if "key" in env_key.lower() or "token" in env_key.lower() or "auth" in env_key.lower():
                    value = _mask_secret(value)
                label = env_key[:6] + "…" if len(env_key) > 7 else env_key
                detail_lines.append((label, value, "detail"))
        detail_lines = detail_lines[:4]
    if context_lines:
        for item in context_lines:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            raw_label = str(item[0])
            detail_lines.append((confirm_label(raw_label), str(item[1]), "fake" if raw_label == "Fake" else "detail"))
    return detail_lines[:10]


def initial_disabled_surfaces(runtime):
    payload = (runtime or {}).get("disabled_session_surfaces") if isinstance(runtime, dict) else {}
    payload = payload if isinstance(payload, dict) else {}
    result = {"mcp": set(), "skills": set(), "hooks": set()}
    aliases = {
        "mcp": "mcp",
        "mcps": "mcp",
        "mcp_servers": "mcp",
        "skills": "skills",
        "skill": "skills",
        "hooks": "hooks",
        "hook": "hooks",
    }
    for raw_key, raw_values in payload.items():
        key = aliases.get(str(raw_key or "").strip().lower())
        if key not in result:
            continue
        if isinstance(raw_values, str):
            raw_values = [raw_values]
        if not isinstance(raw_values, (list, tuple, set)):
            continue
        for item in raw_values:
            value = str(item or "").strip()
            if value:
                result[key].add(value)
    return result
