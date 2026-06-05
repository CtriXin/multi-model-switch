"""Model capability, visibility, and provider probe helpers."""

from __future__ import annotations

import json
import os


def usage_rows_for_runtime(runtime_kind, runtime_id, *, load_usage_stats):
    stats = load_usage_stats()
    rows = []
    for item in stats.get("sources", {}).values():
        if item.get("runtime_kind") == runtime_kind and item.get("id") == runtime_id:
            rows.append(item)
    rows.sort(key=lambda item: (item.get("last_used_at", ""), item.get("launches", 0)), reverse=True)
    return rows


def usage_summary_for_runtime(runtime_kind, runtime_id, *, usage_rows_for_runtime):
    rows = usage_rows_for_runtime(runtime_kind, runtime_id)
    launches = sum(int(item.get("launches", 0)) for item in rows)
    last_used_at = rows[0].get("last_used_at", "") if rows else ""
    return launches, last_used_at


def infer_model_family(model_name, *, model_families):
    raw = str(model_name or "").strip().lower()
    parts = raw.rsplit("/", 1)
    candidates = [raw] if len(parts) == 1 else [raw, parts[-1]]
    for entry in model_families:
        for candidate in candidates:
            if any(kw in candidate for kw in entry["keywords"]):
                return entry["family"], entry["category"]
    return "其他", "其他"


def model_info_looks_domestic(model_info, *, infer_model_family, domestic_model_families, domestic_model_keywords):
    values = []
    if isinstance(model_info, dict):
        primary = str(model_info.get("model") or "").strip()
        if primary:
            values.append(primary)
        values.extend(
            str(value or "").strip()
            for key, value in model_info.items()
            if key not in {"subagent", "model"} and str(value or "").strip()
        )
    else:
        values.append(str(model_info or "").strip())

    for value in values:
        lower = value.lower()
        family, _ = infer_model_family(value)
        if family in domestic_model_families:
            return True
        if any(keyword in lower for keyword in domestic_model_keywords):
            return True
    return False


def mms_model_visible(model_name, *, infer_model_family, hidden_models, hidden_model_families):
    normalized = str(model_name or "").strip()
    if not normalized:
        return True
    if normalized.lower() in hidden_models:
        return False
    family, _ = infer_model_family(normalized)
    return family not in hidden_model_families


def filter_visible_models(models, *, mms_model_visible):
    return [
        str(model_name).strip()
        for model_name in (models or [])
        if str(model_name or "").strip() and mms_model_visible(model_name)
    ]


def model_info_has_visible_models(model_info, *, mms_model_visible):
    if isinstance(model_info, str):
        return mms_model_visible(model_info)
    if not isinstance(model_info, dict):
        return True
    model_like_keys = ("model", "opus", "sonnet", "haiku", "subagent")
    found_model = False
    for key in model_like_keys:
        value = str(model_info.get(key) or "").strip()
        if not value:
            continue
        found_model = True
        if mms_model_visible(value):
            return True
    return not found_model


def vision_sidecar_model_candidates_for_provider(provider_id):
    normalized = str(provider_id or "").strip().lower()
    generic = [
        "mimo-v2.5",
        "mimo-v2-omni",
        "K2.6",
        "K2.6-code-preview",
        "kimi-k2.5",
        "qwen3.6-flash",
        "qwen3.6-plus",
    ]
    if "mimo" in normalized:
        return ["mimo-v2.5", "mimo-v2-omni"]
    if "kimi" in normalized:
        return ["K2.6", "K2.6-code-preview", "kimi-k2.5"]
    if "qwen" in normalized:
        return ["qwen3.6-plus", "qwen3.6-flash"]
    return generic


