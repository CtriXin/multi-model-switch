"""OpenCode profile runtime and route resolver helpers."""

from __future__ import annotations

from dataclasses import dataclass

from mms_opencode_profiles import (
    OPENCODE_AGENT_PROFILE_ID,
    OPENCODE_COMMITTEE_PROFILE_ID,
    OPENCODE_DEBATE_PROFILE_ID,
    OPENCODE_DEFAULT_MODEL_PREFERENCES,
    OPENCODE_REVIEW_PROFILE_ID,
    opencode_lite_pro_specs_for_config,
    opencode_profile_label,
    opencode_profile_selection,
)
from mms_opencode_roster import (
    opencode_agent_model_overrides,
    opencode_agent_roster_overrides,
    opencode_custom_route_key,
    opencode_roster_preset_models,
)
from mms_opencode_routes import (
    append_unique_opencode_route,
    opencode_default_model_rank,
    opencode_is_mimo_direct_route,
    opencode_provider_matches_route_policy,
    opencode_provider_protocols,
    opencode_route_candidate_score,
    opencode_route_transport_candidates,
)


@dataclass(frozen=True)
class OpenCodeResolverDeps:
    provider_candidates: object
    provider_effective_models: object
    provider_supports_cli_name: object
    provider_supports_model_for_cli: object
    provider_label: object
    provider_openai_base_url: object
    provider_anthropic_base_url: object
    infer_model_family: object
    normalize_role: object
    runtime_priority_for_model: object
    runtime_with_priority: object
    mms_model_visible: object
    load_route_health_latest: object
    route_health_for_route: object
    route_health_allows_route: object
    route_health_sort_key: object
    apply_profile: object
    apply_entrypoint: object
    role_weights: dict
    default_priority: int
    default_provider_id: str


def find_opencode_model_route(
    cfg,
    default_provider,
    default_models,
    model_names,
    *,
    deps,
    route_key="route",
    route_policy="",
    profile_id=OPENCODE_AGENT_PROFILE_ID,
    provider_id="",
):
    wanted = [str(item or "").strip() for item in model_names if str(item or "").strip()]
    if not wanted:
        return None
    wanted_lower = [item.lower() for item in wanted]
    forced_provider_id = str(provider_id or "").strip()
    latest_health = deps.load_route_health_latest()
    scored = []
    for provider_seq, (provider, cached_models) in enumerate(deps.provider_candidates(cfg, default_provider, default_models)):
        if forced_provider_id and str(provider.get("id") or "").strip() != forced_provider_id:
            continue
        if not provider.get("enabled", True):
            continue
        if not opencode_provider_matches_route_policy(provider, route_policy, provider_label=deps.provider_label):
            continue
        if not provider.get("api_key"):
            continue
        if not deps.provider_supports_cli_name(provider, "opencode"):
            continue
        models = deps.provider_effective_models(provider, cached_models, cfg)
        by_lower = {str(model or "").strip().lower(): str(model or "").strip() for model in models if str(model or "").strip()}
        for model_rank, wanted_model in enumerate(wanted_lower):
            actual_model = by_lower.get(wanted_model)
            if not actual_model:
                continue
            if not deps.provider_supports_model_for_cli(provider, "opencode", actual_model):
                continue
            for protocol, openai_base_url, anthropic_base_url in opencode_route_transport_candidates(
                provider,
                actual_model,
                infer_model_family=deps.infer_model_family,
                provider_openai_base_url=deps.provider_openai_base_url,
                provider_anthropic_base_url=deps.provider_anthropic_base_url,
                provider_label=deps.provider_label,
            ):
                if opencode_is_mimo_direct_route(provider, actual_model, provider_label=deps.provider_label):
                    # MiMo's official OpenCode path is OpenAI-compatible.
                    # Rank it ahead of any legacy/stale route metadata.
                    protocol_rank = 0 if protocol == "openai_chat_completions" else 2
                else:
                    protocol_rank = 0 if protocol in {"openai_responses", "anthropic_messages"} else 1
                route = {
                    "id": route_key,
                    "model": actual_model,
                    "provider_id": provider.get("id", deps.default_provider_id),
                    "provider_name": deps.provider_label(provider),
                    "protocol": protocol,
                    "openai_base_url": openai_base_url,
                    "anthropic_base_url": anthropic_base_url if protocol == "anthropic_messages" else "",
                    "api_key": provider.get("openai_api_key") or provider.get("api_key", ""),
                    "protocols": opencode_provider_protocols(provider),
                }
                if isinstance(provider.get("model_capabilities"), dict):
                    route["model_capabilities"] = provider["model_capabilities"]
                if provider.get("provider_profile"):
                    route["provider_profile"] = provider.get("provider_profile")
                health_row = deps.route_health_for_route(latest_health, profile_id, route_key, route)
                if not deps.route_health_allows_route(health_row):
                    continue
                health_rank = deps.route_health_sort_key(health_row)
                score = (
                    model_rank,
                    protocol_rank,
                    health_rank,
                    *opencode_route_candidate_score(
                        provider,
                        actual_model,
                        provider_seq,
                        normalize_role=deps.normalize_role,
                        runtime_priority_for_model=deps.runtime_priority_for_model,
                        provider_label=deps.provider_label,
                        role_weights=deps.role_weights,
                        default_priority=deps.default_priority,
                    ),
                )
                if health_row:
                    route["health_status"] = health_row.get("status")
                    route["health_score"] = health_row.get("health_score")
                scored.append((score, route))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0])
    return scored[0][1]


