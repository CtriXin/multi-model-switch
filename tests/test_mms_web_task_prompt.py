"""The task the remote-access row hands to an agent.

Its whole job is to make the agent ask two questions and stop. That held
against seven models across seven vendors, and what made it hold was the
shape: the instruction first, the questions next, everything else fenced off
behind a line saying it is background. Reorder it and the measurement stops
meaning anything, so the shape is pinned here.

The live version of this check is `scripts/probe_task_prompt.py`, which calls
real models. It costs money and needs configured channels, so it is never run
from the suite.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_the_task_keeps_the_shape_that_was_measured():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for frontend contract tests")
    version = subprocess.check_output([node, "--version"], text=True).strip()
    major, minor = (int(part) for part in version[1:].split(".")[:2])
    if (major, minor) < (22, 6):
        pytest.skip("Node 22.6+ required for TypeScript source execution")
    result = subprocess.run(
        [node, "--experimental-strip-types", "--test",
         "tests/frontend/tunnel-task.test.ts"],
        cwd=ROOT, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_live_probe_never_runs_itself():
    """It calls paid models. Nothing may import it into a test run."""
    probe = ROOT / "scripts" / "probe_task_prompt.py"
    source = probe.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in source
    # The suite collects tests/, so a probe that ran on import would bill the
    # user for every `pytest` invocation.
    assert not any(line.startswith("main(") for line in source.splitlines())


def test_the_probe_reads_the_same_task_the_button_sends():
    """A probe against a copy of the wording measures nothing."""
    probe = (ROOT / "scripts" / "probe_task_prompt.py").read_text(encoding="utf-8")
    assert "apps/mms-web/src/tunnel-task.ts" in probe
    component = (ROOT / "apps/mms-web/src/RemoteAccess.tsx").read_text(encoding="utf-8")
    assert 'from "./tunnel-task"' in component
    assert "tunnelTask(" in component
