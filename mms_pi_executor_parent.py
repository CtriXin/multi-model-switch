"""Parent intake adapter for ``mms.pi_executor.result.v1``."""

from __future__ import annotations

import copy
import hashlib
import shlex
from pathlib import Path
from typing import Any, Mapping, Sequence

import mms_pi_executor


PARENT_SCHEMA = "mms.pi_executor.parent_packet.v1"


class ExecutorParentError(RuntimeError):
    """Raised when an executor result cannot be admitted for parent intake."""


def build_parent_packet(result: Mapping[str, Any], *, source: str = "saved") -> dict[str, Any]:
    if result.get("schema") != mms_pi_executor.RESULT_SCHEMA:
        raise ExecutorParentError(f"unsupported executor result schema: {result.get('schema')!r}")
    if source not in {"live", "saved"}:
        raise ExecutorParentError(f"unknown parent source: {source}")
    rows = [copy.deepcopy(dict(row)) for row in result.get("results") or [] if isinstance(row, Mapping)]
    plan = result.get("plan", {}) if isinstance(result.get("plan"), Mapping) else {}
    pack = copy.deepcopy(dict(plan.get("pack", {}))) if isinstance(plan.get("pack"), Mapping) else {}
    intake = plan.get("intake", {}) if isinstance(plan.get("intake"), Mapping) else {}
    pack["_max_patch_bytes"] = int(intake.get("max_patch_bytes") or 2 * 1024 * 1024)
    for row in rows:
        if row.get("admissible") is True and row.get("status") == "success":
            reasons = _verify_admissible_candidate(row, pack)
            if reasons:
                row["admissible"] = False
                row["status"] = "rejected"
                row["terminal_reason"] = "parent_intake_rejected"
                row["intake_rejection_reasons"] = reasons
    admissible = [row for row in rows if row.get("admissible") is True and row.get("status") == "success"]
    rejected = [row for row in rows if row.get("status") == "rejected"]
    failed = [row for row in rows if row not in admissible and row not in rejected]
    patch_index = [
        {
            "candidate_id": row.get("candidate_id"),
            "model": row.get("model"),
            "path": row.get("patch", {}).get("path"),
            "sha256": row.get("patch", {}).get("sha256"),
            "bytes": row.get("patch", {}).get("bytes"),
            "changed_files": row.get("changed_files", []),
            "validation": row.get("validation", []),
        }
        for row in admissible
    ]
    return {
        "schema": PARENT_SCHEMA,
        "run_id": result.get("run_id"),
        "task_id": result.get("task_id"),
        "status": (
            "dry_run"
            if result.get("status") == "dry_run"
            else ("saved_result_requires_host_revalidation" if source == "saved" and admissible else ("ready_for_intake" if admissible else "no_admissible_candidate"))
        ),
        "source_trust": source,
        "health": {
            "planned": result.get("summary", {}).get("candidates", len(rows)),
            "returned": len(rows),
            "admissible": len(admissible),
            "rejected": len(rejected),
            "failed": len(failed),
        },
        "plan": copy.deepcopy(result.get("plan", {})),
        "admissible_candidates": admissible,
        "rejected_candidates": rejected,
        "failed_candidates": failed,
        "patch_index": patch_index,
        "host_intake_contract": {
            "auto_apply": False,
            "selection_required": True,
            "verify_patch_hash_before_use": True,
            "rerun_project_checks_after_apply": True,
            "never_apply_rejected_or_failed_candidates": True,
            "saved_result_validation_is_advisory": source == "saved",
            "parent_actions": [
                "compare admissible candidates against pack success criteria",
                "inspect each patch and validation evidence",
                "select at most one base patch or manually synthesize a new patch",
                "apply only through the host's normal reviewed edit workflow",
            ],
        },
        "source_result_schema": mms_pi_executor.RESULT_SCHEMA,
    }