def resolve_opencode_lite_pro_runtime(cfg, default_provider, default_models, profile_id=OPENCODE_AGENT_PROFILE_ID, *, deps):
    routes = []
    agent_models = {}
    agent_model_overrides = opencode_agent_model_overrides(cfg)
    agent_roster_overrides = opencode_agent_roster_overrides(cfg)
    unresolved_overrides = {}
    gpt_fallback = find_opencode_model_route(
        cfg,
        default_provider,
        default_models,
        ("gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex"),
        deps=deps,
        route_key="gpt_fallback",
        profile_id=profile_id,
    )

    default_specs = list(opencode_lite_pro_specs_for_config(cfg, profile_id))
    default_agents = {str(spec.get("agent") or "").strip() for spec in default_specs}
    default_keys = {str(spec.get("key") or "").strip() for spec in default_specs}

    for spec in default_specs:
        roster_entry = agent_roster_overrides.get(spec["agent"]) or agent_roster_overrides.get(spec["key"]) or {}
        if roster_entry.get("enabled") is False:
            continue
        override = agent_model_overrides.get(spec["agent"]) or agent_model_overrides.get(spec["key"])
        if not override and roster_entry.get("model"):
            override = {"provider_id": roster_entry.get("provider_id", ""), "model": roster_entry.get("model", "")}
        model_names = (override["model"],) if override else spec["models"]
        route = find_opencode_model_route(
            cfg,
            default_provider,
            default_models,
            model_names,
            deps=deps,
            route_key=spec["key"],
            route_policy=spec.get("route_policy", ""),
            profile_id=profile_id,
            provider_id=override.get("provider_id", "") if override else "",
        )
        if route is None and override:
            unresolved_overrides[spec["agent"]] = override
            route = find_opencode_model_route(
                cfg,
                default_provider,
                default_models,
                spec["models"],
                deps=deps,
                route_key=spec["key"],
                route_policy=spec.get("route_policy", ""),
                profile_id=profile_id,
            )
        if route is None and spec["key"] != "builder_primary" and spec.get("gpt_fallback", True) is not False:
            route = gpt_fallback
        route = append_unique_opencode_route(routes, dict(route, id=spec["key"]) if route else None)
        if route:
            agent_models[spec["agent"]] = spec["key"]

    custom_items = []
    for agent_id, entry in agent_roster_overrides.items():
        if agent_id in default_agents or agent_id in default_keys:
            continue
        if entry.get("enabled") is False:
            continue
        if entry.get("custom") is not True:
            entry = dict(entry)
            entry["custom"] = True
            agent_roster_overrides[agent_id] = entry
        priority = int(entry.get("priority") or 1000)
        custom_items.append((priority, agent_id, entry))
    for _priority, agent_id, entry in sorted(custom_items, key=lambda item: (item[0], item[1])):
        route_key = opencode_custom_route_key(agent_id)
        model_names = (entry["model"],) if entry.get("model") else opencode_roster_preset_models(entry.get("preset"))
        route_policy = str(entry.get("route_policy") or "").strip()
        if entry.get("preset") == "vision" and str(entry.get("model") or "").lower().startswith("mimo-"):
            route_policy = "mimo_direct"
        route = find_opencode_model_route(
            cfg,
            default_provider,
            default_models,
            model_names,
            deps=deps,
            route_key=route_key,
            route_policy=route_policy,
            profile_id=profile_id,
            provider_id=entry.get("provider_id", ""),
        )
        route = append_unique_opencode_route(routes, dict(route, id=route_key) if route else None)
        if route:
            agent_models[agent_id] = route_key

    builder_roster = agent_roster_overrides.get("mobius-builder-pro") or agent_roster_overrides.get("builder_primary") or {}
    builder_route = next((route for route in routes if route.get("id") == "builder_primary"), None)
    if builder_route is None:
        if builder_roster.get("enabled") is False:
            return None, None
        builder_route = gpt_fallback
        builder_route = append_unique_opencode_route(routes, dict(builder_route, id="builder_primary") if builder_route else None)
        if builder_route:
            agent_models["mobius-builder-pro"] = "builder_primary"
    if builder_route is None:
        return None, None

    runtime = dict(builder_route)
    runtime["id"] = str(builder_route.get("provider_id") or "opencode-agent")
    runtime["name"] = f"OpenCode {opencode_profile_label(profile_id)}"
    runtime["auth_mode"] = "api_key"
    runtime["runtime_kind"] = "provider"
    runtime["model"] = builder_route["model"]
    runtime["api_key"] = builder_route.get("api_key", "")
    runtime["openai_base_url"] = builder_route.get("openai_base_url", "")
    runtime["protocols"] = ["openai_chat_completions"]
    runtime["supported_clis"] = ["opencode"]
    runtime["opencode_routes"] = routes
    runtime["opencode_agent_model_keys"] = agent_models
    if agent_model_overrides:
        runtime["opencode_agent_model_overrides"] = agent_model_overrides
    if agent_roster_overrides:
        runtime["opencode_agent_roster"] = agent_roster_overrides
    if unresolved_overrides:
        runtime["opencode_agent_model_override_unresolved"] = unresolved_overrides
    runtime["opencode_default_route_key"] = "builder_primary"
    runtime["opencode_builder_fallback_agent"] = "mobius-builder-stable"
    model_info = {"model": builder_route["model"], "profile": profile_id}
    return model_info, deps.apply_profile(runtime, profile_id)


