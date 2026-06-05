"""Launch selection, usage, and model picker helpers."""

from __future__ import annotations


def runtime_usage_key(runtime, cli_name):
    kind = runtime.get("runtime_kind", "provider")
    runtime_id = runtime.get("id", "default")
    return f"{kind}:{cli_name}:{runtime_id}"


def resolve_model_name(model_info):
    if isinstance(model_info, dict):
        for key in ("model", "sonnet", "opus", "haiku"):
            value = model_info.get(key)
            if value:
                return str(value)
        return "official-default"
    return str(model_info or "official-default")


def runtime_hint_from_runtime(runtime, *, runtime_provider_id, runtime_account_id):
    if not isinstance(runtime, dict):
        return {}
    hint = {
        "runtime_kind": str(runtime.get("runtime_kind", "")).strip(),
        "auth_mode": str(runtime.get("auth_mode", "")).strip(),
    }
    provider_id = runtime_provider_id(runtime)
    account_id = runtime_account_id(runtime)
    runtime_id = str(runtime.get("id") or "").strip()
    if provider_id:
        hint["provider_id"] = provider_id
    if account_id:
        hint["account_id"] = account_id
    if runtime_id:
        hint["runtime_id"] = runtime_id
    return {k: v for k, v in hint.items() if v}


def record_usage(
    runtime,
    cli_name,
    model_info,
    *,
    update_usage_stats,
    iso_now,
    runtime_usage_key=runtime_usage_key,
    resolve_model_name=resolve_model_name,
    runtime_hint_from_runtime,
):
    def _mutate(stats):
        sources = stats.setdefault("sources", {})
        key = runtime_usage_key(runtime, cli_name)
        model_name = resolve_model_name(model_info)
        now = iso_now()
        entry = sources.setdefault(key, {
            "runtime_kind": runtime.get("runtime_kind", "provider"),
            "id": runtime.get("id", "default"),
            "name": runtime.get("name", runtime.get("id", "default")),
            "cli": cli_name,
            "launches": 0,
            "last_used_at": "",
            "last_model": "",
            "models": {},
            "model_last_used_at": {},
        })
        entry["launches"] += 1
        entry["last_used_at"] = now
        entry["last_model"] = model_name
        models = entry.setdefault("models", {})
        models[model_name] = int(models.get(model_name, 0)) + 1
        model_last_used_at = entry.setdefault("model_last_used_at", {})
        model_last_used_at[model_name] = now
        last_by_cli = stats.setdefault("last_by_cli", {})
        last_by_cli[cli_name] = {
            "cli": cli_name,
            "model": model_name,
            "model_info": model_info if isinstance(model_info, dict) else {"model": str(model_info)},
            "runtime_hint": runtime_hint_from_runtime(runtime),
            "last_used_at": now,
        }

    update_usage_stats(_mutate)


def record_scene_usage(
    scene_name,
    cli_name,
    model_info,
    *,
    update_usage_stats,
    iso_now,
    resolve_model_name=resolve_model_name,
):
    if not scene_name or str(scene_name).startswith("__"):
        return

    def _mutate(stats):
        scene_stats = stats.setdefault("scenes", {})
        model_name = resolve_model_name(model_info)
        entry = scene_stats.setdefault(scene_name, {
            "launches": 0,
            "last_used_at": "",
            "last_cli": "",
            "last_model": "",
        })
        entry["launches"] += 1
        entry["last_used_at"] = iso_now()
        entry["last_cli"] = cli_name
        entry["last_model"] = model_name

    update_usage_stats(_mutate)


def infer_runtime_hint_from_usage_stats(stats, cli_name, model_name):
    latest_entry = None
    latest_at = ""
    normalized_model = str(model_name or "").strip()
    for entry in (stats.get("sources", {}) or {}).values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("cli") or "").strip() != str(cli_name or "").strip():
            continue
        if str(entry.get("last_model") or "").strip() != normalized_model:
            continue
        used_at = str(entry.get("last_used_at") or "").strip()
        if used_at < latest_at:
            continue
        latest_at = used_at
        latest_entry = entry

    if not isinstance(latest_entry, dict):
        return {}

    runtime_kind = str(latest_entry.get("runtime_kind") or "").strip()
    runtime_id = str(latest_entry.get("id") or "").strip()
    if not runtime_kind or not runtime_id:
        return {}

    hint = {
        "runtime_kind": runtime_kind,
        "runtime_id": runtime_id,
    }
    if runtime_kind == "provider":
        hint["auth_mode"] = "api_key"
        hint["provider_id"] = runtime_id
    elif runtime_kind == "account":
        hint["auth_mode"] = "oauth"
        hint["account_id"] = runtime_id
    else:
        return {}
    return hint


