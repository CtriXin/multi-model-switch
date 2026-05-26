"""OpenCode profile, entrypoint, and Lite Pro roster profile helpers."""

from __future__ import annotations

OPENCODE_DEFAULT_PROFILE_ID = "lite_pro_orchestrated"

OPENCODE_BASE_PROFILE_OPTIONS = [
    {
        "id": OPENCODE_DEFAULT_PROFILE_ID,
        "label": "OpenSpec Multi",
        "badge": "默认",
        "summary": "默认推荐：5.5 总控/终审；5.4 长跑执行；国产 explore/bug-hunt 只读找茬。",
    },
    {
        "id": "lite_pro",
        "label": "Pro Solo",
        "summary": "5.5 主写；5.4 兜底执行；国产 explore/bug-hunt 只读辅助；session-local。",
    },
    {
        "id": "heavy_omo",
        "label": "OMO Global",
        "summary": "读取 global OpenCode + OMO；MMS 不写全局配置。",
    },
    {
        "id": "raw",
        "label": "Raw Pure",
        "summary": "纯 OpenCode；session-local；无 OMO/agents。",
    },
]

OPENCODE_PROFILE_OPTIONS = [
    OPENCODE_BASE_PROFILE_OPTIONS[0],
    {
        "id": "lite_pro_orchestrated_backend",
        "profile_id": "lite_pro_orchestrated",
        "entrypoint": "serve",
        "label": "Backend Multi",
        "badge": "后台",
        "summary": "OpenSpec Multi-Agent + opencode serve；给 SDK/WebUI/headless client 连接。",
    },
    {
        "id": "lite_pro_orchestrated_acp",
        "profile_id": "lite_pro_orchestrated",
        "entrypoint": "acp",
        "label": "ACP Multi",
        "badge": "编辑器",
        "summary": "OpenSpec Multi-Agent + opencode acp；给 ACP-compatible editor/client 连接。",
    },
    *OPENCODE_BASE_PROFILE_OPTIONS[1:],
]

OPENCODE_DEFAULT_MODEL_PREFERENCES = (
    "gpt-5.4",
    "gpt-5.5",
    "gpt-5.4-mini",
    "gpt-5.3-codex",
    "gpt-5.2-codex",
)

OPENCODE_LITE_PRO_SPECS = (
    {"key": "builder_primary", "agent": "mobius-builder-pro", "models": ("gpt-5.5", "gpt-5.4")},
    {"key": "builder_fallback", "agent": "mobius-builder-stable", "models": ("gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex")},
    {"key": "spec_writer", "agent": "mobius-spec-writer", "models": ("gpt-5.5", "gpt-5.4", "gpt-5.3-codex")},
    {"key": "spec_compliance", "agent": "mobius-spec-compliance-reviewer", "models": ("gpt-5.5", "gpt-5.4", "gpt-5.3-codex")},
    {"key": "explore_primary", "agent": "mobius-explore-glm", "models": ("glm-5-turbo", "glm-5.1", "glm-5")},
    {"key": "explore_fallback", "agent": "mobius-explore-kimi", "models": ("kimi-for-coding", "kimi-k2.5")},
    {"key": "vision_primary", "agent": "mobius-vision-mimo", "models": ("mimo-v2.5", "mimo-v2-omni"), "route_policy": "mimo_direct", "gpt_fallback": False},
    {"key": "vision_kimi", "agent": "mobius-vision-kimi", "models": ("kimi-k2.5", "K2.6", "kimi-k2.6"), "gpt_fallback": False},
    {"key": "vision_qwen", "agent": "mobius-vision-qwen", "models": ("qwen3.6-plus", "qwen3.6-flash"), "gpt_fallback": False},
    {"key": "reviewer_primary", "agent": "mobius-reviewer-gpt55", "models": ("gpt-5.5", "gpt-5.4", "gpt-5.3-codex")},
    {"key": "reviewer_fallback", "agent": "mobius-reviewer-gpt54", "models": ("gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex")},
    {"key": "reviewer_mimo", "agent": "mobius-reviewer-mimo", "models": ("mimo-v2.5-pro", "mimo-v2.5", "mimo-v2-pro"), "route_policy": "mimo_direct", "gpt_fallback": False},
    {"key": "bughunt_deepseek", "agent": "mobius-bughunt-deepseek", "models": ("deepseek-v4-pro", "deepseek-v4-flash")},
    {"key": "bughunt_glm", "agent": "mobius-bughunt-glm", "models": ("glm-5.1", "glm-5-turbo", "glm-5")},
    {"key": "fixer_gpt54", "agent": "mobius-fixer-gpt54", "models": ("gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex")},
)

