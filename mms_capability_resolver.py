"""Profile/registry-backed model capability resolution for MMS.

This module is intentionally runtime-adjacent, not runtime-owning. It does not
query SQLite directly and it does not alter provider/model/account selection.
By default it reads the verified latest-approved capability export when
available. Explicitly selected preview roots fail closed when that bundle is
missing or corrupt; stable legacy roots can still fall back to provider profiles
and then conservative defaults.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from mms_provider_profiles import load_provider_profiles, resolve_provider_profile


class CapabilityBundleError(RuntimeError):
    """Raised when selected-root capability facts cannot be safely verified."""


CONSERVATIVE_CAPABILITY_FALLBACK: dict[str, Any] = {
    "context_window_tokens": 8_192,
    "max_output_tokens": 4_096,
    "supports_vision": False,
    "supports_thinking": False,
    "thinking_control": {
        "supported": False,
        "control_type": "none",
        "path": "",
    },
    "expected_protocol": "unknown",
    "protocol_hints": {
        "protocols": [],
        "preferred_protocol": "unknown",
        "cache_sensitive_transport": False,
        "openai_chat_completions_is_fallback": False,
    },
    "body_patch_aliases": {
        "body_patches": {},
        "parameter_aliases": {},
        "model_aliases": {},
    },
}

_CAPABILITY_FIELDS = (
    "context_window_tokens",
    "max_output_tokens",
    "supports_vision",
    "supports_thinking",
    "thinking_control",
    "expected_protocol",
    "protocol_hints",
    "body_patch_aliases",
)

_CONTEXT_KEYS = (
    "context_window_tokens",
    "max_context_tokens",
    "official_context_window_tokens",
    "context_tokens",
    "context_window",
)

_MAX_OUTPUT_KEYS = (
    "max_output_tokens",
    "official_max_output_tokens",
    "max_completion_tokens",
    "output_window_tokens",
)

_THINKING_KEYS = (
    "supports_thinking",
    "thinking_supported",
    "thinking",
    "think",
)

_VISION_KEYS = (
    "supports_vision",
    "vision",
    "image_input",
    "multimodal",
)

_PROTOCOL_KEYS = (
    "expected_protocol",
    "protocol",
    "preferred_protocol",
)


def load_approved_facts(path: str | Path | None) -> dict[str, Any]:
    """Read an approved/export capability payload, returning empty on failure."""
    if not path:
        return {}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def load_default_approved_facts() -> dict[str, Any]:
    """Read verified latest-approved capability facts.

    Stable legacy roots keep conservative fallback compatibility. Explicit
    preview roots must not silently continue when the selected latest-approved
    bundle is missing or invalid.
    """
    try:
        import mms_registry
    except Exception:
        return {}
    try:
        return mms_registry.load_latest_approved_bundle(include_secret=False).get("payloads", {}).get("capabilities") or {}
    except Exception as exc:
        try:
            from mms_state_io import mms_config_root_mode, resolve_mms_config_dir

            config_root = resolve_mms_config_dir()
            if mms_config_root_mode(config_root) == "preview":
                raise CapabilityBundleError(f"latest-approved capabilities unavailable for selected config root: {exc}") from exc
        except CapabilityBundleError:
            raise
        except Exception:
            pass
    return {}


def load_default_model_policy() -> dict[str, Any]:
    """Read non-secret model policy overlays from the selected config root."""
    try:
        from mms_state_io import resolve_mms_config_dir

        config_root = Path(resolve_mms_config_dir())
    except Exception:
        return {}

    merged: dict[str, Any] = {}
    # Generated effective policy is what preview/DB publishes; the root policy is
    # the human source overlay and should win if it was edited after generation.
    for path in (
        config_root / "generated" / "model-policy.effective.json",
        config_root / "model-policy.json",
    ):
        payload = load_approved_facts(path)
        if payload:
            merged = _deep_merge(merged, payload)
    return merged


def resolve_model_capabilities(
    model_name: str,
    *,
    runtime: Mapping[str, Any] | None = None,
    provider_id: str = "",
    base_url: str = "",
    profile_id: str = "",
    manual_override: Mapping[str, Any] | None = None,
    approved_facts: Mapping[str, Any] | None = None,
    approved_facts_path: str | Path | None = None,
    model_policy: Mapping[str, Any] | None = None,
    model_policy_path: str | Path | None = None,
    provider_profiles: Mapping[str, Any] | None = None,
    conservative_fallback: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve effective model capabilities.

    Source order is per-field:
    manual override > model policy > approved registry/export facts >
    provider profile > conservative fallback.
    """
    model = _clean(model_name)
    runtime_dict = dict(runtime or {})
    fallback = _normalize_capability_payload(
        _deep_merge(CONSERVATIVE_CAPABILITY_FALLBACK, dict(conservative_fallback or {})),
        model_name=model,
    )
    result = _base_result(model, fallback)

    profile_caps = _provider_profile_capabilities(
        model,
        runtime=runtime_dict,
        provider_id=provider_id,
        base_url=base_url,
        profile_id=profile_id,
        provider_profiles=provider_profiles,
    )
    _apply_source(result, profile_caps, "provider_profile")

    approved_payload = load_approved_facts(approved_facts_path)
    if approved_facts_path is None and approved_facts is None:
        approved_payload = load_default_approved_facts()
    if approved_facts:
        approved_payload = _deep_merge(approved_payload, dict(approved_facts))
    approved_caps = _approved_capabilities(model, approved_payload)
    _apply_source(result, approved_caps, "approved_facts")

    policy_payload = load_approved_facts(model_policy_path)
    if model_policy_path is None and model_policy is None and approved_facts is None and approved_facts_path is None:
        policy_payload = load_default_model_policy()
    if model_policy:
        policy_payload = _deep_merge(policy_payload, dict(model_policy))
    policy_caps = _policy_capabilities(model, policy_payload)
    _apply_source(result, policy_caps, "model_policy")

    manual_caps = _normalize_capability_payload(dict(manual_override or {}), model_name=model)
    _apply_source(result, manual_caps, "manual_override")

    return result