def get_scene_usage(
    *,
    load_usage_stats,
    resolve_model_name=resolve_model_name,
    infer_runtime_hint_from_usage_stats=infer_runtime_hint_from_usage_stats,
):
    stats = load_usage_stats()
    scene_counts = {}
    for name, entry in stats.get("scenes", {}).items():
        scene_counts[name] = entry.get("launches", 0)
    last_by_cli = {}
    for cli_name, item in (stats.get("last_by_cli", {}) or {}).items():
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        if not isinstance(normalized.get("runtime_hint"), dict):
            model_name = resolve_model_name(
                normalized.get("model_info") if isinstance(normalized.get("model_info"), dict) else normalized.get("model")
            )
            inferred = infer_runtime_hint_from_usage_stats(stats, cli_name, model_name)
            if inferred:
                normalized["runtime_hint"] = inferred
        last_by_cli[cli_name] = normalized
    return last_by_cli, scene_counts


def resolve_last_used_runtime(
    cfg,
    cli_name,
    last_item,
    default_models,
    *,
    resolve_model_name=resolve_model_name,
    resolve_provider_context,
    provider_supports_model_for_cli,
    probe_models,
    provider_effective_models,
    runtime_with_priority,
    resolve_account_context,
    model_matches_account_cli,
):
    if not isinstance(last_item, dict):
        return None, None, None

    hint = last_item.get("runtime_hint")
    if not isinstance(hint, dict):
        return None, None, None

    model_info = last_item.get("model_info") if isinstance(last_item.get("model_info"), dict) else {
        "model": str(last_item.get("model") or "")
    }
    model_name = resolve_model_name(model_info)

    provider_id = str(hint.get("provider_id") or "").strip()
    if provider_id:
        try:
            provider = resolve_provider_context(cfg, provider_id)
        except Exception:
            provider = None
        if provider and provider_supports_model_for_cli(provider, cli_name, model_name):
            models = probe_models(provider, emit_output=False).get("models")
            models = provider_effective_models(provider, models, cfg)
            if str(model_name or "").strip().lower() in {
                str(item or "").strip().lower() for item in (models or [])
            }:
                return (
                    runtime_with_priority(provider, model_name=model_name),
                    models,
                    f"last used provider:{provider_id}",
                )

    auth_mode = str(hint.get("auth_mode") or "").strip()
    account_id = str(hint.get("account_id") or "").strip()
    if account_id and auth_mode != "oauth_bridge":
        try:
            account = resolve_account_context(cfg, account_id=account_id, cli_name=cli_name)
        except Exception:
            account = None
        if account and model_matches_account_cli(cli_name, model_name):
            return (
                runtime_with_priority(account, model_name=model_name),
                list(default_models or []),
                f"last used account:{account_id}",
            )

    return None, None, None


def all_provider_models_for_cli(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    mms_model_visible,
    provider_supports_model_for_cli,
):
    merged = []
    seen = set()
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not provider_has_configured_base_url(provider) or not provider.get("api_key"):
            continue
        models = provider_effective_models(provider, cached_models, cfg)
        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized or normalized in seen:
                continue
            if not mms_model_visible(normalized):
                continue
            if not provider_supports_model_for_cli(provider, cli_name, normalized):
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def aggregate_provider_models(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    provider_label,
    mms_model_visible,
    provider_supports_model_for_cli,
    default_provider_id,
):
    aggregated = []
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not provider_has_configured_base_url(provider) or not provider.get("api_key"):
            continue
        models = provider_effective_models(provider, cached_models, cfg)
        provider_id = provider.get("id", default_provider_id)
        provider_name = provider_label(provider)
        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized:
                continue
            if not mms_model_visible(normalized):
                continue
            if not provider_supports_model_for_cli(provider, cli_name, normalized):
                continue
            aggregated.append({
                "model": normalized,
                "provider_id": provider_id,
                "provider_name": provider_name,
            })
    return aggregated


def categorize_models(models, *, filter_visible_models, infer_model_family):
    categorized = {}
    for model_name in filter_visible_models(models):
        _, category = infer_model_family(model_name)
        categorized.setdefault(category, []).append(model_name)
    return categorized


