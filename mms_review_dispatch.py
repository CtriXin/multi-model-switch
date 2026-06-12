"""Mission Control -> OpenCode Review Hub dispatch helper."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REVIEW_DISPATCH_SCHEMA = "mms.review_dispatch.v1"
DEFAULT_REVIEW_FOCUS = ["code", "verification"]
BLOCKED_READINESS_STATES = {
    "blocked-source",
    "needs-info",
    "out-of-scope-review",
    "ready-for-human",
}
REVIEW_MODEL_PRESETS: dict[str, list[str]] = {
    "code_review": ["MiniMax-M3", "qwen3.7-max", "kimi-k2.6", "mimo-v2.5"],
    "large_arch": ["gpt-5.4", "deepseek-v4-pro", "qwen3.7-max", "glm-5.1"],
    "design_visual": ["mimo-v2.5", "kimi-k2.6", "qwen3.6-flash"],
    "domestic_cross": ["qwen3.7-max", "kimi-k2.6", "glm-5-turbo", "deepseek-v4-flash"],
    "fast_cheap": ["mimo-v2.5", "qwen3.6-flash", "deepseek-v4-flash"],
}
REVIEW_MODEL_PRESET_ALIASES = {
    "code": "code_review",
    "normal": "code_review",
    "ordinary": "code_review",
    "ordinary-code": "code_review",
    "default": "code_review",
    "large": "large_arch",
    "arch": "large_arch",
    "architecture": "large_arch",
    "high-risk": "large_arch",
    "risk": "large_arch",
    "design": "design_visual",
    "ui": "design_visual",
    "visual": "design_visual",
    "image": "design_visual",
    "screenshot": "design_visual",
    "domestic": "domestic_cross",
    "cn": "domestic_cross",
    "china": "domestic_cross",
    "cross": "domestic_cross",
    "quick": "fast_cheap",
    "fast": "fast_cheap",
    "cheap": "fast_cheap",
    "smoke": "fast_cheap",
}
REVIEW_MODEL_ALIASES = {
    "mimo-2.5": "mimo-v2.5",
    "mimo-v2.5": "mimo-v2.5",
    "mimo2.5": "mimo-v2.5",
    "mimo25": "mimo-v2.5",
    "kimi-2.6": "kimi-k2.6",
    "kimi-k2.6": "kimi-k2.6",
    "kimi2.6": "kimi-k2.6",
    "kimi26": "kimi-k2.6",
    "qwen3.6": "qwen3.6-flash",
    "qwen3.6-flash": "qwen3.6-flash",
    "qwen36": "qwen3.6-flash",
    "qwen3.7": "qwen3.7-max",
    "qwen3.7max": "qwen3.7-max",
    "qwen37max": "qwen3.7-max",
    "glm5-turbo": "glm-5-turbo",
    "glm-5-turbo": "glm-5-turbo",
    "glm5turbo": "glm-5-turbo",
    "glm5turobo": "glm-5-turbo",
    "glm51": "glm-5.1",
    "glm5.1": "glm-5.1",
    "minimax-m3": "MiniMax-M3",
    "minimaxm3": "MiniMax-M3",
    "deepseekv4pro": "deepseek-v4-pro",
    "deepseekv4flash": "deepseek-v4-flash",
    "gpt54": "gpt-5.4",
    "gpt5.4": "gpt-5.4",
}
REVIEW_AUTO_KEYWORDS = {
    "large_arch": [
        "architecture",
        "arch",
        "high risk",
        "high-risk",
        "large",
        "migration",
        "routing",
        "route",
        "bridge",
        "config",
        "cache",
        "schema",
        "provider",
        "oauth",
        "auth",
        "security",
        "release",
        "rollback",
        "架构",
        "高风险",
        "大任务",
        "迁移",
        "路由",
        "桥接",
        "配置",
        "缓存",
        "账号",
        "发布",
    ],
    "design_visual": [
        "design",
        "ui",
        "ux",
        "visual",
        "image",
        "screenshot",
        "figma",
        "mockup",
        "prototype",
        "layout",
        "css",
        "frontend",
        "pixel",
        "设计",
        "界面",
        "视觉",
        "图像",
        "截图",
        "前端",
    ],
    "domestic_cross": [
        "domestic",
        "china",
        "cn",
        "cross",
        "cross-review",
        "qwen",
        "kimi",
        "glm",
        "deepseek",
        "国内",
        "国产",
        "交叉审查",
        "交叉",
    ],
    "fast_cheap": [
        "quick",
        "fast",
        "cheap",
        "smoke",
        "light",
        "low cost",
        "low-cost",
        "快速",
        "便宜",
        "低成本",
        "复核",
    ],
}
REVIEW_AUTO_TIE_BREAK = ["large_arch", "design_visual", "domestic_cross", "fast_cheap"]
_MODEL_CATALOG_CACHE: dict[str, dict[str, Any]] = {}


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text or "review"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _first_existing(root: Path, candidates: list[str]) -> Path | None:
    for rel in candidates:
        candidate = root / rel
        if candidate.exists():
            return candidate
    return None


def _mission_context(root: Path) -> dict[str, Any]:
    readiness_path = _first_existing(root, [".mission/readiness.json", "readiness.json"])
    agent_brief_path = _first_existing(root, [".mission/agent-brief.md", "agent-brief.md"])
    mission_prd_path = _first_existing(root, [".mission/mission-prd.md", "mission-prd.md"])
    check_spec_path = _first_existing(
        root,
        [
            ".work-gate/state/check-spec.json",
            "work-gate/state/check-spec.json",
            ".work-gate/check-spec.json",
            "check-spec.json",
        ],
    )
    readiness = _read_json(readiness_path) if readiness_path else {}
    state = str(readiness.get("state") or readiness.get("readiness") or "").strip()
    return {
        "readiness_path": str(readiness_path) if readiness_path else "",
        "readiness_state": state,
        "agent_brief_path": str(agent_brief_path) if agent_brief_path else "",
        "mission_prd_path": str(mission_prd_path) if mission_prd_path else "",
        "check_spec_path": str(check_spec_path) if check_spec_path else "",
        "missing": [
            label
            for label, path in [
                ("readiness", readiness_path),
                ("agent_brief", agent_brief_path),
                ("check_spec", check_spec_path),
            ]
            if path is None
        ],
    }


def _alias_key(value: str) -> str:
    return re.sub(r"[\s_]+", "-", str(value or "").strip().lower())


def _compact_alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower()).replace("turobo", "turbo")


def _selected_config_root() -> Path:
    for key in ("MMS_CONFIG_ROOT", "MMS_CONFIG_DIR"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return Path(value).expanduser()
    return Path.home() / ".config" / "mms"


def _manifest_payload_path(config_root: Path, manifest: dict[str, Any], file_key: str) -> Path | None:
    files = manifest.get("files")
    if not isinstance(files, dict):
        return None
    entry = files.get(file_key)
    if not isinstance(entry, dict):
        return None
    rel_path = str(entry.get("canonical_path") or "").strip()
    if not rel_path:
        return None
    return config_root / rel_path


def _manifest_payload_hash(manifest: dict[str, Any], file_key: str) -> str:
    files = manifest.get("files")
    if not isinstance(files, dict):
        return ""
    entry = files.get(file_key)
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("sha256") or "").strip().lower()


def _read_verified_manifest_payload(config_root: Path, file_key: str) -> dict[str, Any]:
    manifest_path = config_root / "generated" / "model-registry.latest-approved.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    payload_path = _manifest_payload_path(config_root, manifest, file_key)
    if payload_path is None:
        return {}
    expected_hash = _manifest_payload_hash(manifest, file_key)
    try:
        payload_bytes = payload_path.read_bytes()
    except OSError:
        return {}
    if expected_hash and hashlib.sha256(payload_bytes).hexdigest().lower() != expected_hash:
        return {}
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _selector_variants(model_name: str) -> list[str]:
    variants = {_alias_key(model_name), _compact_alias_key(model_name)}
    lowered = str(model_name or "").strip().lower()
    short = re.sub(r"^(kimi)-k(?=\d)", r"\1", lowered)
    short = re.sub(r"^(mimo)-v(?=\d)", r"\1", short)
    variants.add(_alias_key(short))
    variants.add(_compact_alias_key(short))
    return [variant for variant in variants if variant]


def _review_model_catalog() -> dict[str, Any]:
    config_root = _selected_config_root().resolve()
    cache_key = str(config_root)
    cached = _MODEL_CATALOG_CACHE.get(cache_key)
    if cached is not None:
        return cached
    lineup = _read_verified_manifest_payload(config_root, "lineup")
    routes = lineup.get("routes")
    if not isinstance(routes, dict):
        catalog = {"config_root": str(config_root), "models": {}, "available": False}
        _MODEL_CATALOG_CACHE[cache_key] = catalog
        return catalog
    models: dict[str, str] = {}
    for model_name in routes:
        canonical = str(model_name or "").strip()
        if not canonical:
            continue
        for selector in _selector_variants(canonical):
            models.setdefault(selector, canonical)
    catalog = {
        "config_root": str(config_root),
        "models": models,
        "available": True,
        "model_count": len(routes),
        "source": str(config_root / "generated" / "model-routes.lineup.json"),
    }
    _MODEL_CATALOG_CACHE[cache_key] = catalog
    return catalog


def _normalize_review_model(model: str) -> str:
    value = str(model or "").strip()
    catalog_models = _review_model_catalog().get("models")
    if isinstance(catalog_models, dict):
        canonical = catalog_models.get(_alias_key(value)) or catalog_models.get(_compact_alias_key(value))
        if canonical:
            return str(canonical)
    return REVIEW_MODEL_ALIASES.get(_alias_key(value)) or REVIEW_MODEL_ALIASES.get(_compact_alias_key(value), value)


def _model_text_tokens(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    text = re.sub(r"\b(and|with|using|use)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(使用|用|和|与|以及|加上|还有|模型|reviewer|reviewers)", " ", text)
    raw_tokens = re.split(r"[\s,，、;+|/]+", text)
    tokens: list[str] = []
    for token in raw_tokens:
        cleaned = token.strip(" \t\r\n'\"`[](){}<>")
        if not cleaned:
            continue
        alias_hit = _normalize_review_model(cleaned) != cleaned
        looks_model_like = any(char.isdigit() for char in cleaned) or "-" in cleaned or "." in cleaned
        if alias_hit or looks_model_like:
            tokens.append(cleaned)
    return tokens


def _expand_review_model_values(models: list[str], model_text: list[str] | None = None) -> list[str]:
    expanded: list[str] = []
    for model in models:
        tokens = _model_text_tokens(model)
        expanded.extend(tokens or [model])
    for text in model_text or []:
        expanded.extend(_model_text_tokens(text))
    return expanded


def _normalize_review_models(models: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for model in models:
        model_name = _normalize_review_model(model)
        seen_key = model_name.lower()
        if model_name and seen_key not in seen:
            normalized.append(model_name)
            seen.add(seen_key)
    return normalized


def _normalize_focus(focus: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in focus or DEFAULT_REVIEW_FOCUS:
        name = str(item).strip()
        key = name.lower()
        if name and key not in seen:
            normalized.append(name)
            seen.add(key)
    return normalized or list(DEFAULT_REVIEW_FOCUS)


def _claude_review_models(models: list[str]) -> list[str]:
    return [model for model in models if "claude" in model.lower()]


def _review_model_preset_key(value: str) -> str:
    key = _alias_key(value).replace("-", "_")
    if key in REVIEW_MODEL_PRESETS:
        return key
    alias = REVIEW_MODEL_PRESET_ALIASES.get(_alias_key(value)) or REVIEW_MODEL_PRESET_ALIASES.get(key)
    if alias:
        return alias
    allowed = ", ".join(sorted(REVIEW_MODEL_PRESETS))
    raise ValueError(f"unknown review model preset: {value}; expected one of: {allowed}")


def _preset_review_models(preset: str) -> list[str]:
    return _normalize_review_models(REVIEW_MODEL_PRESETS[_review_model_preset_key(preset)])


def _read_context_snippet(path_value: str, *, limit: int = 6000) -> str:
    if not path_value:
        return ""
    try:
        return Path(path_value).read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _review_selection_text(
    *,
    title: str,
    summary: str,
    phase: str,
    focus: list[str],
    context: dict[str, Any],
) -> str:
    parts = [
        title,
        summary,
        phase,
        " ".join(focus),
        str(context.get("readiness_state") or ""),
    ]
    for path_key in ("agent_brief_path", "mission_prd_path", "check_spec_path"):
        parts.append(_read_context_snippet(str(context.get(path_key) or "")))
    return "\n".join(part for part in parts if part).lower()


def _keyword_matched(text: str, keyword: str) -> bool:
    lowered = keyword.lower()
    if lowered.isascii() and len(lowered) <= 3:
        return re.search(rf"\b{re.escape(lowered)}\b", text) is not None
    return lowered in text


def _auto_review_model_selection(
    *,
    title: str,
    summary: str,
    phase: str,
    focus: list[str],
    context: dict[str, Any],
) -> dict[str, Any]:
    text = _review_selection_text(title=title, summary=summary, phase=phase, focus=focus, context=context)
    matches: dict[str, list[str]] = {}
    for preset, keywords in REVIEW_AUTO_KEYWORDS.items():
        matched = [keyword for keyword in keywords if _keyword_matched(text, keyword)]
        if matched:
            matches[preset] = matched
    if matches:
        profile = max(
            matches,
            key=lambda item: (len(matches[item]), -REVIEW_AUTO_TIE_BREAK.index(item)),
        )
        reason = "matched review keywords: " + ", ".join(matches[profile][:6])
    else:
        profile = "code_review"
        reason = "default code review preset; no specialized review keywords matched"
    return {
        "models": _preset_review_models(profile),
        "source": "auto",
        "profile": profile,
        "reason": reason,
    }


def _select_review_models(
    *,
    models: list[str],
    model_text: list[str] | None,
    model_preset: str | None,
    title: str,
    summary: str,
    phase: str,
    focus: list[str],
    context: dict[str, Any],
) -> dict[str, Any]:
    explicit_models = _normalize_review_models(_expand_review_model_values(models, model_text))
    if explicit_models:
        return {
            "models": explicit_models,
            "source": "explicit",
            "profile": "explicit",
            "reason": "explicit --model values",
        }
    if model_preset:
        profile = _review_model_preset_key(model_preset)
        return {
            "models": _preset_review_models(profile),
            "source": "preset",
            "profile": profile,
            "reason": f"explicit --model-preset {model_preset}",
        }
    return _auto_review_model_selection(
        title=title,
        summary=summary,
        phase=phase,
        focus=focus,
        context=context,
    )


def _review_hub_binary() -> str:
    binary = shutil.which("review-hub")
    if not binary:
        raise FileNotFoundError("review-hub executable not found in PATH")
    return binary


def _run_review_hub(args: list[str], *, dry_run: bool = False) -> dict[str, Any]:
    command = [_review_hub_binary()] + args
    if dry_run:
        return {"ok": True, "dry_run": True, "command": command}
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "review-hub failed: "
            + " ".join(shlex.quote(part) for part in command)
            + "\n"
            + (completed.stderr or completed.stdout or "").strip()
        )
    output = (completed.stdout or "").strip()
    if not output:
        return {"ok": True, "command": command}
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"review-hub returned non-JSON output: {output[:500]}") from exc
    if isinstance(payload, dict):
        payload.setdefault("command", command)
        return payload
    return {"ok": True, "command": command, "output": payload}


def _build_request_args(
    *,
    root: Path,
    request_root: Path,
    request_id: str,
    title: str,
    summary: str,
    phase: str,
    adapter: str,
    focus: list[str],
    models: list[str],
    context: dict[str, Any],
) -> list[str]:
    args = [
        "request",
        "--root",
        str(root),
        "--out-dir",
        str(request_root),
        "--request-id",
        request_id,
        "--title",
        title,
        "--summary",
        summary,
        "--phase",
        phase,
        "--adapter",
        adapter,
        "--write",
    ]
    for item in focus:
        args.extend(["--focus", item])
    for path_key in ("agent_brief_path", "mission_prd_path", "check_spec_path"):
        path = context.get(path_key)
        if path:
            args.extend(["--context-path", path])
    for model in models:
        args.extend(["--model", model])
    return args


def _build_worker_plan_args(request_root: Path, models: list[str], runner: str, agent: str) -> list[str]:
    args = [
        "worker-plan",
        "--request",
        str(request_root),
        "--runner",
        runner,
        "--agent",
        agent,
        "--write",
    ]
    for model in models:
        args.extend(["--model", model])
    return args


def _mms_script_path(command_name: str = "mms") -> Path:
    name = str(command_name or "mms").strip() or "mms"
    candidate = Path(__file__).resolve().with_name(Path(name).name)
    return candidate if candidate.exists() else Path(__file__).resolve().with_name("mms")


def _opencode_launch_command(
    request_root: Path,
    *,
    command_name: str = "mms",
    models: list[str] | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(_mms_script_path(command_name)),
        "opencode",
        "--profile",
        "review",
    ]
    if models:
        command.append("--review-models")
        command.extend(models)
    return command


def _review_hub_prompt(request_root: Path) -> str:
    return (
        f"/review-hub {request_root}\n\n"
        "Use the Review Hub request root above. Run the worker plan, delegate to the "
        "configured reviewer agents, and aggregate results. Do not edit source files."
    )


def _fake_reviewer_outputs(request_root: Path, workers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for worker in workers:
        model = str(worker.get("model_name") or "").strip()
        slot_root = Path(str(worker.get("slot_root") or ""))
        if not model or not slot_root:
            continue
        verify_root = slot_root / "verify"
        _write_text(verify_root / "00-preflight.md", f"# Preflight\n\nModel: `{model}`\nStatus: pass\n")
        _write_text(
            verify_root / "01-checks.md",
            f"# Checks\n\n- pass: review-dispatch request was readable for `{model}`.\n",
        )
        _write_json(verify_root / "02-failures.json", {"model": model, "failures": []})
        _write_json(verify_root / "03-residual-risks.json", {"model": model, "residual_risks": []})
        _write_text(
            verify_root / "04-final-verdict.md",
            f"# Final Verdict\n\nVerdict: pass\n\nFake reviewer result for `{model}`.\n",
        )
        results.append({"model": model, "slot_root": str(slot_root), "verify_root": str(verify_root)})
    return results


def build_review_dispatch(
    *,
    root: Path,
    title: str,
    summary: str,
    phase: str,
    models: list[str],
    out_dir: Path | None,
    request_id: str | None,
    adapter: str,
    focus: list[str],
    fake_run: bool,
    dry_run: bool,
    launch: bool,
    allow_incomplete: bool,
    model_preset: str | None = None,
    model_text: list[str] | None = None,
    command_name: str = "mms",
) -> dict[str, Any]:
    root = root.resolve()
    focus = _normalize_focus(focus)
    if not root.exists():
        return {"ok": False, "errors": [f"root does not exist: {root}"]}

    context = _mission_context(root)
    errors: list[str] = []
    if context["missing"] and not allow_incomplete:
        errors.append("missing Mission Control artifacts: " + ", ".join(context["missing"]))
    state = str(context.get("readiness_state") or "").strip()
    if state in BLOCKED_READINESS_STATES:
        errors.append(f"readiness state blocks dispatch: {state}")
    if errors:
        return {"ok": False, "root": str(root), "context": context, "errors": errors}

    try:
        selection = _select_review_models(
            models=models,
            model_text=model_text,
            model_preset=model_preset,
            title=title,
            summary=summary,
            phase=phase,
            focus=focus,
            context=context,
        )
    except ValueError as exc:
        return {"ok": False, "root": str(root), "context": context, "errors": [str(exc)]}
    models = selection["models"]
    blocked_models = _claude_review_models(models)
    if blocked_models:
        return {
            "ok": False,
            "root": str(root),
            "context": context,
            "model_selection_source": selection["source"],
            "model_selection_profile": selection["profile"],
            "model_selection_reason": selection["reason"],
            "models": models,
            "errors": [
                "Claude models are not allowed in review-dispatch reviewer slots: "
                + ", ".join(blocked_models)
            ],
        }
    request_id = request_id or f"{_now_stamp()}-{_slugify(title)}"
    request_root = (
        out_dir.resolve()
        if out_dir
        else root / ".mission" / "review-dispatch" / "opencode" / request_id
    )
    request_args = _build_request_args(
        root=root,
        request_root=request_root,
        request_id=request_id,
        title=title,
        summary=summary,
        phase=phase,
        adapter=adapter,
        focus=focus,
        models=models,
        context=context,
    )
    worker_args = _build_worker_plan_args(request_root, models, "opencode", "review-hub-host")
    launch_command = _opencode_launch_command(request_root, command_name=command_name, models=models)

    payload: dict[str, Any] = {
        "schema": REVIEW_DISPATCH_SCHEMA,
        "ok": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "request_id": request_id,
        "request_root": str(request_root),
        "phase": phase,
        "models": models,
        "model_selection_source": selection["source"],
        "model_selection_profile": selection["profile"],
        "model_selection_reason": selection["reason"],
        "context": context,
        "review_hub_request_command": [_review_hub_binary()] + request_args if shutil.which("review-hub") else request_args,
        "review_hub_worker_plan_command": [_review_hub_binary()] + worker_args if shutil.which("review-hub") else worker_args,
        "opencode_launch_command": launch_command,
        "review_hub_prompt": _review_hub_prompt(request_root),
        "opencode_profile": "review",
        "fake_run": fake_run,
        "dry_run": dry_run,
        "launched": False,
    }
    if dry_run:
        return payload

    request_result = _run_review_hub(request_args)
    worker_plan = _run_review_hub(worker_args)
    payload["review_hub_request"] = request_result
    payload["worker_plan"] = worker_plan

    fake_results: list[dict[str, Any]] = []
    aggregate_result: dict[str, Any] | None = None
    workers = worker_plan.get("workers") if isinstance(worker_plan.get("workers"), list) else []
    if fake_run:
        fake_results = _fake_reviewer_outputs(request_root, workers)
        aggregate_result = _run_review_hub(["aggregate", "--request", str(request_root), "--write"])
        payload["fake_results"] = fake_results
        payload["aggregate"] = aggregate_result

    if launch:
        completed = subprocess.run(launch_command, text=True, check=False)
        payload["launched"] = True
        payload["launch_returncode"] = completed.returncode
        if completed.returncode != 0:
            payload["ok"] = False
            payload.setdefault("errors", []).append(f"OpenCode launch failed with exit code {completed.returncode}")

    _write_json(request_root / "mms-review-dispatch.json", payload)
    return payload


def handle_review_dispatch_command(argv: list[str], *, command_name: str = "mms") -> int:
    parser = argparse.ArgumentParser(
        prog=f"{command_name} review-dispatch",
        description="Create a Mission Control Review Hub request and prepare/launch the OpenCode review profile.",
    )
    parser.add_argument("--root", required=True, help="Mission Control artifact root or repo root")
    parser.add_argument("--title", default="Mission Control review dispatch")
    parser.add_argument("--summary", default="Review Mission Control packet and gate evidence before closeout.")
    parser.add_argument("--phase", choices=["pre", "mid", "post"], default="post")
    parser.add_argument("--adapter", default="mms-opencode")
    parser.add_argument("--focus", action="append", default=list(DEFAULT_REVIEW_FOCUS))
    parser.add_argument("--model", action="append", default=[], help="Reviewer model; repeat for multiple models")
    parser.add_argument("--model-text", action="append", default=[], help="Free-form reviewer model phrase; repeat for more text")
    parser.add_argument("--model-preset", help="Reviewer model preset; defaults to automatic dispatch-time selection")
    parser.add_argument("--out-dir", help="Override Review Hub request root")
    parser.add_argument("--request-id", help="Stable request id")
    parser.add_argument("--allow-incomplete", action="store_true", help="Do not fail on missing Mission Control artifacts")
    parser.add_argument("--dry-run", action="store_true", help="Print planned request/worker/OpenCode commands without writing")
    parser.add_argument("--fake-run", action="store_true", help="Write fake per-model reviewer outputs and aggregate them")
    parser.add_argument("--launch", action="store_true", help="Launch MMS OpenCode review profile after writing request artifacts")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("model_phrase", nargs="*", help="Free-form reviewer phrase, e.g. 使用 kimi2.5 minimaxm3")
    args = parser.parse_args(argv)

    try:
        payload = build_review_dispatch(
            root=Path(args.root),
            title=args.title,
            summary=args.summary,
            phase=args.phase,
            models=args.model,
            model_text=[*args.model_text, " ".join(args.model_phrase)] if args.model_phrase else args.model_text,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            request_id=args.request_id,
            adapter=args.adapter,
            focus=args.focus,
            fake_run=args.fake_run,
            dry_run=args.dry_run,
            launch=args.launch,
            allow_incomplete=args.allow_incomplete,
            model_preset=args.model_preset,
            command_name=command_name,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a structured error
        payload = {"schema": REVIEW_DISPATCH_SCHEMA, "ok": False, "errors": [str(exc)]}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if payload.get("ok"):
            print(f"review-dispatch ready: {payload.get('request_root')}")
            print("OpenCode command:")
            print(" ".join(shlex.quote(str(part)) for part in payload.get("opencode_launch_command", [])))
            if payload.get("aggregate"):
                print(f"aggregate: {payload['aggregate'].get('aggregate_path')}")
        else:
            print("review-dispatch failed", file=sys.stderr)
            for item in payload.get("errors", []):
                print(f"- {item}", file=sys.stderr)
    return 0 if payload.get("ok") else 2


__all__ = [
    "REVIEW_DISPATCH_SCHEMA",
    "REVIEW_MODEL_PRESETS",
    "build_review_dispatch",
    "handle_review_dispatch_command",
]
