"""Driver building blocks for MMS Web rich sessions.

Nothing in this package imports MMS core modules at import time. Real-process
launch goes through ``launch_bridge`` which fails closed until the MMS seam is
available. Tests inject their own process or driver factory.
"""

from __future__ import annotations

import subprocess


class PipedProcessLauncher:
    """Launch a harness child with piped stdin/stdout/stderr (binary mode).

    Binary pipes + explicit LF framing keep the RPC reader protocol-compliant
    (no unicode line separators, no CRLF translation).
    """

    def popen(self, cmd, *, env, cwd=None) -> subprocess.Popen:
        return subprocess.Popen(
            list(cmd),
            env=dict(env),
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )


class DriverClosedError(RuntimeError):
    """The harness child is no longer connected."""


class RpcTimeoutError(RuntimeError):
    """A JSONL command did not get its response in time."""


class LaunchSeamUnavailable(RuntimeError):
    """The MMS launcher seam needed for a real launch is not available."""
