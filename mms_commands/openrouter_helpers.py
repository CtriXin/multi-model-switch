"""OpenRouter extension command helpers."""

from __future__ import annotations

import json


def provider_looks_openrouter(provider):
    if not isinstance(provider, dict):
        return False
    fields = [
        provider.get("id"),
        provider.get("name"),
        provider.get("provider_profile"),
        provider.get("profile"),
        provider.get("extension"),
        provider.get("base_url"),
        provider.get("openai_base_url"),
        provider.get("default_openai_base_url"),
    ]
    return any("openrouter" in str(item or "").lower() for item in fields)


def openrouter_provider_candidates(
    cfg,
    *,
    provider_looks_openrouter=provider_looks_openrouter,
    resolve_provider_context,
):
    providers = []
    for item in cfg.get("providers", []):
        if not provider_looks_openrouter(item):
            continue
        try:
            providers.append(resolve_provider_context(cfg, item.get("id")))
        except Exception:
            providers.append(item)
    return providers


def parse_openrouter_extension_args(args_rest):
    args = list(args_rest or [])
    action = "status"
    provider_id = ""
    limit = 12
    assume_paid = False
    json_output = False
    if args and not args[0].startswith("-"):
        action = args.pop(0).strip().lower() or "status"
    if args and not args[0].startswith("-"):
        provider_id = args.pop(0).strip()
    idx = 0
    while idx < len(args):
        token = args[idx]
        if token in {"--limit", "-n"} and idx + 1 < len(args):
            try:
                limit = max(1, int(args[idx + 1]))
            except ValueError:
                limit = 12
            idx += 2
            continue
        if token == "--assume-paid":
            assume_paid = True
        elif token == "--json":
            json_output = True
        idx += 1
    if action in {"ls", "list"}:
        action = "models"
    if action in {"-h", "--help", "help"}:
        action = "help"
    return {
        "action": action,
        "provider_id": provider_id,
        "limit": limit,
        "assume_paid": assume_paid,
        "json": json_output,
    }


def openrouter_extension_provider(
    cfg,
    provider_id="",
    *,
    provider_map,
    resolve_provider_context,
    provider_looks_openrouter=provider_looks_openrouter,
    openrouter_provider_candidates,
):
    providers = provider_map(cfg)
    if provider_id:
        if provider_id not in providers:
            return None, f"未找到 provider: {provider_id}"
        provider = resolve_provider_context(cfg, provider_id)
        if not provider_looks_openrouter(provider):
            return provider, f"provider '{provider_id}' 不是 OpenRouter 模板，但仍可用其 Key 做探测"
        return provider, ""
    candidates = openrouter_provider_candidates(cfg)
    if candidates:
        return candidates[0], ""
    return None, ""


def handle_openrouter_extension_config(
    cfg,
    args_rest,
    *,
    parse_openrouter_extension_args,
    display_openrouter_extension_help,
    quick_connect_gateway,
    openrouter_extension_provider,
    openrouter_api_key_from_env,
    probe_openrouter_extension,
    display_openrouter_extension_summary,
    console,
):
    parsed = parse_openrouter_extension_args(args_rest)
    action = parsed["action"]
    if action == "help":
        display_openrouter_extension_help()
        return
    if action in {"add", "enable"}:
        quick_connect_gateway(cfg, preset_id="openrouter")
        return

    provider, warning = openrouter_extension_provider(cfg, parsed["provider_id"])
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")
    api_key = ""
    provider_label = ""
    if provider:
        provider_label = f"{provider.get('name') or provider.get('id')} ({provider.get('id')})"
        api_key = str(provider.get("api_key") or "").strip()
    if not api_key:
        api_key = openrouter_api_key_from_env()
        if api_key and not provider_label:
            provider_label = "OPENROUTER_API_KEY"
    summary = probe_openrouter_extension(
        api_key,
        assume_paid=bool(parsed["assume_paid"]),
    )
    if parsed["json"]:
        console.print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    display_openrouter_extension_summary(
        summary,
        provider_label=provider_label,
        limit=int(parsed["limit"]),
        show_models=action == "models",
    )
