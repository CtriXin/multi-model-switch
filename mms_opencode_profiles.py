"""OpenCode profile, entrypoint, and agent roster profile helpers."""

from __future__ import annotations

OPENCODE_AGENT_PROFILE_ID = "lite_pro_orchestrated"
OPENCODE_REVIEW_PROFILE_ID = "review_hub"
OPENCODE_COMMITTEE_PROFILE_ID = "committee"
OPENCODE_DEBATE_PROFILE_ID = "debate"
OPENCODE_DEFAULT_PROFILE_ID = "agent"

OPENCODE_PROFILE_OPTIONS = [
    {
        "id": OPENCODE_DEFAULT_PROFILE_ID,
        "profile_id": OPENCODE_AGENT_PROFILE_ID,
        "label": "Agent",
        "badge": "默认",
        "summary": "默认推荐：session-local agent roster；GPT 总控/规格/执行/修复/终审；国产模型只做 explore、bug-hunt、vision/context checks 等轻量只读辅助。",
    },
    {
        "id": "review",
        "profile_id": OPENCODE_REVIEW_PROFILE_ID,
        "label": "Review",
        "badge": "审核",
        "summary": "审核专用：MMS 先解析/保存 reviewer 模型，再进入 OpenCode TUI，由 GPT-5.4 优先的 review host 派发；配合 review-hub request root 使用。",
    },
    {
        "id": "committee",
        "profile_id": OPENCODE_COMMITTEE_PROFILE_ID,
        "label": "Committee",
        "badge": "委员会",
        "summary": "通用委员会：评判已有 artifact（执行后 review / 共识汇总）；遇事不决、要对 fork/命题辩论时改用 Debate。GPT-5.4 host 默认派发给所选 subagent，最后汇总共识/分歧；默认只选 GPT-5.4，可加 GPT-5.5、DeepSeek、GLM、MiMo、Kimi、MiniMax。",
    },
    {
        "id": "debate",
        "profile_id": OPENCODE_DEBATE_PROFILE_ID,
        "label": "Debate",
        "badge": "辩论",
        "summary": "结构化辩论：用于 fork / 命题（遇事不决、issue 开发方向），不评判单一 artifact（那走 Committee）；独立于 Committee；blind seed -> crossfire -> revision，由 debate-host 写 .ai/debate/<thread-id>/ artifacts 并按 rubric 输出 resolution。",
    },
    {
        "id": "omo",
        "profile_id": "heavy_omo",
        "label": "OMO",
        "summary": "读取 global OpenCode + OMO；MMS 不写全局配置。",
    },
    {
        "id": "raw",
        "label": "Raw",
        "summary": "纯 OpenCode；session-local；无 OMO/agents。",
    },
]

# Kept as an exported compatibility name for older imports; the user-facing
# surface is now just OPENCODE_PROFILE_OPTIONS.
OPENCODE_BASE_PROFILE_OPTIONS = OPENCODE_PROFILE_OPTIONS

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

OPENCODE_REVIEW_HUB_SPECS = (
    {"key": "builder_primary", "agent": "review-hub-host", "models": ("glm-5-turbo", "kimi-k2.6", "qwen3.6-flash", "gpt-5.4")},
    {"key": "builder_fallback", "agent": "review-hub-host-stable", "models": ("gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex", "gpt-5.5")},
    {"key": "review_qwen", "agent": "review-qwen", "models": ("qwen3.7-max", "qwen3.6-plus", "qwen3.6-flash", "qwen3-coder-plus")},
    {"key": "review_kimi", "agent": "review-kimi", "models": ("kimi-k2.6", "K2.6", "kimi-for-coding", "kimi-k2.5")},
    {"key": "review_glm", "agent": "review-glm", "models": ("glm-5.1", "glm-5-turbo", "glm-5")},
    {"key": "review_deepseek", "agent": "review-deepseek", "models": ("deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v3.2")},
    {"key": "review_mimo", "agent": "review-mimo", "models": ("mimo-v2.5", "mimo-v2-pro"), "route_policy": "mimo_direct", "gpt_fallback": False},
    {"key": "review_mimo_pro", "agent": "review-mimo-pro", "models": ("mimo-v2.5-pro", "mimo-v2.5"), "route_policy": "mimo_direct", "gpt_fallback": False},
)