def display_models(
    models,
    role,
    recommend,
    *,
    ensure_rich,
    categorize_models,
    normalize_user_role,
    mode_recommended,
    model_capability_summary,
    model_cli_summary,
    table_cls,
    console,
):
    ensure_rich()
    categorized = categorize_models(models)
    table = table_cls(title="可用模型", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("模型", style="green")
    table.add_column("分类", style="yellow")
    table.add_column("能力", style="magenta")
    table.add_column("CLI", style="dim")

    flat = []
    for category, category_models in categorized.items():
        for model_name in category_models:
            flat.append((model_name, category))

    if normalize_user_role(role) == mode_recommended and recommend:
        flat = [(model_name, category) for model_name, category in flat if model_name in recommend]

    for index, (model_name, category) in enumerate(flat, 1):
        tag = " ⭐" if recommend and model_name in recommend else ""
        table.add_row(
            str(index),
            model_name + tag,
            category,
            model_capability_summary(model_name),
            model_cli_summary(model_name),
        )

    console.print(table)
    return [model_name for model_name, _ in flat]


def filter_models_for_display(models, role, recommend, *, categorize_models, normalize_user_role, mode_recommended):
    categorized = categorize_models(models)
    flat = []
    for category, category_models in categorized.items():
        for model_name in category_models:
            flat.append((model_name, category))
    if normalize_user_role(role) == mode_recommended and recommend:
        allowed = set(recommend)
        flat = [(model_name, category) for model_name, category in flat if model_name in allowed]
    return flat


def group_models_for_custom(models, role, recommend, *, filter_models_for_display, infer_model_family):
    grouped = {}
    order = []
    for model_name, _ in filter_models_for_display(models, role, recommend):
        family, _ = infer_model_family(model_name)
        if family not in grouped:
            grouped[family] = []
            order.append(family)
        grouped[family].append(model_name)
    return [(family, grouped[family]) for family in order]


def group_models_by_family_and_provider(
    aggregated_models,
    role,
    recommend,
    *,
    filter_models_for_display,
    infer_model_family,
):
    plain_models = [entry["model"] for entry in aggregated_models]
    allowed = {
        model_name for model_name, _ in filter_models_for_display(plain_models, role, recommend)
    }

    family_order = []
    family_providers = {}
    for entry in aggregated_models:
        model_name = entry["model"]
        if model_name not in allowed:
            continue
        family, _ = infer_model_family(model_name)
        provider_key = f"{entry['provider_name']}||{entry['provider_id']}"

        if family not in family_providers:
            family_providers[family] = {}
            family_order.append(family)
        providers = family_providers[family]
        providers.setdefault(provider_key, [])
        if model_name not in providers[provider_key]:
            providers[provider_key].append(model_name)

    return [(family, dict(family_providers[family])) for family in family_order]


def select_custom_model(
    models,
    cli_name,
    role="all",
    recommend=None,
    use_tui=False,
    *,
    group_models_by_family_and_provider,
    group_models_for_custom,
    table_cls,
    int_prompt_cls,
    console,
    exit_func,
    select_model_tui=None,
):
    """Select model by family, provider, then model; supports legacy and aggregated inputs."""
    is_aggregated = models and isinstance(models[0], dict)

    if is_aggregated:
        groups = group_models_by_family_and_provider(models, role, recommend)
    else:
        plain_groups = group_models_for_custom(models, role, recommend)
        groups = [(family, {"_default_||_default_": items}) for family, items in plain_groups]

    if not groups:
        return (None, None) if is_aggregated else None

    if use_tui and select_model_tui is None:
        from mms_display.tui import select_model_tui as select_model_tui_impl

        select_model_tui = select_model_tui_impl

    if len(groups) == 1:
        selected_family, provider_map = groups[0]
    else:
        total_per_family = []
        for family, pmap in groups:
            count = sum(len(m) for m in pmap.values())
            total_per_family.append(count)
        family_labels = [f"{family} ({total_per_family[i]})" for i, (family, _) in enumerate(groups)]
        if use_tui:
            selected_label = select_model_tui(family_labels, title=f"为 {cli_name} 选择模型品牌")
            if selected_label is None:
                return (None, None) if is_aggregated else None
            family_index = family_labels.index(selected_label)
        else:
            family_index = None
            while family_index is None:
                table = table_cls(title=f"{cli_name} · 选择模型品牌", show_lines=True)
                table.add_column("#", style="cyan", width=4)
                table.add_column("品牌", style="green")
                table.add_column("数量", style="yellow", width=6)
                for idx, (family, _) in enumerate(groups, 1):
                    table.add_row(str(idx), family, str(total_per_family[idx - 1]))
                console.print(table)
                try:
                    picked = int_prompt_cls.ask("选择模型品牌编号") - 1
                except KeyboardInterrupt:
                    exit_func(0)
                if 0 <= picked < len(groups):
                    family_index = picked
                else:
                    console.print(f"[red]请输入 1-{len(groups)}[/red]")
        selected_family, provider_map = groups[family_index]

    provider_keys = list(provider_map.keys())
    if len(provider_keys) == 1:
        selected_provider_key = provider_keys[0]
    else:
        provider_labels = []
        for key in provider_keys:
            label, _ = key.split("||", 1)
            count = len(provider_map[key])
            provider_labels.append(f"{label} ({count})")
        if use_tui:
            selected_label = select_model_tui(provider_labels, title=f"{selected_family} · 选择 Provider")
            if selected_label is None:
                return (None, None) if is_aggregated else None
            provider_index = provider_labels.index(selected_label)
        else:
            provider_index = None
            while provider_index is None:
                table = table_cls(title=f"{cli_name} · {selected_family} · 选择 Provider", show_lines=True)
                table.add_column("#", style="cyan", width=4)
                table.add_column("Provider", style="green")
                table.add_column("模型数", style="yellow", width=6)
                for idx, plabel in enumerate(provider_labels, 1):
                    table.add_row(str(idx), plabel, "")
                console.print(table)
                try:
                    picked = int_prompt_cls.ask("选择 Provider 编号") - 1
                except KeyboardInterrupt:
                    exit_func(0)
                if 0 <= picked < len(provider_keys):
                    provider_index = picked
                else:
                    console.print(f"[red]请输入 1-{len(provider_keys)}[/red]")
        selected_provider_key = provider_keys[provider_index]

    family_models = provider_map[selected_provider_key]
    _, selected_provider_id = selected_provider_key.split("||", 1)

    if use_tui:
        model = select_model_tui(family_models, title=f"{selected_family} · 选择子模型")
    else:
        model = None
        while model is None:
            table = table_cls(title=f"{cli_name} · {selected_family}", show_lines=True)
            table.add_column("#", style="cyan", width=4)
            table.add_column("模型", style="green")
            for idx, model_name in enumerate(family_models, 1):
                table.add_row(str(idx), model_name)
            console.print(table)
            try:
                model_index = int_prompt_cls.ask("选择子模型编号") - 1
            except KeyboardInterrupt:
                exit_func(0)
            if 0 <= model_index < len(family_models):
                model = family_models[model_index]
            else:
                console.print(f"[red]请输入 1-{len(family_models)}[/red]")

    if is_aggregated:
        pid = selected_provider_id if selected_provider_id != "_default_" else None
        return (model, pid) if model else (None, None)
    return model


def select_model_interactive(models_list, *, int_prompt_cls, console, exit_func):
    while True:
        try:
            choice = int_prompt_cls.ask("选择模型编号")
            if 1 <= choice <= len(models_list):
                return models_list[choice - 1]
            console.print(f"[red]请输入 1-{len(models_list)}[/red]")
        except KeyboardInterrupt:
            exit_func(0)


def build_provider_options_map(
    cfg,
    cli_name,
    default_provider,
    default_models,
    model_names,
    *,
    infer_model_family,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    provider_supports_model_for_cli,
    runtime_with_priority,
    provider_label,
    account_options_for_model,
    default_provider_id,
):
    result = {}
    for model_name in model_names:
        selected_family, _ = infer_model_family(model_name)
        options = []
        for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
            if not provider.get("enabled", True):
                continue
            if not provider_has_configured_base_url(provider):
                continue
            if not provider.get("api_key"):
                continue
            models = provider_effective_models(provider, cached_models, cfg)
            model_lower = [str(item or "").strip().lower() for item in models]
            if model_name.strip().lower() not in model_lower:
                continue
            if not provider_supports_model_for_cli(provider, cli_name, model_name):
                continue
            runtime = runtime_with_priority(provider, model_name=model_name, family_name=selected_family)
            options.append({
                "provider_name": provider_label(provider),
                "provider_id": provider.get("id", default_provider_id),
                "priority_family": selected_family,
                "provider_ctx": runtime,
            })
        account_options = account_options_for_model(
            cfg,
            cli_name,
            default_models,
            model_info={"model": model_name},
            allow_selected_model=True,
        )
        for option in account_options:
            runtime = option.get("runtime") or {}
            options.append({
                "provider_name": f"{option.get('title', runtime.get('id', 'account'))} OAuth",
                "provider_id": runtime.get("id", ""),
                "priority_family": option.get("priority_family", selected_family),
                "provider_ctx": runtime,
            })
        if len(options) > 1:
            result[model_name] = options
    return result


def make_provider_options_loader(cfg, cli_name, default_provider, default_models, *, build_provider_options_map):
    cache = {}

    def _loader(model_name):
        key = str(model_name or "").strip()
        if not key:
            return []
        if key not in cache:
            cache[key] = build_provider_options_map(
                cfg, cli_name, default_provider, default_models, [key]
            ).get(key, [])
        return cache[key]

    return _loader


def apply_runtime_priority_changes(
    cfg,
    pri_changes,
    *,
    canonical_model_family,
    normalize_family_priority_overrides,
    normalize_priority,
):
    changed = False
    if not pri_changes:
        return changed

    for runtime_id, new_priority in pri_changes.items():
        family_name = ""
        actual_runtime_id = runtime_id
        if "||" in str(runtime_id):
            actual_runtime_id, family_name = str(runtime_id).split("||", 1)
            family_name = canonical_model_family(family_name)
        matched = False
        for provider_def in cfg.get("providers", []):
            if provider_def.get("id") == actual_runtime_id:
                if family_name:
                    overrides = normalize_family_priority_overrides(
                        provider_def.get("family_priority_overrides", {})
                    )
                    overrides[family_name] = normalize_priority(new_priority)
                    provider_def["family_priority_overrides"] = overrides
                else:
                    provider_def["priority"] = normalize_priority(new_priority)
                changed = True
                matched = True
                break
        if matched:
            continue
        for account_def in cfg.get("accounts", []):
            if account_def.get("id") == actual_runtime_id:
                if family_name:
                    overrides = normalize_family_priority_overrides(
                        account_def.get("family_priority_overrides", {})
                    )
                    overrides[family_name] = normalize_priority(new_priority)
                    account_def["family_priority_overrides"] = overrides
                else:
                    account_def["priority"] = normalize_priority(new_priority)
                changed = True
                break
    return changed


def resolve_visible_clis(
    cfg,
    default_provider,
    default_models,
    *,
    cli_names,
    managed_oauth_clis,
    cli_model_family_hints,
    accounts_for_cli,
    check_cli_installed,
    resolve_provider_for_cli,
    disabled_clis=(),
):
    visible = []
    disabled = set(disabled_clis or [])

    for cli_name in cli_names:
        if cli_name in disabled:
            continue
        if cli_name in managed_oauth_clis:
            if accounts_for_cli(cfg, cli_name):
                visible.append(cli_name)
                continue
            # Antigravity is OAuth-native, so show the tab before account setup
            # when the binary exists and let the TUI connect flow handle setup.
            if cli_name == "agy":
                try:
                    if check_cli_installed(cli_name):
                        visible.append(cli_name)
                        continue
                except Exception:
                    pass
        provider, family_models = resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)
        if provider is None:
            continue
        if cli_name in cli_model_family_hints and not family_models:
            continue
        visible.append(cli_name)

    return visible


