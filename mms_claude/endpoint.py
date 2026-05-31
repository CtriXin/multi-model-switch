"""Claude endpoint resolution helpers for MMS launchers."""

from __future__ import annotations


def resolve_anthropic_base_url(runtime, probe_model="claude-sonnet-4-6"):
    """
    Resolve the ANTHROPIC_BASE_URL shape expected by Claude Code SDK.

    The implementation reads helper functions through ``mms_launchers`` at call
    time so existing tests and callers can keep monkeypatching the compatibility
    wrappers on that module.
    """
    import mms_launchers as _launchers

    configured, probe_source = _launchers._anthropic_probe_target(runtime)
    api_key = runtime.get("api_key", "")
    provider_id = runtime.get("id", "default")

    if not configured or not api_key:
        return None, "no_config"

    url = configured.rstrip("/")
    normalized_url = url[:-3] if url.endswith("/v1") else url
    cache_key = _launchers._anthropic_cache_key(provider_id, configured)

    cached = _launchers._ANTHROPIC_URL_CACHE.get(cache_key)
    if cached:
        age = (_launchers.datetime.now() - cached["ts"]).total_seconds()
        if age < 3600:
            return cached["url"], "cached"

    file_cached = _launchers._load_anthropic_url_file_cache().get(cache_key)
    if isinstance(file_cached, dict):
        cached_url = str(file_cached.get("url", "")).strip()
        cached_ts = str(file_cached.get("ts", "")).strip()
        if cached_url and cached_ts:
            try:
                age = (_launchers.datetime.now() - _launchers.datetime.fromisoformat(cached_ts)).total_seconds()
            except ValueError:
                age = 999999
            if age < 24 * 3600:
                _launchers._ANTHROPIC_URL_CACHE[cache_key] = {
                    "url": cached_url,
                    "ts": _launchers.datetime.now(),
                }
                return cached_url, "file_cached"

    if probe_source == "configured" and url.endswith("/v1"):
        _launchers._remember_anthropic_url(provider_id, url, normalized_url)
        return normalized_url, "normalized"

    if provider_id and runtime.get("skip_anthropic_probe"):
        if probe_source != "configured":
            return None, "openai_fallback_failed"
        _launchers.console.print("[dim]已跳过 Anthropic 端点探测，直接使用配置 URL[/dim]")
        _launchers._remember_anthropic_url(provider_id, url, url)
        return url, "config_bypass"

    if _launchers._runtime_is_sensitive_claude_provider(runtime):
        if probe_source != "configured":
            return None, "openai_fallback_failed"
        _launchers.console.print("[dim]敏感 Claude provider：跳过 Anthropic 端点探测，直接使用配置 URL[/dim]")
        _launchers._remember_anthropic_url(provider_id, url, url)
        return url, "sensitive_bypass"

    if provider_id == "bailian-codingplan":
        if probe_source != "configured":
            return None, "openai_fallback_failed"
        _launchers.console.print("[dim]百炼 CodingPlan：跳过 Anthropic 端点探测，直接使用配置 URL[/dim]")
        _launchers._remember_anthropic_url(provider_id, url, url)
        return url, "bypass_for_bailian"

    probe_nonce = _launchers.os.urandom(8).hex()
    body = _launchers.json.dumps({
        "model": probe_model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
        "metadata": {
            "user_id": _launchers.json.dumps({
                "device_id": f"device-{probe_nonce}",
                "session_id": f"session-{probe_nonce}",
            }, ensure_ascii=False),
        },
    }).encode()
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    candidate = _launchers.detect_working_base_url(
        url,
        "/v1/messages",
        headers,
        body=body,
        timeout=5,
        runtime=runtime,
    )

    if candidate is not None:
        _launchers._remember_anthropic_url(provider_id, configured, candidate)
        if candidate != url:
            _launchers.console.print(f"[dim]✓ Anthropic 端点自动修正: {url} → {candidate}[/dim]")
        if probe_source == "openai_fallback":
            return candidate, "openai_fallback_probed"
        return candidate, "probed"

    if probe_source == "openai_fallback":
        return None, "openai_fallback_failed"
    return None, "failed"


def pick_gateway_model(runtime, base_url):
    """Fetch /models from gateway and return the best model ID for Claude slots."""
    import mms_launchers as _launchers

    try:
        import httpx as _httpx  # noqa: F401
    except ImportError:
        return None
    api_key = runtime.get("api_key", "")
    if not base_url or not api_key:
        return None
    url_v1 = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
    try:
        response = _launchers._runtime_httpx_request(
            "GET",
            f"{url_v1}/models",
            runtime=runtime,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
            follow_redirects=True,
        )
        if response.status_code != 200:
            return None
        models = [model.get("id", "") for model in response.json().get("data", [])]
    except Exception:
        return None
    if not models:
        return None
    for keyword in ("opus-4", "opus", "sonnet-4", "sonnet", "claude"):
        for model in models:
            if keyword in model.lower():
                return model
    return None