def _base_result(model_name: str, fallback: Mapping[str, Any]) -> dict[str, Any]:
    result = {"model_name": model_name, "sources": {}}
    for field in _CAPABILITY_FIELDS:
        result[field] = copy.deepcopy(fallback.get(field, CONSERVATIVE_CAPABILITY_FALLBACK[field]))
        result["sources"][field] = "conservative_fallback"
    return result


def _apply_source(result: dict[str, Any], candidate: Mapping[str, Any], source: str) -> None:
    for field in _CAPABILITY_FIELDS:
        if field not in candidate:
            continue
        value = candidate[field]
        if not _value_present(field, value):
            continue
        result[field] = copy.deepcopy(value)
        result["sources"][field] = source


def _value_present(field: str, value: Any) -> bool:
    if field in {"context_window_tokens", "max_output_tokens"}:
        return isinstance(value, int) and value > 0
    if field in {"supports_thinking", "supports_vision"}:
        return isinstance(value, bool)
    if field == "expected_protocol":
        return bool(_clean(value))
    if field in {"thinking_control", "protocol_hints", "body_patch_aliases"}:
        return isinstance(value, Mapping) and bool(value)
    return value is not None


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _clean(value).lower()


def _normalize_model(value: Any) -> str:
    model = _lower(value)
    if "/" in model:
        model = model.rsplit("/", 1)[-1]
    return model


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, Mapping) and isinstance(override, Mapping):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = _deep_merge(merged.get(key), value)
        return merged
    if override is None:
        return copy.deepcopy(base)
    return copy.deepcopy(override)