def use_tui(stdin, get_terminal_size, *, min_columns=40):
    if not stdin.isatty():
        return False
    try:
        cols = get_terminal_size().columns
        return cols >= min_columns
    except OSError:
        return False


def clean_model_info(model_info):
    if not isinstance(model_info, dict):
        return model_info
    return {key: value for key, value in model_info.items() if key != "provider"}


def uses_native_account_entry(runtime, cli, *, oauth_capable_clis):
    return bool(runtime and runtime.get("auth_mode") == "oauth" and cli in oauth_capable_clis)


def uses_broker_entry(runtime, cli):
    return bool(runtime and runtime.get("runtime_kind") == "broker" and cli == "claude")


def uses_managed_entry(runtime, cli, *, oauth_capable_clis):
    return uses_native_account_entry(runtime, cli, oauth_capable_clis=oauth_capable_clis)


DIRECT_CLI_LAUNCH_DEFAULTS = {
    "claude": (
        ("direct-deepseek", "deepseek-v4-pro"),
        ("direct-deepseek", "deepseek-v4-flash"),
        ("mimo-direct", "mimo-v2.5"),
    ),
    "codex": (
        ("uscrsopenai", "gpt-5.4"),
        ("uscrsopenai", "gpt-5.5"),
        ("uscrsopenai", "gpt-5.3-codex"),
    ),
    "pi": (
        ("mimo-direct", "mimo-v2.5"),
        ("direct-deepseek", "deepseek-v4-pro"),
        ("direct-zai", "glm-5.1"),
        ("direct-zai", "glm-5-turbo"),
    ),
}


