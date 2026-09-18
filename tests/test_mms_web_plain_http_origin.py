"""What the browser gives up outside a secure context, and what must not break.

A phone reaching this machine at ``http://192.168.x.x`` is not in a secure
context: only HTTPS and ``localhost`` are. The APIs that gates off are not
optional extras for Pilot, so this pins the two that mattered.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB_SRC = ROOT / "apps" / "mms-web" / "src"


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for frontend contract tests")
    version = subprocess.check_output([node, "--version"], text=True).strip()
    major, minor = (int(part) for part in version[1:].split(".")[:2])
    if (major, minor) < (22, 6):
        pytest.skip("Node 22.6+ required for TypeScript source execution")
    return node


def test_request_ids_survive_a_plain_http_origin():
    """``crypto.randomUUID`` is secure-context only; requestId cannot be."""
    result = subprocess.run(
        [_node(), "--experimental-strip-types", "--test",
         "tests/frontend/request-id.test.ts"],
        cwd=ROOT, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_nothing_reaches_for_randomuuid_directly():
    """Every generated id must go through the fallback.

    A direct ``crypto.randomUUID()`` throws on a plain-http origin. In a write
    path that failed every mutation before the request was built; in the guided
    tour, the quote-to-composer flow and template import it crashed the click.
    """
    offenders = []
    for path in sorted(WEB_SRC.rglob("*.ts")) + sorted(WEB_SRC.rglob("*.tsx")):
        if path.name == "request-id.ts":
            continue
        text = path.read_text(encoding="utf-8")
        if "crypto.randomUUID" in text:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == [], (
        "use newRequestId() from request-id.ts instead: " + ", ".join(offenders))


def test_clipboard_writes_cannot_throw_on_a_plain_http_origin():
    """``navigator.clipboard`` is absent there, so reading .writeText off it
    throws synchronously and a promise .catch never sees it."""
    offenders = []
    for path in sorted(WEB_SRC.rglob("*.ts")) + sorted(WEB_SRC.rglob("*.tsx")):
        if path.name == "clipboard.ts":
            continue
        text = path.read_text(encoding="utf-8")
        # Reading the event's own clipboardData in a paste handler is fine;
        # only navigator.clipboard is gated by the secure context.
        if re.search(r"navigator\s*\.\s*clipboard", text):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == [], (
        "use copyText() from clipboard.ts instead: " + ", ".join(offenders))


def test_touch_devices_can_reach_the_row_and_folder_menus():
    """Both only appeared on :hover, which a phone never produces."""
    blocks = []
    for path in sorted(WEB_SRC.glob("*.css")):
        text = path.read_text(encoding="utf-8")
        blocks += re.findall(r"@media \(hover: none\) \{(.*?)\n\}", text, re.S)
    assert blocks, "a (hover: none) block must reveal what hover would have"
    joined = "\n".join(blocks)
    assert ".session-row-menu" in joined and "visibility: visible" in joined
    assert ".workspace-row-actions" in joined and "pointer-events: auto" in joined