OPENCODE_COMMITTEE_SPECS = (
    {"key": "builder_primary", "agent": "committee-host", "models": ("gpt-5.4", "gpt-5.5", "gpt-5.3-codex")},
    {"key": "builder_fallback", "agent": "committee-host-pro", "models": ("gpt-5.5", "gpt-5.4", "gpt-5.3-codex")},
)

OPENCODE_DEBATE_SPECS = (
    {"key": "builder_primary", "agent": "debate-host", "models": ("gpt-5.4", "gpt-5.5", "gpt-5.3-codex")},
    {"key": "builder_fallback", "agent": "debate-host-pro", "models": ("gpt-5.5", "gpt-5.4", "gpt-5.3-codex")},
)

# Named committee tiers (issue #67). Each tier is a fixed host/fallback/member
# bundle that AI review consumers can select by profile alias
# `--profile committee-<tier>` without restating the model/channel list.
OPENCODE_COMMITTEE_TIERS = ("fast", "light", "standard", "heavy", "vision")
OPENCODE_COMMITTEE_DEFAULT_TIER = "standard"
OPENCODE_COMMITTEE_DEFAULT_CHANNEL = "direct"

OPENCODE_COMMITTEE_BARE_DEFAULT = {
    "host_primary": "gpt-5.4",
    "members": ["gpt-5.4"],
    "channel": "direct",
}

OPENCODE_COMMITTEE_TIER_DEFAULTS = {
    "fast": {
        "host_primary": "glm-5.2",
        "host_primary_channel": "direct-zai",
        "host_fallback": "kimi-for-coding",
        "host_fallback_channel": "direct-kimi",
        "members": ["deepseek-v4-flash", "MiniMax-M3", "mimo-v2.5"],
        "member_channels": {
            "deepseek-v4-flash": "direct-deepseek",
            "MiniMax-M3": "direct-minimax",
            "mimo-v2.5": "mimo-direct",
        },
        "channel": "direct",
    },
    "light": {
        "host_primary": "glm-5.2",
        "host_primary_channel": "direct-zai",
        "host_fallback": "kimi-for-coding",
        "host_fallback_channel": "direct-kimi",
        "members": ["deepseek-v4-pro", "MiniMax-M3", "glm-5.2", "mimo-v2.5-pro"],
        "member_channels": {
            "deepseek-v4-pro": "direct-deepseek",
            "MiniMax-M3": "direct-minimax",
            "glm-5.2": "direct-zai",
            "mimo-v2.5-pro": "mimo-direct",
        },
        "channel": "direct",
    },
    "standard": {
        "host_primary": "gpt-5.4",
        "host_primary_channel": "uscrsopenai",
        "host_fallback": "gpt-5.5",
        "host_fallback_channel": "uscrsopenai",
        "members": ["gpt-5.5", "glm-5.2", "deepseek-v4-pro", "MiniMax-M3", "mimo-v2.5-pro", "qwen3.7-max"],
        "member_channels": {
            "gpt-5.5": "uscrsopenai",
            "glm-5.2": "direct-zai",
            "deepseek-v4-pro": "direct-deepseek",
            "MiniMax-M3": "direct-minimax",
            "mimo-v2.5-pro": "mimo-direct",
            "qwen3.7-max": "direct-qwen",
        },
        "channel": "uscrsopenai",
    },
    "heavy": {
        "host_primary": "gpt-5.5",
        "host_primary_channel": "uscrsopenai",
        "host_fallback": "gpt-5.4",
        "host_fallback_channel": "uscrsopenai",
        "members": [
            "claude-opus-4-6-thinking",
            "gemini-3-flash-agent(high)",
            "gpt-5.5",
            "gpt-5.4",
            "glm-5.2",
            "deepseek-v4-pro",
            "MiniMax-M3",
            "mimo-v2.5-pro",
            "qwen3.7-max",
        ],
        "member_channels": {
            "claude-opus-4-6-thinking": "newapi-personal-tokyo",
            "gemini-3-flash-agent(high)": "newapi-personal-tokyo",
            "gpt-5.5": "uscrsopenai",
            "gpt-5.4": "uscrsopenai",
            "glm-5.2": "direct-zai",
            "deepseek-v4-pro": "direct-deepseek",
            "MiniMax-M3": "direct-minimax",
            "mimo-v2.5-pro": "mimo-direct",
            "qwen3.7-max": "direct-qwen",
        },
        "channel": "uscrsopenai",
    },
    "vision": {
        "host_primary": "mimo-v2.5",
        "host_primary_channel": "mimo-direct",
        "host_fallback": "kimi-k2.6",
        "host_fallback_channel": "direct-kimi",
        "members": ["kimi-k2.6", "qwen3.6-flash", "MiniMax-M3", "mimo-v2.5", "qwen3.7-max", "gemini-3-flash-agent(high)"],
        "member_channels": {
            "kimi-k2.6": "direct-kimi",
            "qwen3.6-flash": "direct-qwen",
            "MiniMax-M3": "direct-minimax",
            "mimo-v2.5": "mimo-direct",
            "qwen3.7-max": "direct-qwen",
            "gemini-3-flash-agent(high)": "newapi-personal-tokyo",
        },
        "channel": "mimo-direct",
    },
}