def resolve_direct_cli_launch_default(
    cli_name,
    cfg,
    default_provider,
    default_models,
    *,
    provider_candidates,
    provider_effective_models,
    provider_supports_model_for_cli,
):
    cli_name = str(cli_name or "").strip().lower()
    if cli_name == "opencode":
        opencode = cfg.get("opencode") if isinstance(cfg, dict) and isinstance(cfg.get("opencode"), dict) else {}
        if opencode.get("default_profile") or opencode.get("profile"):
            return {}
        return {"profile": "pro", "source": "launch default"}

    wanted = DIRECT_CLI_LAUNCH_DEFAULTS.get(cli_name)
    if not wanted:
        return {}

    provider_map = {}
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        provider_id = str((provider or {}).get("id") or "").strip()
        if provider_id and provider_id not in provider_map:
            provider_map[provider_id] = (provider, cached_models)

    for provider_id, model_name in wanted:
        provider_entry = provider_map.get(provider_id)
        if not provider_entry:
            continue
        provider, cached_models = provider_entry
        if not provider.get("enabled", True) or not provider.get("api_key"):
            continue
        models = provider_effective_models(provider, cached_models, cfg)
        models_by_lower = {
            str(item or "").strip().lower(): str(item or "").strip()
            for item in models or []
            if str(item or "").strip()
        }
        actual_model = models_by_lower.get(str(model_name or "").strip().lower())
        if not actual_model:
            continue
        if not provider_supports_model_for_cli(provider, cli_name, actual_model):
            continue
        return {
            "provider": provider_id,
            "model": actual_model,
            "model_info": {"model": actual_model},
            "source": "launch default",
        }
    return {}


