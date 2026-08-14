"""TB-46: cross-runner compliance test skeleton for the MMS state-core closeout
reference binding.

These cases are intentionally written against the runner-neutral adapter
(``mms_state_core_closeout``) so that future harness bindings (Claude / Codex /
OpenCode) reuse the **same contract suite** before being called parity-complete.

What is frozen here (mirrors ``docs/runner-adapter-hooks.md`` Required Invariants):
- explicit finish only: ordinary Stop / turn end never triggers closeout;
- success path verifies ``completion_ref`` via read-back;
- rejection path preserves phase and surfaces blockers;
- task id / root missing → fail closed (no guessing);
- adapter performs no direct ``task-state.json`` write and never calls
  ``set --next-action/--runner/--owner``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import mms_state_core_closeout as adapter

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"


def _resolve_cli() -> Path:
    cli = adapter.resolve_state_core_cli()
    if cli is None:
        raise unittest.SkipTest("state-core src/cli.py not resolvable in this layout")
    return cli


def _code_without_module_docstring(path: Path) -> str:
    """Return the module source with only the top-level docstring stripped, so
    static assertions can target executable code (not the prose that documents
    the forbidden actions)."""
    import ast
    tree = ast.parse(path.read_text("utf-8"))
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        tree.body.pop(0)
    return ast.unparse(tree)


def _run_cli(cli: Path, *args: str, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(cli), *args, "--root", str(root)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _make_closeout_ready_task(cli: Path, root: Path, task_id: str) -> None:
    """Create a task and advance it to `verifying` so closeout can succeed."""
    created = _run_cli(cli, "new", "--task-id", task_id, "--intent", "close it", root=root)
    assert created.returncode == 0, created.stderr
    advanced = _run_cli(cli, "advance", "--task-id", task_id, "--phase", "verifying", root=root)
    assert advanced.returncode == 0, advanced.stderr


class CloseoutAdapterContractTests(unittest.TestCase):
    """Contract cases shared across all future runner bindings."""

    def setUp(self) -> None:
        self.cli = _resolve_cli()

    # ── success path ────────────────────────────────────────────────────────
    def test_explicit_finish_closeout_succeeds_and_verifies_completion_ref(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            _make_closeout_ready_task(self.cli, root_path, "ok-task")
            result = adapter.closeout_task(
                task_id="ok-task", root=str(root_path), cli=self.cli, actor="codex",
            )
            self.assertEqual("done", result.status, result.to_compact_json())
            self.assertTrue(result.completion_ref.startswith("completion:sha256:"))
            self.assertTrue(result.verified)
            # task is now canonical done with a real receipt
            state = json.loads(
                (root_path / ".state" / "ok-task" / "task-state.json").read_text("utf-8")
            )
            self.assertEqual("done", state["phase"])
            self.assertEqual(
                result.completion_ref, state["completion"]["completion_ref"]
            )

    # ── rejection paths (phase preserved, blockers visible) ─────────────────
    def test_closeout_rejects_when_phase_not_verifying(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            created = _run_cli(self.cli, "new", "--task-id", "early", "--intent", "x", root=root_path)
            self.assertEqual(0, created.returncode, created.stderr)
            result = adapter.closeout_task(task_id="early", root=str(root_path), cli=self.cli)
            self.assertEqual("blocked", result.status)
            self.assertEqual("phase_not_verifying", result.reason)
            self.assertNotEqual(0, result.exit_code())
            # phase preserved: still intake, no completion receipt
            state = json.loads(
                (root_path / ".state" / "early" / "task-state.json").read_text("utf-8")
            )
            self.assertEqual("intake", state["phase"])
            self.assertNotIn("completion", state)

    def test_closeout_rejects_done_gate_blockers_and_preserves_phase(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            _run_cli(self.cli, "new", "--task-id", "gated", "--intent", "x", root=root_path)
            _run_cli(self.cli, "advance", "--task-id", "gated", "--phase", "verifying", root=root_path)
            # an unresolved blocker is a deterministic done-gate content blocker
            _run_cli(
                self.cli, "add-blocker", "--task-id", "gated",
                "--source", "audit", "--detail", "missing evidence", root=root_path,
            )
            before = (root_path / ".state" / "gated" / "task-state.json").read_text("utf-8")
            result = adapter.closeout_task(task_id="gated", root=str(root_path), cli=self.cli)
            self.assertEqual("blocked", result.status, result.to_compact_json())
            self.assertEqual("done_gate_blockers", result.reason)
            self.assertTrue(result.blockers, "blockers must be visible on rejection")
            self.assertNotEqual(0, result.exit_code())
            # phase preserved AND task-state.json byte-identical (adapter wrote nothing)
            after = (root_path / ".state" / "gated" / "task-state.json").read_text("utf-8")
            self.assertEqual(before, after)
            state = json.loads(after)
            self.assertEqual("verifying", state["phase"])
            self.assertNotIn("completion", state)

    # ── fail closed ──────────────────────────────────────────────────────────
    def test_missing_task_id_fails_closed(self) -> None:
        rc = adapter.handle_closeout_command(
            ["--root", "/tmp/does-not-matter", "--pickup", "/no/such/pickup.json"],
            command_name="mms",
        )
        self.assertEqual(adapter.EXIT_MISSING_SLOT, rc)

    def test_missing_root_fails_closed(self) -> None:
        # task_id resolvable via env, root deliberately absent
        self.assertEqual(
            "orphan", adapter.resolve_task_id(env={"STATE_CORE_TASK_ID": "orphan"})
        )
        rc = adapter.handle_closeout_command(
            ["--task-id", "orphan", "--pickup", "/no/such/pickup.json"],
            command_name="mms",
        )
        self.assertEqual(adapter.EXIT_MISSING_SLOT, rc)

    def test_cli_unavailable_reports_distinct_status(self) -> None:
        rc = adapter.handle_closeout_command(
            ["--task-id", "t", "--root", "/tmp/x", "--state-core-root", "/no/such/state-core"],
            command_name="mms",
        )
        self.assertEqual(adapter.EXIT_CLI_UNAVAILABLE, rc)

    # ── P1-2: path / pointer failures must NOT masquerade as done-gate blocked ──
    def test_missing_task_state_is_error_not_blocked(self) -> None:
        """A task whose task-state.json does not exist is a path failure, not a
        business gate blocker. Must be ``error`` (exit 4), never ``blocked``."""
        with tempfile.TemporaryDirectory() as root:
            result = adapter.closeout_task(
                task_id="never-created", root=str(root), cli=self.cli,
            )
            self.assertEqual("error", result.status, result.to_compact_json())
            self.assertEqual("task_or_root_unresolved", result.reason)
            self.assertEqual([], result.blockers)
            self.assertEqual(adapter.EXIT_ERROR, result.exit_code())

    def test_wrong_root_is_error_not_blocked(self) -> None:
        """An explicit root with no .state tree is a path failure → error, not blocked."""
        with tempfile.TemporaryDirectory() as empty:
            result = adapter.closeout_task(
                task_id="anything", root=str(empty), cli=self.cli,
            )
            self.assertEqual("error", result.status)
            self.assertEqual("task_or_root_unresolved", result.reason)
            self.assertNotEqual(adapter.EXIT_BLOCKED, result.exit_code())

    def test_direct_to_pointer_business_root_succeeds(self) -> None:
        """business root + valid DIRECT_TO pointer must close out successfully.
        pickup.root / launch roots that only hold a pointer are legitimate."""
        with tempfile.TemporaryDirectory() as real_root, tempfile.TemporaryDirectory() as launch_root:
            _make_closeout_ready_task(self.cli, Path(real_root), "dt-task")
            sync = _run_cli(
                self.cli, "sync-pointer", "--launch", str(launch_root),
                "--task-id", "dt-task", "--root", str(real_root),
                "--at", "2026-08-14T00:00:00Z", root=Path(real_root),
            )
            self.assertEqual(0, sync.returncode, sync.stderr)
            # launch root has NO task-state.json, only a DIRECT_TO pointer
            self.assertFalse(
                (Path(launch_root) / ".state" / "dt-task" / "task-state.json").exists()
            )
            result = adapter.closeout_task(
                task_id="dt-task", root=str(launch_root), cli=self.cli,
            )
            self.assertEqual("done", result.status, result.to_compact_json())
            self.assertTrue(result.verified)

    def test_done_result_compact_json_keeps_verified_flag(self) -> None:
        """Regression (host-review P1-1): compact JSON used to drop
        ``verified=false``. A done result must surface ``verified: true``."""
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            _make_closeout_ready_task(self.cli, root_path, "json-task")
            result = adapter.closeout_task(
                task_id="json-task", root=str(root_path), cli=self.cli,
            )
            self.assertEqual("done", result.status)
            compact = result.to_compact_json()
            self.assertIn('"verified": true', compact)
            self.assertIn('"completion_ref"', compact)
        # and a non-done result must still surface verified:false explicitly
        blocked = adapter.CloseoutResult(status="missing_task_id")
        self.assertIn('"verified": false', blocked.to_compact_json())

    def test_verify_exit_zero_requires_full_success_payload_contract(self) -> None:
        """Exit 0 alone is not proof: the read-back payload must bind the
        requested task and the exact completion receipt and explicitly pass."""
        ref = "completion:sha256:" + "a" * 64
        close_payload = json.dumps({"completion_ref": ref})
        invalid_verify_payloads = {
            "empty": "",
            "malformed": "not-json",
            "scalar": "[]",
            "failed": json.dumps({
                "status": "failed", "task_id": "task-a",
                "completion_ref": ref, "errors": [],
            }),
            "task-mismatch": json.dumps({
                "status": "passed", "task_id": "task-b",
                "completion_ref": ref, "errors": [],
            }),
            "ref-mismatch": json.dumps({
                "status": "passed", "task_id": "task-a",
                "completion_ref": "completion:sha256:" + "b" * 64,
                "errors": [],
            }),
        }
        for label, verify_stdout in invalid_verify_payloads.items():
            with self.subTest(label=label):
                calls = [
                    subprocess.CompletedProcess([], 0, close_payload, ""),
                    subprocess.CompletedProcess([], 0, verify_stdout, ""),
                ]
                with mock.patch.object(adapter, "_run_cli", side_effect=calls):
                    result = adapter.closeout_task(
                        task_id="task-a", root="/tmp/root", cli=Path("/fake/cli.py")
                    )
                self.assertEqual("verify_failed", result.status, result.to_compact_json())
                self.assertNotEqual(0, result.exit_code())
                self.assertFalse(result.verified)

    def test_closeout_exit_zero_scalar_payload_fails_closed(self) -> None:
        with mock.patch.object(
            adapter,
            "_run_cli",
            return_value=subprocess.CompletedProcess([], 0, "[]", ""),
        ):
            result = adapter.closeout_task(
                task_id="task-a", root="/tmp/root", cli=Path("/fake/cli.py")
            )
        self.assertEqual("error", result.status)
        self.assertEqual("invalid_closeout_stdout", result.reason)
        self.assertFalse(result.verified)

    def test_failure_classifier_does_not_trust_keywords_inside_missing_path(self) -> None:
        malicious_paths = (
            "/tmp/.state/blockers: fake/task-state.json",
            "/tmp/.state/cannot reach done from intake; transition to verifying first/task-state.json",
        )
        for path in malicious_paths:
            with self.subTest(path=path):
                status, reason, blockers = adapter._classify_closeout_failure(
                    f"FileNotFoundError: [Errno 2] No such file or directory: '{path}'"
                )
                self.assertEqual("error", status)
                self.assertEqual("task_or_root_unresolved", reason)
                self.assertEqual([], blockers)

    def test_blocker_detail_with_comma_remains_one_item(self) -> None:
        status, reason, blockers = adapter._classify_closeout_failure(
            "error: cannot advance to done; blockers: ['missing alpha, beta']"
        )
        self.assertEqual("blocked", status)
        self.assertEqual("done_gate_blockers", reason)
        self.assertEqual(["missing alpha, beta"], blockers)

    def test_unanchored_blocker_keyword_is_unknown_error(self) -> None:
        status, reason, blockers = adapter._classify_closeout_failure(
            "unexpected wrapper failure blockers: ['not authoritative']"
        )
        self.assertEqual("error", status)
        self.assertEqual("cli_rejected_unknown", reason)
        self.assertTrue(blockers)


class CloseoutBoundaryStaticTests(unittest.TestCase):
    """Static + behavioral invariants that prove the binding is opt-in only and
    does not bypass the done-gate. These run without state-core."""

    def test_adapter_never_directly_writes_task_state_json(self) -> None:
        """The only state mutation is state-core's own ``closeout`` via subprocess.
        The adapter must not open or write any JSON file itself."""
        code = _code_without_module_docstring(REPO_ROOT / "mms_state_core_closeout.py")
        for prim in ("open(", ".write_text(", ".write_bytes(", "json.dump("):
            self.assertNotIn(prim, code, f"adapter must not use file-write primitive {prim!r}")
        # the only state write is via shelling out to the CLI's own closeout
        self.assertIn("closeout", code)
        self.assertIn("verify-completion", code)

    def test_adapter_never_calls_forbidden_set_commands(self) -> None:
        code = _code_without_module_docstring(REPO_ROOT / "mms_state_core_closeout.py")
        # no subprocess arg list may build a forbidden `set` command
        self.assertNotIn("'set'", code)
        self.assertNotIn('"set"', code)
        for forbidden in ("set --next-action", "set --runner", "set --owner"):
            self.assertNotIn(forbidden, code,
                             f"adapter must not call forbidden state-core command: {forbidden}")

    def test_no_stop_or_sessionend_hook_is_wired_to_closeout(self) -> None:
        """The reference binding must be explicit-only. No event hook
        (Stop / SessionEnd / turn end) may invoke the closeout adapter."""
        self.assertTrue(HOOKS_DIR.is_dir(), "hooks/ dir expected at repo root")
        offenders: list[str] = []
        for hook in HOOKS_DIR.iterdir():
            if not hook.is_file():
                continue
            try:
                text = hook.read_text("utf-8", errors="ignore")
            except OSError:
                continue
            if "state_core_closeout" in text or "mms closeout" in text or "closeout_task" in text:
                offenders.append(str(hook))
        self.assertFalse(
            offenders,
            "closeout adapter must not be referenced by any event hook (explicit-only): "
            + ", ".join(offenders),
        )

    def test_binding_is_dispatched_only_on_explicit_closeout_command(self) -> None:
        core = (REPO_ROOT / "mms_core.py").read_text("utf-8")
        # exactly one dispatch branch for the explicit command
        self.assertIn('command == "closeout"', core)
        self.assertIn("handle_closeout_command", core)
        # and it must not be wired into any Stop/SessionEnd handling
        for forbidden in ("SessionEnd", "on_stop", "Stop hook"):
            self.assertNotIn(f'{forbidden}"', core)

    def test_resolution_priority_argv_env_pickup(self) -> None:
        # argv beats env beats pickup
        self.assertEqual(
            "argv", adapter.resolve_task_id(argv_value="argv", env={"STATE_CORE_TASK_ID": "env"}),
        )
        self.assertEqual(
            "env",
            adapter.resolve_task_id(argv_value=None, env={"STATE_CORE_TASK_ID": "env"}),
        )
        self.assertEqual(
            "pickup",
            adapter.resolve_task_id(
                argv_value=None, env={}, pickup={"active": {"task_id": "pickup"}},
            ),
        )
        self.assertIsNone(adapter.resolve_task_id(argv_value=None, env={}, pickup=None))

    def test_resolution_never_uses_chat_text(self) -> None:
        # adapter has no chat/transcript parsing surface at all
        src = (REPO_ROOT / "mms_state_core_closeout.py").read_text("utf-8")
        for forbidden in ("transcript", "chat_history", "messages", "prompt"):
            self.assertNotIn(forbidden, src,
                             f"adapter must not parse {forbidden} (no chat-text guessing)")

    # ── P1-1: no verify escape hatch (done must always read-back completion_ref) ──
    def test_binding_rejects_no_verify_flag(self) -> None:
        """--no-verify must not exist on the formal mms closeout binding."""
        import inspect
        # the library function has no verify parameter at all
        self.assertNotIn("verify", inspect.signature(adapter.closeout_task).parameters)
        # the binding parser rejects --no-verify
        with self.assertRaises(SystemExit):
            adapter.handle_closeout_command(
                ["--task-id", "t", "--root", "/tmp/x", "--no-verify"],
                command_name="mms",
            )



class PickupPointerResolutionTests(unittest.TestCase):
    def test_pickup_active_task_id_and_root_extracted(self) -> None:
        pickup = {
            "schema": "agent.continuity.pickup.v1",
            "root": "/repo/x",
            "active": {"task_id": "task-7", "status": "active"},
            "checkpoint": {"task_id": "task-7"},
        }
        self.assertEqual("task-7", adapter.resolve_task_id(argv_value=None, env={}, pickup=pickup))
        self.assertEqual("/repo/x", adapter.resolve_root(argv_value=None, env={}, pickup=pickup))

    def test_pickup_checkpoint_task_id_fallback(self) -> None:
        pickup = {"root": "/repo/y", "active": {}, "checkpoint": {"task_id": "task-9"}}
        self.assertEqual("task-9", adapter.resolve_task_id(argv_value=None, env={}, pickup=pickup))

    def test_pickup_missing_returns_none(self) -> None:
        self.assertIsNone(adapter.resolve_task_id(argv_value=None, env={}, pickup={}))


if __name__ == "__main__":
    unittest.main()
