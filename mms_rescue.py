from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from mms_state_io import atomic_write_text, locked_state_file, resolve_real_user_home


RESCUE_SCHEMA = "mms.rescue_event.v1"
GLOBAL_INDEX_SCHEMA = "mms.rescue_index.v1"
FALLBACK_HANDOVER_SCHEMA = "mms.rescue_fallback_handover.v1"
_RESCUE_LIST_LIMIT = 20

_AUTH_BEARING_PATH_PARTS = {
    ".claude.json",
    "auth.json",
    "credentials.json",
    "credentials.sh",
    "config.toml",
    "override.toml",
    "accounts",
    "keychain",
    ".gemini",
}

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r'(?i)("authorization"\s*:\s*"bearer\s+)[^"]+(")'), r"\1<REDACTED>\2"),
    (re.compile(r'(?i)("x-api-key"\s*:\s*")[^"]+(")'), r"\1<REDACTED>\2"),
    (re.compile(r'(?i)("api_key"\s*:\s*")[^"]+(")'), r"\1<REDACTED>\2"),
    (re.compile(r'(?i)("access_token"\s*:\s*")[^"]+(")'), r"\1<REDACTED>\2"),
    (re.compile(r'(?i)("refresh_token"\s*:\s*")[^"]+(")'), r"\1<REDACTED>\2"),
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+"), r"\1<REDACTED>"),
    (re.compile(r"(?i)(x-api-key\s*:\s*)[^\s\"']+"), r"\1<REDACTED>"),
    (re.compile(r"(?i)(api-key\s*:\s*)[^\s\"']+"), r"\1<REDACTED>"),
    (re.compile(r"(?i)(api_key\s*[=:]\s*)[^\s,\"'&]+"), r"\1<REDACTED>"),
    (re.compile(r"(?i)(access_token\s*[=:]\s*)[^\s,\"'&]+"), r"\1<REDACTED>"),
    (re.compile(r"(?i)(refresh_token\s*[=:]\s*)[^\s,\"'&]+"), r"\1<REDACTED>"),
    (re.compile(r"(?i)(client_secret\s*[=:]\s*)[^\s,\"'&]+"), r"\1<REDACTED>"),
    (re.compile(r"(?i)([?&](?:api_key|key|token|access_token|refresh_token|client_secret|code)=)[^&\s]+"), r"\1<REDACTED>"),
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{12,})\b"), "<REDACTED_KEY>"),
)