def vision_sidecar_candidate_pairs(raw, provider_ids, *, explicit_model="", explicit_provider_id=""):
    configured = (raw.get("candidates") or raw.get("routes")) if isinstance(raw, dict) else None
    pairs = []

    def _append(provider_id, model):
        provider_id = str(provider_id or "").strip()
        model = str(model or "").strip()
        if provider_id and model and (provider_id, model) not in pairs:
            pairs.append((provider_id, model))

    if isinstance(configured, list):
        for item in configured:
            if not isinstance(item, dict):
                continue
            provider_id = item.get("provider_id") or item.get("provider")
            model = item.get("model") or item.get("vision_model")
            _append(provider_id, model)

    if explicit_model:
        for provider_id in provider_ids:
            _append(provider_id, explicit_model)
        return pairs

    if explicit_provider_id:
        for model in vision_sidecar_model_candidates_for_provider(explicit_provider_id):
            _append(explicit_provider_id, model)
        return pairs

    preferred_pairs = [
        ("mimo-direct-anthropic", "mimo-v2.5"),
        ("direct-mimo", "mimo-v2.5"),
        ("direct-kimi", "K2.6"),
        ("newapi-personal-kimi", "K2.6-code-preview"),
        ("newapi-personal-kimi", "kimi-k2.5"),
        ("direct-qwen", "qwen3.6-plus"),
        ("newapi-personal-qwen", "qwen3.6-plus"),
        ("newapi-personal-tokyo", "K2.6"),
        ("xin", "K2.6"),
    ]
    for provider_id, model in preferred_pairs:
        _append(provider_id, model)
    for provider_id in provider_ids:
        for model in vision_sidecar_model_candidates_for_provider(provider_id):
            _append(provider_id, model)
    return pairs


