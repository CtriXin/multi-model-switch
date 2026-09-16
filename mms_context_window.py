"""The one place that answers "how large is this model's context window?".

Issue #230: the same number used to be decided in several places — a model-name
table in ``mms_launchers``, a second one in ``mms_pi_support``, per-model
special cases for Kimi K3 and MiMo, plus the provider profiles and the approved
capability facts. Four harnesses (Claude Code, Codex, Pi, OpenCode) read
whichever of those happened to be nearest, so one model could be 1M in one
harness and 256K in the next, and every new long-context model needed a code
change in several files.

Everything now flows through :func:`resolve_context_window`. The chain, highest
first:

1. ``model-context-overrides.json`` in the selected config root — the user's own
   file, so it wins outright.
2. ``manual_override`` / ``model_policy`` capability sources — what the Pilot's
   model page writes when a human sets a value.
3. ``approved_facts`` — the published capability bundle.
4. The provider profile for that provider (``config/provider-profiles.json``).
5. The provider's cached ``/models`` listing, when the upstream reported a
   window for the model.
6. ``config/model-context-windows.json`` — vendor-documented windows for models
   that no profile covers.
7. The Claude-family rule: an Anthropic model is 1M unless it is a Haiku.

Anything else returns ``None`` and the caller applies its own default. No step
is a hard-coded map from a non-Claude model name to a number: adding a model, or
a provider that reports one, must never require editing code again.

``[1m]`` is a selector suffix, not part of the model name. Every lookup tries the
name as written first and then the stripped name, so ``k3[1m]`` resolves exactly
like ``k3`` unless a provider profile deliberately lists the suffixed name as a
different selector (MiMo's Claude Code endpoint does).
"""

from __future__ import annotations

import json
import os
from typing import Any

ONE_M_SELECTOR_SUFFIX = "[1m]"

# A model we know nothing about. Callers apply this themselves; the resolver
# reports ``None`` so they can tell "unknown" from "known to be 200K".
DEFAULT_CONTEXT_WINDOW = 200_000
CLAUDE_STANDARD_CONTEXT_WINDOW = 200_000
CLAUDE_ONE_M_CONTEXT_WINDOW = 1_000_000

# A number outside this range is a units mistake or a placeholder, not a window.
MIN_PLAUSIBLE_CONTEXT_WINDOW = 4_096
MAX_PLAUSIBLE_CONTEXT_WINDOW = 10_000_000

# Fields an OpenAI-compatible or OpenRouter-style listing uses for the window.
REMOTE_LISTING_CONTEXT_KEYS = (
    "context_length",
    "context_window",
    "context_window_tokens",
    "max_context_tokens",
    "max_model_len",
    "max_input_tokens",
)

_USER_CAPABILITY_SOURCES = ("manual_override", "model_policy")
_APPROVED_CAPABILITY_SOURCES = ("approved_facts",)
_PROFILE_CAPABILITY_SOURCES = ("provider_profile",)

_DATA_FILE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config", "model-context-windows.json"
)

_OVERRIDES_CACHE: dict[str, Any] = {"path": None, "mtime": None, "data": None}
_DATA_FILE_CACHE: dict[str, Any] = {"mtime": None, "data": None}


# ── name handling ────────────────────────────────────────────────────────────

def strip_one_m_selector(model_name: Any) -> str:
    """Drop the ``[1m]`` selector suffix, keeping the rest of the name as written."""
    normalized = str(model_name or "").strip()
    if not normalized:
        return ""
    return (
        normalized.replace(ONE_M_SELECTOR_SUFFIX, "")
        .replace(ONE_M_SELECTOR_SUFFIX.upper(), "")
        .strip()
    )


def _leaf_name(model_name: Any) -> str:
    """Lower-case leaf name, selector suffix left as written."""
    normalized = str(model_name or "").strip().lower()
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def normalize_model_selector(model_name: Any) -> str:
    """Lower-case leaf name with the ``[1m]`` selector removed.

    The shared key for any table that is keyed by model name — context, Pi
    hints, vision — so a selector never needs a duplicate entry of its own.
    """
    return strip_one_m_selector(_leaf_name(model_name))


