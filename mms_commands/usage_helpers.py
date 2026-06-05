"""Usage and model-family helpers for command flows."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone


def usage_key(runtime_kind, cli_name, runtime_id):
    return f"{runtime_kind}:{cli_name}:{runtime_id}"


def rename_usage_account(
    old_id,
    new_id,
    new_name,
    cli_name,
    *,
    usage_path,
    path_exists=os.path.exists,
    update_usage_stats,
    usage_key=usage_key,
):
    if not path_exists(usage_path):
        return False

    def _mutate(stats):
        sources = stats.get("sources", {})
        old_key = usage_key("account", cli_name, old_id)
        entry = sources.pop(old_key, None)
        if entry is None:
            return False
        entry["id"] = new_id
        entry["name"] = new_name
        sources[usage_key("account", cli_name, new_id)] = entry
        return True

    return bool(update_usage_stats(_mutate))


def rename_usage_provider(
    old_id,
    new_id,
    new_name,
    *,
    usage_path,
    path_exists=os.path.exists,
    update_usage_stats,
    usage_key=usage_key,
):
    if not path_exists(usage_path):
        return False

    def _mutate(stats):
        sources = stats.get("sources", {})
        changed = False
        rewritten = {}
        for key, entry in list(sources.items()):
            if entry.get("runtime_kind") != "provider" or entry.get("id") != old_id:
                continue
            sources.pop(key, None)
            updated = dict(entry)
            updated["id"] = new_id
            updated["name"] = new_name
            cli_name = str(updated.get("cli", "default")).strip() or "default"
            rewritten[usage_key("provider", cli_name, new_id)] = updated
            changed = True
        sources.update(rewritten)
        return changed

    return bool(update_usage_stats(_mutate))


def parse_usage_timestamp(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def usage_recency_score(value, now=None, half_life_days=14, *, parse_usage_timestamp=parse_usage_timestamp):
    parsed = parse_usage_timestamp(value)
    if parsed is None:
        return 0.0
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    if half_life_days <= 0:
        return 1.0
    age_days = max(0.0, (current - parsed).total_seconds()) / 86400.0
    return 0.5 ** (age_days / float(half_life_days))


def sort_family_entries_for_tui(families, preferred_family="", now=None, *, usage_recency_score=usage_recency_score):
    def _key(item):
        family = str(item.get("family") or "") if isinstance(item, dict) else ""
        last_at = str(item.get("last_used_at") or "").strip() if isinstance(item, dict) else ""
        recency = usage_recency_score(last_at, now=now)
        has_recent = 1 if recency > 0 else 0
        preferred_rank = 0 if family == str(preferred_family or "").strip() else 1
        return (-has_recent, -recency, preferred_rank, family.lower())

    return sorted(list(families or []), key=_key)


def family_is_cold_for_tui(
    family_name,
    total_use,
    last_used_at="",
    *,
    preferred_family="",
    known_model_family_names,
    cold_max_use_count,
    cold_idle_days,
    parse_usage_timestamp=parse_usage_timestamp,
    now=None,
):
    if str(family_name or "").strip() == str(preferred_family or "").strip():
        return False
    if str(family_name or "").strip() in known_model_family_names:
        return False
    if int(total_use or 0) > cold_max_use_count:
        return False
    parsed = parse_usage_timestamp(last_used_at)
    if parsed is None:
        return True
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    return parsed < (current - timedelta(days=cold_idle_days))


def build_model_families_for_cli(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    normalize_role,
    runtime_priority_for_model,
    runtime_with_priority,
    provider_label,
    mms_model_visible,
    infer_model_family,
    load_usage_stats,
    provider_supports_model_for_cli,
    role_weights,
    default_provider_id,
):
    """Aggregate provider models by family and attach the best runtime provider."""
    model_best = {}
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not provider_has_configured_base_url(provider):
            continue
        if not provider.get("api_key"):
            continue

        models = provider_effective_models(provider, cached_models, cfg)
        if not models:
            continue

        role = normalize_role(provider.get("role", "auto"))
        provider_id = provider.get("id", default_provider_id)
        provider_name = provider_label(provider)

        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized:
                continue
            if not provider_supports_model_for_cli(provider, cli_name, normalized):
                continue
            priority = runtime_priority_for_model(provider, normalized)
            score = (role_weights.get(role, 1), -priority)
            existing = model_best.get(normalized)
            if existing is None or score < existing[0]:
                model_best[normalized] = (
                    score,
                    runtime_with_priority(provider, model_name=normalized),
                    provider_name,
                    provider_id,
                )

    use_counts = {}
    last_used_at_by_model = {}
    stats = load_usage_stats()
    for source in stats.get("sources", {}).values():
        if str(source.get("cli") or "").strip() != str(cli_name or "").strip():
            continue
        used_at = str(source.get("last_used_at") or "").strip()
        model_last_used_at = source.get("model_last_used_at")
        if not isinstance(model_last_used_at, dict):
            model_last_used_at = {}
        for model_name, count in source.get("models", {}).items():
            use_counts[model_name] = use_counts.get(model_name, 0) + count
            model_used_at = str(model_last_used_at.get(model_name) or "").strip()
            if model_used_at and model_used_at > last_used_at_by_model.get(model_name, ""):
                last_used_at_by_model[model_name] = model_used_at
        last_model = str(source.get("last_model") or "").strip()
        if (
            last_model
            and used_at
            and last_model not in model_last_used_at
            and used_at > last_used_at_by_model.get(last_model, "")
        ):
            last_used_at_by_model[last_model] = used_at

    family_map = {}
    family_order = []

    for model_name, (_, provider_ctx, provider_name, provider_id) in model_best.items():
        if not mms_model_visible(model_name):
            continue
        family, _ = infer_model_family(model_name)
        if family not in family_map:
            family_map[family] = []
            family_order.append(family)
        family_map[family].append({
            "model": model_name,
            "family": family,
            "provider_id": provider_id,
            "provider_name": provider_name,
            "provider_ctx": provider_ctx,
            "use_count": use_counts.get(model_name, 0),
            "last_used_at": last_used_at_by_model.get(model_name, ""),
        })

    return [{"family": family, "models": family_map[family]} for family in family_order]