OPENCODE_LITE_PRO_ORCHESTRATED_EXTRA_SPECS = (
    {"key": "explore_qwen", "agent": "mobius-explore-qwen", "models": ("qwen3.7-max", "qwen3.6-plus", "qwen3.6-flash")},
    {"key": "bughunt_qwen", "agent": "mobius-bughunt-qwen", "models": ("qwen3.7-max", "qwen3.6-plus", "qwen3.6-flash", "qwen3-coder-plus")},
    {"key": "executor_gpt54", "agent": "mobius-executor-gpt54", "models": ("gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex")},
)


def normalize_opencode_profile_id(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "pro": "lite_pro",
        "pro_solo": "lite_pro",
        "litepro": "lite_pro",
        "lite_pro": "lite_pro",
        "5_5_pro": "lite_pro",
        "orchestrated": "lite_pro_orchestrated",
        "multi_agent": "lite_pro_orchestrated",
        "5_5_multi_agent": "lite_pro_orchestrated",
        "openspec_multi": "lite_pro_orchestrated",
        "lite_multi_agent": "lite_pro_orchestrated",
        "lite_pro_orchestrated": "lite_pro_orchestrated",
        "omo": "heavy_omo",
        "heavy": "heavy_omo",
        "heavy_omo": "heavy_omo",
        "raw": "raw",
        "lite": "lite",
    }
    return aliases.get(normalized, "")


def normalize_opencode_entrypoint(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "tui": "tui",
        "interactive": "tui",
        "ui": "tui",
        "backend": "serve",
        "backend_agent": "serve",
        "headless": "serve",
        "server": "serve",
        "serve": "serve",
        "acp": "acp",
        "editor": "acp",
        "agent_client_protocol": "acp",
    }
    return aliases.get(normalized, "")


def opencode_profile_selection(value):
    raw = str(value or "").strip()
    if not raw:
        return "", ""
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    for option in OPENCODE_PROFILE_OPTIONS:
        option_id = str(option.get("id") or "").strip()
        if normalized != option_id.lower().replace("-", "_").replace(" ", "_"):
            continue
        profile_id = normalize_opencode_profile_id(option.get("profile_id") or option_id)
        entrypoint = normalize_opencode_entrypoint(option.get("entrypoint") or "")
        return profile_id, entrypoint
    aliases = {
        "backend_multi": ("lite_pro_orchestrated", "serve"),
        "multi_backend": ("lite_pro_orchestrated", "serve"),
        "multi_agent_backend": ("lite_pro_orchestrated", "serve"),
        "openspec_multi_backend": ("lite_pro_orchestrated", "serve"),
        "lite_pro_orchestrated_backend": ("lite_pro_orchestrated", "serve"),
        "acp_multi": ("lite_pro_orchestrated", "acp"),
        "multi_acp": ("lite_pro_orchestrated", "acp"),
        "multi_agent_acp": ("lite_pro_orchestrated", "acp"),
        "openspec_multi_acp": ("lite_pro_orchestrated", "acp"),
        "lite_pro_orchestrated_acp": ("lite_pro_orchestrated", "acp"),
    }
    if normalized in aliases:
        return aliases[normalized]
    return normalize_opencode_profile_id(value), ""