def runtime_with_vision_sidecar(
    cfg,
    runtime,
    *,
    config_truthy,
    provider_map,
    resolve_config_provider_id,
    vision_sidecar_candidate_pairs=vision_sidecar_candidate_pairs,
    resolve_provider_context,
    provider_anthropic_base_url,
    load_probe_file_cache,
    provider_effective_models,
    environ=None,
):
    if not isinstance(runtime, dict) or runtime.get("vision_sidecar"):
        return runtime
    raw = cfg.get("vision_sidecar") if isinstance(cfg, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    if raw and not config_truthy(raw.get("enabled"), default=True):
        return runtime

    environ = os.environ if environ is None else environ
    explicit_model = str(
        environ.get("MMS_VISION_SIDECAR_MODEL")
        or raw.get("model")
        or raw.get("vision_model")
        or ""
    ).strip()
    explicit_provider_id = str(
        environ.get("MMS_VISION_SIDECAR_PROVIDER")
        or raw.get("provider_id")
        or raw.get("provider")
        or ""
    ).strip()
    preferred_ids = (
        [explicit_provider_id]
        if explicit_provider_id
        else [
            "mimo-direct-anthropic",
            "direct-mimo",
            "direct-kimi",
            "newapi-personal-kimi",
            "newapi-personal-tokyo",
            "xin",
        ]
    )
    providers = cfg.get("providers", []) if isinstance(cfg, dict) else []
    provider_defs = provider_map(cfg) if isinstance(cfg, dict) else {}
    explicit_provider_id = resolve_config_provider_id(provider_defs, explicit_provider_id)
    all_ids = [
        str(item.get("id") or "").strip()
        for item in providers
        if isinstance(item, dict) and item.get("id")
    ]
    candidate_ids = []
    for provider_id in preferred_ids + all_ids:
        if provider_id and provider_id not in candidate_ids:
            candidate_ids.append(provider_id)

    for provider_id, model in vision_sidecar_candidate_pairs(
        raw,
        candidate_ids,
        explicit_model=explicit_model,
        explicit_provider_id=explicit_provider_id,
    ):
        if provider_id not in provider_defs:
            continue
        try:
            provider = resolve_provider_context(cfg, provider_id)
        except Exception:
            continue
        if not provider or not provider.get("enabled", True):
            continue
        api_key = str(provider.get("api_key") or provider.get("openai_api_key") or "").strip()
        anthropic_url = provider_anthropic_base_url(provider)
        if not api_key or not anthropic_url:
            continue
        if not explicit_provider_id:
            try:
                cached = load_probe_file_cache(provider_id, allow_stale=True)
                cached_models = (cached or {}).get("raw_models") or (cached or {}).get("models")
                models = provider_effective_models(provider, cached_models, cfg)
            except Exception:
                models = []
            model_l = model.lower()
            if models and model_l not in {str(item or "").strip().lower() for item in models}:
                continue
        updated = dict(runtime)
        updated["vision_sidecar"] = {
            "enabled": True,
            "provider_id": provider_id,
            "provider_profile": str(provider.get("profile") or provider.get("provider_profile") or ""),
            "model": model,
            "anthropic_base_url": anthropic_url,
            "api_key": api_key,
            "proxy_url": str(provider.get("proxy") or "").strip(),
            "no_proxy": str(provider.get("no_proxy") or "").strip(),
        }
        return updated
    return runtime


def native_clis_for_model(model_name):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return []
    if normalized.startswith("claude-"):
        return ["claude"]
    if normalized.startswith(("gpt-", "o1-", "o3-", "o4-", "codex-")):
        return ["codex"]
    return []


def model_context_window(
    model_name,
    *,
    resolve_model_capabilities,
    model_context_windows,
):
    clean = str(model_name or "").replace("[1m]", "").strip()
    if not clean:
        return None
    try:
        caps = resolve_model_capabilities(clean)
        if caps.get("sources", {}).get("context_window_tokens") in {"approved_facts", "model_policy", "manual_override"}:
            window = int(caps.get("context_window_tokens"))
            if window > 0:
                return window
    except Exception:
        pass
    try:
        windows = model_context_windows()
    except Exception:
        return None
    window = windows.get(clean)
    if window is not None:
        return window
    lower = clean.lower()
    for key, value in windows.items():
        if key.lower() == lower:
            return value
    return None


def model_matches_account_cli(cli_name, model_name):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return False
    if cli_name == "claude":
        return normalized.startswith("claude-")
    if cli_name == "codex":
        return normalized.startswith(("gpt-", "o1-", "o3-", "o4-", "codex-"))
    if cli_name == "gemini":
        return normalized.startswith("gemini-")
    return False


def model_matches_cli_family(cli_name, model_name, *, cli_model_family_hints):
    hints = cli_model_family_hints.get(cli_name, ())
    normalized = str(model_name or "").lower()
    return any(hint in normalized for hint in hints)


def models_for_cli_family(
    cli_name,
    models,
    *,
    cli_model_family_hints,
    model_matches_cli_family=model_matches_cli_family,
):
    if cli_name not in cli_model_family_hints:
        return list(models or [])
    return [
        model_name
        for model_name in (models or [])
        if model_matches_cli_family(cli_name, model_name, cli_model_family_hints=cli_model_family_hints)
    ]


def provider_models_for_cli(
    cli_name,
    models,
    *,
    cli_model_family_hints,
    provider=None,
    pi_model_available_for_runtime=None,
):
    if cli_name in cli_model_family_hints:
        result = models_for_cli_family(cli_name, models, cli_model_family_hints=cli_model_family_hints)
    else:
        result = list(models or [])
    if cli_name == "pi" and isinstance(provider, dict) and callable(pi_model_available_for_runtime):
        result = [model_name for model_name in result if pi_model_available_for_runtime(provider, model_name)]
    return result


def provider_supports_cli_name(provider, cli_name):
    provider_id = str(provider.get("id", "")).strip().lower()
    cli_name = str(cli_name or "").strip().lower()
    if cli_name == "agy":
        return False
    if cli_name == "codex" and provider_id.startswith("kimi"):
        return False
    supported_clis = provider.get("supported_clis", [])
    if isinstance(supported_clis, str):
        supported_clis = [supported_clis]
    supported_clis = [str(item or "").strip().lower() for item in supported_clis]
    protocols = provider.get("protocols", [])
    if isinstance(protocols, str):
        protocols = [protocols]
    protocols = [str(item or "").strip() for item in protocols]
    if cli_name == "pi" and "pi" not in supported_clis:
        if "openai_chat_completions" in protocols and any(
            item in supported_clis for item in ("codex", "opencode", "claude")
        ):
            return True
        if "anthropic_messages" in protocols and "claude" in supported_clis:
            return True
    if cli_name == "opencode" and "opencode" not in supported_clis:
        if "openai_chat_completions" in protocols and any(
            item in supported_clis for item in ("codex", "claude")
        ):
            return True
        if "anthropic_messages" in protocols and "claude" in supported_clis:
            return True
    return cli_name in supported_clis


def provider_supports_model_for_cli(
    provider,
    cli_name,
    model_name=None,
    *,
    model_matches_account_cli,
    provider_supports_cli_name,
    bridge_clis_for_model,
    pi_model_available_for_runtime=None,
):
    normalized_model = str(model_name or "").strip()
    if cli_name == "pi" and normalized_model and callable(pi_model_available_for_runtime):
        if not pi_model_available_for_runtime(provider, normalized_model):
            return False
    if cli_name == "claude" and normalized_model:
        if model_matches_account_cli("claude", normalized_model):
            return provider_supports_cli_name(provider, "claude")
        bridge_clis = bridge_clis_for_model(normalized_model)
        return cli_name in bridge_clis and provider_supports_cli_name(provider, cli_name)

    if provider_supports_cli_name(provider, cli_name):
        return True
    if not normalized_model:
        return False
    return False


def probe_file_cache_path(provider_id, *, probe_file_cache_dir):
    return os.path.join(probe_file_cache_dir, f"models_{provider_id}.json")


def invalidate_probe_cache(
    provider_id,
    *,
    probe_cache,
    probe_file_cache_path,
    path_exists=os.path.exists,
    remove=os.remove,
):
    probe_cache.pop(provider_id, None)
    path = probe_file_cache_path(provider_id)
    if path_exists(path):
        try:
            remove(path)
        except OSError:
            pass


def probe_cache_age(
    provider_id,
    *,
    probe_file_cache_path,
    path_exists=os.path.exists,
    getmtime=os.path.getmtime,
    time_func=None,
):
    path = probe_file_cache_path(provider_id)
    if not path_exists(path):
        return None
    try:
        if time_func is None:
            import time as _time

            time_func = _time.time
        return max(0.0, time_func() - getmtime(path))
    except OSError:
        return None


def load_probe_file_cache(
    provider_id,
    allow_stale=False,
    *,
    probe_file_cache_path,
    normalize_model_id_list,
    file_cache_ttl,
    negative_ttl,
    path_exists=os.path.exists,
    getmtime=os.path.getmtime,
    time_func=None,
):
    """Read provider model probe cache without owning global MMS paths."""
    path = probe_file_cache_path(provider_id)
    try:
        if time_func is None:
            import time as _time

            time_func = _time.time
        if not path_exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        raw_models = normalize_model_id_list(data.get("raw_models") or data.get("models") or [])
        error_kind = data.get("error_kind")
        ttl = negative_ttl if error_kind or not raw_models else file_cache_ttl
        age = time_func() - getmtime(path)
        is_stale = age > ttl
        if is_stale and not allow_stale:
            return None
        normalized = dict(data)
        normalized["raw_models"] = raw_models
        normalized["models"] = list(raw_models)
        normalized.setdefault("base_source", "remote")
        normalized.setdefault("error", None)
        normalized.setdefault("error_kind", None)
        normalized.setdefault("details", [])
        normalized["is_stale"] = is_stale
        return normalized
    except Exception:
        pass
    return None


def save_probe_file_cache(
    provider_id,
    result,
    *,
    probe_file_cache_dir,
    probe_file_cache_path,
    makedirs=os.makedirs,
):
    base_source = result.get("base_source")
    if base_source not in {"remote", "fallback", "manual"}:
        return
    try:
        makedirs(probe_file_cache_dir, exist_ok=True)
        path = probe_file_cache_path(provider_id)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "raw_models": result.get("raw_models") or [],
                    "working_url": result.get("working_url"),
                    "base_source": base_source or "remote",
                    "error": result.get("error"),
                    "error_kind": result.get("error_kind"),
                },
                handle,
            )
    except Exception:
        pass


