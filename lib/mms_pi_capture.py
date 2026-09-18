"""Opt-in request capture for Pi launches.

Diagnostic surface for issue #97: mmf-launched Pi intermittently gets a 400 from
the relay complaining about a raw control byte inside a JSON string literal.
Synthetic replays never reproduce it, so the only way to settle whether Pi wrote
the bad bytes is to record what leaves its socket during a real session.

Default-off. With ``MMS_PI_CAPTURE_PROXY`` unset nothing here touches the launch
path: the generated ``models.json`` and the launch environment are unchanged.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from mms_state_io import atomic_write_text

CAPTURE_ENV = "MMS_PI_CAPTURE_PROXY"
CAPTURE_DIR_ENV = "MMS_PI_CAPTURE_DIR"
CAPTURE_ENDPOINT_ENV = "MMS_PI_CAPTURE_ENDPOINT"
CAPTURE_PATH_PREFIX = "/__mms_capture__"

_STARTUP_TIMEOUT_SECONDS = 8.0
_STARTUP_POLL_SECONDS = 0.1


def capture_setting(env=None):
    """Return the raw opt-in value, or "" when capture is disabled."""
    source = env if isinstance(env, dict) else os.environ
    value = str(source.get(CAPTURE_ENV) or "").strip()
    if value.lower() in ("", "0", "false", "off", "no"):
        return ""
    return value


def encode_origin(origin):
    """Encode an upstream origin so it can ride inside the proxied URL path."""
    raw = str(origin or "").strip().rstrip("/")
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_origin(token):
    """Inverse of :func:`encode_origin`."""
    text = str(token or "").strip()
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("ascii")).decode("utf-8")


def capture_url(endpoint, base_url):
    """Rewrite one provider baseUrl so it resolves to the capture proxy."""
    parsed = urlsplit(str(base_url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    origin = f"{parsed.scheme}://{parsed.netloc}"
    suffix = parsed.path.rstrip("/")
    return f"http://{endpoint}{CAPTURE_PATH_PREFIX}/{encode_origin(origin)}{suffix}"


def rewrite_models_payload(payload, endpoint):
    """Point every provider in a models.json payload at the capture proxy.

    Returns ``(payload, routes)``. Providers whose baseUrl cannot be parsed are
    left alone so an unexpected shape degrades to "no capture" instead of a
    broken launch.
    """
    routes = {}
    providers = payload.get("providers") if isinstance(payload, dict) else None
    if not isinstance(providers, dict):
        return payload, routes
    for name, provider in providers.items():
        if not isinstance(provider, dict):
            continue
        original = str(provider.get("baseUrl") or "").strip()
        rewritten = capture_url(endpoint, original)
        if not rewritten:
            continue
        provider["baseUrl"] = rewritten
        routes[name] = {"original": original, "captured": rewritten}
    return payload, routes


def _proxy_script_path():
    path = Path(__file__).resolve().parent / "scripts" / "pi_capture_proxy.py"
    return str(path) if path.is_file() else ""


def _normalize_endpoint(value):
    """Accept "1"/"auto" (spawn), ":PORT", "PORT", or "HOST:PORT"."""
    text = str(value or "").strip()
    if text.lower() in ("1", "true", "on", "yes", "auto"):
        return ""
    if text.startswith(":"):
        return "127.0.0.1" + text
    if text.isdigit():
        return f"127.0.0.1:{text}"
    return text


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_listening(port, timeout=_STARTUP_TIMEOUT_SECONDS):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(_STARTUP_POLL_SECONDS)
    return False


def _spawn_proxy(capture_dir, parent_pid):
    script = _proxy_script_path()
    if not script:
        return "", "capture proxy script is missing"
    port = _free_port()
    os.makedirs(capture_dir, mode=0o700, exist_ok=True)
    os.chmod(capture_dir, 0o700)
    stdout_path = os.path.join(capture_dir, "proxy.out")
    command = [
        sys.executable,
        script,
        "--port",
        str(port),
        "--log-dir",
        capture_dir,
        "--parent-pid",
        str(parent_pid),
    ]
    try:
        fd = os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "ab", buffering=0) as stream:
            subprocess.Popen(
                command,
                stdout=stream,
                stderr=stream,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
    except OSError as exc:
        return "", f"capture proxy failed to start: {exc}"
    if not _wait_until_listening(port):
        return "", f"capture proxy did not start listening on 127.0.0.1:{port}"
    return f"127.0.0.1:{port}", ""


def apply_capture_proxy(models_path, env, session_home, *, setting=None):
    """Route the launch's Pi providers through a local capture proxy.

    No-op unless the opt-in env var is set. On any failure the models config is
    left untouched so the normal launch path keeps working.
    """
    value = setting if setting is not None else capture_setting(env)
    if not value:
        return ""

    capture_dir = os.path.join(str(session_home or "."), "pi-capture")
    endpoint = _normalize_endpoint(value)
    if not endpoint:
        endpoint, error = _spawn_proxy(capture_dir, os.getpid())
        if error:
            print(f"[mms] {error}; Pi launch continues without capture", file=sys.stderr)
            return ""
    else:
        os.makedirs(capture_dir, mode=0o700, exist_ok=True)
        os.chmod(capture_dir, 0o700)

    try:
        payload = json.loads(Path(models_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[mms] capture proxy could not read {models_path}: {exc}", file=sys.stderr)
        return ""

    payload, routes = rewrite_models_payload(payload, endpoint)
    if not routes:
        print("[mms] capture proxy found no rewritable provider baseUrl", file=sys.stderr)
        return ""

    atomic_write_text(models_path, json.dumps(payload, indent=2) + "\n", mode=0o600)
    atomic_write_text(
        os.path.join(capture_dir, "routes.json"),
        json.dumps(routes, indent=2, ensure_ascii=False) + "\n",
        mode=0o600,
    )
    if isinstance(env, dict):
        env[CAPTURE_DIR_ENV] = capture_dir
        env[CAPTURE_ENDPOINT_ENV] = endpoint
    print(f"[mms] Pi request capture active: {capture_dir}", file=sys.stderr)
    return capture_dir