def opencode_profile_selection_ids():
    ids = ["lite"] + [str(option.get("id") or "").strip() for option in OPENCODE_PROFILE_OPTIONS]
    return [item for item in ids if item]


def apply_opencode_entrypoint(runtime, entrypoint):
    runtime = dict(runtime or {})
    normalized = normalize_opencode_entrypoint(entrypoint)
    if not normalized:
        return runtime
    runtime["opencode_entrypoint"] = normalized
    return runtime


def opencode_lite_pro_specs(profile_id="lite_pro"):
    specs = list(OPENCODE_LITE_PRO_SPECS)
    if normalize_opencode_profile_id(profile_id) == "lite_pro_orchestrated":
        insert_at = next(
            (index + 1 for index, spec in enumerate(specs) if spec.get("key") == "explore_fallback"),
            len(specs),
        )
        specs[insert_at:insert_at] = list(OPENCODE_LITE_PRO_ORCHESTRATED_EXTRA_SPECS)
    return tuple(specs)


def opencode_profile_label(profile_id):
    profile_id = normalize_opencode_profile_id(profile_id) or str(profile_id or "").strip()
    if profile_id == "lite":
        return "Lite"
    for option in OPENCODE_PROFILE_OPTIONS:
        if option["id"] == profile_id:
            return option["label"]
    return profile_id or "Raw"


def apply_opencode_profile(runtime, profile_id):
    runtime = dict(runtime or {})
    profile_id, selection_entrypoint = opencode_profile_selection(profile_id)
    profile_id = profile_id or "lite"
    runtime["opencode_profile"] = profile_id
    runtime["opencode_profile_label"] = opencode_profile_label(profile_id)
    if profile_id == "heavy_omo":
        runtime["opencode_use_global_config"] = True
        runtime["opencode_pure"] = False
        runtime["opencode_lite_agents"] = False
        runtime["opencode_agent"] = ""
    elif profile_id == "raw":
        runtime["opencode_use_global_config"] = False
        runtime["opencode_pure"] = True
        runtime["opencode_lite_agents"] = False
        runtime["opencode_agent"] = ""
    elif profile_id in {"lite_pro", "lite_pro_orchestrated"}:
        runtime["opencode_use_global_config"] = False
        runtime["opencode_pure"] = True
        runtime["opencode_lite_agents"] = True
        runtime["opencode_agent"] = "mobius-builder-pro"
        runtime["opencode_default_agent"] = "mobius-builder-pro"
        runtime["opencode_roster"] = profile_id
        runtime["opencode_contract_workflow"] = "openspec"
        runtime["opencode_backend_agent_capable"] = True
        runtime["opencode_acp_capable"] = True
        runtime["opencode_launch_preflight"] = False
        runtime["opencode_launch_fallback_route_keys"] = ["builder_primary", "builder_fallback"]
        runtime["opencode_launch_fallback_agents"] = {
            "builder_primary": "mobius-builder-pro",
            "builder_fallback": "mobius-builder-stable",
        }
    else:
        runtime["opencode_use_global_config"] = False
        runtime["opencode_pure"] = True
        runtime["opencode_lite_agents"] = True
        runtime["opencode_agent"] = "mobius-builder"
    if selection_entrypoint:
        runtime = apply_opencode_entrypoint(runtime, selection_entrypoint)
    return runtime


__all__ = [
    "OPENCODE_BASE_PROFILE_OPTIONS",
    "OPENCODE_DEFAULT_MODEL_PREFERENCES",
    "OPENCODE_DEFAULT_PROFILE_ID",
    "OPENCODE_LITE_PRO_ORCHESTRATED_EXTRA_SPECS",
    "OPENCODE_LITE_PRO_SPECS",
    "OPENCODE_PROFILE_OPTIONS",
    "apply_opencode_entrypoint",
    "apply_opencode_profile",
    "normalize_opencode_entrypoint",
    "normalize_opencode_profile_id",
    "opencode_lite_pro_specs",
    "opencode_profile_label",
    "opencode_profile_selection",
    "opencode_profile_selection_ids",
]
