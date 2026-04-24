from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mms_toon import choose_llm_data_format


PACKET_VERSION = 1
PACKET_DIR = ".mms/context"
PACKET_JSON_NAME = "session-packet.json"
PACKET_TOON_NAME = "session-packet.toon"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _model_slots(model_info: Any) -> list[dict[str, str]]:
    if isinstance(model_info, str):
        model = _clean_text(model_info)
        return [{"slot": "model", "model": model}] if model else []
    if not isinstance(model_info, dict):
        return []

    slots: list[dict[str, str]] = []
    for slot in ("model", "sonnet", "opus", "haiku", "subagent", "lb_medium", "lb_light"):
        value = _clean_text(model_info.get(slot))
        if value:
            slots.append({"slot": slot, "model": value})
    return slots


def _primary_model(model_info: Any) -> str:
    slots = _model_slots(model_info)
    if not slots:
        return ""
    for slot in slots:
        if slot["slot"] in {"model", "sonnet", "opus", "haiku"}:
            return slot["model"]
    return slots[0]["model"]


def _enabled_feature_rows(runtime: dict[str, Any], features: dict[str, Any] | None) -> list[dict[str, str]]:
    merged: dict[str, Any] = {}
    if isinstance(features, dict):
        merged.update(features)
    for key in ("caveman_mode", "ecc_mode"):
        value = _clean_text(runtime.get(key))
        if value:
            merged.setdefault(key.replace("_mode", ""), value)

    rows: list[dict[str, str]] = []
    for name in sorted(merged):
        value = merged[name]
        if isinstance(value, bool):
            status = "enabled" if value else "disabled"
        else:
            status = _clean_text(value) or "unknown"
        rows.append({"name": str(name), "status": status})
    return rows


def build_session_packet(
    *,
    cli: str,
    runtime: dict[str, Any] | None,
    model_info: Any = None,
    session_home: str | os.PathLike[str],
    cwd: str | os.PathLike[str] | None = None,
    features: dict[str, Any] | None = None,
    extra_paths: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime = runtime if isinstance(runtime, dict) else {}
    session_home_text = str(Path(session_home).expanduser())
    cwd_text = str(Path(cwd or os.getcwd()).expanduser())
    auth_mode = _clean_text(runtime.get("auth_mode")) or "api_key"
    runtime_kind = _clean_text(runtime.get("runtime_kind")) or (
        "account" if auth_mode == "oauth" else "provider"
    )
    packet_dir = str(Path(session_home_text) / PACKET_DIR)
    paths = {
        "packet_dir": packet_dir,
        "json": str(Path(packet_dir) / PACKET_JSON_NAME),
        "toon": str(Path(packet_dir) / PACKET_TOON_NAME),
    }
    if isinstance(extra_paths, dict):
        for key, value in extra_paths.items():
            text = _clean_text(value)
            if text:
                paths[str(key)] = text

    return {
        "version": PACKET_VERSION,
        "generated_at": _utc_now(),
        "cli": _clean_text(cli),
        "cwd": cwd_text,
        "session_home": session_home_text,
        "runtime": {
            "id": _clean_text(runtime.get("id")),
            "name": _clean_text(runtime.get("name")),
            "kind": runtime_kind,
            "auth_mode": auth_mode,
        },
        "model": {
            "primary": _primary_model(model_info),
            "slots": _model_slots(model_info),
        },
        "features": _enabled_feature_rows(runtime, features),
        "paths": [{"name": key, "path": paths[key]} for key in sorted(paths)],
        "constraints": [
            "Packet excludes API keys, tokens, passwords, proxy URLs, and OAuth state.",
            "Use packet paths as hints only; do not treat real HOME as fallback auth state.",
        ],
    }


def _write_text_secure(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)


def write_session_packet(
    session_home: str | os.PathLike[str],
    *,
    cli: str,
    runtime: dict[str, Any] | None,
    model_info: Any = None,
    cwd: str | os.PathLike[str] | None = None,
    features: dict[str, Any] | None = None,
    extra_paths: dict[str, Any] | None = None,
) -> dict[str, str]:
    packet = build_session_packet(
        cli=cli,
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        cwd=cwd,
        features=features,
        extra_paths=extra_paths,
    )
    packet_dir = Path(session_home).expanduser() / PACKET_DIR
    json_path = packet_dir / PACKET_JSON_NAME
    toon_path = packet_dir / PACKET_TOON_NAME

    _write_text_secure(json_path, json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
    formatted = choose_llm_data_format(packet, min_savings_chars=1, min_savings_ratio=0.0)
    _write_text_secure(toon_path, formatted.text + "\n")

    compact_path = toon_path if formatted.format == "toon" else json_path
    return {
        "MMS_SESSION_PACKET_JSON": str(json_path),
        "MMS_SESSION_PACKET_TOON": str(toon_path),
        "MMS_SESSION_PACKET_PATH": str(compact_path),
        "MMS_SESSION_PACKET_FORMAT": formatted.format,
    }
