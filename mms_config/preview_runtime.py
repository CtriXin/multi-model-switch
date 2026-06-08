"""Build runtime config from a verified preview latest-approved bundle."""

from __future__ import annotations


def _bundle_runtime_leaf_model(route_model, leaf):
    value = str((leaf or {}).get("model_id") or "").strip()
    return value or str(route_model or "").strip()


def _bundle_runtime_protocols(leaf):
    protocols = []
    if str((leaf or {}).get("anthropic_base_url") or "").strip():
        protocols.append("anthropic_messages")
    if str((leaf or {}).get("openai_base_url") or "").strip():
        protocols.append("openai_chat_completions")
    return protocols


def _bundle_runtime_supported_clis(protocols, *, normalize_supported_clis):
    supported = []
    if "anthropic_messages" in protocols:
        supported.append("claude")
    if "openai_chat_completions" in protocols:
        supported.extend(["claude", "codex", "opencode"])
    return normalize_supported_clis(supported, protocols=protocols)


def _bundle_runtime_default_provider_id(profile_payload, providers, *, default_provider_id):
    profile_payload = profile_payload if isinstance(profile_payload, dict) else {}
    provider_cfg = profile_payload.get("provider") if isinstance(profile_payload.get("provider"), dict) else {}
    explicit_default = str(provider_cfg.get("default") or profile_payload.get("default_provider") or "").strip()
    if explicit_default:
        for provider in providers or []:
            if provider.get("id") == explicit_default or provider.get("route_provider_id") == explicit_default:
                return provider.get("id")
    return providers[0]["id"] if providers else default_provider_id


def load_preview_runtime_config_from_latest_bundle(
    *,
    config_dir,
    preview_root_mode,
    default_provider_id,
    mode_all,
    probe_async_refresh_after,
    probe_async_min_interval,
    normalize_model_id_list,
    normalize_supported_clis,
):
    if not preview_root_mode():
        return None
    try:
        import mms_registry

        bundle = mms_registry.load_latest_approved_bundle(config_dir=config_dir, include_secret=True)
    except Exception:
        return None
    payloads = bundle.get("payloads") if isinstance(bundle.get("payloads"), dict) else {}
    router = payloads.get("router") if isinstance(payloads.get("router"), dict) else {}
    profile_payload = payloads.get("profile") if isinstance(payloads.get("profile"), dict) else {}
    profiles = profile_payload.get("profiles") if isinstance(profile_payload.get("profiles"), dict) else {}
    routes = router.get("routes") if isinstance(router.get("routes"), dict) else {}
    if not routes:
        return None

    providers_by_key = {}
    providers = []
    provider_ids = set()
    route_models = []
    manifest = bundle.get("manifest") if isinstance(bundle.get("manifest"), dict) else {}

    for route_index, (route_model, entry) in enumerate(routes.items()):
        route_model_name = str(route_model or "").strip()
        if route_model_name:
            route_models.append(route_model_name)
        if not isinstance(entry, dict):
            continue
        leaves = [("primary", entry.get("primary"))]
        if isinstance(entry.get("fallbacks"), list):
            leaves.extend(("fallback", item) for item in entry.get("fallbacks") or [])
        for leaf_kind, leaf in leaves:
            if not isinstance(leaf, dict):
                continue
            model_name = _bundle_runtime_leaf_model(route_model_name, leaf)
            provider_id = str(leaf.get("provider_id") or "").strip()
            api_key = str(leaf.get("api_key") or leaf.get("openai_api_key") or "").strip()
            anthropic_url = str(leaf.get("anthropic_base_url") or "").strip().rstrip("/")
            openai_url = str(leaf.get("openai_base_url") or "").strip().rstrip("/")
            protocols = _bundle_runtime_protocols(leaf)
            if not provider_id or not model_name or not api_key or not protocols:
                continue
            profile = profiles.get(provider_id) if isinstance(profiles.get(provider_id), dict) else {}
            key = (provider_id, anthropic_url, openai_url, api_key)
            provider = providers_by_key.get(key)
            if provider is None:
                unique_id = provider_id
                if unique_id in provider_ids:
                    suffix = 2
                    while f"{provider_id}__bundle_{suffix}" in provider_ids:
                        suffix += 1
                    unique_id = f"{provider_id}__bundle_{suffix}"
                provider_ids.add(unique_id)
                supported_clis = profile.get("supported_clis") or _bundle_runtime_supported_clis(
                    protocols,
                    normalize_supported_clis=normalize_supported_clis,
                )
                provider = {
                    "id": unique_id,
                    "name": str(profile.get("name") or provider_id) if unique_id == provider_id else f"{provider_id} ({unique_id})",
                    "enabled": True,
                    "role": str(profile.get("role") or ("primary" if leaf_kind == "primary" else "fallback")),
                    "priority": int(profile.get("priority") or max(1, 1000 - route_index)),
                    "protocols": normalize_model_id_list(profile.get("protocols")) or protocols,
                    "supported_clis": normalize_supported_clis(supported_clis, protocols=protocols),
                    "models_endpoint": str(profile.get("models_endpoint") or "manual"),
                    "fallback_models": [],
                    "extra_models": [],
                    "hidden_models": normalize_model_id_list(profile.get("hidden_models")),
                    "default_anthropic_base_url": anthropic_url,
                    "default_openai_base_url": openai_url,
                    "anthropic_base_url": anthropic_url,
                    "openai_base_url": openai_url,
                    "api_key": api_key,
                    "openai_api_key": str(leaf.get("openai_api_key") or api_key).strip(),
                    "route_provider_id": provider_id,
                    "route_source": f"mms:latest-approved:{manifest.get('bundle_revision') or ''}",
                    "_mms_bundle_runtime": True,
                }
                providers_by_key[key] = provider
                providers.append(provider)
            elif leaf_kind == "primary" and not str(profile.get("role") or "").strip():
                provider["role"] = "primary"
            if model_name not in provider["fallback_models"]:
                provider["fallback_models"].append(model_name)

    if not providers:
        return None
    default_provider_id = _bundle_runtime_default_provider_id(
        profile_payload,
        providers,
        default_provider_id=default_provider_id,
    )
    return {
        "ui": {"language": "zh"},
        "user": {"role": mode_all},
        "cache": {
            "probe_async_refresh_after_sec": probe_async_refresh_after,
            "probe_async_min_interval_sec": probe_async_min_interval,
        },
        "provider": {"default": default_provider_id},
        "providers": providers,
        "account": {"defaults": {}},
        "accounts": [],
        "recommend": {"models": normalize_model_id_list(route_models)[:20]},
        "presets": {},
        "_mms_config_source": "latest-approved-bundle",
        "_mms_bundle_revision": manifest.get("bundle_revision") or "",
    }