def base_probe_result_from_cache(provider_id, file_cached):
    return {
        "provider_id": provider_id,
        "raw_models": list(file_cached["raw_models"]),
        "models": list(file_cached["raw_models"]),
        "error": file_cached.get("error"),
        "error_kind": file_cached.get("error_kind"),
        "working_url": file_cached.get("working_url"),
        "details": list(file_cached.get("details") or []),
        "base_source": file_cached.get("base_source", "remote"),
        "is_stale": bool(file_cached.get("is_stale")),
    }


def probe_models(
    provider,
    *,
    emit_output=True,
    force_refresh=False,
    skip_cache=False,
    default_provider_id,
    probe_cache,
    probe_cache_ttl,
    invalidate_probe_cache,
    load_probe_file_cache,
    base_probe_result_from_cache,
    apply_provider_model_patch,
    provider_openai_base_url,
    ensure_httpx,
    get_httpx,
    runtime_httpx_request,
    save_probe_file_cache,
    provider_label,
    console,
    time_func,
):
    provider_id = provider.get("id", default_provider_id)
    if force_refresh:
        invalidate_probe_cache(provider_id)

    if not skip_cache:
        cached = probe_cache.get(provider_id)
        if cached:
            cached_at, cached_result = cached
            if time_func() - cached_at < probe_cache_ttl:
                patched_cached = apply_provider_model_patch(provider, cached_result)
                if emit_output and cached_result.get("error"):
                    style = "yellow" if cached_result.get("error_kind") == "protocol_unsupported" else "red"
                    console.print(f"[{style}]{cached_result['error']}[/{style}]")
                return patched_cached

        file_cached = load_probe_file_cache(provider_id)
        if file_cached:
            base_result = base_probe_result_from_cache(provider_id, file_cached)
            probe_cache[provider_id] = (time_func(), base_result)
            return apply_provider_model_patch(provider, base_result)

    protocols = provider.get("protocols", [])
    base_url = provider_openai_base_url(provider)
    api_key = provider.get("api_key", "")
    result = {
        "provider_id": provider_id,
        "models": None,
        "raw_models": None,
        "error": None,
        "error_kind": None,
        "working_url": None,
        "details": [],
        "base_source": "remote",
    }

    ensure_httpx()
    if "openai_chat_completions" not in protocols:
        result["error_kind"] = "protocol_unsupported"
        models_endpoint = provider.get("models_endpoint", "/models")
        result["error"] = f"provider '{provider_id}' 未声明 openai_chat_completions，无法探测 {models_endpoint}"
    elif get_httpx() is None:
        result["error_kind"] = "missing_httpx"
        result["error"] = "缺少 httpx，请执行: pip install httpx"
    elif not base_url and not api_key:
        result["error_kind"] = "missing_credentials"
        result["error"] = "当前 provider 还没有配置 API 地址和 API Key"
    elif not base_url:
        result["error_kind"] = "missing_base_url"
        result["error"] = "当前 provider 缺少 API 地址"
    elif not api_key:
        result["error_kind"] = "missing_api_key"
        result["error"] = "当前 provider 缺少 API Key"
    else:
        alt_url = base_url[:-3] if base_url.endswith("/v1") else f"{base_url}/v1"
        last_exc = None
        models_endpoint = provider.get("models_endpoint", "/models")
        if models_endpoint == "manual":
            fallback = provider.get("fallback_models") or []
            result["raw_models"] = list(fallback)
            result["models"] = list(fallback)
            result["working_url"] = base_url
            result["error"] = None
            result["error_kind"] = None
            result["base_source"] = "manual"
            if emit_output:
                console.print("[dim]已跳过远端 /models 探测，直接使用手工模型列表[/dim]")
        else:
            if not models_endpoint.startswith("/"):
                models_endpoint = "/" + models_endpoint
            for try_url in [base_url, alt_url]:
                try:
                    if "{key}" in models_endpoint:
                        endpoint_url = models_endpoint.replace("{key}", api_key)
                    elif "?" in models_endpoint:
                        endpoint_url = f"{models_endpoint}&key={api_key}"
                    else:
                        endpoint_url = models_endpoint
                    full_url = f"{try_url}{endpoint_url}"
                    headers = {}
                    if "/api/models/info" not in models_endpoint:
                        headers["Authorization"] = f"Bearer {api_key}"
                    response = runtime_httpx_request(
                        "GET",
                        full_url,
                        runtime=provider,
                        headers=headers,
                        timeout=15,
                    )
                    response.raise_for_status()
                    data = response.json()
                    models = [m["id"] for m in data.get("data", [])]
                    models.sort()
                    result["raw_models"] = models
                    result["models"] = models
                    result["working_url"] = try_url
                    if try_url != base_url and emit_output:
                        console.print(f"[yellow]⚠ 地址 {base_url} 不通，已自动用 {try_url} 连接成功[/yellow]")
                    if not models:
                        continue
                    break
                except Exception as exc:
                    last_exc = exc
            if result["models"] is not None and not result["models"]:
                result["error_kind"] = "empty_models"
                result["error"] = "接口返回成功，但模型列表为空"
            elif result["models"] is None and last_exc is not None:
                fallback = provider.get("fallback_models")
                if fallback:
                    result["raw_models"] = list(fallback)
                    result["models"] = list(fallback)
                    result["working_url"] = base_url
                    result["error"] = None
                    result["error_kind"] = None
                    result["base_source"] = "fallback"
                    if emit_output:
                        console.print(f"[dim]该来源不支持 /models 端点，使用内置模型列表 ({len(fallback)} 个模型)[/dim]")
                else:
                    result["error_kind"] = "request_failed"
                    result["error"] = f"拉取模型列表失败: {last_exc}"

    details = [
        f"provider: {provider_label(provider)} ({provider_id})",
        f"openai_base_url: {base_url or '(未设置)'}",
        f"protocols: {', '.join(protocols) if protocols else '(未声明)'}",
    ]
    if result["error"]:
        details.append(f"error: {result['error']}")
    result["details"] = details

    if emit_output and result["error"]:
        style = "yellow" if result["error_kind"] == "protocol_unsupported" else "red"
        console.print(f"[{style}]{result['error']}[/{style}]")

    probe_cache[provider_id] = (time_func(), result)
    save_probe_file_cache(provider_id, result)
    return apply_provider_model_patch(provider, result)


