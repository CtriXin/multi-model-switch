"""OpenCode resolver adapters used by core command glue."""

from __future__ import annotations


def opencode_default_profile_from_config(cfg, *, opencode_profile_selection, default_profile=None):
    opencode = cfg.get("opencode") if isinstance(cfg, dict) and isinstance(cfg.get("opencode"), dict) else {}
    return opencode_profile_selection(opencode.get("default_profile") or opencode.get("profile") or default_profile)


def build_opencode_resolver_deps(
    *,
    resolver_deps_cls,
    provider_candidates,
    provider_effective_models,
    provider_supports_cli_name,
    provider_supports_model_for_cli,
    provider_label,
    provider_openai_base_url,
    provider_anthropic_base_url,
    infer_model_family,
    normalize_role,
    runtime_priority_for_model,
    runtime_with_priority,
    mms_model_visible,
    load_route_health_latest,
    route_health_for_route,
    route_health_allows_route,
    route_health_sort_key,
    apply_profile,
    apply_entrypoint,
    role_weights,
    default_priority,
    default_provider_id,
):
    return resolver_deps_cls(
        provider_candidates=provider_candidates,
        provider_effective_models=provider_effective_models,
        provider_supports_cli_name=provider_supports_cli_name,
        provider_supports_model_for_cli=provider_supports_model_for_cli,
        provider_label=provider_label,
        provider_openai_base_url=provider_openai_base_url,
        provider_anthropic_base_url=provider_anthropic_base_url,
        infer_model_family=infer_model_family,
        normalize_role=normalize_role,
        runtime_priority_for_model=runtime_priority_for_model,
        runtime_with_priority=runtime_with_priority,
        mms_model_visible=mms_model_visible,
        load_route_health_latest=load_route_health_latest,
        route_health_for_route=route_health_for_route,
        route_health_allows_route=route_health_allows_route,
        route_health_sort_key=route_health_sort_key,
        apply_profile=apply_profile,
        apply_entrypoint=apply_entrypoint,
        role_weights=role_weights,
        default_priority=default_priority,
        default_provider_id=default_provider_id,
    )


def find_opencode_model_route(
    cfg,
    default_provider,
    default_models,
    model_names,
    *,
    opencode_resolver_deps,
    find_opencode_model_route_impl,
    route_key="route",
    route_policy="",
    profile_id="agent",
    provider_id="",
):
    return find_opencode_model_route_impl(
        cfg,
        default_provider,
        default_models,
        model_names,
        deps=opencode_resolver_deps(),
        route_key=route_key,
        route_policy=route_policy,
        profile_id=profile_id,
        provider_id=provider_id,
    )