def resolve_interactive_launch_model(
    cli,
    runtime,
    cli_models,
    models_cache,
    role,
    recommend,
    *,
    uses_native_account_entry,
    uses_broker_entry,
    ensure_models_cache_available,
    display_models,
    select_model_interactive,
    console,
):
    if uses_native_account_entry(runtime, cli):
        console.print(f"[cyan]{cli} 当前使用账号档案登录，直接进入官方 CLI；模型选择交由官方 CLI 处理。[/cyan]")
        return True, None

    if uses_broker_entry(runtime, cli):
        console.print(f"[cyan]{cli} 当前使用 broker profile；先选模型，然后直接进入 remote official Claude Code。[/cyan]")
        available_models = cli_models or models_cache
        if not ensure_models_cache_available(available_models):
            return False, None
        models_list = display_models(available_models, role, recommend)
        return True, select_model_interactive(models_list)

    available_models = cli_models or models_cache
    if not ensure_models_cache_available(available_models):
        return False, None
    models_list = display_models(available_models, role, recommend)
    return True, select_model_interactive(models_list)


def preset_model_info(preset, *, excluded_keys=frozenset({"cli", "provider", "account", "description", "bridge"})):
    if not isinstance(preset, dict):
        return {}
    return {key: value for key, value in preset.items() if key not in excluded_keys}


def save_preset_interactive(
    cfg,
    cli,
    model_info,
    *,
    prompt_ask,
    normalize_preset_entry,
    save_config,
    console,
):
    name = prompt_ask("预设名称")
    description = prompt_ask("预设描述（可留空）", default="").strip()
    preset = {"cli": cli}
    if isinstance(model_info, dict):
        preset.update(model_info)
    else:
        preset["model"] = model_info
    if "presets" not in cfg:
        cfg["presets"] = {}
    if description:
        preset["description"] = description
    cfg["presets"][name] = normalize_preset_entry(name, preset)
    save_config(cfg)
    console.print(f"[green]✓ 预设 '{name}' 已保存[/green]")