_SECRET_DETECTORS: tuple[re.Pattern[str], ...] = (
    re.compile(r'(?i)"authorization"\s*:\s*"bearer\s+(?!<REDACTED>)\S+'),
    re.compile(r'(?i)"x-api-key"\s*:\s*"(?!<REDACTED>)\S+'),
    re.compile(r'(?i)"refresh_token"\s*:\s*"(?!<REDACTED>)\S+'),
    re.compile(r'(?i)"access_token"\s*:\s*"(?!<REDACTED>)\S+'),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+(?!<REDACTED>)\S+"),
    re.compile(r"(?i)x-api-key\s*:\s*(?!<REDACTED>)\S+"),
    re.compile(r"(?i)refresh_token\s*[=:]\s*(?!<REDACTED>)\S+"),
    re.compile(r"(?i)access_token\s*[=:]\s*(?!<REDACTED>)\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)

_BLOCKING_STATUS_CODES = {401, 403, 408, 409, 413, 425, 429, 500, 502, 503, 504}
_CONTEXT_OVERFLOW_MARKERS = (
    "context_length_exceeded",
    "context length",
    "context window",
    "context overflow",
    "maximum context",
    "max context",
    "token limit",
    "too many tokens",
)
_RATE_LIMIT_MARKERS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "quota",
    "insufficient_quota",
    "billing quota",
)
_MODEL_NOT_FOUND_MARKERS = (
    "model not found",
    "model_not_found",
    "unknown model",
    "does not exist",
    "not found",
)
_UNSUPPORTED_MARKERS = (
    "unsupported",
    "unsupported_parameter",
    "unsupported capability",
    "unsupported parameter",
    "unknown parameter",
    "invalid parameter",
    "not supported",
)
_TIMEOUT_MARKERS = (
    "timeout",
    "timed out",
    "deadline exceeded",
    "read timeout",
    "connect timeout",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_real_mms_config_dir(env: Mapping[str, str] | None = None) -> Path:
    """Resolve real MMS config root without trusting isolated session HOME."""
    real_home = resolve_real_user_home(dict(env or os.environ))
    return Path(real_home) / ".config" / "mms"


def redact_text(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def is_secret_safe(text: str) -> bool:
    return not any(pattern.search(text or "") for pattern in _SECRET_DETECTORS)


def assert_secret_safe(text: str) -> None:
    if not is_secret_safe(text):
        raise ValueError("rescue artifact still contains secret-looking content after redaction")


def _status_int(status_code: Any) -> int | None:
    try:
        return int(status_code)
    except (TypeError, ValueError):
        return None


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(marker in lowered for marker in markers)


def classify_blocking_failure(
    *,
    status_code: Any = None,
    body_text: Any = "",
    error_type: Any = "",
    exception: Any = "",
) -> str:
    """Return a stable rescue reason for failures that should write L3 rescue."""
    status = _status_int(status_code)
    haystack = " ".join(str(item or "") for item in (body_text, error_type, exception)).lower()
    if status == 429 or _contains_any(haystack, _RATE_LIMIT_MARKERS):
        return "rate_limit_or_quota"
    if status in {408, 504} or _contains_any(haystack, _TIMEOUT_MARKERS):
        return "timeout"
    if status == 413 or _contains_any(haystack, _CONTEXT_OVERFLOW_MARKERS):
        return "context_overflow"
    if (status == 404 and "model" in haystack) or _contains_any(haystack, _MODEL_NOT_FOUND_MARKERS):
        return "model_not_found"
    if _contains_any(haystack, _UNSUPPORTED_MARKERS):
        return "unsupported_capability_or_parameter"
    if status in {401, 403}:
        return "provider_auth_or_permission"
    if status in {500, 502, 503}:
        return "provider_error"
    if status in _BLOCKING_STATUS_CODES:
        return f"http_{status}"
    return ""


def is_auth_bearing_path(path: str | os.PathLike[str]) -> bool:
    normalized = str(path or "").replace("\\", "/").lower()
    parts = {part for part in normalized.split("/") if part}
    if parts & _AUTH_BEARING_PATH_PARTS:
        return True
    return any(part.endswith((".pem", ".key", ".p12", ".p8")) for part in parts)


def _safe_artifact_name(name: str) -> str:
    value = str(name or "artifact").strip().replace("\\", "/").split("/")[-1]
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return value or "artifact"


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_json_object(path: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _rescue_event_from_payload(payload: Mapping[str, Any], index_item: Mapping[str, Any] | None = None) -> dict[str, Any]:
    failed = payload.get("failed") if isinstance(payload.get("failed"), Mapping) else {}
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), Mapping) else {}
    item = dict(index_item or {})
    artifact_json = str(item.get("artifact_json") or artifacts.get("json") or "").strip()
    artifact_markdown = str(item.get("artifact_markdown") or artifacts.get("markdown") or "").strip()
    return {
        "schema": str(item.get("schema") or GLOBAL_INDEX_SCHEMA),
        "event_id": str(payload.get("event_id") or item.get("event_id") or ""),
        "created_at": str(payload.get("created_at") or item.get("created_at") or ""),
        "repo_path": str(payload.get("repo_path") or item.get("repo_path") or ""),
        "rescue_level": str(payload.get("rescue_level") or item.get("rescue_level") or ""),
        "failed_model": str(failed.get("model") or item.get("failed_model") or ""),
        "failed_provider_id": str(failed.get("provider_id") or item.get("failed_provider_id") or ""),
        "status_code": failed.get("status_code"),
        "failure_kind": str(failed.get("failure_kind") or failed.get("error_type") or ""),
        "error_summary": redact_text(failed.get("error_summary") or ""),
        "artifact_json": artifact_json,
        "artifact_markdown": artifact_markdown,
        "next_action": redact_text(payload.get("next_action") or ""),
    }


def list_rescue_events(
    *,
    repo_root: str | os.PathLike[str] | None = None,
    config_root: str | os.PathLike[str] | None = None,
    limit: int = _RESCUE_LIST_LIMIT,
) -> list[dict[str, Any]]:
    """Return recent rescue events from the global index plus current repo latest."""
    cfg = Path(config_root).expanduser().resolve() if config_root else resolve_real_mms_config_dir()
    index_path = cfg / "rescue" / "index.jsonl"
    candidates: list[dict[str, Any]] = []
    if index_path.exists():
        try:
            lines = index_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines[-max(int(limit or 1) * 3, 1):]:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            payload = _read_json_object(str(item.get("artifact_json") or ""))
            if payload:
                candidates.append(_rescue_event_from_payload(payload, item))
            else:
                candidates.append({
                    "schema": str(item.get("schema") or GLOBAL_INDEX_SCHEMA),
                    "event_id": str(item.get("event_id") or ""),
                    "created_at": str(item.get("created_at") or ""),
                    "repo_path": str(item.get("repo_path") or ""),
                    "rescue_level": str(item.get("rescue_level") or ""),
                    "failed_model": str(item.get("failed_model") or ""),
                    "failed_provider_id": str(item.get("failed_provider_id") or ""),
                    "status_code": "",
                    "failure_kind": "",
                    "error_summary": "",
                    "artifact_json": str(item.get("artifact_json") or ""),
                    "artifact_markdown": str(item.get("artifact_markdown") or ""),
                    "next_action": "",
                })

    repo = Path(repo_root or os.getcwd()).expanduser().resolve()
    local_latest = repo / ".mms" / "rescue" / "latest.json"
    if local_latest.exists():
        payload = _read_json_object(local_latest)
        if payload:
            candidates.append(_rescue_event_from_payload(payload))

    deduped: dict[str, dict[str, Any]] = {}
    for item in candidates:
        key = str(item.get("event_id") or item.get("artifact_json") or item.get("artifact_markdown") or id(item))
        deduped[key] = item
    events = sorted(
        deduped.values(),
        key=lambda item: str(item.get("created_at") or ""),
        reverse=True,
    )
    return events[: max(int(limit or _RESCUE_LIST_LIMIT), 1)]


def write_demo_rescue_packet(
    *,
    repo_root: str | os.PathLike[str] | None = None,
    config_root: str | os.PathLike[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create a safe local demo rescue packet for TUI/manual verification."""
    return write_file_only_rescue(
        {
            "registry_revision": "demo",
            "failed": {
                "model": "demo-rescue-model",
                "provider_id": "demo-provider",
                "status_code": 429,
                "error_type": "rate_limit_or_quota",
                "failure_kind": "rate_limit_or_quota",
                "error_summary": "Demo rescue packet; no upstream request was made.",
            },
            "git": {"status_short": "demo packet"},
            "fallback_reason": "demo rescue packet; automatic continuation fallback not attempted",
            "next_action": "This is a demo packet. Use it to verify the Rescue viewer, then ignore or delete repo/.mms/rescue demo artifacts.",
        },
        repo_root=repo_root,
        config_root=config_root,
        raw_artifacts={"demo-upstream-response.txt": "demo only; no upstream request was made"},
        created_at=created_at,
    )


def _handover_context_policy(payload: Mapping[str, Any]) -> dict[str, Any]:
    failed = payload.get("failed") if isinstance(payload.get("failed"), Mapping) else {}
    failure_kind = str(failed.get("failure_kind") or failed.get("error_type") or "").strip()
    status = _status_int(failed.get("status_code"))
    if status == 413 or failure_kind == "context_overflow":
        return {
            "mode": "compact_first",
            "reason": "The failed run looks context-bound; compact or summarize before using a smaller fallback model.",
        }
    return {
        "mode": "handover_first",
        "reason": "A fallback model can start from the generated handover packet without replaying the full transcript.",
    }


def _fallback_handover_markdown(payload: Mapping[str, Any]) -> str:
    failed = payload.get("failed") if isinstance(payload.get("failed"), Mapping) else {}
    fallback = payload.get("fallback") if isinstance(payload.get("fallback"), Mapping) else {}
    context_policy = payload.get("context_policy") if isinstance(payload.get("context_policy"), Mapping) else {}
    source_artifacts = payload.get("source_artifacts") if isinstance(payload.get("source_artifacts"), Mapping) else {}
    automatic_model_call = bool((payload.get("fallback") or {}).get("automatic_model_call"))
    lines = [
        "# MMS Rescue Fallback Handover",
        "",
        f"- schema: `{payload.get('schema')}`",
        f"- created_at: `{payload.get('created_at')}`",
        f"- source_event_id: `{payload.get('source_event_id') or 'unknown'}`",
        f"- repo_path: `{payload.get('repo_path') or 'unknown'}`",
        "",
        "## Failed Route",
        "",
        f"- model: `{failed.get('model') or 'unknown'}`",
        f"- provider_id: `{failed.get('provider_id') or 'unknown'}`",
        f"- status_code: `{failed.get('status_code') or 'unknown'}`",
        f"- failure_kind: `{failed.get('failure_kind') or failed.get('error_type') or 'unknown'}`",
        f"- summary: {failed.get('error_summary') or 'unknown'}",
        "",
        "## Fallback Target",
        "",
        f"- model: `{fallback.get('model') or 'manual-select'}`",
        f"- cli: `{fallback.get('cli') or 'select in MMS'}`",
        f"- mode: `{fallback.get('mode') or 'manual_handover'}`",
        f"- automatic_model_call: `{automatic_model_call}`",
        "",
        "## Context Policy",
        "",
        f"- mode: `{context_policy.get('mode') or 'handover_first'}`",
        f"- reason: {context_policy.get('reason') or '-'}",
        "",
        "## Continue Prompt",
        "",
        "```text",
        "Continue from this MMS rescue handover.",
        f"Repo: {payload.get('repo_path') or 'unknown'}",
        f"Previous failed model: {failed.get('model') or 'unknown'}",
        f"Failure: {failed.get('failure_kind') or failed.get('error_type') or 'unknown'} / {failed.get('status_code') or 'unknown'}",
        f"Fallback target: {fallback.get('model') or 'manual-select'}",
        "",
        "Read the rescue packet first, summarize the needed state, then finish only the smallest safe next step.",
        "Do not replay unrelated transcript. If context_policy is compact_first, create a concise checkpoint before continuing.",
        "```",
        "",
        "## Source Artifacts",
        "",
        f"- rescue.md: `{source_artifacts.get('markdown') or '-'}`",
        f"- rescue.json: `{source_artifacts.get('json') or '-'}`",
        "",
        "## Safety",
        "",
        f"- automatic_model_call: `{automatic_model_call}`",
        "- auth_bearing_state_read: `False`",
        "- privacy_boundary_crossed: `False`",
        "",
    ]
    text = "\n".join(lines)
    assert_secret_safe(text)
    return text


def write_fallback_handover(
    rescue_event: Mapping[str, Any],
    *,
    fallback_model: str,
    fallback_cli: str = "",
    mode: str = "manual_handover",
    automatic_model_call: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Write a safe continuation packet for an explicit fallback model."""
    model = str(fallback_model or "").strip()
    if not model:
        raise ValueError("fallback_model is required")

    raw_artifacts = rescue_event.get("artifacts") if isinstance(rescue_event.get("artifacts"), Mapping) else {}
    artifact_json = str(rescue_event.get("artifact_json") or raw_artifacts.get("json") or "").strip()
    if str(rescue_event.get("schema") or "") == RESCUE_SCHEMA and isinstance(rescue_event.get("failed"), Mapping):
        source_payload = dict(rescue_event)
    else:
        source_payload = _read_json_object(artifact_json) if artifact_json else {}
    if not source_payload:
        source_payload = {
            "event_id": rescue_event.get("event_id") or "",
            "created_at": rescue_event.get("created_at") or "",
            "repo_path": rescue_event.get("repo_path") or os.getcwd(),
            "failed": {
                "model": rescue_event.get("failed_model") or "",
                "provider_id": rescue_event.get("failed_provider_id") or "",
                "status_code": rescue_event.get("status_code"),
                "failure_kind": rescue_event.get("failure_kind") or "",
                "error_summary": rescue_event.get("error_summary") or "",
            },
            "artifacts": {
                "json": rescue_event.get("artifact_json") or "",
                "markdown": rescue_event.get("artifact_markdown") or "",
            },
        }

    failed = _redacted_mapping(dict(source_payload.get("failed") or {}))
    repo_path = str(source_payload.get("repo_path") or rescue_event.get("repo_path") or os.getcwd())
    artifacts = source_payload.get("artifacts") if isinstance(source_payload.get("artifacts"), Mapping) else {}
    created = created_at or utc_now_iso()
    event_dir = Path(str(artifacts.get("dir") or "")).expanduser()
    if not str(event_dir) or not event_dir.exists():
        source_json_path = Path(artifact_json).expanduser() if artifact_json else None
        event_dir = source_json_path.parent if source_json_path and source_json_path.exists() else Path(repo_path) / ".mms" / "rescue" / "fallback-handover"
    event_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": FALLBACK_HANDOVER_SCHEMA,
        "created_at": created,
        "source_event_id": source_payload.get("event_id") or rescue_event.get("event_id") or "",
        "repo_path": repo_path,
        "failed": failed,
        "fallback": {
            "selected": True,
            "model": redact_text(model),
            "cli": redact_text(fallback_cli or ""),
            "mode": redact_text(mode or "manual_handover"),
            "automatic_model_call": bool(automatic_model_call),
        },
        "context_policy": _handover_context_policy(source_payload),
        "source_artifacts": {
            "json": str(artifacts.get("json") or rescue_event.get("artifact_json") or ""),
            "markdown": str(artifacts.get("markdown") or rescue_event.get("artifact_markdown") or ""),
        },
        "safety": {
            "file_only_written_first": True,
            "automatic_model_call": bool(automatic_model_call),
            "global_oauth_fallback": "disabled",
            "auth_bearing_state_read": False,
            "privacy_boundary_crossed": False,
        },
    }
    handover_json = event_dir / "fallback-handover.json"
    handover_md = event_dir / "fallback-handover.md"
    repo_rescue = Path(repo_path) / ".mms" / "rescue"
    payload["artifacts"] = {
        "json": str(handover_json),
        "markdown": str(handover_md),
        "latest_json": str(repo_rescue / "latest-fallback-handover.json"),
        "latest_markdown": str(repo_rescue / "latest-fallback-handover.md"),
    }
    json_text = _json_dumps(payload)
    assert_secret_safe(json_text)
    md_text = _fallback_handover_markdown(payload)
    atomic_write_text(handover_json, json_text, mode=0o600)
    atomic_write_text(handover_md, md_text, mode=0o600)
    atomic_write_text(repo_rescue / "latest-fallback-handover.json", json_text, mode=0o600)
    atomic_write_text(repo_rescue / "latest-fallback-handover.md", md_text, mode=0o600)
    return payload


def _event_id(created_at: str, repo_path: str, failed_model: str) -> str:
    digest = hashlib.sha256(f"{created_at}\0{repo_path}\0{failed_model}".encode("utf-8")).hexdigest()
    return digest[:16]


def _redacted_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, Mapping):
            out[str(key)] = _redacted_mapping(value)
        elif isinstance(value, list):
            out[str(key)] = [redact_text(item) if not isinstance(item, Mapping) else _redacted_mapping(item) for item in value]
        elif value is None or isinstance(value, (int, float, bool)):
            out[str(key)] = value
        else:
            out[str(key)] = redact_text(value)
    return out


def build_rescue_event(
    event: Mapping[str, Any],
    *,
    repo_root: str | os.PathLike[str],
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or utc_now_iso()
    repo_path = str(Path(repo_root).expanduser().resolve())
    failed = _redacted_mapping(dict(event.get("failed") or {}))
    failed_model = str(failed.get("model") or event.get("model") or "unknown")
    event_id = str(event.get("event_id") or _event_id(created, repo_path, failed_model))
    automatic_model_call = bool(event.get("automatic_model_call"))
    payload = {
        "schema": RESCUE_SCHEMA,
        "event_id": event_id,
        "created_at": created,
        "rescue_level": "L3_file_only",
        "repo_path": repo_path,
        "registry_revision": redact_text(event.get("registry_revision") or ""),
        "failed": failed,
        "git": _redacted_mapping(dict(event.get("git") or {})),
        "plan_refs": [redact_text(item) for item in event.get("plan_refs") or []],
        "fallback": {
            "selected": False,
            "reason": redact_text(event.get("fallback_reason") or "file-only rescue baseline"),
        },
        "health": _redacted_mapping(dict(event.get("health") or {})),
        "bridge": _redacted_mapping(dict(event.get("bridge") or {})),
        "safety": {
            "file_only_written_first": True,
            "automatic_model_call": automatic_model_call,
            "global_oauth_fallback": "disabled",
            "auth_bearing_state_read": False,
            "privacy_boundary_crossed": False,
        },
        "next_action": redact_text(event.get("next_action") or "Open latest.md and resume with a compatible model."),
    }
    serialized = _json_dumps(payload)
    assert_secret_safe(serialized)
    return payload


def render_rescue_markdown(payload: Mapping[str, Any]) -> str:
    failed = payload.get("failed") if isinstance(payload.get("failed"), Mapping) else {}
    git = payload.get("git") if isinstance(payload.get("git"), Mapping) else {}
    lines = [
        "# MMS Rescue Packet",
        "",
        f"- schema: `{payload.get('schema')}`",
        f"- event_id: `{payload.get('event_id')}`",
        f"- created_at: `{payload.get('created_at')}`",
        f"- rescue_level: `{payload.get('rescue_level')}`",
        f"- repo_path: `{payload.get('repo_path')}`",
        f"- registry_revision: `{payload.get('registry_revision') or 'unknown'}`",
        "",
        "## Failed Route",
        "",
        f"- model: `{failed.get('model') or 'unknown'}`",
        f"- provider_id: `{failed.get('provider_id') or 'unknown'}`",
        f"- status_code: `{failed.get('status_code') or 'unknown'}`",
        f"- error_type: `{failed.get('error_type') or 'unknown'}`",
        f"- error_summary: {failed.get('error_summary') or failed.get('message') or 'unknown'}",
        "",
        "## Git Snapshot",
        "",
        "```text",
        str(git.get("status_short") or "not captured"),
        "```",
        "",
        "## Rescue Safety",
        "",
        f"- mode: `{'file-first-hot-fallback' if payload.get('safety', {}).get('automatic_model_call') else 'file-only'}`",
        f"- automatic_model_call: `{bool(payload.get('safety', {}).get('automatic_model_call'))}`",
        "- global_oauth_fallback: `disabled`",
        "- privacy_boundary_crossed: `False`",
        "",
        "## Next Action",
        "",
        str(payload.get("next_action") or "Resume from this rescue packet."),
        "",
    ]
    text = "\n".join(lines)
    assert_secret_safe(text)
    return text


def write_file_only_rescue(
    event: Mapping[str, Any],
    *,
    repo_root: str | os.PathLike[str] | None = None,
    config_root: str | os.PathLike[str] | None = None,
    raw_artifacts: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Write an L3 file-only rescue packet and metadata-only global index entry."""
    repo = Path(repo_root or os.getcwd()).expanduser().resolve()
    payload = build_rescue_event(event, repo_root=repo, created_at=created_at)
    event_dir = repo / ".mms" / "rescue" / str(payload["created_at"]).replace(":", "").replace("+", "Z")
    raw_dir = event_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    skipped: list[str] = []
    written_raw: list[str] = []
    for name, value in (raw_artifacts or {}).items():
        if is_auth_bearing_path(name):
            skipped.append(str(name))
            continue
        safe_name = _safe_artifact_name(str(name))
        text = redact_text(value)
        assert_secret_safe(text)
        target = raw_dir / safe_name
        atomic_write_text(target, text + ("" if text.endswith("\n") else "\n"), mode=0o600)
        written_raw.append(str(target))

    payload["artifacts"] = {
        "dir": str(event_dir),
        "json": str(event_dir / "rescue.json"),
        "markdown": str(event_dir / "rescue.md"),
        "raw_dir": str(raw_dir),
        "raw_written": written_raw,
        "raw_skipped_auth_bearing": skipped,
    }
    payload_text = _json_dumps(payload)
    assert_secret_safe(payload_text)
    markdown = render_rescue_markdown(payload)
    atomic_write_text(event_dir / "rescue.json", payload_text, mode=0o600)
    atomic_write_text(event_dir / "rescue.md", markdown, mode=0o600)
    atomic_write_text(repo / ".mms" / "rescue" / "latest.json", payload_text, mode=0o600)
    atomic_write_text(repo / ".mms" / "rescue" / "latest.md", markdown, mode=0o600)

    cfg = Path(config_root).expanduser().resolve() if config_root else resolve_real_mms_config_dir()
    index_path = cfg / "rescue" / "index.jsonl"
    index_item = {
        "schema": GLOBAL_INDEX_SCHEMA,
        "event_id": payload["event_id"],
        "created_at": payload["created_at"],
        "repo_path": payload["repo_path"],
        "rescue_level": payload["rescue_level"],
        "failed_model": (payload.get("failed") or {}).get("model"),
        "failed_provider_id": (payload.get("failed") or {}).get("provider_id"),
        "artifact_json": payload["artifacts"]["json"],
        "artifact_markdown": payload["artifacts"]["markdown"],
    }
    index_line = json.dumps(index_item, ensure_ascii=False, sort_keys=True)
    assert_secret_safe(index_line)
    with locked_state_file(index_path):
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with index_path.open("a", encoding="utf-8") as handle:
            handle.write(index_line + "\n")

    return payload


def record_blocking_failure(
    *,
    repo_root: str | os.PathLike[str] | None = None,
    config_root: str | os.PathLike[str] | None = None,
    model: str = "",
    provider_id: str = "",
    status_code: Any = None,
    body_text: Any = "",
    error_type: Any = "",
    error_summary: Any = "",
    request_url: str = "",
    request_path: str = "",
    route_count: Any = None,
    bridge_surface: str = "",
    registry_revision: str = "",
    raw_artifacts: Mapping[str, Any] | None = None,
    git: Mapping[str, Any] | None = None,
    automatic_model_call: bool = False,
    created_at: str | None = None,
) -> dict[str, Any] | None:
    """Thin bridge/launcher entry: write L3 file-only rescue for blocking failures."""
    failure_kind = classify_blocking_failure(
        status_code=status_code,
        body_text=body_text,
        error_type=error_type,
    )
    if not failure_kind:
        return None

    status = _status_int(status_code)
    summary = error_summary or body_text or (f"HTTP {status}" if status is not None else failure_kind)
    failed = {
        "model": model or "unknown",
        "provider_id": provider_id or "unknown",
        "status_code": status,
        "error_type": error_type or failure_kind,
        "error_summary": summary,
        "request_url": request_url,
        "request_path": request_path,
        "route_count": route_count,
        "failure_kind": failure_kind,
    }
    event = {
        "registry_revision": registry_revision,
        "automatic_model_call": bool(automatic_model_call),
        "failed": failed,
        "git": dict(git or {}),
        "bridge": {
            "surface": bridge_surface or "unknown",
            "route_count": route_count,
        },
        "health": {
            "status": "degraded",
            "reason": failure_kind,
            "ttl_seconds": 900,
        },
        "fallback_reason": (
            "L3 file-only rescue hook written before configured hot fallback model call"
            if automatic_model_call
            else "L3 file-only rescue hook; automatic continuation fallback not attempted"
        ),
        "next_action": (
            "Configured hot fallback is being attempted; inspect latest-fallback-handover if it cannot finish."
            if automatic_model_call
            else "Open .mms/rescue/latest.md and resume with an explicitly selected compatible runtime."
        ),
    }
    artifacts = dict(raw_artifacts or {})
    if body_text not in (None, "") and "upstream-response.txt" not in artifacts:
        artifacts["upstream-response.txt"] = body_text
    return write_file_only_rescue(
        event,
        repo_root=repo_root,
        config_root=config_root,
        raw_artifacts=artifacts,
        created_at=created_at,
    )