def _opencode_model_list(value):
    if isinstance(value, str):
        raw_items = value.replace(",", "\n").splitlines()
        items = []
        for raw in raw_items:
            items.extend(str(raw or "").split())
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        items = []
    result = []
    seen = set()
    for item in items:
        model = str(item or "").strip()
        key = model.lower()
        if not model or key in seen:
            continue
        seen.add(key)
        result.append(model)
    return tuple(result)


def _opencode_channel_map(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, channel in value.items():
        model = str(key or "").strip()
        route = str(channel or "").strip()
        if model and route:
            result[model] = route
    return result


def _opencode_channel_for_model(channel_map, model, fallback):
    model_text = str(model or "").strip()
    lower = model_text.lower()
    for key, channel in (channel_map or {}).items():
        if str(key or "").strip().lower() == lower:
            return str(channel or "").strip()
    return str(fallback or "").strip()


def opencode_review_host_config(cfg):
    cfg = cfg if isinstance(cfg, dict) else {}
    opencode = cfg.get("opencode") if isinstance(cfg.get("opencode"), dict) else {}
    review = opencode.get("review") if isinstance(opencode.get("review"), dict) else {}
    host = review.get("host") if isinstance(review.get("host"), dict) else {}
    if not host and isinstance(opencode.get("review_host"), dict):
        host = opencode.get("review_host")
    primary_models = _opencode_model_list(host.get("primary_models") or host.get("models"))
    fallback_models = _opencode_model_list(host.get("fallback_models") or host.get("fallback"))
    result = {}
    if primary_models:
        result["primary_models"] = primary_models
    if fallback_models:
        result["fallback_models"] = fallback_models
    return result


def opencode_committee_host_config(cfg):
    cfg = cfg if isinstance(cfg, dict) else {}
    opencode = cfg.get("opencode") if isinstance(cfg.get("opencode"), dict) else {}
    committee = opencode.get("committee") if isinstance(opencode.get("committee"), dict) else {}
    host = committee.get("host") if isinstance(committee.get("host"), dict) else {}
    primary_models = _opencode_model_list(
        host.get("primary_models")
        or host.get("models")
        or host.get("model")
        or committee.get("host_model")
    )
    fallback_models = _opencode_model_list(host.get("fallback_models") or host.get("fallback"))
    result = {}
    if primary_models:
        result["primary_models"] = primary_models
    if fallback_models:
        result["fallback_models"] = fallback_models
    return result


def opencode_debate_host_config(cfg):
    cfg = cfg if isinstance(cfg, dict) else {}
    opencode = cfg.get("opencode") if isinstance(cfg.get("opencode"), dict) else {}
    debate = opencode.get("debate") if isinstance(opencode.get("debate"), dict) else {}
    host = debate.get("host") if isinstance(debate.get("host"), dict) else {}
    primary_models = _opencode_model_list(
        host.get("primary_models")
        or host.get("models")
        or host.get("model")
        or debate.get("host_model")
    )
    fallback_models = _opencode_model_list(host.get("fallback_models") or host.get("fallback"))
    result = {}
    if primary_models:
        result["primary_models"] = primary_models
    if fallback_models:
        result["fallback_models"] = fallback_models
    return result


def opencode_lite_pro_specs_for_config(cfg, profile_id=OPENCODE_AGENT_PROFILE_ID):
    specs = [dict(spec) for spec in opencode_lite_pro_specs(profile_id)]
    normalized_profile = normalize_opencode_profile_id(profile_id)
    if normalized_profile == OPENCODE_REVIEW_PROFILE_ID:
        host = opencode_review_host_config(cfg)
    elif normalized_profile == OPENCODE_COMMITTEE_PROFILE_ID:
        host = opencode_committee_host_config(cfg)
    elif normalized_profile == OPENCODE_DEBATE_PROFILE_ID:
        host = opencode_debate_host_config(cfg)
    else:
        return tuple(specs)
    if not host:
        return tuple(specs)
    for spec in specs:
        if spec.get("key") == "builder_primary" and host.get("primary_models"):
            spec["models"] = tuple(host["primary_models"])
        elif spec.get("key") == "builder_fallback" and host.get("fallback_models"):
            spec["models"] = tuple(host["fallback_models"])
    return tuple(specs)


def normalize_opencode_profile_id(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "agent": OPENCODE_AGENT_PROFILE_ID,
        "agents": OPENCODE_AGENT_PROFILE_ID,
        "multi": OPENCODE_AGENT_PROFILE_ID,
        "multi_agent": OPENCODE_AGENT_PROFILE_ID,
        "openspec": OPENCODE_AGENT_PROFILE_ID,
        "openspec_multi": OPENCODE_AGENT_PROFILE_ID,
        "orchestrated": OPENCODE_AGENT_PROFILE_ID,
        "lite_multi_agent": OPENCODE_AGENT_PROFILE_ID,
        "5_5_multi_agent": OPENCODE_AGENT_PROFILE_ID,
        "lite_pro_orchestrated": OPENCODE_AGENT_PROFILE_ID,
        "review": OPENCODE_REVIEW_PROFILE_ID,
        "reviews": OPENCODE_REVIEW_PROFILE_ID,
        "review_hub": OPENCODE_REVIEW_PROFILE_ID,
        "reviewhub": OPENCODE_REVIEW_PROFILE_ID,
        "reviewer": OPENCODE_REVIEW_PROFILE_ID,
        "multi_review": OPENCODE_REVIEW_PROFILE_ID,
        "multi_reviewer": OPENCODE_REVIEW_PROFILE_ID,
        "committee": OPENCODE_COMMITTEE_PROFILE_ID,
        "committees": OPENCODE_COMMITTEE_PROFILE_ID,
        "council": OPENCODE_COMMITTEE_PROFILE_ID,
        "board": OPENCODE_COMMITTEE_PROFILE_ID,
        "multi_committee": OPENCODE_COMMITTEE_PROFILE_ID,
        # Committee tier aliases (issue #67): normalize to the committee profile;
        # the tier itself is recovered via extract_opencode_committee_tier().
        "committee_fast": OPENCODE_COMMITTEE_PROFILE_ID,
        "committee_light": OPENCODE_COMMITTEE_PROFILE_ID,
        "committee_standard": OPENCODE_COMMITTEE_PROFILE_ID,
        "committee_heavy": OPENCODE_COMMITTEE_PROFILE_ID,
        "committee_vision": OPENCODE_COMMITTEE_PROFILE_ID,
        "debate": OPENCODE_DEBATE_PROFILE_ID,
        "debates": OPENCODE_DEBATE_PROFILE_ID,
        "structured_debate": OPENCODE_DEBATE_PROFILE_ID,
        # Legacy pro spellings now fold into the single Agent profile.
        "pro": OPENCODE_AGENT_PROFILE_ID,
        "pro_solo": OPENCODE_AGENT_PROFILE_ID,
        "litepro": OPENCODE_AGENT_PROFILE_ID,
        "lite_pro": OPENCODE_AGENT_PROFILE_ID,
        "5_5_pro": OPENCODE_AGENT_PROFILE_ID,
        "omo": "heavy_omo",
        "heavy": "heavy_omo",
        "heavy_omo": "heavy_omo",
        "raw": "raw",
        "lite": "lite",
    }
    return aliases.get(normalized, "")


def extract_opencode_committee_tier(value):
    """Recover the committee tier from a raw profile string.

    `normalize_opencode_profile_id` collapses `committee-fast` and `committee`
    to the same profile id, so the tier must be re-read from the raw value.
    Returns "" for a bare committee profile (falls back to the default tier).
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = raw.lower().replace(" ", "-").replace("_", "-")
    prefix = "committee-"
    if not normalized.startswith(prefix):
        return ""
    tier = normalized[len(prefix):]
    return tier if tier in OPENCODE_COMMITTEE_TIERS else ""


def opencode_committee_preset_config(cfg, tier=""):
    """Resolve a committee tier preset to host/fallback/member models and channels.

    Precedence for an explicit tier: user config
    `opencode.committee.presets.{tier}` > built-in
    `OPENCODE_COMMITTEE_TIER_DEFAULTS`. An unknown/empty tier intentionally uses
    the bare legacy default instead of editable standard, so bare
    `--profile committee` keeps its previous host path. Always returns a
    complete dict so callers never need to special-case missing keys.
    """
    requested_tier = str(tier or "").strip()
    explicit_tier = requested_tier in OPENCODE_COMMITTEE_TIERS
    cfg = cfg if isinstance(cfg, dict) else {}
    opencode = cfg.get("opencode") if isinstance(cfg.get("opencode"), dict) else {}
    committee = opencode.get("committee") if isinstance(opencode.get("committee"), dict) else {}
    presets = committee.get("presets") if isinstance(committee.get("presets"), dict) else {}
    user_preset = presets.get(requested_tier) if explicit_tier and isinstance(presets.get(requested_tier), dict) else {}
    has_user_preset = bool(user_preset)

    base = dict(OPENCODE_COMMITTEE_TIER_DEFAULTS.get(requested_tier) or {}) if explicit_tier else dict(OPENCODE_COMMITTEE_BARE_DEFAULT)
    host_primary = str(user_preset.get("host_primary") or base.get("host_primary") or "").strip()
    host_fallback = str(user_preset.get("host_fallback") or base.get("host_fallback") or "").strip()
    members = _opencode_model_list(user_preset.get("members")) or _opencode_model_list(base.get("members"))
    channel = str(user_preset.get("channel") or base.get("channel") or OPENCODE_COMMITTEE_DEFAULT_CHANNEL).strip()
    if has_user_preset:
        base_member_channels = {}
        user_member_channels = _opencode_channel_map(user_preset.get("member_channels"))
    else:
        base_member_channels = _opencode_channel_map(base.get("member_channels"))
        user_member_channels = {}
    member_channel_source = {**base_member_channels, **user_member_channels}
    member_channels = {
        member: _opencode_channel_for_model(member_channel_source, member, channel)
        for member in members
        if _opencode_channel_for_model(member_channel_source, member, channel)
    }
    if "host_primary_channel" in user_preset:
        host_primary_channel = str(user_preset.get("host_primary_channel") or "").strip()
    elif has_user_preset:
        host_primary_channel = channel
    else:
        host_primary_channel = str(base.get("host_primary_channel") or channel).strip()
    if "host_fallback_channel" in user_preset:
        host_fallback_channel = str(user_preset.get("host_fallback_channel") or "").strip()
    elif has_user_preset:
        host_fallback_channel = channel
    else:
        host_fallback_channel = str(base.get("host_fallback_channel") or channel).strip()
    result = {"host_primary": host_primary, "members": list(members), "channel": channel}
    if host_primary_channel:
        result["host_primary_channel"] = host_primary_channel
    if host_fallback:
        result["host_fallback"] = host_fallback
    if host_fallback and host_fallback_channel:
        result["host_fallback_channel"] = host_fallback_channel
    if member_channels:
        result["member_channels"] = member_channels
    return result


def validate_opencode_committee_tier_preset(tier, preset):
    """Return a list of human-readable validation errors for a tier preset.

    Empty list means valid. The fast tier must carry at least two members
    (no host-only fast tier). Every tier requires a host_primary and members.
    """
    errors = []
    if tier not in OPENCODE_COMMITTEE_TIERS:
        errors.append(f"unknown committee tier: {tier!r}")
        return errors
    preset = preset if isinstance(preset, dict) else {}
    host_primary = str(preset.get("host_primary") or "").strip()
    members = _opencode_model_list(preset.get("members"))
    if not host_primary:
        errors.append(f"tier {tier}: host_primary is required")
    if not members:
        errors.append(f"tier {tier}: at least one member model is required")
    if tier == "fast" and len(members) < 2:
        errors.append("tier fast: at least two member models are required (no host-only fast tier)")
    return errors


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
        "backend_multi": (OPENCODE_AGENT_PROFILE_ID, "serve"),
        "multi_backend": (OPENCODE_AGENT_PROFILE_ID, "serve"),
        "multi_agent_backend": (OPENCODE_AGENT_PROFILE_ID, "serve"),
        "openspec_multi_backend": (OPENCODE_AGENT_PROFILE_ID, "serve"),
        "lite_pro_orchestrated_backend": (OPENCODE_AGENT_PROFILE_ID, "serve"),
        "review_backend": (OPENCODE_REVIEW_PROFILE_ID, "serve"),
        "review_hub_backend": (OPENCODE_REVIEW_PROFILE_ID, "serve"),
        "committee_backend": (OPENCODE_COMMITTEE_PROFILE_ID, "serve"),
        "debate_backend": (OPENCODE_DEBATE_PROFILE_ID, "serve"),
        "acp_multi": (OPENCODE_AGENT_PROFILE_ID, "acp"),
        "multi_acp": (OPENCODE_AGENT_PROFILE_ID, "acp"),
        "multi_agent_acp": (OPENCODE_AGENT_PROFILE_ID, "acp"),
        "openspec_multi_acp": (OPENCODE_AGENT_PROFILE_ID, "acp"),
        "lite_pro_orchestrated_acp": (OPENCODE_AGENT_PROFILE_ID, "acp"),
        "review_acp": (OPENCODE_REVIEW_PROFILE_ID, "acp"),
        "review_hub_acp": (OPENCODE_REVIEW_PROFILE_ID, "acp"),
        "committee_acp": (OPENCODE_COMMITTEE_PROFILE_ID, "acp"),
        "debate_acp": (OPENCODE_DEBATE_PROFILE_ID, "acp"),
    }
    if normalized in aliases:
        return aliases[normalized]
    return normalize_opencode_profile_id(value), ""


def opencode_profile_selection_ids():
    ids = [str(option.get("id") or "").strip() for option in OPENCODE_PROFILE_OPTIONS]
    return [item for item in ids if item]


def apply_opencode_entrypoint(runtime, entrypoint):
    runtime = dict(runtime or {})
    normalized = normalize_opencode_entrypoint(entrypoint)
    if not normalized:
        return runtime
    runtime["opencode_entrypoint"] = normalized
    return runtime


def opencode_lite_pro_specs(profile_id=OPENCODE_AGENT_PROFILE_ID):
    normalized_profile = normalize_opencode_profile_id(profile_id)
    if normalized_profile == OPENCODE_REVIEW_PROFILE_ID:
        return OPENCODE_REVIEW_HUB_SPECS
    if normalized_profile == OPENCODE_COMMITTEE_PROFILE_ID:
        return OPENCODE_COMMITTEE_SPECS
    if normalized_profile == OPENCODE_DEBATE_PROFILE_ID:
        return OPENCODE_DEBATE_SPECS
    specs = list(OPENCODE_LITE_PRO_SPECS)
    if normalized_profile == "lite_pro_orchestrated":
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
        if option["id"] == profile_id or normalize_opencode_profile_id(option.get("profile_id") or option["id"]) == profile_id:
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
    elif profile_id == OPENCODE_AGENT_PROFILE_ID:
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
    elif profile_id == OPENCODE_REVIEW_PROFILE_ID:
        runtime["opencode_use_global_config"] = False
        runtime["opencode_pure"] = True
        runtime["opencode_lite_agents"] = True
        runtime["opencode_agent"] = "review-hub-host"
        runtime["opencode_default_agent"] = "review-hub-host"
        runtime["opencode_roster"] = profile_id
        runtime["opencode_contract_workflow"] = "review-hub"
        runtime["opencode_backend_agent_capable"] = True
        runtime["opencode_acp_capable"] = True
        runtime["opencode_launch_preflight"] = False
        runtime["opencode_launch_fallback_route_keys"] = ["builder_primary", "builder_fallback"]
        runtime["opencode_launch_fallback_agents"] = {
            "builder_primary": "review-hub-host",
            "builder_fallback": "review-hub-host-stable",
        }
    elif profile_id == OPENCODE_COMMITTEE_PROFILE_ID:
        runtime["opencode_use_global_config"] = False
        runtime["opencode_pure"] = True
        runtime["opencode_lite_agents"] = True
        runtime["opencode_agent"] = "committee-host"
        runtime["opencode_default_agent"] = "committee-host"
        runtime["opencode_roster"] = profile_id
        runtime["opencode_contract_workflow"] = "committee"
        runtime["opencode_backend_agent_capable"] = True
        runtime["opencode_acp_capable"] = True
        runtime["opencode_launch_preflight"] = False
        runtime["opencode_launch_fallback_route_keys"] = ["builder_primary", "builder_fallback"]
        runtime["opencode_launch_fallback_agents"] = {
            "builder_primary": "committee-host",
            "builder_fallback": "committee-host-pro",
        }
    elif profile_id == OPENCODE_DEBATE_PROFILE_ID:
        runtime["opencode_use_global_config"] = False
        runtime["opencode_pure"] = True
        runtime["opencode_lite_agents"] = True
        runtime["opencode_agent"] = "debate-host"
        runtime["opencode_default_agent"] = "debate-host"
        runtime["opencode_roster"] = profile_id
        runtime["opencode_contract_workflow"] = "debate"
        runtime["opencode_backend_agent_capable"] = True
        runtime["opencode_acp_capable"] = True
        runtime["opencode_launch_preflight"] = False
        runtime["opencode_launch_fallback_route_keys"] = ["builder_primary", "builder_fallback"]
        runtime["opencode_launch_fallback_agents"] = {
            "builder_primary": "debate-host",
            "builder_fallback": "debate-host-pro",
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
    "OPENCODE_AGENT_PROFILE_ID",
    "OPENCODE_BASE_PROFILE_OPTIONS",
    "OPENCODE_COMMITTEE_PROFILE_ID",
    "OPENCODE_COMMITTEE_SPECS",
    "OPENCODE_COMMITTEE_TIERS",
    "OPENCODE_COMMITTEE_BARE_DEFAULT",
    "OPENCODE_COMMITTEE_TIER_DEFAULTS",
    "OPENCODE_COMMITTEE_DEFAULT_TIER",
    "OPENCODE_DEBATE_PROFILE_ID",
    "OPENCODE_DEBATE_SPECS",
    "OPENCODE_DEFAULT_MODEL_PREFERENCES",
    "OPENCODE_DEFAULT_PROFILE_ID",
    "OPENCODE_LITE_PRO_ORCHESTRATED_EXTRA_SPECS",
    "OPENCODE_LITE_PRO_SPECS",
    "OPENCODE_PROFILE_OPTIONS",
    "OPENCODE_REVIEW_HUB_SPECS",
    "OPENCODE_REVIEW_PROFILE_ID",
    "apply_opencode_entrypoint",
    "apply_opencode_profile",
    "extract_opencode_committee_tier",
    "normalize_opencode_entrypoint",
    "normalize_opencode_profile_id",
    "opencode_committee_preset_config",
    "validate_opencode_committee_tier_preset",
    "opencode_lite_pro_specs",
    "opencode_lite_pro_specs_for_config",
    "opencode_committee_host_config",
    "opencode_debate_host_config",
    "opencode_profile_label",
    "opencode_profile_selection",
    "opencode_profile_selection_ids",
    "opencode_review_host_config",
]
