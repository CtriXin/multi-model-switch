"""OpenCode configurable agent roster normalization helpers."""

from __future__ import annotations

import re

OPENCODE_ROSTER_PRESETS = {
    "builder",
    "executor",
    "explore",
    "bughunt",
    "vision",
    "reviewer",
    "spec",
    "fixer",
}
OPENCODE_REQUIRED_BUILDER_AGENTS = {"mobius-builder-pro", "builder_primary"}


def _truthy(value, default=True):
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return bool(default)


def _opencode_section(cfg):
    cfg = cfg if isinstance(cfg, dict) else {}
    opencode = cfg.get("opencode") if isinstance(cfg.get("opencode"), dict) else {}
    return opencode


def opencode_agent_model_overrides(cfg):
    opencode = _opencode_section(cfg)
    raw = opencode.get("agent_models")
    if not isinstance(raw, dict):
        raw = opencode.get("agent_model_overrides")
    raw = raw if isinstance(raw, dict) else {}
    overrides = {}
    for agent, entry in raw.items():
        agent_id = str(agent or "").strip()
        if not agent_id:
            continue
        provider_id = ""
        model = ""
        if isinstance(entry, dict):
            provider_id = str(entry.get("provider_id") or entry.get("provider") or "").strip()
            model = str(entry.get("model") or entry.get("model_id") or "").strip()
        elif isinstance(entry, str):
            model = entry.strip()
        if not model:
            continue
        overrides[agent_id] = {
            "provider_id": provider_id,
            "model": model,
        }
    return overrides


def opencode_roster_preset(agent_id, fallback="explore"):
    text = str(agent_id or "").strip().lower()
    if "vision" in text:
        return "vision"
    if "bughunt" in text:
        return "bughunt"
    if "explore" in text:
        return "explore"
    if "review" in text or "compliance" in text:
        return "reviewer"
    if "spec" in text:
        return "spec"
    if "executor" in text:
        return "executor"
    if "fixer" in text:
        return "fixer"
    if "builder" in text:
        return "builder"
    return fallback


def opencode_roster_preset_models(preset):
    preset = str(preset or "").strip().lower()
    if preset == "vision":
        return ("mimo-v2.5", "mimo-v2-omni", "kimi-k2.5", "qwen3.6-plus", "qwen3.5-plus")
    if preset == "executor":
        return ("gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex")
    if preset == "reviewer":
        return ("gpt-5.5", "gpt-5.4", "gpt-5.3-codex")
    if preset == "spec":
        return ("gpt-5.5", "gpt-5.4", "gpt-5.3-codex")
    if preset == "bughunt":
        return ("qwen3.6-plus", "qwen3.5-plus", "deepseek-v4-pro", "deepseek-v4-flash", "glm-5.1")
    if preset == "fixer":
        return ("gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex")
    if preset == "builder":
        return ("gpt-5.5", "gpt-5.4")
    return ("glm-5-turbo", "glm-5.1", "kimi-for-coding", "kimi-k2.5")


def opencode_agent_roster_overrides(cfg):
    opencode = _opencode_section(cfg)
    raw = opencode.get("agent_roster")
    raw = raw if isinstance(raw, dict) else {}
    roster = {}
    for agent, entry in raw.items():
        agent_id = str(agent or "").strip()
        if not agent_id or not isinstance(entry, dict):
            continue
        payload = {}
        preset = str(entry.get("preset") or entry.get("category") or opencode_roster_preset(agent_id)).strip().lower()
        if preset not in OPENCODE_ROSTER_PRESETS:
            preset = opencode_roster_preset(agent_id)
        payload["preset"] = preset
        if "enabled" in entry:
            enabled = _truthy(entry.get("enabled"), default=True)
            payload["enabled"] = True if agent_id in OPENCODE_REQUIRED_BUILDER_AGENTS and not enabled else enabled
        if entry.get("custom") is True:
            payload["custom"] = True
        provider_id = str(entry.get("provider_id") or entry.get("provider") or "").strip()
        model = str(entry.get("model") or entry.get("model_id") or "").strip()
        if provider_id and (model or payload.get("custom")):
            payload["provider_id"] = provider_id
        if model:
            payload["model"] = model
        try:
            priority = int(entry.get("priority"))
        except (TypeError, ValueError):
            priority = 0
        if priority > 0:
            payload["priority"] = priority
        description = str(entry.get("description") or "").strip()
        if description:
            payload["description"] = description[:240]
        prompt = str(entry.get("prompt") or "").strip()
        if prompt:
            payload["prompt"] = prompt[:4000]
        roster[agent_id] = payload
    return roster


def opencode_custom_route_key(agent_id):
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(agent_id or "").strip()).strip("_")
    return f"custom_{cleaned or 'agent'}"


__all__ = [
    "OPENCODE_REQUIRED_BUILDER_AGENTS",
    "OPENCODE_ROSTER_PRESETS",
    "opencode_agent_model_overrides",
    "opencode_agent_roster_overrides",
    "opencode_custom_route_key",
    "opencode_roster_preset",
    "opencode_roster_preset_models",
]
