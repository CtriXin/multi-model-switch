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
MAX_FILE_CHARS_ENV = "MMS_REVIEW_LAUNCH_MAX_FILE_CHARS"
MAX_PROMPT_CHARS_ENV = "MMS_REVIEW_LAUNCH_MAX_PROMPT_CHARS"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_MAX_FILE_CHARS = 12000
DEFAULT_MAX_PROMPT_CHARS = 90000


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
        if not (_path_under(path, repo_root) or str(path).startswith("/Users/xin/auto-skills/")):
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


def _resolve_provider_for_model(model_name: str, env: dict[str, str]) -> tuple[dict[str, Any] | None, str]:
    try:
        from mms_core import (
            _default_config,
            _provider_effective_models,
            _resolve_best_provider,
            apply_local_overrides,
            load_config,
            resolve_provider_context,
        )
    except Exception as exc:
        return None, f"cannot import MMS provider resolver: {exc}"

    cfg = load_config() or _default_config()
    cfg = apply_local_overrides(cfg)
    provider_id = str(env.get(PROVIDER_ID_ENV) or "").strip()
    if provider_id:
        try:
            provider = resolve_provider_context(cfg, provider_id)
        except Exception as exc:
            return None, f"cannot resolve provider {provider_id}: {exc}"
        if not provider.get("api_key"):
            return None, f"provider {provider_id} has no api_key"
        if not _provider_openai_base_url(provider):
            return None, f"provider {provider_id} has no OpenAI-compatible base_url"
        return provider, ""

    default_id = str((cfg.get("provider") or {}).get("default") or "default")
    try:
        default_provider = resolve_provider_context(cfg, default_id)
    except Exception:
        default_provider = {}
    default_models = _provider_effective_models(default_provider, None, cfg) if default_provider else []
    provider, _provider_name = _resolve_best_provider(
        cfg,
        model_name,
        default_provider,
        default_models,
        protocol="openai_chat_completions",
    )
    if provider is None:
        return None, f"no configured OpenAI-compatible provider found for reviewer model {model_name}"
    return provider, ""


async def _call_model_openai_chat(
    *,
    provider: dict[str, Any],
    model_name: str,
    prompt: str,
    max_tokens: int,
) -> str:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - exercised only without dependency
        raise RuntimeError("httpx is required for real review-launch model dispatch") from exc

    base_url = _provider_openai_base_url(provider)
    api_key = str(provider.get("openai_api_key") or provider.get("api_key") or "").strip()
    if not base_url or not api_key:
        raise RuntimeError("provider is missing OpenAI-compatible base_url or api_key")

    url = f"{base_url.rstrip('/')}/v1/chat/completions"
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

    timeout = httpx.Timeout(connect=20, write=20, read=900, pool=20)
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(f"model dispatch failed HTTP {response.status_code}: {response.text[:1000]}")
    data = response.json()
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices:
        raise RuntimeError("model response has no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    content = str((message or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("model response content is empty")
    return content


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
            provider, provider_error = _resolve_provider_for_model(reviewer_id, effective_env)
            if provider_error:
                raise RuntimeError(provider_error)
            provider_id = str((provider or {}).get("id") or "")
            max_tokens = _int_env(effective_env, MAX_TOKENS_ENV, DEFAULT_MAX_TOKENS, maximum=200000)
            model_calls = 1
            review_text = asyncio.run(
                _call_model_openai_chat(
                    provider=provider or {},
                    model_name=reviewer_id,
                    prompt=prompt,
                    max_tokens=max_tokens,
                )
            )
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
