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
