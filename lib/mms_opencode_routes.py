"""OpenCode provider route scoring and transport helpers."""

from __future__ import annotations

from urllib.parse import urlparse


def opencode_default_model_rank(model_name, *, default_model_preferences, infer_model_family):
    normalized = str(model_name or "").strip().lower()
    for idx, preferred in enumerate(default_model_preferences):
        if normalized == preferred:
            return idx
    family, _ = infer_model_family(normalized)
    if family == "GPT":
        return len(default_model_preferences)
    return len(default_model_preferences) + 100


def opencode_provider_protocols(provider):
    protocols = provider.get("protocols", [])
    if isinstance(protocols, str):
        protocols = [protocols]
    return [str(item).strip() for item in protocols if str(item).strip()]


def opencode_normalized_openai_base_url(provider, *, provider_openai_base_url):
    base_url = str(provider_openai_base_url(provider) or "").strip().rstrip("/")
    if not base_url:
        return ""
    path = urlparse(base_url).path.rstrip("/")
    last_segment = path.rsplit("/", 1)[-1].lower() if path else ""
    if last_segment != "v1":
        return f"{base_url}/v1"
    return base_url


def opencode_normalized_anthropic_base_url(provider, *, provider_openai_base_url, provider_anthropic_base_url):
    base_url = str(provider_anthropic_base_url(provider) or "").strip().rstrip("/")
    if not base_url and "anthropic_messages" in opencode_provider_protocols(provider):
        base_url = str(provider_openai_base_url(provider) or "").strip().rstrip("/")
    if not base_url:
        return ""
    path = urlparse(base_url).path.rstrip("/")
    last_segment = path.rsplit("/", 1)[-1].lower() if path else ""
    if last_segment != "v1":
        return f"{base_url}/v1"
    return base_url


def opencode_is_mimo_direct_route(provider, model_name="", *, provider_label):
    provider_identity = " ".join(
        str(value or "").strip().lower()
        for value in (
            provider.get("id"),
            provider_label(provider),
            provider.get("base_url"),
            provider.get("openai_base_url"),
            provider.get("anthropic_base_url"),
        )
    )
    return "mimo" in provider_identity or "xiaomimimo.com" in provider_identity


def opencode_mimo_openai_base_from_anthropic(anthropic_base_url):
    """Derive MiMo's official OpenCode/OpenAI-compatible base from Anthropic base."""
    base_url = str(anthropic_base_url or "").strip().rstrip("/")
    if not base_url or "xiaomimimo.com" not in base_url.lower():
        return ""
    parsed = urlparse(base_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/anthropic/v1"):
        path = path[: -len("/anthropic/v1")] + "/v1"
    elif path.endswith("/anthropic"):
        path = path[: -len("/anthropic")] + "/v1"
    else:
        return ""
    return parsed._replace(path=path or "/v1", params="", query="", fragment="").geturl().rstrip("/")


def opencode_route_transport(
    provider,
    model_name,
    *,
    infer_model_family,
    provider_openai_base_url,
    provider_anthropic_base_url,
    provider_label,
):
    candidates = opencode_route_transport_candidates(
        provider,
        model_name,
        infer_model_family=infer_model_family,
        provider_openai_base_url=provider_openai_base_url,
        provider_anthropic_base_url=provider_anthropic_base_url,
        provider_label=provider_label,
    )
    if not candidates:
        openai_base_url = opencode_normalized_openai_base_url(
            provider,
            provider_openai_base_url=provider_openai_base_url,
        )
        anthropic_base_url = opencode_normalized_anthropic_base_url(
            provider,
            provider_openai_base_url=provider_openai_base_url,
            provider_anthropic_base_url=provider_anthropic_base_url,
        )
        return "", openai_base_url, anthropic_base_url
    return candidates[0]


def opencode_route_transport_candidates(
    provider,
    model_name,
    *,
    infer_model_family,
    provider_openai_base_url,
    provider_anthropic_base_url,
    provider_label,
):
    protocols = opencode_provider_protocols(provider)
    family, _ = infer_model_family(model_name)
    openai_base_url = opencode_normalized_openai_base_url(
        provider,
        provider_openai_base_url=provider_openai_base_url,
    )
    anthropic_base_url = opencode_normalized_anthropic_base_url(
        provider,
        provider_openai_base_url=provider_openai_base_url,
        provider_anthropic_base_url=provider_anthropic_base_url,
    )
    candidates = []
    if family == "GPT":
        if openai_base_url:
            candidates.append(("openai_responses", openai_base_url, anthropic_base_url))
        if "openai_chat_completions" in protocols and openai_base_url:
            candidates.append(("openai_chat_completions", openai_base_url, anthropic_base_url))
        return candidates
    if opencode_is_mimo_direct_route(provider, model_name, provider_label=provider_label):
        mimo_openai_base_url = openai_base_url or opencode_mimo_openai_base_from_anthropic(anthropic_base_url)
        if mimo_openai_base_url:
            # Official MiMo OpenCode guidance uses the OpenAI-compatible
            # provider. Do not add Anthropic as a fallback: OpenCode can miss
            # MiMo reasoning_content there during tool-result loops.
            candidates.append(("openai_chat_completions", mimo_openai_base_url, anthropic_base_url))
            return candidates
    if "anthropic_messages" in protocols and anthropic_base_url:
        candidates.append(("anthropic_messages", openai_base_url, anthropic_base_url))
    return candidates


def opencode_route_candidate_score(
    provider,
    model_name,
    sequence,
    *,
    normalize_role,
    runtime_priority_for_model,
    provider_label,
    role_weights,
    default_priority,
):
    role = normalize_role(provider.get("role", "auto"))
    priority = runtime_priority_for_model(provider, model_name)
    return (
        role_weights.get(role, 1),
        -int(priority or default_priority),
        str(provider_label(provider)),
        int(sequence),
    )


def opencode_provider_matches_route_policy(provider, route_policy, *, provider_label):
    policy = str(route_policy or "").strip()
    if not policy:
        return True
    provider_id = str(provider.get("id") or "").strip().lower()
    provider_name = str(provider_label(provider) or "").strip().lower()
    base_urls = " ".join(
        str(value or "").strip().lower()
        for value in (
            provider.get("base_url"),
            provider.get("openai_base_url"),
            provider.get("anthropic_base_url"),
        )
    )
    identity = f"{provider_id} {provider_name}"
    if policy == "mimo_direct":
        return "xiaomimimo.com" in base_urls or "mimo-direct" in identity or "xiaomi-direct" in identity
    return False


def append_unique_opencode_route(routes, route):
    if not route:
        return None
    key = (route.get("id"), route.get("provider_id"), route.get("openai_base_url"), route.get("model"))
    for existing in routes:
        existing_key = (existing.get("id"), existing.get("provider_id"), existing.get("openai_base_url"), existing.get("model"))
        if existing_key == key:
            return existing
    routes.append(route)
    return route


__all__ = [
    "append_unique_opencode_route",
    "opencode_default_model_rank",
    "opencode_is_mimo_direct_route",
    "opencode_mimo_openai_base_from_anthropic",
    "opencode_normalized_anthropic_base_url",
    "opencode_normalized_openai_base_url",
    "opencode_provider_matches_route_policy",
    "opencode_provider_protocols",
    "opencode_route_candidate_score",
    "opencode_route_transport",
    "opencode_route_transport_candidates",
]