def resolve_opencode_profile_runtime(cfg, default_provider, default_models, profile_id, *, deps):
    """Resolve fixed OpenCode profile runtime without asking for a model/channel."""
    profile_id, selection_entrypoint = opencode_profile_selection(profile_id)
    profile_id = profile_id or "lite"
    if profile_id == "heavy_omo":
        runtime = {
            "id": "global-opencode-omo",
            "name": "Global OpenCode / OMO",
            "runtime_kind": "opencode_profile",
            "auth_mode": "global_config",
        }
        runtime = deps.apply_profile(runtime, profile_id)
        return {"model": "global-omo"}, deps.apply_entrypoint(runtime, selection_entrypoint)
    if profile_id in {
        OPENCODE_AGENT_PROFILE_ID,
        OPENCODE_REVIEW_PROFILE_ID,
        OPENCODE_COMMITTEE_PROFILE_ID,
        OPENCODE_DEBATE_PROFILE_ID,
    }:
        model_info, runtime = resolve_opencode_lite_pro_runtime(
            cfg,
            default_provider,
            default_models,
            profile_id=profile_id,
            deps=deps,
        )
        if runtime is None:
            return model_info, runtime
        return model_info, deps.apply_entrypoint(runtime, selection_entrypoint)

    candidates = []
    for provider, cached_models in deps.provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not provider.get("api_key"):
            continue
        protocols = provider.get("protocols", [])
        if isinstance(protocols, str):
            protocols = [protocols]
        if "openai_chat_completions" not in protocols:
            continue
        if not deps.provider_openai_base_url(provider):
            continue
        if not deps.provider_supports_cli_name(provider, "opencode"):
            continue

        models = deps.provider_effective_models(provider, cached_models, cfg)
        if not models:
            continue
        role = deps.normalize_role(provider.get("role", "auto"))
        provider_id = provider.get("id", deps.default_provider_id)
        provider_name = deps.provider_label(provider)
        openai_only = "anthropic_messages" not in protocols

        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized or not deps.mms_model_visible(normalized):
                continue
            if not deps.provider_supports_model_for_cli(provider, "opencode", normalized):
                continue
            family, _ = deps.infer_model_family(normalized)
            # Lite/Raw must not inherit cache-sensitive dual-protocol domestic models
            # such as K2.6, because OpenCode drives this lane through chat/completions.
            if family != "GPT" and not openai_only:
                continue
            model_rank = opencode_default_model_rank(
                normalized,
                default_model_preferences=OPENCODE_DEFAULT_MODEL_PREFERENCES,
                infer_model_family=deps.infer_model_family,
            )
            family_rank = 0 if family == "GPT" else 1
            priority = deps.runtime_priority_for_model(provider, normalized)
            candidates.append((
                family_rank,
                model_rank,
                deps.role_weights.get(role, 1),
                -int(priority or deps.default_priority),
                provider_name,
                normalized,
                provider_id,
                len(candidates),
                provider,
                family,
            ))

    if not candidates:
        return None, None

    candidates.sort()
    _family_rank, _model_rank, _role, _priority, _pname, model_name, _pid, _seq, provider, family = candidates[0]
    runtime = deps.runtime_with_priority(provider, model_name=model_name, family_name=family)
    runtime["model"] = model_name
    runtime = deps.apply_profile(runtime, profile_id)
    return {"model": model_name}, deps.apply_entrypoint(runtime, selection_entrypoint)


__all__ = [
    "OpenCodeResolverDeps",
    "find_opencode_model_route",
    "resolve_opencode_lite_pro_runtime",
    "resolve_opencode_profile_runtime",
]