def probe_models_for_startup(
    cfg,
    provider,
    *,
    emit_output=True,
    default_provider_id,
    probe_cache,
    probe_cache_ttl,
    load_probe_file_cache,
    base_probe_result_from_cache,
    schedule_probe_refresh,
    apply_provider_model_patch,
    probe_models,
    console,
    time_func,
):
    provider_id = provider.get("id", default_provider_id)

    cached = probe_cache.get(provider_id)
    if cached:
        cached_at, cached_result = cached
        if time_func() - cached_at < probe_cache_ttl:
            return apply_provider_model_patch(provider, cached_result)

    fresh_file_cached = load_probe_file_cache(provider_id)
    if fresh_file_cached:
        base_result = base_probe_result_from_cache(provider_id, fresh_file_cached)
        probe_cache[provider_id] = (time_func(), base_result)
        return apply_provider_model_patch(provider, base_result)

    stale_file_cached = load_probe_file_cache(provider_id, allow_stale=True)
    if stale_file_cached:
        base_result = base_probe_result_from_cache(provider_id, stale_file_cached)
        probe_cache[provider_id] = (time_func(), base_result)
        schedule_probe_refresh(provider, cfg, reason="startup_stale")
        if emit_output:
            console.print("[dim]已使用本地模型缓存快速启动，后台正在刷新 provider 模型列表[/dim]")
        return apply_provider_model_patch(provider, base_result)

    return probe_models(provider, emit_output=emit_output)


