"""Runtime provider protocol and endpoint URL helpers."""

from __future__ import annotations


def provider_protocols(provider):
    protocols = provider.get("protocols", [])
    if isinstance(protocols, str):
        return [protocols]
    return list(protocols)


def openai_base_url(provider):
    explicit = str(provider.get("openai_base_url", "")).strip().rstrip("/")
    if explicit:
        return explicit
    base_url = str(provider.get("base_url", "")).strip().rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/v1"):
        return base_url
    return f"{base_url}/v1"


def anthropic_base_url(provider):
    explicit = str(provider.get("anthropic_base_url", "")).strip().rstrip("/")
    if explicit:
        return explicit
    if "anthropic_messages" not in provider_protocols(provider):
        return ""
    return str(provider.get("base_url", "")).strip().rstrip("/")


def anthropic_probe_target(runtime):
    configured = anthropic_base_url(runtime)
    if configured:
        return configured.rstrip("/"), "configured"
    if "anthropic_messages" not in provider_protocols(runtime):
        return "", ""
    openai_url = str(openai_base_url(runtime) or "").strip().rstrip("/")
    if not openai_url:
        return "", ""
    if openai_url.endswith("/v1"):
        return openai_url[:-3], "openai_fallback"
    return openai_url, "openai_fallback"
