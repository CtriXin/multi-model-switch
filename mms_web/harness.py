"""Harness ids shared by catalog, launch, and Pilot session code.

Pi remains the default rich Web harness. Grok is an optional second rich
harness. Claude/Codex/OpenCode stay launchable from the TUI, not from Pilot.
"""

from __future__ import annotations

WEB_RICH_HARNESSES = ("pi", "grok")
PROVIDER_LAUNCHABLE_HARNESSES = ("claude", "codex", "opencode", "pi", "grok")
KNOWN_HARNESSES = ("pi", "codex", "claude", "opencode", "gemini", "agy", "grok")
DEFAULT_WEB_HARNESS = "pi"


def is_web_rich(harness: str) -> bool:
    return str(harness or "").strip() in WEB_RICH_HARNESSES


def web_preset_prefix(harness: str) -> str:
    name = str(harness or "").strip() or DEFAULT_WEB_HARNESS
    return f"web:{name}:"