def _first_int(payload: Mapping[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        if key not in payload:
            continue
        try:
            value = int(payload[key])
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _first_bool(payload: Mapping[str, Any], keys: tuple[str, ...]) -> bool | None:
    for key in keys:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, bool):
            return value
    return None


def _first_str(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _clean(payload.get(key))
        if value:
            return value
    return ""


def _normalize_capability_payload(payload: Mapping[str, Any], *, model_name: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    context_tokens = _first_int(payload, _CONTEXT_KEYS)
    if context_tokens is None and payload.get("one_m_context") is True:
        context_tokens = 1_000_000
    if context_tokens is not None:
        normalized["context_window_tokens"] = context_tokens

    max_output_tokens = _first_int(payload, _MAX_OUTPUT_KEYS)
    if max_output_tokens is not None:
        normalized["max_output_tokens"] = max_output_tokens

    supports_thinking = _first_bool(payload, _THINKING_KEYS)
    if supports_thinking is not None:
        normalized["supports_thinking"] = supports_thinking

    supports_vision = _first_bool(payload, _VISION_KEYS)
    if supports_vision is not None:
        normalized["supports_vision"] = supports_vision

    thinking_control = payload.get("thinking_control")
    if isinstance(thinking_control, Mapping):
        normalized["thinking_control"] = _normalize_thinking_control(thinking_control)
    elif isinstance(payload.get("thinking"), Mapping):
        normalized["thinking_control"] = _normalize_thinking_control(payload["thinking"])

    expected_protocol = _first_str(payload, _PROTOCOL_KEYS)
    if expected_protocol:
        normalized["expected_protocol"] = expected_protocol

    protocol_hints = _protocol_hints_from_payload(payload, expected_protocol)
    if protocol_hints:
        normalized["protocol_hints"] = protocol_hints

    aliases = _body_patch_aliases_from_payload(payload)
    if aliases:
        normalized["body_patch_aliases"] = aliases

    return normalized


def _normalize_thinking_control(control: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(control))
    path = _clean(normalized.get("path") or normalized.get("official_control"))
    control_type = _clean(normalized.get("control_type") or normalized.get("type"))
    if not path:
        path = _path_from_control_type(control_type)
    if not control_type and path:
        control_type = _control_type_from_path(path)
    if path:
        normalized["path"] = path
    if control_type:
        normalized["control_type"] = control_type
    if control_type == "thinkingLevel":
        normalized.setdefault("numeric_budget_tokens", None)
    if "supported" not in normalized:
        normalized["supported"] = control_type not in {"", "none"}
    return normalized


def _path_from_control_type(control_type: str) -> str:
    token = _lower(control_type)
    if token == "thinkinglevel":
        return "thinkingConfig.thinkingLevel"
    if token == "thinkingbudget":
        return "thinkingConfig.thinkingBudget"
    if token == "thinking.type":
        return "thinking.type"
    if token in {"reasoning.effort", "effort"}:
        return "reasoning.effort"
    return ""


def _control_type_from_path(path: str) -> str:
    token = _lower(path)
    if token.endswith("thinkingconfig.thinkinglevel") or "thinkinglevel" in token:
        return "thinkingLevel"
    if token.endswith("thinkingconfig.thinkingbudget") or "thinkingbudget" in token:
        return "thinkingBudget"
    if token == "thinking.type" or token.endswith(".thinking.type"):
        return "thinking.type"
    if token.endswith("reasoning.effort"):
        return "reasoning.effort"
    if token.endswith("output_config.effort"):
        return "output_config.effort"
    return path


def _normalize_protocol_token(value: Any) -> str:
    token = _lower(value)
    if token in {"openai_chat", "openai_chat_completion", "chat_completions", "chat/completions"}:
        return "openai_chat_completions"
    if token in {"anthropic", "anthropic_messages", "messages", "claude_messages"}:
        return "anthropic_messages"
    if token in {"response", "responses", "openai_responses"}:
        return "responses"
    return token


def _protocols_from_expected(expected_protocol: str) -> list[str]:
    raw = expected_protocol.replace(",", "/").replace("|", "/")
    protocols: list[str] = []
    for item in raw.split("/"):
        protocol = _normalize_protocol_token(item)
        if protocol and protocol not in protocols and protocol not in {"gateway", "proxy", "dependent"}:
            protocols.append(protocol)
    if "chat" in protocols and "completions" in protocols:
        protocols = [p for p in protocols if p not in {"chat", "completions"}]
        protocols.append("openai_chat_completions")
    return protocols


def _protocol_hints_from_payload(payload: Mapping[str, Any], expected_protocol: str = "") -> dict[str, Any]:
    hints: dict[str, Any] = {}
    if isinstance(payload.get("protocol_hints"), Mapping):
        hints.update(copy.deepcopy(dict(payload["protocol_hints"])))

    protocols: list[str] = []
    hint_protocols = hints.get("protocols")
    if isinstance(hint_protocols, list):
        for item in hint_protocols:
            protocol = _normalize_protocol_token(item)
            if protocol and protocol not in protocols:
                protocols.append(protocol)
    for item in payload.get("protocols") or []:
        protocol = _normalize_protocol_token(item)
        if protocol and protocol not in protocols:
            protocols.append(protocol)
    protocols.extend(p for p in _protocols_from_expected(expected_protocol) if p not in protocols)

    api_formats = payload.get("api_formats")
    if isinstance(api_formats, Mapping):
        hints.setdefault("api_formats", copy.deepcopy(dict(api_formats)))
        for key in api_formats:
            protocol = _normalize_protocol_token(key)
            if protocol and protocol not in protocols:
                protocols.append(protocol)

    explicit_cache_sensitive = isinstance(payload.get("cache_sensitive"), bool)
    if not hints and not protocols and not expected_protocol and not explicit_cache_sensitive:
        return {}

    preferred = _normalize_protocol_token(hints.get("preferred_protocol"))
    if not preferred:
        preferred = _preferred_protocol(protocols)
    if protocols:
        hints["protocols"] = protocols
    if preferred:
        hints["preferred_protocol"] = preferred

    cache_sensitive = _cache_sensitive_protocols(protocols, preferred, payload)
    hints["cache_sensitive_transport"] = cache_sensitive
    hints["openai_chat_completions_is_fallback"] = (
        "anthropic_messages" in protocols
        and "openai_chat_completions" in protocols
        and preferred == "anthropic_messages"
    )
    return hints


def _preferred_protocol(protocols: list[str]) -> str:
    if "anthropic_messages" in protocols:
        return "anthropic_messages"
    if "responses" in protocols:
        return "responses"
    if "openai_chat_completions" in protocols:
        return "openai_chat_completions"
    return protocols[0] if protocols else ""


def _cache_sensitive_protocols(protocols: list[str], preferred: str, payload: Mapping[str, Any]) -> bool:
    explicit = payload.get("cache_sensitive")
    if isinstance(explicit, bool):
        return explicit
    return (
        preferred == "anthropic_messages"
        and "anthropic_messages" in protocols
        and "openai_chat_completions" in protocols
    )


def _body_patch_aliases_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("body_patch_aliases"), Mapping):
        return copy.deepcopy(dict(payload["body_patch_aliases"]))
    aliases: dict[str, Any] = {}
    for key in ("body_patches", "parameter_aliases", "model_aliases"):
        value = payload.get(key)
        if isinstance(value, Mapping) and value:
            aliases[key] = copy.deepcopy(dict(value))
    return aliases


def _approved_capabilities(model_name: str, approved_facts: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(approved_facts, Mapping) or not approved_facts:
        return {}
    fact = _lookup_approved_fact(model_name, approved_facts)
    if not fact:
        return {}
    return _normalize_capability_payload(fact, model_name=model_name)


def _policy_capabilities(model_name: str, model_policy: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(model_policy, Mapping) or not model_policy:
        return {}
    models = model_policy.get("models")
    if not isinstance(models, Mapping):
        return {}
    model_key = _normalize_model(model_name)
    entry = None
    for key, value in models.items():
        if _normalize_model(key) == model_key and isinstance(value, Mapping):
            entry = dict(value)
            break
    if not entry:
        return {}
    payload: dict[str, Any] = {}
    capabilities = entry.get("capabilities")
    if isinstance(capabilities, Mapping):
        payload.update(dict(capabilities))
    for key in _CONTEXT_KEYS + _MAX_OUTPUT_KEYS + _THINKING_KEYS + _VISION_KEYS + _PROTOCOL_KEYS:
        if key in entry:
            payload[key] = entry[key]
    if isinstance(entry.get("protocol_hints"), Mapping):
        payload["protocol_hints"] = dict(entry["protocol_hints"])
    return _normalize_capability_payload(payload, model_name=model_name)


def _lookup_approved_fact(model_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if _looks_like_capability_fact(payload):
        return dict(payload)

    indexed: dict[str, dict[str, Any]] = {}
    model_rows = payload.get("models")
    if isinstance(model_rows, list):
        for row in model_rows:
            if isinstance(row, Mapping):
                _index_fact_row(indexed, row)

    for section_name in ("capabilities", "model_capabilities", "facts", "routes"):
        section = payload.get(section_name)
        if isinstance(section, Mapping):
            for key, value in section.items():
                if not isinstance(value, Mapping):
                    continue
                row = dict(value)
                if section_name == "routes":
                    primary = row.get("primary")
                    row = dict(primary) if isinstance(primary, Mapping) else row
                row.setdefault("alias", key)
                _index_fact_row(indexed, row)

    if not indexed:
        for key, value in payload.items():
            if isinstance(value, Mapping):
                row = dict(value)
                row.setdefault("alias", key)
                _index_fact_row(indexed, row)

    model_key = _normalize_model(model_name)
    return indexed.get(model_key, {})


def _looks_like_capability_fact(payload: Mapping[str, Any]) -> bool:
    known = set(_CONTEXT_KEYS + _MAX_OUTPUT_KEYS + _THINKING_KEYS + _VISION_KEYS + _PROTOCOL_KEYS + ("one_m_context",))
    return bool(known.intersection(payload.keys()))


def _index_fact_row(indexed: dict[str, dict[str, Any]], row: Mapping[str, Any]) -> None:
    row_dict = dict(row)
    for key in ("alias", "model", "model_name", "model_id", "routed_model_id", "canonical_model_id"):
        model_key = _normalize_model(row.get(key))
        if model_key and model_key not in indexed:
            indexed[model_key] = row_dict


def _provider_profile_capabilities(
    model_name: str,
    *,
    runtime: Mapping[str, Any],
    provider_id: str,
    base_url: str,
    profile_id: str,
    provider_profiles: Mapping[str, Any] | None,
) -> dict[str, Any]:
    resolved_profile_id, profile = _resolve_profile(
        model_name=model_name,
        runtime=runtime,
        provider_id=provider_id,
        base_url=base_url,
        profile_id=profile_id,
        provider_profiles=provider_profiles,
    )
    if not profile:
        return {}

    caps: dict[str, Any] = {
        "profile": resolved_profile_id,
    }
    context_tokens = _longest_prefix_int(_effective_section(profile, "context_windows", model_name), model_name)
    if context_tokens is not None:
        caps["context_window_tokens"] = context_tokens
    max_output_tokens = _longest_prefix_int(_effective_section(profile, "max_output_tokens", model_name), model_name)
    if max_output_tokens is not None:
        caps["max_output_tokens"] = max_output_tokens

    thinking = _effective_section(profile, "thinking", model_name)
    if isinstance(thinking.get("supported"), bool):
        caps["supports_thinking"] = bool(thinking["supported"])

    control = _thinking_control_from_profile(profile, model_name)
    if control:
        caps["thinking_control"] = control

    api_formats = _effective_section(profile, "api_formats", model_name)
    protocol_hints = _protocol_hints_from_payload({"api_formats": api_formats}) if api_formats else {}
    if protocol_hints:
        caps["protocol_hints"] = protocol_hints
        protocols = protocol_hints.get("protocols") or []
        if protocols:
            caps["expected_protocol"] = "/".join(protocols)

    body_aliases = _body_patch_aliases_from_payload(
        {
            "body_patches": _effective_section(profile, "body_patches", model_name),
            "parameter_aliases": _effective_section(profile, "parameter_aliases", model_name),
            "model_aliases": _effective_section(profile, "model_aliases", model_name),
        }
    )
    if body_aliases:
        caps["body_patch_aliases"] = body_aliases

    return caps


def _resolve_profile(
    *,
    model_name: str,
    runtime: Mapping[str, Any],
    provider_id: str,
    base_url: str,
    profile_id: str,
    provider_profiles: Mapping[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    if provider_profiles is None:
        return resolve_provider_profile(
            runtime=dict(runtime),
            provider_id=provider_id,
            base_url=base_url,
            model_name=model_name,
            profile_id=profile_id,
        )
    payload = dict(provider_profiles)
    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), Mapping) else payload
    if not isinstance(profiles, Mapping):
        profiles = load_provider_profiles().get("profiles") or {}

    explicit = _clean(profile_id or runtime.get("profile") or runtime.get("provider_profile"))
    if explicit and isinstance(profiles.get(explicit), Mapping):
        return explicit, copy.deepcopy(dict(profiles[explicit]))

    provider = _clean(provider_id or runtime.get("id") or runtime.get("provider_id"))
    base = _clean(
        base_url
        or runtime.get("openai_base_url")
        or runtime.get("anthropic_base_url")
        or runtime.get("base_url")
    )
    model = _clean(model_name or runtime.get("model"))
    best_id = ""
    best_profile: dict[str, Any] = {}
    best_score = 0
    for candidate_id, profile in profiles.items():
        if not isinstance(profile, Mapping):
            continue
        score = _profile_match_score(str(candidate_id), profile, provider_id=provider, base_url=base, model_name=model)
        if score > best_score:
            best_id = str(candidate_id)
            best_profile = dict(profile)
            best_score = score
    return best_id, copy.deepcopy(best_profile)


def _profile_match_score(profile_id: str, profile: Mapping[str, Any], *, provider_id: str, base_url: str, model_name: str) -> int:
    match = profile.get("match") if isinstance(profile.get("match"), Mapping) else {}
    if match.get("profile_only"):
        return 0
    score = 0
    provider_l = _lower(provider_id)
    base_l = _lower(base_url)
    model_l = _normalize_model(model_name)
    for item in match.get("provider_id_contains") or []:
        token = _lower(item)
        if token and token in provider_l:
            score = max(score, 70)
    for item in match.get("base_url_contains") or []:
        token = _lower(item)
        if token and token in base_l:
            score = max(score, 90)
    for item in match.get("model_prefixes") or []:
        token = _lower(item)
        if token and model_l.startswith(token):
            score = max(score, 50)
    if profile_id and profile_id in {provider_l, model_l}:
        score = max(score, 80)
    return score


def _lookup_model_override(profile: Mapping[str, Any], model_name: str) -> dict[str, Any]:
    overrides = profile.get("model_overrides") if isinstance(profile.get("model_overrides"), Mapping) else {}
    model = _normalize_model(model_name)
    best_key = ""
    best_value: dict[str, Any] = {}
    for key, value in overrides.items():
        key_l = _lower(key)
        if not key_l or not model.startswith(key_l):
            continue
        if len(key_l) > len(best_key) and isinstance(value, Mapping):
            best_key = key_l
            best_value = dict(value)
    return best_value


def _effective_section(profile: Mapping[str, Any], section: str, model_name: str) -> dict[str, Any]:
    base = profile.get(section) if isinstance(profile.get(section), Mapping) else {}
    override = _lookup_model_override(profile, model_name).get(section)
    if isinstance(override, Mapping):
        return _deep_merge(base, override)
    return copy.deepcopy(dict(base))


def _longest_prefix_int(values: Mapping[str, Any], model_name: str) -> int | None:
    model = _normalize_model(model_name)
    best_len = 0
    best_value: int | None = None
    for key, value in values.items():
        key_l = _lower(key)
        if not key_l or not model.startswith(key_l) or len(key_l) <= best_len:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed <= 0:
            continue
        best_len = len(key_l)
        best_value = parsed
    return best_value


def _thinking_control_from_profile(profile: Mapping[str, Any], model_name: str) -> dict[str, Any]:
    thinking = _effective_section(profile, "thinking", model_name)
    if thinking.get("supported") is False:
        return {"supported": False, "control_type": "none", "path": ""}

    configs_by_path: dict[str, dict[str, Any]] = {}
    for section_name in ("effort", "budget"):
        section = _effective_section(profile, section_name, model_name)
        for config in section.values():
            if not isinstance(config, Mapping):
                continue
            path = _clean(config.get("path"))
            if path:
                configs_by_path.setdefault(path, dict(config))

    patch_paths = _thinking_patch_paths(_effective_section(profile, "body_patches", model_name))
    for path in patch_paths:
        configs_by_path.setdefault(path, {"path": path})

    path = _select_thinking_path(list(configs_by_path))
    if not path:
        return _normalize_thinking_control({"supported": bool(thinking.get("supported"))})

    config = configs_by_path.get(path, {})
    control = {
        "supported": True,
        "path": path,
        "control_type": _control_type_from_path(path),
    }
    for key in ("allowed", "default", "map"):
        if key in config:
            control[key] = copy.deepcopy(config[key])
    if _control_type_from_path(path) == "thinkingBudget":
        default_budget = config.get("default")
        try:
            control["numeric_budget_tokens"] = int(default_budget)
        except (TypeError, ValueError):
            control["numeric_budget_tokens"] = None
    elif _control_type_from_path(path) == "thinkingLevel":
        control["numeric_budget_tokens"] = None
    return _normalize_thinking_control(control)


def _thinking_patch_paths(body_patches: Mapping[str, Any]) -> list[str]:
    paths: list[str] = []
    for protocol_patches in body_patches.values():
        if not isinstance(protocol_patches, Mapping):
            continue
        for patch in protocol_patches.values():
            if not isinstance(patch, Mapping):
                continue
            for path in patch:
                path_s = _clean(path)
                if "thinking" in _lower(path_s) and path_s not in paths:
                    paths.append(path_s)
    return paths


def _select_thinking_path(paths: list[str]) -> str:
    priority = (
        "thinkingConfig.thinkingLevel",
        "thinkingConfig.thinkingBudget",
        "thinking.type",
        "reasoning.effort",
        "output_config.effort",
        "thinking_budget",
    )
    by_lower = {_lower(path): path for path in paths}
    for target in priority:
        target_l = _lower(target)
        for path_l, original in by_lower.items():
            if path_l == target_l or path_l.endswith(target_l):
                return original
    return paths[0] if paths else ""