def run_parent_executor(
    *,
    config_root: str | Path,
    pack_path: str | Path,
    target_repo: str | Path,
    explicit_models: Sequence[str],
    artifact_dir: str | Path | None = None,
    max_concurrency: int = mms_pi_executor.DEFAULT_MAX_CONCURRENCY,
    timeout_seconds: int = mms_pi_executor.DEFAULT_TIMEOUT_SECONDS,
    idle_timeout_seconds: int = mms_pi_executor.DEFAULT_IDLE_TIMEOUT_SECONDS,
    validation_timeout_seconds: int = mms_pi_executor.DEFAULT_VALIDATION_TIMEOUT_SECONDS,
    max_output_bytes: int = mms_pi_executor.DEFAULT_MAX_OUTPUT_BYTES,
    max_repeated_events: int = mms_pi_executor.DEFAULT_MAX_REPEATED_EVENTS,
    max_patch_bytes: int = mms_pi_executor.DEFAULT_MAX_PATCH_BYTES,
    executor_timeout_seconds: int = mms_pi_executor.DEFAULT_EXECUTOR_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    result = mms_pi_executor.run_executor(
        config_root=config_root,
        pack_path=pack_path,
        target_repo=target_repo,
        explicit_models=explicit_models,
        artifact_dir=artifact_dir,
        max_concurrency=max_concurrency,
        timeout_seconds=timeout_seconds,
        idle_timeout_seconds=idle_timeout_seconds,
        validation_timeout_seconds=validation_timeout_seconds,
        max_output_bytes=max_output_bytes,
        max_repeated_events=max_repeated_events,
        max_patch_bytes=max_patch_bytes,
        executor_timeout_seconds=executor_timeout_seconds,
        dry_run=dry_run,
    )
    return build_parent_packet(result, source="live")


def _verify_admissible_candidate(row: Mapping[str, Any], pack: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    patch = row.get("patch") if isinstance(row.get("patch"), Mapping) else {}
    path_text = str(patch.get("path") or "").strip()
    path = Path(path_text).expanduser() if path_text else None
    payload = b""
    if (
        path is None
        or not path.is_absolute()
        or path.suffix != ".patch"
        or _has_symlink_component(path)
        or not path.is_file()
    ):
        reasons.append("patch_missing_or_unsafe")
    else:
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != str(patch.get("sha256") or ""):
            reasons.append("patch_hash_mismatch")
        if len(payload) != int(patch.get("bytes") or -1):
            reasons.append("patch_size_mismatch")
        max_bytes = int(pack.get("_max_patch_bytes") or 2 * 1024 * 1024)
        if len(payload) > max_bytes:
            reasons.append("patch_limit")
    claimed = sorted(str(item) for item in row.get("changed_files") or [])
    parsed = _patch_changed_files(payload.decode("utf-8", errors="replace")) if payload else []
    if not claimed or claimed != parsed:
        reasons.append("patch_changed_files_mismatch")
    scope_pack = {
        "writable_files": list(pack.get("writable_files") or []),
        "read_only_files": list(pack.get("read_only_files") or []),
        "forbidden_files": list(pack.get("forbidden_files") or []),
    }
    try:
        if mms_pi_executor._scope_violations(parsed, scope_pack):
            reasons.append("parent_scope_violation")
    except (mms_pi_executor.ExecutorError, KeyError, TypeError):
        reasons.append("invalid_pack_scope")
    if row.get("scope_violations"):
        reasons.append("recorded_scope_violation")
    if row.get("rejection_reasons"):
        reasons.append("recorded_rejection_reason")
    if row.get("validation_mutated_worktree"):
        reasons.append("validation_mutated_worktree")
    expected_validations = pack.get("validation_commands") or []
    validations = row.get("validation") if isinstance(row.get("validation"), list) else []
    if expected_validations and (
        len(validations) < len(expected_validations)
        or any(not isinstance(item, Mapping) or item.get("status") != "passed" for item in validations)
    ):
        reasons.append("validation_evidence_incomplete")
    return list(dict.fromkeys(reasons))


def _patch_changed_files(text: str) -> list[str]:
    paths: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("diff --git "):
            continue
        try:
            fields = shlex.split(line)
        except ValueError:
            return []
        if len(fields) != 4 or not fields[2].startswith("a/") or not fields[3].startswith("b/"):
            return []
        paths.add(fields[3][2:])
    return sorted(paths)


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False
