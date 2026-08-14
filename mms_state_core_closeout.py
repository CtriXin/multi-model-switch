"""MMS-managed runner-neutral closeout adapter for state-core.

TB-46 (workflow-reliability-batch9). This is the **first reference binding** of
the ratified ``docs/runner-adapter-hooks.md`` consume contract (state-core owns
canonical state + done-gate + ``completion_ref``; runner adapters only consume).

What this module is
-------------------
- A runner-neutral adapter: only **explicit** finish/closeout requests reach
  state-core ``closeout``. Ordinary turn ``Stop`` / ``SessionEnd`` / process
  exit are **never** wired here (see docs/STATE_CORE_CLOSEOUT_BINDING.md for the
  finish-vs-Stop boundary).
- Explicit opt-in: it runs only when an agent/human invokes it (the
  ``mms closeout`` subcommand, or directly as a script). It is **not** installed
  as a global hard hook on any session.
- Deterministic failure: missing task id / missing root / stale completion /
  done-gate rejection / CLI unavailable each produce a distinct non-zero exit;
  error/abort/timeout never infer ``done`` or ``blocked``. Only *identified*
  phase / done-gate rejections are reported as ``blocked``; a missing task,
  wrong root, or bad DIRECT_TO pointer is reported as ``error`` so a path
  failure can never masquerade as a business gate blocker.

Hard boundaries (frozen by the consume contract)
-------------------------------------------------
- Never reads or writes ``task-state.json`` directly; the only state write is
  state-core's own ``closeout`` (which the adapter shells out to).
- Never calls ``set --next-action``, ``set --runner``, or ``set --owner``.
- Never injects full task-state into a subagent (this adapter has no subagent
  surface; it is a single explicit finish call).

task_id / root resolution priority
-----------------------------------
1. explicit argv (``--task-id`` / ``--root``)
2. env (``STATE_CORE_TASK_ID`` / ``STATE_CORE_ROOT``)
3. handover pickup pointer (``.agent.local/continuity/pickup.json``
   ``active.task_id`` and top-level ``root``)
4. fail closed — never guessed from chat text.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Exit code policy (kept distinct so runner bindings can branch deterministically).
EXIT_OK = 0
EXIT_BLOCKED = 1            # closeout ran but done-gate / phase rejected it
EXIT_MISSING_SLOT = 2       # task_id or root could not be resolved
EXIT_CLI_UNAVAILABLE = 3    # state-core cli.py missing / no closeout subcommand
EXIT_ERROR = 4              # subprocess crash / timeout / unexpected

_COMPLETION_PREFIX = "completion:sha256:"
_PICKUP_DEFAULT_REL = ".agent.local/continuity/pickup.json"
_CLOSEOUT_TIMEOUT_DEFAULT = 60  # seconds


@dataclass
class CloseoutResult:
    """Machine-readable result of one closeout attempt.

    ``status`` is one of: ``done`` | ``blocked`` | ``missing_task_id`` |
    ``missing_root`` | ``cli_unavailable`` | ``verify_failed`` | ``error``.
    Only ``status == "done"`` carries a verified ``completion_ref``.
    """

    status: str
    task_id: str | None = None
    root: str | None = None
    completion_ref: str | None = None
    revision_sha256: str | None = None
    state_path: str | None = None
    verified: bool = False
    reason: str | None = None
    blockers: list[str] = field(default_factory=list)
    hint: str | None = None

    def exit_code(self) -> int:
        return {
            "done": EXIT_OK,
            "missing_task_id": EXIT_MISSING_SLOT,
            "missing_root": EXIT_MISSING_SLOT,
            "cli_unavailable": EXIT_CLI_UNAVAILABLE,
            "blocked": EXIT_BLOCKED,
            "verify_failed": EXIT_BLOCKED,
            "error": EXIT_ERROR,
        }.get(self.status, EXIT_ERROR)

    def to_compact_json(self) -> str:
        # keep booleans (verified flag is meaningful); drop only None / empty lists
        payload = {k: v for k, v in asdict(self).items() if v is not None and v != []}
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


# ──────────────────────────────────────────────────────────────────────────────
# Resolution helpers (pure, no I/O side effects beyond reading env / files)
# ──────────────────────────────────────────────────────────────────────────────

def resolve_state_core_cli(*, env: dict[str, str] | None = None,
                           override_root: str | None = None) -> Path | None:
    """Locate ``<state-core>/src/cli.py``.

    Priority: explicit argv override (authoritative, fail closed if it points
    nowhere) > ``STATE_CORE_ROOT`` env hint > ancestor walk. The ancestor walk
    works for both the main checkout and ``.worktrees/<slug>`` layouts because it
    walks up ancestors of *this file* and looks for a ``state-core`` sibling.
    Returns ``None`` (fail closed) if no candidate resolves.
    """
    env = env or dict(os.environ)
    # 1. explicit argv override is authoritative — never silently fall through.
    if override_root:
        cli = Path(override_root) / "src" / "cli.py"
        return cli if cli.is_file() else None
    # 2. env hint (best-effort; may be stale globally, so fall through on miss).
    env_root = env.get("STATE_CORE_ROOT", "").strip()
    if env_root:
        candidate = Path(env_root) / "src" / "cli.py"
        if candidate.is_file():
            return candidate
    # 3. ancestor walk (default discovery; handles main checkout + worktrees).
    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        candidate = ancestor / "state-core" / "src" / "cli.py"
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _read_pickup(pickup_path: Path) -> dict[str, Any] | None:
    try:
        if pickup_path.is_file():
            data = json.loads(pickup_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        return None
    return None


def resolve_task_id(*, argv_value: str | None = None,
                    env: dict[str, str] | None = None,
                    pickup: dict[str, Any] | None = None) -> str | None:
    """argv > env ``STATE_CORE_TASK_ID`` > pickup ``active.task_id`` (then
    ``checkpoint.task_id``). Never guesses from chat text."""
    if argv_value and argv_value.strip():
        return argv_value.strip()
    env = env or dict(os.environ)
    env_value = env.get("STATE_CORE_TASK_ID", "").strip()
    if env_value:
        return env_value
    if isinstance(pickup, dict):
        active = pickup.get("active")
        if isinstance(active, dict) and isinstance(active.get("task_id"), str):
            tid = active["task_id"].strip()
            if tid:
                return tid
        checkpoint = pickup.get("checkpoint")
        if isinstance(checkpoint, dict) and isinstance(checkpoint.get("task_id"), str):
            tid = checkpoint["task_id"].strip()
            if tid:
                return tid
    return None


def resolve_root(*, argv_value: str | None = None,
                 env: dict[str, str] | None = None,
                 pickup: dict[str, Any] | None = None) -> str | None:
    """argv > env ``STATE_CORE_ROOT`` > pickup ``root``."""
    if argv_value and argv_value.strip():
        return argv_value.strip()
    env = env or dict(os.environ)
    env_value = env.get("STATE_CORE_ROOT", "").strip()
    if env_value:
        return env_value
    if isinstance(pickup, dict) and isinstance(pickup.get("root"), str):
        root = pickup["root"].strip()
        if root:
            return root
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Core closeout
# ──────────────────────────────────────────────────────────────────────────────

def _classify_closeout_failure(stderr: str) -> tuple[str, str, list[str]]:
    """Classify a non-zero ``closeout`` stderr into (status, reason, blockers).

    Only *identified* phase / done-gate rejections are ``blocked``. Everything
    else (missing task-state.json, wrong root, bad DIRECT_TO pointer, JSON parse
    errors, unknown CLI errors) is ``error`` so a path/pointer failure can never
    masquerade as a business gate blocker (TB-46 host-review P1-2).
    """
    text = stderr or ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Resolution/corruption errors take precedence. A task id or path is
    # untrusted text and may itself contain words from the blocker grammar.
    path_error_patterns = (
        r"(?:error|FileNotFoundError): \[Errno 2\] No such file or directory: ['\"].*[/\\]\.state[/\\].*['\"]",
        r"error: pointer target does not exist: .+ \(from (?:DIRECT_TO|MOVED_TO) at .+\)",
        r"error: pointer (?:DIRECT_TO|MOVED_TO) at .+ has empty target",
        r"error: pointer chain detected at .+ — corruption",
        r"error: corruption: both task-state\.json and pointer exist at .+",
    )
    if any(
        re.fullmatch(pattern, line)
        for pattern in path_error_patterns
        for line in lines
    ):
        return "error", "task_or_root_unresolved", []

    # Only state-core's anchored stderr grammar is a business-gate rejection.
    if any(
        re.fullmatch(
            r"error: cannot reach done from .+; transition to verifying first",
            line,
        )
        for line in lines
    ):
        return "blocked", "phase_not_verifying", []

    blocker_line = next(
        (
            match.group(1)
            for line in lines
            if (match := re.fullmatch(
                r"error: cannot (?:advance to|reach) done; blockers: (.+)", line
            ))
        ),
        None,
    )
    if blocker_line is not None:
        after = blocker_line.strip()
        blockers: list[str] = []
        try:
            parsed = json.loads(after)
            if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                blockers = parsed
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(after)
                if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                    blockers = parsed
            except (SyntaxError, ValueError):
                pass
        # Never comma-split an opaque blocker: commas are valid detail text.
        if not blockers:
            blockers = [after]
        return "blocked", "done_gate_blockers", blockers
    # any other non-zero (unknown CLI error, state JSON corruption, etc.)
    return "error", "cli_rejected_unknown", [text.strip()] if text.strip() else []


def _run_cli(cli: Path, args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(cli), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def closeout_task(
    *,
    task_id: str,
    root: str,
    cli: Path | None = None,
    actor: str | None = None,
    at: str | None = None,
    timeout: int = _CLOSEOUT_TIMEOUT_DEFAULT,
) -> CloseoutResult:
    """Run one explicit closeout against state-core and read-back the result.

    The adapter performs no direct ``task-state.json`` access. A successful
    closeout is **always** followed by a ``verify-completion`` read-back — there
    is no opt-out, so no code path can emit ``status=done`` without a verified
    ``completion_ref`` (TB-46 consume contract; host-review P1-1).
    """
    resolved_cli = cli or resolve_state_core_cli()
    if resolved_cli is None:
        return CloseoutResult(
            status="cli_unavailable",
            task_id=task_id,
            root=root,
            hint="state-core src/cli.py not found; set STATE_CORE_ROOT or pass --state-core-root",
        )

    close_args = ["closeout", "--task-id", task_id, "--root", root]
    if actor:
        close_args += ["--actor", actor]
    if at:
        close_args += ["--at", at]

    try:
        proc = _run_cli(resolved_cli, close_args, timeout=timeout)
    except subprocess.TimeoutExpired:
        return CloseoutResult(status="error", task_id=task_id, root=root,
                              reason="timeout", hint=f"closeout exceeded {timeout}s")
    except (OSError, ValueError) as exc:
        return CloseoutResult(status="error", task_id=task_id, root=root,
                              reason="cli_invoke_failed", hint=str(exc))

    if proc.returncode != 0:
        status, reason, blockers = _classify_closeout_failure(proc.stderr)
        if status == "blocked":
            return CloseoutResult(
                status="blocked",
                task_id=task_id,
                root=root,
                reason=reason,
                blockers=blockers,
                hint="phase preserved; resolve done-gate blockers or advance to verifying before retrying",
            )
        # path / pointer / CLI exception — NOT a business gate blocker
        return CloseoutResult(
            status="error",
            task_id=task_id,
            root=root,
            reason=reason,
            hint=(
                "no state inferred; check task id / root / DIRECT_TO pointer "
                f"(state-core stderr: {proc.stderr.strip() or 'empty'})"
            ),
        )

    # success path: parse + verify completion_ref
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return CloseoutResult(status="error", task_id=task_id, root=root,
                              reason="invalid_closeout_stdout",
                              hint=f"closeout exited 0 but stdout was not JSON: {exc}")
    if not isinstance(payload, dict):
        return CloseoutResult(status="error", task_id=task_id, root=root,
                              reason="invalid_closeout_stdout",
                              hint="closeout exited 0 but stdout was not a JSON object")

    completion_ref = payload.get("completion_ref")
    if not isinstance(completion_ref, str) or not completion_ref.startswith(_COMPLETION_PREFIX):
        return CloseoutResult(status="error", task_id=task_id, root=root,
                              reason="invalid_completion_ref",
                              hint="closeout succeeded but emitted no valid completion_ref")

    verify_args = ["verify-completion", "--task-id", task_id, "--root", root,
                   "--completion-ref", completion_ref]
    try:
        vproc = _run_cli(resolved_cli, verify_args, timeout=timeout)
    except subprocess.TimeoutExpired:
        return CloseoutResult(status="verify_failed", task_id=task_id, root=root,
                              completion_ref=completion_ref,
                              reason="verify_timeout")
    except (OSError, ValueError) as exc:
        return CloseoutResult(status="verify_failed", task_id=task_id, root=root,
                              completion_ref=completion_ref,
                              reason="verify_invoke_failed", hint=str(exc))

    try:
        vpayload = json.loads(vproc.stdout)
    except json.JSONDecodeError as exc:
        return CloseoutResult(
            status="verify_failed",
            task_id=task_id,
            root=root,
            completion_ref=completion_ref,
            reason="invalid_verify_stdout",
            blockers=[f"verify-completion stdout was not JSON: {exc}"],
        )

    if vproc.returncode != 0:
        errors = vpayload.get("errors", []) if isinstance(vpayload, dict) else []
        return CloseoutResult(
            status="verify_failed",
            task_id=task_id,
            root=root,
            completion_ref=completion_ref,
            reason="completion_ref_did_not_read_back",
            blockers=[str(e) for e in errors] or ["verify-completion returned non-zero"],
        )

    contract_errors: list[str] = []
    if not isinstance(vpayload, dict):
        contract_errors.append("verify-completion payload must be an object")
    else:
        if vpayload.get("status") != "passed":
            contract_errors.append("verify-completion status is not passed")
        if vpayload.get("task_id") != task_id:
            contract_errors.append("verify-completion task_id mismatch")
        if vpayload.get("completion_ref") != completion_ref:
            contract_errors.append("verify-completion completion_ref mismatch")
        errors = vpayload.get("errors")
        if errors not in (None, []):
            contract_errors.append("verify-completion returned errors")
    if contract_errors:
        return CloseoutResult(
            status="verify_failed",
            task_id=task_id,
            root=root,
            completion_ref=completion_ref,
            reason="verify_payload_contract_failed",
            blockers=contract_errors,
        )

    return CloseoutResult(
        status="done",
        task_id=task_id,
        root=root,
        completion_ref=completion_ref,
        revision_sha256=payload.get("revision_sha256"),
        state_path=payload.get("state_path"),
        verified=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# MMS subcommand binding (``mms closeout``) + standalone CLI
# ──────────────────────────────────────────────────────────────────────────────

def _build_parser(command_name: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=f"{command_name} closeout",
        description=(
            "Explicit opt-in closeout: advance a state-core task through the "
            "done-gate, read-back completion_ref. Only call this on an explicit "
            "finish/closeout request — never on ordinary Stop/SessionEnd."
        ),
    )
    p.add_argument("--task-id", help="state-core task id (or STATE_CORE_TASK_ID env / pickup)")
    p.add_argument("--root", help="state-core state root, i.e. the task's repo (or STATE_CORE_ROOT env / pickup.root)")
    p.add_argument("--state-core-root", help="state-core repo root containing src/cli.py (or STATE_CORE_ROOT env)")
    p.add_argument("--actor", help="actor recorded on the completion receipt")
    p.add_argument("--at", help="ISO timestamp recorded on the completion receipt")
    p.add_argument("--pickup", default=_PICKUP_DEFAULT_REL,
                   help=f"handover pickup.json path (default: {_PICKUP_DEFAULT_REL})")
    p.add_argument("--timeout", type=int, default=_CLOSEOUT_TIMEOUT_DEFAULT,
                   help=f"per-CLI-invocation timeout in seconds (default {_CLOSEOUT_TIMEOUT_DEFAULT})")
    p.add_argument("--json", dest="as_json", action="store_true", default=True,
                   help="emit compact machine-readable JSON (default)")
    p.add_argument("--no-json", dest="as_json", action="store_false",
                   help="emit a short human-readable line instead of JSON")
    return p


def _load_pickup(pickup_arg: str, root: str | None) -> dict[str, Any] | None:
    pickup_path = Path(pickup_arg)
    if not pickup_path.is_absolute():
        base = Path(root) if root else Path.cwd()
        pickup_path = base / pickup_path
    return _read_pickup(pickup_path)


def handle_closeout_command(argv: list[str], *, command_name: str = "mms") -> int:
    """``mms closeout`` reference binding entry point.

    Resolves task_id/root (argv > env > pickup; fail closed), then delegates to
    :func:`closeout_task`. Emits compact JSON to stdout on every path so runner
    bindings can parse deterministically; a short human hint goes to stderr.
    """
    args = _build_parser(command_name).parse_args(argv)

    cli_override = args.state_core_root
    resolved_cli = resolve_state_core_cli(override_root=cli_override)
    # Pre-flight: fail closed with a precise status before touching state.
    if resolved_cli is None:
        result = CloseoutResult(
            status="cli_unavailable",
            hint="state-core src/cli.py not found; set STATE_CORE_ROOT or pass --state-core-root",
        )
        _emit(result, args.as_json)
        return result.exit_code()

    pickup = _load_pickup(args.pickup, args.root)
    task_id = resolve_task_id(argv_value=args.task_id, pickup=pickup)
    root = resolve_root(argv_value=args.root, pickup=pickup)

    if not task_id:
        result = CloseoutResult(
            status="missing_task_id",
            hint="pass --task-id, set STATE_CORE_TASK_ID, or provide a pickup.json with active.task_id",
        )
        _emit(result, args.as_json)
        return result.exit_code()
    if not root:
        result = CloseoutResult(
            status="missing_root",
            task_id=task_id,
            hint="pass --root, set STATE_CORE_ROOT, or provide a pickup.json with root",
        )
        _emit(result, args.as_json)
        return result.exit_code()

    result = closeout_task(
        task_id=task_id,
        root=root,
        cli=resolved_cli,
        actor=args.actor,
        at=args.at,
        timeout=args.timeout,
    )
    _emit(result, args.as_json)
    return result.exit_code()


def _emit(result: CloseoutResult, as_json: bool) -> None:
    if as_json:
        sys.stdout.write(result.to_compact_json() + "\n")
    else:
        if result.status == "done":
            sys.stdout.write(
                f"done: {result.task_id} completion_ref={result.completion_ref} "
                f"verified={result.verified}\n"
            )
        else:
            label = {
                "blocked": "blocked (phase preserved)",
                "verify_failed": "closeout ok but completion_ref did not read back",
                "missing_task_id": "missing task_id (fail closed)",
                "missing_root": "missing root (fail closed)",
                "cli_unavailable": "state-core CLI unavailable",
                "error": "error (no state inferred)",
            }.get(result.status, result.status)
            sys.stdout.write(f"{result.status}: {label}\n")
    if result.status != "done" and result.hint:
        sys.stderr.write(f"hint: {result.hint}\n")
    if result.status not in ("done",) and result.blockers:
        sys.stderr.write("blockers:\n")
        for b in result.blockers:
            sys.stderr.write(f"  - {b}\n")


def main(argv: list[str] | None = None) -> int:
    return handle_closeout_command(sys.argv[1:] if argv is None else argv,
                                   command_name=os.environ.get("MMS_COMMAND_NAME", "mms"))


if __name__ == "__main__":
    raise SystemExit(main())