def has_one_m_selector(model_name: Any) -> bool:
    return ONE_M_SELECTOR_SUFFIX in str(model_name or "").strip().lower()


def coerce_context_window(value: Any) -> int | None:
    try:
        window = int(value)
    except (TypeError, ValueError):
        return None
    return window if window > 0 else None


def _plausible(value: Any) -> int | None:
    window = coerce_context_window(value)
    if window is None:
        return None
    if window < MIN_PLAUSIBLE_CONTEXT_WINDOW or window > MAX_PLAUSIBLE_CONTEXT_WINDOW:
        return None
    return window


def _config_root() -> str:
    from mms_state_io import resolve_mms_config_dir

    return resolve_mms_config_dir()


# ── step 1: the user's own overrides file ────────────────────────────────────

def model_context_overrides_path() -> str:
    try:
        config_root = _config_root()
    except Exception:
        config_root = os.path.join(os.path.expanduser("~"), ".config", "mms-next")
    return os.path.join(config_root, "model-context-overrides.json")


def load_model_context_overrides() -> dict[str, Any]:
    """Read ``model-context-overrides.json`` from the selected config root."""
    overrides_path = model_context_overrides_path()
    try:
        mtime = os.path.getmtime(overrides_path)
    except OSError:
        _OVERRIDES_CACHE.update(
            {"path": overrides_path, "mtime": None, "data": {"models": {}, "provider_overrides": {}}}
        )
        return _OVERRIDES_CACHE["data"]

    if _OVERRIDES_CACHE.get("path") == overrides_path and _OVERRIDES_CACHE.get("mtime") == mtime:
        return _OVERRIDES_CACHE["data"]

    models: dict[str, int] = {}
    provider_overrides: dict[str, int] = {}
    try:
        with open(overrides_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        payload = {}

    if isinstance(payload, dict):
        raw_models = payload.get("models", payload)
        if isinstance(raw_models, dict):
            for key, value in raw_models.items():
                if key in {"models", "provider_overrides"}:
                    continue
                window = coerce_context_window(value)
                if window:
                    models[str(key).strip()] = window

        raw_provider_overrides = payload.get("provider_overrides", {})
        if isinstance(raw_provider_overrides, dict):
            for key, value in raw_provider_overrides.items():
                if isinstance(value, dict):
                    provider_id = str(key or "").strip()
                    if not provider_id:
                        continue
                    for model_id, window_value in value.items():
                        window = coerce_context_window(window_value)
                        if window:
                            provider_overrides[f"{provider_id}:{str(model_id).strip()}"] = window
                else:
                    window = coerce_context_window(value)
                    if window:
                        provider_overrides[str(key).strip()] = window

    _OVERRIDES_CACHE.update(
        {
            "path": overrides_path,
            "mtime": mtime,
            "data": {"models": models, "provider_overrides": provider_overrides},
        }
    )
    return _OVERRIDES_CACHE["data"]


def _override_window(candidate: str, provider_key: str) -> tuple[int | None, str]:
    if not candidate:
        return None, ""
    overrides = load_model_context_overrides()
    candidate_lower = candidate.lower()

    if provider_key:
        provider_overrides = overrides.get("provider_overrides", {})
        direct = provider_overrides.get(f"{provider_key}:{candidate}")
        if direct is not None:
            return coerce_context_window(direct), "provider_override"
        for key, value in provider_overrides.items():
            try:
                override_provider, override_model = key.split(":", 1)
            except ValueError:
                continue
            if override_provider == provider_key and override_model.lower() == candidate_lower:
                return coerce_context_window(value), "provider_override"

    models = overrides.get("models", {})
    direct = models.get(candidate)
    if direct is not None:
        return coerce_context_window(direct), "user_override"
    for key, value in models.items():
        if key.lower() == candidate_lower:
            return coerce_context_window(value), "user_override"
    return None, ""


# ── steps 2 and 3: capability facts ──────────────────────────────────────────

def _model_capabilities(model_name: str, provider_id: str, base_url: str = "") -> dict[str, Any]:
    """Capability facts for one model: policy, approved bundle and profile at once.

    Steps 2 to 4 of the chain all live in this one resolution, so the launcher
    and Pi read the same profile for the same provider instead of two lookups
    that can drift apart.
    """
    if not model_name:
        return {}
    from mms_capability_resolver import resolve_model_capabilities

    try:
        return resolve_model_capabilities(model_name, provider_id=provider_id or "", base_url=base_url or "")
    except Exception:
        # A config root without a readable approved bundle still has a policy
        # file, and a value the user set there must not be lost with it.
        try:
            from mms_capability_resolver import load_default_model_policy

            return resolve_model_capabilities(
                model_name,
                provider_id=provider_id or "",
                base_url=base_url or "",
                approved_facts={},
                model_policy=load_default_model_policy(),
            )
        except Exception:
            return {}


def _capability_window(caps: dict[str, Any], accepted_sources: tuple[str, ...]) -> tuple[int | None, str]:
    source = caps.get("sources", {}).get("context_window_tokens") if isinstance(caps, dict) else None
    if source not in accepted_sources:
        return None, ""
    return coerce_context_window(caps.get("context_window_tokens")), str(source)


# ── step 5: what the provider's own /models listing reported ─────────────────

def _remote_listing_details(provider_id: str) -> dict[str, Any]:
    if not provider_id:
        return {}
    try:
        path = os.path.join(_config_root(), "cache", f"models_{provider_id}.json")
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    details = payload.get("model_details")
    return details if isinstance(details, dict) else {}


def _remote_listing_window(model_name: str, provider_id: str) -> int | None:
    details = _remote_listing_details(provider_id)
    if not details:
        return None
    wanted = normalize_model_selector(model_name)
    if not wanted:
        return None
    for key, entry in details.items():
        if normalize_model_selector(key) != wanted:
            continue
        if isinstance(entry, dict):
            for field in REMOTE_LISTING_CONTEXT_KEYS:
                window = _plausible(entry.get(field))
                if window:
                    return window
            top_provider = entry.get("top_provider")
            if isinstance(top_provider, dict):
                for field in REMOTE_LISTING_CONTEXT_KEYS:
                    window = _plausible(top_provider.get(field))
                    if window:
                        return window
        else:
            window = _plausible(entry)
            if window:
                return window
    return None


# ── step 6: vendor-documented windows for models no profile covers ───────────

def load_context_window_data() -> dict[str, int]:
    """Read ``config/model-context-windows.json``.

    A data file, not a code table: every row names the source it came from, and
    it only answers for a model whose channel profile says nothing about it.
    Keys stay as written (lower-cased leaf), so a row for a `[1m]` selector can
    say something different from the plain name where a vendor really means it.
    """
    try:
        mtime = os.path.getmtime(_DATA_FILE_PATH)
    except OSError:
        return {}
    if _DATA_FILE_CACHE.get("mtime") == mtime and isinstance(_DATA_FILE_CACHE.get("data"), dict):
        return _DATA_FILE_CACHE["data"]
    try:
        with open(_DATA_FILE_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        payload = {}
    models = payload.get("models") if isinstance(payload, dict) else None
    table: dict[str, int] = {}
    if isinstance(models, dict):
        for key, row in models.items():
            value = row.get("context_window_tokens") if isinstance(row, dict) else row
            window = _plausible(value)
            if window:
                table[_leaf_name(key)] = window
    _DATA_FILE_CACHE.update({"mtime": mtime, "data": table})
    return table


def _data_file_window(model_name: str) -> int | None:
    table = load_context_window_data()
    if not table:
        return None
    exact = table.get(_leaf_name(model_name))
    if exact:
        return exact
    return table.get(normalize_model_selector(model_name))


# ── step 7: the Claude family ────────────────────────────────────────────────

def is_claude_family_model(model_name: Any) -> bool:
    lower = strip_one_m_selector(model_name).lower()
    return any(token in lower for token in ("claude", "opus", "sonnet", "haiku"))


def claude_family_context_window(model_name: Any) -> int | None:
    """Anthropic's own models: 1M for Opus/Sonnet, the standard 200K for Haiku.

    A family rule rather than a name list, so a new Claude release needs no
    entry. Whether 1M is actually *used* stays with the caller: a sensitive
    provider keeps it disabled through ``enable_claude_1m``.
    """
    if not is_claude_family_model(model_name):
        return None
    lower = strip_one_m_selector(model_name).lower()
    if "haiku" in lower:
        return CLAUDE_STANDARD_CONTEXT_WINDOW
    return CLAUDE_ONE_M_CONTEXT_WINDOW


# ── the chain ────────────────────────────────────────────────────────────────

def _runtime_base_url(runtime: Any) -> str:
    if not isinstance(runtime, dict):
        return ""
    for key in ("openai_base_url", "anthropic_base_url", "base_url"):
        value = str(runtime.get(key) or "").strip()
        if value:
            return value
    return ""


def user_context_window_override(model_name: Any, *, provider_id: Any = None, runtime: Any = None) -> int | None:
    """The window the user pinned in ``model-context-overrides.json``, if any.

    The top of the chain, exposed on its own so a harness that resolves its own
    capability facts can still put the user's file above them instead of
    silently ignoring it.
    """
    raw_model = str(model_name or "").strip()
    if not raw_model:
        return None
    runtime_id = runtime.get("id") if isinstance(runtime, dict) else ""
    provider_key = str(provider_id or runtime_id or "").strip()
    clean = strip_one_m_selector(raw_model)
    for candidate in ([raw_model] if raw_model == clean else [raw_model, clean]):
        window, _source = _override_window(candidate, provider_key)
        if window:
            return window
    return None


def context_window_sources(model_name: Any, *, provider_id: Any = None, runtime: Any = None) -> dict[str, Any]:
    """Resolve the window and report which step of the chain answered."""
    raw_model = str(model_name or "").strip()
    runtime_id = runtime.get("id") if isinstance(runtime, dict) else ""
    provider_key = str(provider_id or runtime_id or "").strip()
    result = {
        "model": raw_model,
        "provider_id": provider_key,
        "context_window_tokens": None,
        "source": "unresolved",
    }
    if not raw_model:
        return result

    base_url = _runtime_base_url(runtime)
    clean = strip_one_m_selector(raw_model)
    # The name as written first, then without the selector: an explicit entry for
    # the suffixed name is a deliberate statement that it is a different
    # selector, and only then does stripping apply.
    candidates = [raw_model] if raw_model == clean else [raw_model, clean]

    for candidate in candidates:
        window, source = _override_window(candidate, provider_key)
        if window:
            result.update({"context_window_tokens": window, "source": source})
            return result

    caps_by_candidate = {
        candidate: _model_capabilities(candidate, provider_key, base_url) for candidate in candidates
    }
    for accepted in (_USER_CAPABILITY_SOURCES, _APPROVED_CAPABILITY_SOURCES, _PROFILE_CAPABILITY_SOURCES):
        for candidate in candidates:
            window, source = _capability_window(caps_by_candidate[candidate], accepted)
            if window:
                result.update({"context_window_tokens": window, "source": source})
                return result

    window = _remote_listing_window(raw_model, provider_key)
    if window:
        result.update({"context_window_tokens": window, "source": "remote_listing"})
        return result

    window = _data_file_window(raw_model)
    if window:
        result.update({"context_window_tokens": window, "source": "context_window_data"})
        return result

    window = claude_family_context_window(raw_model)
    if window:
        result.update({"context_window_tokens": window, "source": "claude_family"})
        return result

    return result


def resolve_context_window(model_name: Any, *, provider_id: Any = None, runtime: Any = None) -> int | None:
    """The window for this model on this provider, or ``None`` when unknown."""
    return context_window_sources(model_name, provider_id=provider_id, runtime=runtime)[
        "context_window_tokens"
    ]


def clear_context_window_caches() -> None:
    """Drop the overrides/data-file caches; for tests and config reloads."""
    _OVERRIDES_CACHE.update({"path": None, "mtime": None, "data": None})
    _DATA_FILE_CACHE.update({"mtime": None, "data": None})
