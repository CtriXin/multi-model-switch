"""MMS noninteractive multi-review launcher.

This command is intentionally narrow: it validates the Moebius review-dispatch
environment, builds a bounded reviewer prompt from the supplied review pack,
dispatches one reviewer model, and writes exactly the expected review file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mms_provider_profiles import apply_profile_auth_headers, apply_profile_body_patches


REVIEW_LAUNCH_CONTRACT_SCHEMA = "mms.review_launch_contract.v1"
REVIEW_LAUNCH_VALIDATION_SCHEMA = "mms.review_launch_validation.v1"
REVIEW_LAUNCH_RESULT_SCHEMA = "mms.review_launch_result.v1"
REQUIRED_ENV = [
    "MOEBIUS_RUN_ID",
    "MOEBIUS_RUN_DIR",
    "MOEBIUS_REPO_ROOT",
    "MOEBIUS_REVIEW_DISPATCH_ADAPTER_CONFIG",
    "MOEBIUS_REVIEW_DISPATCH_GATE",
    "MOEBIUS_REVIEW_DISPATCH_PLAN",
    "MOEBIUS_REVIEWER_ID",
    "MOEBIUS_REVIEW_EXPECTED_OUTPUT",
    "MULTI_REVIEW_REVIEWER",
    "MOEBIUS_REVIEW_PACK",
]
WRAPPER_ONLY_IDS = {"agent", "claude-code", "cli", "codex", "default", "local", "mms", "reviewer", "unknown"}
FAKE_RESPONSE_ENV = "MMS_REVIEW_LAUNCH_FAKE_RESPONSE"
FAKE_RESPONSE_FILE_ENV = "MMS_REVIEW_LAUNCH_FAKE_RESPONSE_FILE"
PROVIDER_ID_ENV = "MMS_REVIEW_LAUNCH_PROVIDER_ID"
MAX_TOKENS_ENV = "MMS_REVIEW_LAUNCH_MAX_TOKENS"
MAX_CANDIDATES_ENV = "MMS_REVIEW_LAUNCH_MAX_CANDIDATES"
READ_TIMEOUT_ENV = "MMS_REVIEW_LAUNCH_READ_TIMEOUT_SECONDS"
MAX_FILE_CHARS_ENV = "MMS_REVIEW_LAUNCH_MAX_FILE_CHARS"
MAX_PROMPT_CHARS_ENV = "MMS_REVIEW_LAUNCH_MAX_PROMPT_CHARS"
PROTOCOL_ENV = "MMS_REVIEW_LAUNCH_PROTOCOL"
ALLOWED_READ_ROOTS_ENV = "MMS_REVIEW_LAUNCH_ALLOWED_READ_ROOTS"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_MAX_CANDIDATES = 6
DEFAULT_READ_TIMEOUT_SECONDS = 180
DEFAULT_MAX_FILE_CHARS = 12000
DEFAULT_MAX_PROMPT_CHARS = 90000
OPENAI_CHAT_PROTOCOL = "openai_chat_completions"
ANTHROPIC_MESSAGES_PROTOCOL = "anthropic_messages"
DEFAULT_PROTOCOL_ORDER = (ANTHROPIC_MESSAGES_PROTOCOL, OPENAI_CHAT_PROTOCOL)


class ReviewLaunchDispatchError(RuntimeError):
    def __init__(self, message: str, attempts: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.attempts = attempts


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"json root must be an object: {path}")
    return data


def _resolve(path: str, repo_root: Path) -> Path:
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else repo_root / candidate


def _int_env(env: dict[str, str], name: str, default: int, *, minimum: int = 1, maximum: int = 200000) -> int:
    raw = str(env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _path_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _relative_to(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except (OSError, ValueError):
        return str(path)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def build_review_launch_contract(command_name: str = "mms") -> dict[str, Any]:
    return {
        "schema": REVIEW_LAUNCH_CONTRACT_SCHEMA,
        "generated_at": _now(),
        "command": f"{command_name} review-launch",
        "purpose": "noninteractive multi-review reviewer launcher",
        "model_dispatch_implemented": True,
        "review_file_write_implemented": True,
        "required_env": REQUIRED_ENV,
        "identity_contract": {
            "reviewer_id": "MOEBIUS_REVIEWER_ID",
            "multi_review_reviewer_must_equal_reviewer_id": True,
            "expected_output": "MOEBIUS_REVIEW_EXPECTED_OUTPUT",
            "gemini_cli_compat_identity_allowed": True,
            "wrapper_only_ids_rejected": sorted(WRAPPER_ONLY_IDS),
        },
        "modes": {
            "--contract-json": "print this local contract and exit",
            "--validate-env": "validate Moebius reviewer-launch environment and exit without model calls",
            "default": "after an approved Moebius review-dispatch gate, call one reviewer model and write MOEBIUS_REVIEW_EXPECTED_OUTPUT",
            "--allow-model-call": "accepted compatibility latch; Moebius HumanGate plus --allow-real-review-dispatch remains the required outer latch",
        },
        "boundaries": [
            "One reviewer model call after approved Moebius review-dispatch gate.",
            "Exactly one review file write to MOEBIUS_REVIEW_EXPECTED_OUTPUT.",
            "No review intake or gate clear.",
            "No Pilot, Ant, Hive, addon, deploy, browser, IM, webhook, daemon, or product repo action.",
        ],
        "test_hooks": {
            FAKE_RESPONSE_ENV: "optional test-only fake reviewer response text; avoids real provider calls",
            FAKE_RESPONSE_FILE_ENV: "optional test-only path to fake reviewer response text",
        },
        "provider_protocols": {
            "supported": list(DEFAULT_PROTOCOL_ORDER),
            "selection": "Providers are ordered by MMS routing; each provider tries Anthropic-compatible protocol first, then OpenAI chat completions when configured.",
            PROTOCOL_ENV: "optional override: auto, anthropic_messages, or openai_chat_completions",
            MAX_CANDIDATES_ENV: f"optional cap for provider/protocol fallback attempts; default {DEFAULT_MAX_CANDIDATES}",
            READ_TIMEOUT_ENV: f"optional per-attempt read timeout seconds; default {DEFAULT_READ_TIMEOUT_SECONDS}",
        },
        "read_context": {
            ALLOWED_READ_ROOTS_ENV: "optional os.pathsep-separated absolute roots for read-only context outside MOEBIUS_REPO_ROOT",
            "default": "only MOEBIUS_REPO_ROOT is readable unless the host injects explicit roots",
        },
    }


def validate_review_launch_env(env: dict[str, str] | None = None) -> dict[str, Any]:
    effective_env = dict(env or os.environ)
    missing = [name for name in REQUIRED_ENV if not str(effective_env.get(name) or "").strip()]
    errors: list[str] = []
    warnings: list[str] = []
    if missing:
        errors.append("missing required env: " + ", ".join(missing))

    reviewer_id = str(effective_env.get("MOEBIUS_REVIEWER_ID") or "").strip()
    multi_review_reviewer = str(effective_env.get("MULTI_REVIEW_REVIEWER") or "").strip()
    repo_root_ref = str(effective_env.get("MOEBIUS_REPO_ROOT") or "").strip()
    expected_output_ref = str(effective_env.get("MOEBIUS_REVIEW_EXPECTED_OUTPUT") or "").strip()
    gate_ref = str(effective_env.get("MOEBIUS_REVIEW_DISPATCH_GATE") or "").strip()
    pack_ref = str(effective_env.get("MOEBIUS_REVIEW_PACK") or "").strip()

    if reviewer_id and reviewer_id in WRAPPER_ONLY_IDS:
        errors.append(f"reviewer id is a wrapper/tool id, not a model identity: {reviewer_id}")
    if reviewer_id and multi_review_reviewer and reviewer_id != multi_review_reviewer:
        errors.append("MULTI_REVIEW_REVIEWER must match MOEBIUS_REVIEWER_ID")

    repo_root = Path(repo_root_ref).expanduser() if repo_root_ref else Path(".")
    if repo_root_ref and not repo_root.exists():
        errors.append(f"MOEBIUS_REPO_ROOT does not exist: {repo_root}")

    expected_output = _resolve(expected_output_ref, repo_root) if expected_output_ref else None
    if expected_output is not None and reviewer_id:
        if not _path_under(expected_output, repo_root):
            errors.append("MOEBIUS_REVIEW_EXPECTED_OUTPUT must stay under MOEBIUS_REPO_ROOT")
            output_rel = Path("")
        else:
            output_rel = expected_output.resolve().relative_to(repo_root.resolve())
        expected_prefix = Path(".ai") / "reviews" / reviewer_id
        if output_rel.parts and not str(output_rel).startswith(str(expected_prefix) + os.sep):
            errors.append(f"expected output must be under {expected_prefix}")

    if pack_ref:
        pack_path = _resolve(pack_ref, repo_root)
        if not pack_path.exists():
            errors.append(f"MOEBIUS_REVIEW_PACK does not exist: {pack_path}")

    gate_status = ""
    if gate_ref:
        try:
            gate = _read_json(_resolve(gate_ref, repo_root))
            gate_status = str(gate.get("gate_status") or "")
            if gate_status != "approved":
                errors.append("review-dispatch gate must be approved before launch")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"cannot read review-dispatch gate: {exc}")

    if reviewer_id == "gemini-cli":
        warnings.append("gemini-cli compatibility identity is accepted when path/header exactly match")

    return {
        "schema": REVIEW_LAUNCH_VALIDATION_SCHEMA,
        "validated_at": _now(),
        "ok": not errors,
        "status": "ready_for_future_dispatch" if not errors else "blocked",
        "reviewer_id": reviewer_id,
        "expected_output": expected_output_ref,
        "gate_status": gate_status,
        "errors": errors,
        "warnings": warnings,
        "model_calls": 0,
        "review_file_writes": 0,
    }


def _read_text_preview(path: Path, max_chars: int) -> tuple[str, bool, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return "", False, f"unreadable: {exc}"
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars] + "\n...[truncated by MMS review-launch]\n"
    return text, truncated, ""


def _allowed_read_roots(repo_root: Path, env: dict[str, str]) -> list[Path]:
    roots = [repo_root]
    raw = str(env.get(ALLOWED_READ_ROOTS_ENV) or "").strip()
    for item in raw.split(os.pathsep):
        if item.strip():
            roots.append(Path(item).expanduser())
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            key = str(root.resolve())
        except OSError:
            key = str(root)
        if key not in seen:
            deduped.append(root)
            seen.add(key)
    return deduped


def _path_under_any(path: Path, roots: list[Path]) -> bool:
    return any(_path_under(path, root) for root in roots)


def _pack_paths(pack: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("prompt_path",):
        value = pack.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    for key in ("read_only_files", "changed_files"):
        raw = pack.get(key)
        if isinstance(raw, list):
            values.extend(str(item).strip() for item in raw if str(item).strip())
    paths = pack.get("paths") if isinstance(pack.get("paths"), dict) else {}
    pack_md = paths.get("pack_md") if isinstance(paths, dict) else ""
    if isinstance(pack_md, str) and pack_md.strip():
        values.append(pack_md.strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped


def _render_file_context(repo_root: Path, pack: dict[str, Any], env: dict[str, str]) -> tuple[str, list[dict[str, Any]]]:
    max_file_chars = _int_env(env, MAX_FILE_CHARS_ENV, DEFAULT_MAX_FILE_CHARS, maximum=100000)
    max_prompt_chars = _int_env(env, MAX_PROMPT_CHARS_ENV, DEFAULT_MAX_PROMPT_CHARS, maximum=500000)
    allowed_roots = _allowed_read_roots(repo_root, env)
    sections: list[str] = []
    entries: list[dict[str, Any]] = []
    used_chars = 0
    for raw_ref in _pack_paths(pack):
        path = _resolve(raw_ref, repo_root)
        entry = {
            "path": raw_ref,
            "resolved_path": str(path),
            "exists": path.exists(),
            "read": False,
            "truncated": False,
            "error": "",
        }
        if not path.exists() or not path.is_file():
            entry["error"] = "missing_or_not_file"
            entries.append(entry)
            continue
        if not _path_under_any(path, allowed_roots):
            entry["error"] = "path_outside_allowed_read_roots"
            entries.append(entry)
            continue
        remaining = max_prompt_chars - used_chars
        if remaining <= 0:
            entry["error"] = "prompt_context_limit_reached"
            entries.append(entry)
            continue
        text, truncated, error = _read_text_preview(path, min(max_file_chars, remaining))
        if error:
            entry["error"] = error
            entries.append(entry)
            continue
        entry["read"] = True
        entry["truncated"] = truncated
        used_chars += len(text)
        sections.append(f"### File: {raw_ref}\n\n```text\n{text}\n```\n")
        entries.append(entry)
    return "\n".join(sections), entries


def _review_prompt(repo_root: Path, pack_path: Path, pack: dict[str, Any], env: dict[str, str]) -> tuple[str, list[dict[str, Any]]]:
    reviewer_id = str(env.get("MOEBIUS_REVIEWER_ID") or "").strip()
    expected_output = str(env.get("MOEBIUS_REVIEW_EXPECTED_OUTPUT") or "").strip()
    file_context, context_entries = _render_file_context(repo_root, pack, env)
    return (
        "You are an independent multi-review reviewer for a Moebius review gate.\n"
        "Review the supplied pack and file excerpts. Do not claim to have run commands unless the excerpts explicitly show that evidence.\n"
        "Return only the Markdown review content that should be written to the expected review file.\n\n"
        "Hard requirements:\n"
        f"- Reviewer field must be exactly: Reviewer: {reviewer_id}\n"
        f"- Expected output path is: {expected_output}\n"
        "- Use verdict PASS, PASS_WITH_NOTES, or BLOCKED.\n"
        "- Lead with concrete blockers if any, with file/path references.\n"
        "- Do not declare the gate clear. Host intake owns gate aggregation.\n\n"
        f"Review pack path: {pack_path}\n\n"
        "Review pack JSON:\n"
        "```json\n"
        f"{json.dumps(pack, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "File excerpts:\n"
        f"{file_context or '(no readable file excerpts supplied)'}\n",
        context_entries,
    )


def _ensure_reviewer_header(text: str, reviewer_id: str) -> str:
    cleaned = str(text or "").strip()
    needle = f"Reviewer: {reviewer_id}"
    if any(line.strip() == needle for line in cleaned.splitlines()):
        return cleaned + "\n"
    return f"{needle}\n\n{cleaned}\n"


def _provider_openai_base_url(runtime: dict[str, Any]) -> str:
    for key in ("openai_base_url", "base_url", "url"):
        value = str(runtime.get(key) or "").strip()
        if value:
            return value.rstrip("/")
    return ""


def _provider_anthropic_base_url(runtime: dict[str, Any]) -> str:
    for key in ("anthropic_base_url",):
        value = str(runtime.get(key) or "").strip()
        if value:
            return value.rstrip("/")
    protocols = runtime.get("protocols", [])
    if isinstance(protocols, str):
        protocols = [protocols]
    base_url = str(runtime.get("base_url") or runtime.get("url") or "").strip().rstrip("/")
    if base_url and ANTHROPIC_MESSAGES_PROTOCOL in protocols:
        return base_url
    return ""


def _provider_protocols(runtime: dict[str, Any]) -> list[str]:
    raw = runtime.get("protocols", [])
    if isinstance(raw, str):
        raw = [raw]
    return [str(item).strip() for item in raw if str(item).strip()]


def _protocol_order(env: dict[str, str]) -> list[str]:
    requested = str(env.get(PROTOCOL_ENV) or "").strip()
    if not requested or requested == "auto":
        return list(DEFAULT_PROTOCOL_ORDER)
    if requested in DEFAULT_PROTOCOL_ORDER:
        return [requested]
    return list(DEFAULT_PROTOCOL_ORDER)


def _provider_base_url_for_protocol(provider: dict[str, Any], protocol: str) -> str:
    if protocol == ANTHROPIC_MESSAGES_PROTOCOL:
        return _provider_anthropic_base_url(provider)
    if protocol == OPENAI_CHAT_PROTOCOL:
        return _provider_openai_base_url(provider)
    return ""


def _provider_api_key_for_protocol(provider: dict[str, Any], protocol: str) -> str:
    if protocol == OPENAI_CHAT_PROTOCOL:
        return str(provider.get("openai_api_key") or provider.get("api_key") or "").strip()
    return str(provider.get("api_key") or "").strip()


def _provider_ready_for_protocol(provider: dict[str, Any], protocol: str) -> str:
    protocols = _provider_protocols(provider)
    if protocol not in protocols:
        return f"provider {provider.get('id') or ''} does not declare protocol {protocol}"
    if not _provider_base_url_for_protocol(provider, protocol):
        return f"provider {provider.get('id') or ''} has no {protocol} base_url"
    if not _provider_api_key_for_protocol(provider, protocol):
        return f"provider {provider.get('id') or ''} has no api_key for {protocol}"
    return ""


def _canonical_model_name(models: list[str], requested: str) -> str:
    requested_l = str(requested or "").strip().lower()
    for model_name in models:
        normalized = str(model_name or "").strip()
        if normalized.lower() == requested_l:
            return normalized
    return str(requested or "").strip()


def _cached_provider_models(provider_id: str, load_cache_fn: Any) -> list[str] | None:
    try:
        cached = load_cache_fn(provider_id, allow_stale=True)
    except TypeError:
        cached = load_cache_fn(provider_id)
    except Exception:
        cached = None
    if not isinstance(cached, dict):
        return None
    raw = cached.get("raw_models") or cached.get("models") or []
    return [str(item).strip() for item in raw if str(item).strip()]


def _provider_models(
    provider: dict[str, Any],
    cached_models: list[str] | None,
    cfg: dict[str, Any],
    provider_effective_models_fn: Any,
    load_cache_fn: Any,
) -> list[str]:
    if cached_models is None:
        cached_models = _cached_provider_models(str(provider.get("id") or ""), load_cache_fn)
    try:
        models = provider_effective_models_fn(provider, cached_models, cfg)
    except TypeError:
        models = provider_effective_models_fn(provider, cached_models)
    return [str(item).strip() for item in (models or []) if str(item).strip()]


def _resolve_review_launch_candidates(model_name: str, env: dict[str, str]) -> tuple[list[dict[str, Any]], str]:
    try:
        from mms_core import (
            ROLE_WEIGHTS,
            _default_config,
            _load_probe_file_cache,
            _normalize_role,
            _provider_candidates,
            _provider_effective_models,
            _runtime_priority_for_model,
            _runtime_with_priority,
            apply_local_overrides,
            load_config,
            resolve_provider_context,
        )
    except Exception as exc:
        return [], f"cannot import MMS provider resolver: {exc}"

    cfg = load_config() or _default_config()
    cfg = apply_local_overrides(cfg)
    provider_id = str(env.get(PROVIDER_ID_ENV) or "").strip()
    protocol_order = _protocol_order(env)

    if provider_id:
        try:
            provider = resolve_provider_context(cfg, provider_id)
        except Exception as exc:
            return [], f"cannot resolve provider {provider_id}: {exc}"
        errors: list[str] = []
        models = _provider_models(provider, None, cfg, _provider_effective_models, _load_probe_file_cache)
        dispatch_model = _canonical_model_name(models, model_name)
        candidates: list[dict[str, Any]] = []
        for protocol in protocol_order:
            error = _provider_ready_for_protocol(provider, protocol)
            if error:
                errors.append(error)
                continue
            candidate_provider = dict(provider)
            candidate_provider["review_launch_model_name"] = dispatch_model
            candidates.append({"provider": candidate_provider, "protocol": protocol, "model_name": dispatch_model})
        if candidates:
            return candidates, ""
        return [], "; ".join(errors)

    default_id = str((cfg.get("provider") or {}).get("default") or "default")
    try:
        default_provider = resolve_provider_context(cfg, default_id)
    except Exception:
        default_provider = {}

    default_cached = (
        _cached_provider_models(str(default_provider.get("id") or ""), _load_probe_file_cache)
        if default_provider
        else []
    )
    default_models = (
        _provider_models(default_provider, default_cached, cfg, _provider_effective_models, _load_probe_file_cache)
        if default_provider
        else []
    )

    rows: list[tuple[int, int, int, dict[str, Any], str]] = []
    requested_l = str(model_name or "").strip().lower()
    for index, (provider, cached_models) in enumerate(_provider_candidates(cfg, default_provider, default_models)):
        if not isinstance(provider, dict) or not provider.get("enabled", True):
            continue
        models = _provider_models(provider, cached_models, cfg, _provider_effective_models, _load_probe_file_cache)
        model_names_lower = [item.lower() for item in models]
        if requested_l not in model_names_lower:
            continue
        dispatch_model = _canonical_model_name(models, model_name)
        role_weight = ROLE_WEIGHTS.get(_normalize_role(provider.get("role", "auto")), 1)
        priority = _runtime_priority_for_model(provider, dispatch_model)
        rows.append((role_weight, -priority, index, provider, dispatch_model))

    rows.sort(key=lambda item: (item[0], item[1], item[2]))
    candidates = []
    for _role_weight, _priority, _index, provider, dispatch_model in rows:
        provider_with_priority = _runtime_with_priority(provider, model_name=dispatch_model)
        for protocol in protocol_order:
            if _provider_ready_for_protocol(provider_with_priority, protocol):
                continue
            candidate_provider = dict(provider_with_priority)
            candidate_provider["review_launch_model_name"] = dispatch_model
            candidates.append({"provider": candidate_provider, "protocol": protocol, "model_name": dispatch_model})

    if candidates:
        return candidates, ""
    return [], (
        f"no configured review-launch provider found for reviewer model {model_name} "
        f"with supported protocols {', '.join(protocol_order)}"
    )


def _resolve_provider_for_model(model_name: str, env: dict[str, str]) -> tuple[dict[str, Any] | None, str, str]:
    candidates, error = _resolve_review_launch_candidates(model_name, env)
    if error:
        return None, "", error
    first = candidates[0]
    return first["provider"], str(first["protocol"]), ""


def _extract_response_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(_extract_response_text(item) for item in value).strip()
    if isinstance(value, dict):
        return _extract_response_text(value.get("text") or value.get("content") or "")
    return ""


def _openai_chat_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _extract_openai_stream_text(text: str) -> str:
    chunks: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data_text = line[len("data:") :].strip()
        if not data_text or data_text == "[DONE]":
            continue
        try:
            data = json.loads(data_text)
        except json.JSONDecodeError:
            continue
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            continue
        first = choices[0] if isinstance(choices[0], dict) else {}
        delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        raw_chunk = delta.get("content") or message.get("content") or ""
        chunk = raw_chunk if isinstance(raw_chunk, str) else _extract_response_text(raw_chunk)
        if chunk:
            chunks.append(chunk)
    return "".join(chunks).strip()


def _dispatch_attempt(provider: dict[str, Any], protocol: str, model_name: str) -> dict[str, Any]:
    return {
        "provider_id": str(provider.get("id") or ""),
        "provider_protocol": protocol,
        "model_name": model_name,
    }


def _compact_error(exc: Exception) -> str:
    return str(exc)[:1000]


def _format_attempt_errors(attempts: list[dict[str, Any]]) -> str:
    failed = [item for item in attempts if not item.get("ok")]
    if not failed:
        return "no dispatch candidates attempted"
    parts = []
    for item in failed:
        parts.append(
            f"{item.get('provider_id')}/{item.get('provider_protocol')}/{item.get('model_name')}: "
            f"{item.get('error')}"
        )
    return "; ".join(parts)


async def _call_first_working_model(
    *,
    candidates: list[dict[str, Any]],
    prompt: str,
    max_tokens: int,
    read_timeout_seconds: int,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    for candidate in candidates:
        provider = candidate["provider"]
        protocol = str(candidate["protocol"])
        model_name = str(candidate["model_name"])
        attempt = _dispatch_attempt(provider, protocol, model_name)
        try:
            content = await _call_model(
                provider=provider,
                protocol=protocol,
                model_name=model_name,
                prompt=prompt,
                max_tokens=max_tokens,
                read_timeout_seconds=read_timeout_seconds,
            )
        except Exception as exc:
            attempt["ok"] = False
            attempt["error"] = _compact_error(exc)
            attempts.append(attempt)
            continue
        attempt["ok"] = True
        attempts.append(attempt)
        return content, candidate, attempts
    raise ReviewLaunchDispatchError("all model dispatch candidates failed: " + _format_attempt_errors(attempts), attempts)


async def _call_model_openai_chat(
    *,
    provider: dict[str, Any],
    model_name: str,
    prompt: str,
    max_tokens: int,
    read_timeout_seconds: int = DEFAULT_READ_TIMEOUT_SECONDS,
) -> str:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - exercised only without dependency
        raise RuntimeError("httpx is required for real review-launch model dispatch") from exc

    base_url = _provider_openai_base_url(provider)
    api_key = str(provider.get("openai_api_key") or provider.get("api_key") or "").strip()
    if not base_url or not api_key:
        raise RuntimeError("provider is missing OpenAI-compatible base_url or api_key")

    url = _openai_chat_url(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a precise code-review agent. Return only the review Markdown."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": max_tokens,
    }
    provider_id = str(provider.get("id") or "")
    provider_profile = str(provider.get("profile") or provider.get("provider_profile") or "")
    apply_profile_body_patches(
        payload,
        protocol="openai_chat",
        runtime=provider,
        provider_id=provider_id,
        profile_id=provider_profile,
        base_url=base_url,
        model_name=model_name,
        thinking_enabled=True,
        reasoning_effort=str(provider.get("reasoning_effort") or "high"),
        purpose="review_launch",
    )
    apply_profile_auth_headers(
        headers,
        protocol="openai_chat",
        api_key=api_key,
        runtime=provider,
        provider_id=provider_id,
        profile_id=provider_profile,
        base_url=base_url,
        model_name=model_name,
    )

    timeout = httpx.Timeout(connect=20, write=20, read=read_timeout_seconds, pool=20)
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=timeout)
        if response.status_code == 400 and "Stream must be set to true" in response.text:
            stream_payload = dict(payload)
            stream_payload["stream"] = True
            response = await client.post(url, headers=headers, json=stream_payload, timeout=timeout)
            if response.status_code < 400:
                content = _extract_openai_stream_text(response.text)
                if content:
                    return content
    if response.status_code >= 400:
        raise RuntimeError(f"model dispatch failed HTTP {response.status_code}: {response.text[:1000]}")
    data = response.json()
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices:
        raise RuntimeError("model response has no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    content = _extract_response_text((message or {}).get("content"))
    if not content:
        raise RuntimeError("model response content is empty")
    return content


def _with_query_param_once(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    if not any(item_key == key for item_key, _item_value in query_items):
        query_items.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))


def _review_launch_needs_newapi_beta(provider: dict[str, Any]) -> bool:
    """NewAPI Claude Messages cache path expects the same beta query Claude Code sends."""
    haystack = " ".join(
        str(provider.get(key) or "").lower()
        for key in ("id", "name", "profile", "provider_profile")
    )
    return "newapi" in haystack or "new-api" in haystack


def _anthropic_messages_url(base_url: str, *, provider: dict[str, Any] | None = None) -> str:
    parts = urlsplit(base_url.rstrip("/"))
    path = parts.path.rstrip("/")
    if path.endswith("/v1/messages") or path.endswith("/messages"):
        messages_path = path
    elif path.endswith("/v1"):
        messages_path = f"{path}/messages"
    else:
        messages_path = f"{path}/v1/messages"
    url = urlunsplit((parts.scheme, parts.netloc, messages_path, parts.query, parts.fragment))
    if provider and _review_launch_needs_newapi_beta(provider):
        return _with_query_param_once(url, "beta", "true")
    return url


async def _call_model_anthropic_messages(
    *,
    provider: dict[str, Any],
    model_name: str,
    prompt: str,
    max_tokens: int,
    read_timeout_seconds: int = DEFAULT_READ_TIMEOUT_SECONDS,
) -> str:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - exercised only without dependency
        raise RuntimeError("httpx is required for real review-launch model dispatch") from exc

    base_url = _provider_anthropic_base_url(provider)
    api_key = _provider_api_key_for_protocol(provider, ANTHROPIC_MESSAGES_PROTOCOL)
    if not base_url or not api_key:
        raise RuntimeError("provider is missing Anthropic-compatible base_url or api_key")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model_name,
        "system": "You are a precise code-review agent. Return only the review Markdown.",
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        "stream": False,
        "max_tokens": max_tokens,
    }
    provider_id = str(provider.get("id") or "")
    provider_profile = str(provider.get("profile") or provider.get("provider_profile") or "")
    apply_profile_body_patches(
        payload,
        protocol="anthropic_messages",
        runtime=provider,
        provider_id=provider_id,
        profile_id=provider_profile,
        base_url=base_url,
        model_name=model_name,
        thinking_enabled=True,
        reasoning_effort=str(provider.get("reasoning_effort") or "high"),
        purpose="review_launch",
    )
    apply_profile_auth_headers(
        headers,
        protocol="anthropic_messages",
        api_key=api_key,
        runtime=provider,
        provider_id=provider_id,
        profile_id=provider_profile,
        base_url=base_url,
        model_name=model_name,
    )

    timeout = httpx.Timeout(connect=20, write=20, read=read_timeout_seconds, pool=20)
    async with httpx.AsyncClient() as client:
        response = await client.post(_anthropic_messages_url(base_url, provider=provider), headers=headers, json=payload, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(f"model dispatch failed HTTP {response.status_code}: {response.text[:1000]}")
    data = response.json()
    blocks = data.get("content") if isinstance(data, dict) else None
    if isinstance(blocks, str):
        content = blocks.strip()
    elif isinstance(blocks, list):
        content = _extract_response_text(blocks)
    else:
        choices = data.get("choices") if isinstance(data, dict) else None
        message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        content = _extract_response_text((message or {}).get("content"))
    if not content:
        raise RuntimeError("model response content is empty")
    return content


async def _call_model(
    *,
    provider: dict[str, Any],
    protocol: str,
    model_name: str,
    prompt: str,
    max_tokens: int,
    read_timeout_seconds: int = DEFAULT_READ_TIMEOUT_SECONDS,
) -> str:
    if protocol == ANTHROPIC_MESSAGES_PROTOCOL:
        return await _call_model_anthropic_messages(
            provider=provider,
            model_name=model_name,
            prompt=prompt,
            max_tokens=max_tokens,
            read_timeout_seconds=read_timeout_seconds,
        )
    if protocol == OPENAI_CHAT_PROTOCOL:
        return await _call_model_openai_chat(
            provider=provider,
            model_name=model_name,
            prompt=prompt,
            max_tokens=max_tokens,
            read_timeout_seconds=read_timeout_seconds,
        )
    raise RuntimeError(f"unsupported review-launch provider protocol: {protocol}")


def _fake_response(env: dict[str, str]) -> str:
    inline = str(env.get(FAKE_RESPONSE_ENV) or "")
    if inline:
        return inline
    file_ref = str(env.get(FAKE_RESPONSE_FILE_ENV) or "").strip()
    if not file_ref:
        return ""
    return Path(file_ref).expanduser().read_text(encoding="utf-8")


def run_review_launch(env: dict[str, str] | None = None) -> dict[str, Any]:
    effective_env = dict(env or os.environ)
    validation = validate_review_launch_env(effective_env)
    if not validation["ok"]:
        return {
            **validation,
            "schema": REVIEW_LAUNCH_RESULT_SCHEMA,
            "status": "blocked",
            "model_calls": 0,
            "review_file_writes": 0,
            "review_file_written": False,
        }

    reviewer_id = str(effective_env.get("MOEBIUS_REVIEWER_ID") or "").strip()
    repo_root = Path(str(effective_env["MOEBIUS_REPO_ROOT"])).expanduser()
    pack_path = _resolve(str(effective_env["MOEBIUS_REVIEW_PACK"]), repo_root)
    expected_output = _resolve(str(effective_env["MOEBIUS_REVIEW_EXPECTED_OUTPUT"]), repo_root)
    started_at = _now()
    errors: list[str] = []
    warnings: list[str] = list(validation.get("warnings") or [])
    model_calls = 0
    fake_dispatch = False
    provider_id = ""
    provider_protocol = ""
    dispatch_model_name = reviewer_id
    dispatch_attempts: list[dict[str, Any]] = []
    dispatch_candidates_count = 0
    context_entries: list[dict[str, Any]] = []

    try:
        pack = _read_json(pack_path)
        prompt, context_entries = _review_prompt(repo_root, pack_path, pack, effective_env)
        fake_text = _fake_response(effective_env)
        if fake_text:
            fake_dispatch = True
            model_calls = 1
            review_text = fake_text
        else:
            candidates, provider_error = _resolve_review_launch_candidates(reviewer_id, effective_env)
            if provider_error:
                raise RuntimeError(provider_error)
            max_candidates = _int_env(
                effective_env,
                MAX_CANDIDATES_ENV,
                DEFAULT_MAX_CANDIDATES,
                minimum=1,
                maximum=20,
            )
            candidates = candidates[:max_candidates]
            dispatch_candidates_count = len(candidates)
            max_tokens = _int_env(effective_env, MAX_TOKENS_ENV, DEFAULT_MAX_TOKENS, maximum=200000)
            read_timeout_seconds = _int_env(
                effective_env,
                READ_TIMEOUT_ENV,
                DEFAULT_READ_TIMEOUT_SECONDS,
                minimum=5,
                maximum=900,
            )
            try:
                review_text, selected_candidate, dispatch_attempts = asyncio.run(
                    _call_first_working_model(
                        candidates=candidates,
                        prompt=prompt,
                        max_tokens=max_tokens,
                        read_timeout_seconds=read_timeout_seconds,
                    )
                )
            except ReviewLaunchDispatchError as exc:
                dispatch_attempts = exc.attempts
                model_calls = len(dispatch_attempts)
                if dispatch_attempts:
                    last_attempt = dispatch_attempts[-1]
                    provider_id = str(last_attempt.get("provider_id") or "")
                    provider_protocol = str(last_attempt.get("provider_protocol") or "")
                    dispatch_model_name = str(last_attempt.get("model_name") or reviewer_id)
                raise RuntimeError(str(exc)) from exc
            model_calls = len(dispatch_attempts)
            provider_id = str((selected_candidate.get("provider") or {}).get("id") or "")
            provider_protocol = str(selected_candidate.get("protocol") or "")
            dispatch_model_name = str(selected_candidate.get("model_name") or reviewer_id)
        final_text = _ensure_reviewer_header(review_text, reviewer_id)
        if not _path_under(expected_output, repo_root):
            raise RuntimeError("expected output escaped repo root after validation")
        preexisting = expected_output.exists()
        _write_text_atomic(expected_output, final_text)
        review_file_writes = 1
        status = "review_written"
        review_file_written = True
    except Exception as exc:
        errors.append(str(exc))
        preexisting = expected_output.exists()
        review_file_writes = 0
        status = "failed"
        review_file_written = False

    return {
        "schema": REVIEW_LAUNCH_RESULT_SCHEMA,
        "launched_at": started_at,
        "completed_at": _now(),
        "ok": status == "review_written",
        "status": status,
        "reviewer_id": reviewer_id,
        "provider_id": provider_id,
        "provider_protocol": provider_protocol,
        "dispatch_model_name": dispatch_model_name,
        "dispatch_candidates_count": dispatch_candidates_count,
        "dispatch_attempts": dispatch_attempts,
        "fake_dispatch": fake_dispatch,
        "expected_output": str(expected_output),
        "expected_output_rel": _relative_to(expected_output, repo_root),
        "review_file_preexisting": preexisting,
        "review_file_written": review_file_written,
        "model_calls": model_calls,
        "review_file_writes": review_file_writes,
        "review_intake_run": False,
        "context_entries": context_entries,
        "errors": errors,
        "warnings": warnings,
    }


def _print_payload(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if payload.get("schema") == REVIEW_LAUNCH_CONTRACT_SCHEMA:
        print(f"{payload['command']} — {payload['purpose']}")
        print("Modes: --contract-json, --validate-env")
        print("Model dispatch: implemented, gated by Moebius review-dispatch HumanGate")
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def handle_review_launch_command(argv: list[str], *, command_name: str = "mms") -> int:
    parser = argparse.ArgumentParser(
        prog=f"{command_name} review-launch",
        description=(
            "MMS review-launch — noninteractive multi-review reviewer launcher. "
            "Reads Moebius reviewer env, validates identity/output contract, "
            "dispatches one model after an approved gate, and writes exactly one review file."
        ),
    )
    parser.add_argument("--contract-json", action="store_true", help="print the local review-launch contract JSON")
    parser.add_argument("--validate-env", action="store_true", help="validate Moebius reviewer-launch env without model calls")
    parser.add_argument("--json", action="store_true", help="print JSON for validation/default output")
    parser.add_argument(
        "--allow-model-call",
        action="store_true",
        help="compatibility latch for callers that want an explicit MMS-side model-call flag",
    )
    args = parser.parse_args(argv)

    if args.contract_json:
        _print_payload(build_review_launch_contract(command_name), json_output=True)
        return 0

    if args.validate_env:
        result = validate_review_launch_env()
        _print_payload(result, json_output=args.json or True)
        return 0 if result["ok"] else 2

    result = run_review_launch()
    _print_payload(result, json_output=args.json or True)
    return 0 if result.get("ok") is True else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(handle_review_launch_command(os.sys.argv[1:]))
