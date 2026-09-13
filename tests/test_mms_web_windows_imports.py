"""The Pilot web import graph must not require POSIX-only modules on Windows.

Unconditional ``import fcntl`` in ``mms_web/bots.py`` and ``mms_web/bot_memory.py``
broke ``mms web start`` on Windows with ModuleNotFoundError (Windows acceptance
phase 8). Locks must go through ``mms_web/file_lock.py``, which carries the
msvcrt branch. These tests pin that contract:

* no bare top-level fcntl import anywhere in the web import graph;
* the full server import chain loads in a fresh interpreter;
* the Bot store and memory locks exercise the shim on every platform.
"""
import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORT_GRAPH = sorted((ROOT / "mms_web").rglob("*.py")) + [
    ROOT / name
    for name in ("mms", "mms_runtime.py", "mms_platform.py", "mms_state_io.py", "mms_core.py")
    if (ROOT / name).is_file()
]


def _bare_fcntl_imports(path: Path) -> list[int]:
    """Top-level fcntl imports not guarded by try/except or a platform branch."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = []

    def visit(statements, guarded):
        for node in statements:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                if any(name.split(".")[0] == "fcntl" for name in names) and not guarded:
                    offenders.append(node.lineno)
            elif isinstance(node, ast.Try):
                visit(node.body, True)
            elif isinstance(node, ast.If):
                # Platform branches (os.name / sys.platform) are explicit guards.
                visit(node.body, True)
                visit(node.orelse, True)
            # Function/class bodies hold runtime imports, not import-time blockers.

    visit(tree.body, False)
    return offenders


def test_no_bare_fcntl_import_in_web_import_graph():
    failures = {
        str(path.relative_to(ROOT)): lines
        for path in IMPORT_GRAPH
        if (lines := _bare_fcntl_imports(path))
    }
    assert not failures, f"unconditional fcntl imports fail on Windows: {failures}"


def test_pilot_server_import_chain_loads_in_a_fresh_interpreter():
    code = (
        "import mms_web.server, mms_web.bots, mms_web.bot_memory, mms_web.__main__;"
        "print('IMPORT_CHAIN_OK')"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    result = subprocess.run([sys.executable, "-P", "-c", code], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=60)
    assert "IMPORT_CHAIN_OK" in result.stdout, result.stderr[-2000:]


def test_bot_store_and_memory_locks_use_the_cross_platform_shim(tmp_path):
    """Both stores must lock through mms_web.file_lock, not fcntl directly."""
    from mms_web import bots, bot_memory

    assert bots.flock is bot_memory.flock
    assert bots.flock.__module__ == "mms_web.file_lock"

    store = bot_memory.BotMemoryStore(tmp_path)
    store.remember("bot_probe", "windows lock probe")
    notes = store.get("bot_probe")["notes"]
    assert notes[0]["content"] == "windows lock probe" and notes[0]["kind"] == "fact"
    store.delete("bot_probe")
    assert not (tmp_path / "bots" / "memory" / "bot_probe").exists()