def warm_probe_cache_async(
    cfg,
    default_provider,
    *,
    probe_async_refresh_after,
    probe_cache_age,
    schedule_probe_refresh,
    resolve_provider_context,
):
    default_id = default_provider.get("id")
    refresh_after = probe_async_refresh_after(cfg)
    for provider_def in cfg.get("providers", []):
        provider_id = provider_def.get("id")
        if not provider_id or provider_id == default_id:
            continue
        age = probe_cache_age(provider_id)
        if age is not None and age < refresh_after:
            continue
        schedule_probe_refresh(resolve_provider_context(cfg, provider_id), cfg, reason="startup_warm")


def select_provider_for_warm(cfg, *, select_provider_for_models):
    return select_provider_for_models(cfg)


def fetch_models(provider, *, probe_models):
    return probe_models(provider, emit_output=True).get("models")


def ensure_models_cache_available(models_cache, *, console):
    if models_cache:
        return True
    console.print("[yellow]当前没有可用的模型列表。请先修复 provider 校验，或先使用预设 / 直接 CLI 启动。[/yellow]")
    return False


def _normalize_model_id_list(values):
    if isinstance(values, str):
        values = [chunk.strip() for chunk in values.split(",")]
    normalized = []
    seen = set()
    for item in values or []:
        model_id = str(item or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        normalized.append(model_id)
    return normalized


def provider_supports_mimo_anthropic_selectors(provider):
    provider = provider if isinstance(provider, dict) else {}
    identity = " ".join(
        str(provider.get(key) or "").strip().lower()
        for key in ("id", "name", "label", "provider_profile")
    )
    urls = " ".join(
        str(provider.get(key) or "").strip().lower()
        for key in ("anthropic_base_url", "openai_base_url", "base_url")
    )
    if "openrouter" in identity or "openrouter.ai" in urls:
        return False
    anthropic_base = str(provider.get("anthropic_base_url") or "").strip().lower()
    if "xiaomimimo.com" in anthropic_base:
        return True
    base_url = str(provider.get("base_url") or "").strip().lower()
    if "xiaomimimo.com" in base_url and "/anthropic" in base_url:
        return True
    return bool(anthropic_base and any(token in identity for token in ("mimo", "xiaomi")))


def derived_model_aliases(
    base_models,
    provider=None,
    *,
    provider_supports_mimo_anthropic_selectors=provider_supports_mimo_anthropic_selectors,
):
    aliases = []
    claude_tails = [str(model_id or "").strip().lower().rsplit("/", 1)[-1] for model_id in base_models]
    if any(model_id.startswith("claude-sonnet-4-") or model_id.startswith("claude-sonnet-4.") for model_id in claude_tails):
        aliases.append("claude-sonnet-4-6")
    if any(model_id.startswith("claude-opus-4-") or model_id.startswith("claude-opus-4.") for model_id in claude_tails):
        aliases.append("claude-opus-4-6")
    # MiMo 1M is now controlled by model-policy context_window_tokens. Keep
    # explicit legacy [1m] selectors from config, but do not invent duplicates.
    return aliases


def apply_provider_model_patch(
    provider,
    base_result,
    *,
    normalize_model_id_list=None,
    derived_model_aliases=derived_model_aliases,
):
    if normalize_model_id_list is None:
        normalize_model_id_list = _normalize_model_id_list
    result = dict(base_result)
    base_models = normalize_model_id_list(result.get("raw_models") or result.get("models") or [])
    extra_models = normalize_model_id_list(provider.get("extra_models", []))
    hidden_requested = set(normalize_model_id_list(provider.get("hidden_models", [])))
    hidden_requested_lower = {model_id.lower() for model_id in hidden_requested}
    alias_base_models = [model_id for model_id in base_models if model_id.lower() not in hidden_requested_lower]
    aliases = derived_model_aliases(alias_base_models, provider)
    base_source = result.get("base_source") or ("fallback" if result.get("used_fallback") else "remote")

    effective_models = []
    model_sources = {}
    for model_id in base_models:
        if model_id in model_sources:
            continue
        model_sources[model_id] = base_source
        effective_models.append(model_id)

    for model_id in extra_models:
        if model_id in model_sources:
            continue
        model_sources[model_id] = "extra"
        effective_models.append(model_id)

    for model_id in aliases:
        if model_id in model_sources:
            continue
        model_sources[model_id] = "derived_alias"
        effective_models.append(model_id)

    domestic_keywords = ("glm", "kimi", "qwen", "minimax", "deepseek", "doubao", "seed", "bailian")
    claude_keep = {
        "claude-opus-4-6", "claude-opus-4-6-thinking", "claude-sonnet-4-6",
        "claude-opus-4-5-20251101", "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
    }
    effective_models = [
        model_id for model_id in effective_models
        if not (model_id.startswith("claude-") and any(kw in model_id.lower() for kw in domestic_keywords))
        and not (model_id.startswith("claude-") and model_id not in claude_keep)
    ]

    hidden_applied = [model_id for model_id in effective_models if model_id.lower() in hidden_requested_lower]
    if hidden_requested:
        effective_models = [model_id for model_id in effective_models if model_id.lower() not in hidden_requested_lower]
    visible_sources = {model_id: model_sources.get(model_id, base_source) for model_id in effective_models}

    result["raw_models"] = base_models
    result["models"] = effective_models
    result["model_sources"] = visible_sources
    result["extra_models"] = extra_models + [model_id for model_id in aliases if model_id not in extra_models]
    result["hidden_models"] = hidden_applied
    result["base_source"] = base_source
    return result


def provider_candidates(
    cfg,
    default_provider,
    default_models,
    *,
    load_probe_file_cache,
    resolve_provider_context,
):
    candidates = [(default_provider, list(default_models or []))]
    seen_ids = {default_provider.get("id")}
    for provider_def in cfg.get("providers", []):
        provider_id = provider_def.get("id")
        if not provider_id or provider_id in seen_ids:
            continue
        file_cached = load_probe_file_cache(provider_id, allow_stale=True)
        cached_models = None
        if file_cached is not None and not file_cached.get("is_stale"):
            cached_models = list((file_cached or {}).get("raw_models") or [])
        candidates.append((resolve_provider_context(cfg, provider_id), cached_models))
        seen_ids.add(provider_id)
    return candidates


def provider_effective_models(
    provider,
    cached_models,
    cfg=None,
    *,
    schedule_probe_refresh,
    apply_provider_model_patch,
):
    if provider.get("_mms_bundle_runtime"):
        base_models = list(provider.get("fallback_models") or [])
        base_source = "approved"
    elif cached_models is None:
        if provider.get("models_endpoint") == "manual":
            base_models = list(provider.get("fallback_models") or [])
            base_source = "manual"
        else:
            schedule_probe_refresh(provider, cfg, reason="cache_miss")
            base_models = list(provider.get("fallback_models") or [])
            base_source = "fallback" if base_models else "remote"
    else:
        base_models = list(cached_models or [])
        base_source = "remote"

    patched = apply_provider_model_patch(
        provider,
        {"raw_models": base_models, "models": base_models, "base_source": base_source},
    )
    return list(patched.get("models") or [])


def is_installed_mms_layout(
    module_path,
    *,
    real_user_home,
    abspath=os.path.abspath,
    commonpath=os.path.commonpath,
):
    current_path = abspath(module_path)
    installed_root = abspath(os.path.join(real_user_home(), ".mms"))
    try:
        return commonpath([current_path, installed_root]) == installed_root
    except ValueError:
        return False


def default_gpt_reasoning_effort(*, module_path, is_installed_mms_layout):
    return "high" if is_installed_mms_layout(module_path) else "xhigh"


def default_reasoning_effort_for_model_info(
    model_info,
    *,
    model_matches_account_cli,
    default_gpt_reasoning_effort,
):
    values = []
    if isinstance(model_info, dict):
        values.extend(str(value or "") for key, value in model_info.items() if key != "subagent")
    else:
        values.append(str(model_info or ""))
    for item in values:
        normalized = str(item or "").strip().lower()
        if "/" in normalized:
            normalized = normalized.rsplit("/", 1)[-1]
        if model_matches_account_cli("codex", normalized):
            return default_gpt_reasoning_effort()
    return "high"


def bridge_clis_for_model(model_name, *, infer_model_family):
    family, _ = infer_model_family(model_name)
    if family == "Unknown":
        return []
    native = set(native_clis_for_model(model_name))
    bridge = []
    for cli_name in ("claude", "codex"):
        if cli_name not in native:
            bridge.append(cli_name)
    return bridge


def model_supports_vision(model_name, *, vision_capable_model_names, vision_capable_model_hints):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return False
    model_id = normalized.rsplit("/", 1)[-1]
    if model_id in vision_capable_model_names:
        return True
    return any(hint in model_id for hint in vision_capable_model_hints)


def model_cli_modes(model_name, *, infer_model_family):
    native = set(native_clis_for_model(model_name))
    bridge = set(bridge_clis_for_model(model_name, infer_model_family=infer_model_family))
    modes = {}
    for cli_name in ("claude", "codex"):
        if cli_name in native:
            modes[cli_name] = "native"
        elif cli_name in bridge:
            modes[cli_name] = "bridge"
        else:
            modes[cli_name] = "unsupported"
    return modes


def model_cli_summary(model_name, *, infer_model_family):
    modes = model_cli_modes(model_name, infer_model_family=infer_model_family)
    parts = []
    for cli_name in ("claude", "codex"):
        mode = modes.get(cli_name)
        if mode == "native":
            parts.append(f"{cli_name}:native")
        elif mode == "bridge":
            parts.append(f"{cli_name}:bridge")
    return ", ".join(parts) if parts else "-"


def model_capability_tags(
    model_name,
    *,
    infer_model_family,
    model_context_window,
    reasoning_model_hints,
    tool_use_families,
    vision_capable_model_names,
    vision_capable_model_hints,
    resolve_model_capabilities=None,
):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return []
    family, _ = infer_model_family(model_name)
    tags = []
    if model_supports_vision(
        model_name,
        vision_capable_model_names=vision_capable_model_names,
        vision_capable_model_hints=vision_capable_model_hints,
    ):
        tags.append("vision")
    if family in tool_use_families:
        tags.append("tool_use")
    if any(hint in normalized for hint in reasoning_model_hints):
        tags.append("reasoning")
    if resolve_model_capabilities is not None:
        try:
            caps = resolve_model_capabilities(model_name)
            if caps.get("supports_thinking") is True and caps.get("sources", {}).get("supports_thinking") != "conservative_fallback":
                tags.append("thinking")
        except Exception:
            pass
    context_window = model_context_window(model_name)
    if context_window and context_window >= 200_000:
        tags.append("long_context")
    if "claude" in bridge_clis_for_model(model_name, infer_model_family=infer_model_family):
        tags.append("bridge_required")
    return tags


def model_capability_summary(model_name, *, model_capability_tags):
    tags = model_capability_tags(model_name)
    return ", ".join(tags) if tags else "-"
