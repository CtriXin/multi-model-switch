"""`mms web status|url|start|stop|restart`: manage the Pilot service from a shell.

The server has no supervisor: the installer starts one detached process and
nothing restarts it later. These commands answer the two questions that
kept getting lost — "which of the Pilots on this machine is mine, and what
is its address" — and start or stop that one. Discovery is by port probe:
every Pilot answers HEAD / with `X-MMS-Web-Identity` (source|config_root|
version), `X-MMS-Web-Version` and `X-MMS-Web-State` (a fingerprint of its
state root, which is what makes an instance "mine"); the process details come
from `lsof`/`ps` or `netstat`/CIM, never from a pid file that could go stale.
"""
from __future__ import annotations

import base64
import http.client
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

VERBS = ("status", "url", "start", "stop", "restart", "doctor")
HELP_FLAGS = ("help", "-h", "--help")
DEFAULT_PORT_BASE = 8765
PORT_SEARCH_LIMIT = 20
START_TIMEOUT = 30
STOP_TIMEOUT = 20
# A Windows Pilot cannot be asked to exit by signal: it has no console of its
# own and no window for CloseMainWindow. It watches this file in its state root
# instead, so `stop` stays a request and never a forced kill.
STOP_REQUEST = "stop-requested"


def command_label() -> str:
    """How this entry point is spelled, so examples can be pasted as printed."""
    invoked = Path(sys.argv[0] or "").name
    if invoked == "mms-web":
        return "mms-web"
    named = str(os.environ.get("MMS_COMMAND_NAME") or "").strip()
    if named:
        return f"{named} web"
    if invoked in ("mms", "mmf", "mmg", "mmd", "mmm"):
        return f"{invoked} web"
    return "mms web"


def wants_help(argv: list[str]) -> bool:
    """True when the command was typed with nothing to do.

    A bare `mms web` reaches this module as ``--config-root <root>`` because
    mms_core prepends the selected root, so "bare" means "no option that asks
    for a server", not an empty list.
    """
    rest: list[str] = []
    skip = False
    for token in argv:
        if skip:
            skip = False
            continue
        if token == "--config-root":
            skip = True
            continue
        if token.startswith("--config-root="):
            continue
        rest.append(token)
    if not rest:
        return True
    return any(token in HELP_FLAGS for token in rest)


def _display_width(text: str) -> int:
    """Terminal columns, counting the wide forms CJK punctuation renders as."""
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text)


def _rows(pairs: list[tuple[str, str]], indent: str = "  ", gap: int = 3) -> str:
    """Two columns that stay aligned whatever the entry point is called."""
    width = max(_display_width(left) for left, _ in pairs) + gap
    return "\n".join(f"{indent}{left}{' ' * (width - _display_width(left))}{right}"
                     for left, right in pairs)


def help_text(command: str | None = None) -> str:
    from mms_version import VERSION

    name = command or command_label()
    usage = _rows([
        (f"{name} <命令> [选项]", "管理后台运行的 Pilot"),
        (f"{name} [选项]", "在当前终端前台启动，Ctrl+C 停止"),
    ])
    verbs = _rows([
        ("start", "启动。已经在跑就直接返回地址，不会起第二个"),
        ("status", "本机在跑的 Pilot：地址、版本、pid、数据目录、配置根"),
        ("url", "只打印当前实例的地址，方便复制"),
        ("stop", "请当前实例退出；加 --all 停掉本机全部 Pilot"),
        ("restart", "先停再起"),
        ("doctor", "自动检查并验证 Pilot、本地 API 和会话详情"),
    ])
    examples = _rows([
        (f"{name} start --open", "后台启动并打开浏览器"),
        (f"{name} url", "拿地址"),
        (f"{name} status", "分不清哪个实例是自己的时候看这个"),
        (f"{name} stop", "收工"),
        (f"{name} doctor", "自检；没有 Pilot 时自动启动"),
        (f"{name} --open", "前台启动，日志直接打在终端"),
    ])
    options = _rows([
        ("--open", "启动后打开浏览器"),
        ("--port N", "起始端口，默认 8765，被占用就往后找"),
        ("--state-root DIR", "会话与 Web 配置，默认 ~/.local/share/mms-web"),
        ("--config-root DIR", "MMS 配置根，默认 ~/.config/mms-next"),
        ("--listen loopback|lan|all", "仅本次启动的访问范围；不给就用设置里的开关"),
        ("--hostname HOST", "额外允许的访问域名，可重复"),
        ("--json", "让上面五个命令输出 JSON"),
    ])
    return (
        f"MMS Pilot {VERSION} — 在浏览器里用 MMS 的模型、通道和会话\n\n"
        f"用法\n{usage}\n\n"
        f"命令\n{verbs}\n\n"
        f"例子\n{examples}\n\n"
        f"选项\n{options}\n\n"
        "后台启动的日志在 <state-root>/logs/mms-web.log。\n"
        "手机或另一台电脑访问：设置 → 使用 → 让手机或另一台电脑访问。\n"
        f"每个命令还有自己的 --help，例如 {name} stop --help。\n"
        "更多说明：docs/mms-web/GETTING-STARTED.md"
    )


def default_state_root() -> Path:
    from mms_platform import describe_platform
    return Path(describe_platform().state_root)


def source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _is_windows() -> bool:
    """One seam for every Windows branch, so each can be tested on any host."""
    return os.name == "nt"


def _windows_console_codepages() -> list[str]:
    """OEM/ANSI codepages console tools actually emit; empty off Windows.

    ``locale.getpreferredencoding(False)`` is unusable here: PYTHONUTF8=1 (set
    by the installer/CI) makes it answer "utf-8" while netstat and
    powershell.exe still write the machine codepage (cp936 on a Chinese
    system). Ask the Win32 API directly instead.
    """
    if os.name != "nt":
        return []
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        pages = []
        for getter in (kernel32.GetOEMCP, kernel32.GetACP):
            try:
                page = int(getter())
            except (TypeError, ValueError):
                continue
            if page:
                pages.append(f"cp{page}")
        return pages
    except (AttributeError, OSError):
        return []


def _decode_windows_command_output(data) -> str:
    """Decode console-tool output that can never crash the lifecycle path.

    Only netstat's ASCII protocol/port/PID fields are consumed. Localized
    headings may use an OEM/ANSI codepage, even under PYTHONUTF8=1.
    Unicode process command lines use a separate Base64/UTF-8 contract.
    """
    if isinstance(data, str):
        return data
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for encoding in _windows_console_codepages():
        try:
            return data.decode(encoding, errors="replace")
        except LookupError:
            continue
    return data.decode("utf-8", errors="replace")


def state_identity(path) -> str:
    """A path-free fingerprint of one state root, published by the server.

    `mine` used to be decided by re-parsing the server's command line. On
    Windows that means CIM plus POSIX-escaped splitting of `C:\\Users\\...`,
    which drops every separator, so no instance was ever recognized as its
    own. Comparing fingerprints needs neither the process list nor the path.
    """
    import hashlib

    resolved = Path(path).expanduser().resolve()
    return hashlib.sha256(os.path.normcase(str(resolved)).encode("utf-8")).hexdigest()


def _probe(port: int, timeout: float = 0.4):
    """Headers of a Pilot listening on the port, or None."""
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        conn.request("HEAD", "/", headers={"Host": f"127.0.0.1:{port}"})
        response = conn.getresponse()
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass
    identity = response.getheader("X-MMS-Web-Identity")
    if not identity:
        return None
    return {"identity": identity, "version": response.getheader("X-MMS-Web-Version") or "",
            "stateIdentity": response.getheader("X-MMS-Web-State") or ""}


def _listening_pids(port: int) -> list[int]:
    try:
        if _is_windows():
            raw = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                                 capture_output=True, timeout=5).stdout
            out = _decode_windows_command_output(raw)
            pids = []
            for line in out.splitlines():
                fields = line.split()
                if len(fields) >= 5 and fields[0].upper() == "TCP":
                    local = fields[1].rsplit(":", 1)
                    if len(local) == 2 and local[1] == str(port) and fields[3].upper() == "LISTENING" and fields[4].isdigit():
                        pids.append(int(fields[4]))
            return sorted(set(pids))
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pids = []
    for line in out.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pids.append(int(line[1:]))
    return sorted(set(pids))


def _command_line(pid: int) -> list[str]:
    try:
        if _is_windows():
            # Transport Unicode through ASCII: Windows PowerShell's console
            # codepage can differ from both Python's locale and the system ACP.
            command = (
                "$p=Get-CimInstance Win32_Process -Filter 'ProcessId=%s'; "
                "if ($p) { [Convert]::ToBase64String("
                "[Text.Encoding]::UTF8.GetBytes($p.CommandLine)) }"
            ) % pid
            raw = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command],
                                 capture_output=True, timeout=5).stdout
            out = base64.b64decode(raw.strip(), validate=True).decode("utf-8").strip()
        else:
            out = subprocess.run(["ps", "-o", "command=", "-p", str(pid)],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return _split_command_line(out)


def _split_command_line(text: str) -> list[str]:
    """Split one command line the way the platform that wrote it meant it."""
    if _is_windows():
        # POSIX escaping would eat the backslashes in every `C:\...` argument.
        try:
            tokens = shlex.split(text, posix=False)
        except ValueError:
            tokens = text.split()
        return [token[1:-1] if len(token) > 1 and token[0] == token[-1] == '"' else token
                for token in tokens]
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _option(argv: list[str], name: str) -> str:
    for index, token in enumerate(argv):
        if token == name and index + 1 < len(argv):
            return argv[index + 1]
        if token.startswith(name + "="):
            return token[len(name) + 1:]
    return ""


def _cwd(pid: int) -> str:
    if _is_windows():
        return ""
    try:
        out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:]
    return ""


def discover(port_base: int = DEFAULT_PORT_BASE, limit: int = PORT_SEARCH_LIMIT,
             state_root: Path | None = None) -> list[dict]:
    """Every Pilot answering on the probed ports, ours flagged by state root."""
    mine_root = (state_root or default_state_root())
    mine_fingerprint = state_identity(mine_root)
    found = []
    for port in range(port_base, port_base + limit):
        probe = _probe(port)
        if probe is None:
            continue
        pids = _listening_pids(port)
        pid = pids[0] if pids else 0
        argv = _command_line(pid) if pid else []
        raw_state = _option(argv, "--state-root")
        state = str(Path(raw_state).expanduser().resolve()) if raw_state else str(default_state_root())
        fingerprint = probe.get("stateIdentity") or ""
        # The header is authoritative. The command line is a fallback for a
        # Pilot older than the header, and the only source for pid and source.
        mine = fingerprint == mine_fingerprint if fingerprint else (bool(argv) and state == str(mine_root))
        entry = {
            "port": port,
            "pid": pid,
            "version": probe["version"],
            "identity": probe["identity"],
            "stateRoot": state,
            "configRoot": _option(argv, "--config-root"),
            "source": _cwd(pid) if pid else "",
            "url": f"http://127.0.0.1:{port}",
            "mine": mine,
        }
        token_file = Path(state) / "remote-access-token"
        if entry["mine"] and (Path(state) / "remote-access.json").is_file() and token_file.is_file():
            try:
                token = token_file.read_text(encoding="utf-8").strip()
            except OSError:
                token = ""
            if token:
                from .remote_access import QUERY
                entry["url"] = f"http://127.0.0.1:{port}/?{QUERY}={token}"
        found.append(entry)
    return found


def _mine(instances: list[dict]) -> dict | None:
    for entry in instances:
        if entry["mine"]:
            return entry
    return None


def _free_port(port_base: int, limit: int) -> int:
    import socket

    for port in range(port_base, port_base + limit):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise SystemExit(f"没有空闲端口（{port_base}..{port_base + limit - 1}）。")


def _print_status(instances: list[dict], state_root: Path, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"stateRoot": str(state_root), "instances": instances}, ensure_ascii=False, indent=2))
        return
    if not instances:
        print("没有 Pilot 在运行。启动：mms web start")
        return
    for entry in instances:
        mark = "●" if entry["mine"] else "○"
        version = entry["version"] or "?"
        print(f"{mark} {entry['url']}  v{version}  pid {entry['pid'] or '?'}")
        print(f"    state-root  {entry['stateRoot']}")
        if entry["configRoot"]:
            print(f"    config-root {entry['configRoot']}")
        if entry["source"]:
            print(f"    source      {entry['source']}")
    mine = _mine(instances)
    if mine is None:
        print(f"○ 这些都不是当前 state-root（{state_root}）的实例。启动自己的：mms web start")
    else:
        print("● 当前实例。停止：mms web stop；重启：mms web restart")


def _doctor_request(base_url: str, path: str, timeout: float = 8.0) -> tuple[bool, object]:
    """Read one local Pilot API endpoint without depending on shell encoding."""
    request = urllib.request.Request(base_url.rstrip("/") + path,
                                     headers={"Accept": "application/json"})
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
        return True, json.loads(raw.decode("utf-8", errors="replace"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        detail = str(error)
        if isinstance(error, urllib.error.HTTPError):
            try:
                body = error.read().decode("utf-8", errors="replace")
                detail = f"HTTP {error.code}: {body[:500]}"
            except OSError:
                detail = f"HTTP {error.code}"
        return False, detail


def doctor(*, state_root: Path, port_base: int, limit: int, restart: bool = False,
           as_json: bool = False) -> int:
    """Self-check the Windows lifecycle without changing config or credentials."""
    if restart:
        stop(state_root=state_root, port_base=port_base, limit=limit, everyone=False, quiet=True)
    started = False
    try:
        instance = _mine(discover(port_base, limit, state_root))
        if instance is None:
            instance = start(state_root=state_root, port_base=port_base, limit=limit,
                             open_browser=False, quiet=True)
            started = True
    except (SystemExit, OSError) as error:
        result = {"ok": False, "started": started, "error": str(error),
                  "stateRoot": str(state_root),
                  "log": str(state_root / "logs" / "mms-web.log")}
        if as_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("FAIL Pilot 启动：" + str(error))
            print("日志：" + result["log"])
        return 1

    base_url = f"http://127.0.0.1:{instance['port']}"
    checks: list[dict] = []

    def check(name: str, path: str, predicate=None):
        ok, payload = _doctor_request(base_url, path)
        passed = ok and (predicate(payload) if predicate else True)
        checks.append({"name": name, "path": path, "ok": passed,
                       **({"detail": payload} if not passed else {})})
        return passed, payload

    bootstrap_ok, bootstrap = check(
        "bootstrap", "/api/v1/bootstrap",
        lambda value: isinstance(value, dict) and value.get("version") == "1" and isinstance(value.get("capabilities"), dict),
    )
    sessions_ok, sessions = check(
        "sessions", "/api/v1/sessions",
        lambda value: isinstance(value, dict) and isinstance(value.get("sessions"), list),
    )
    rows = sessions.get("sessions", []) if isinstance(sessions, dict) else []
    detail_rows = [row for row in rows[:3] if isinstance(row, dict) and row.get("id")]
    if detail_rows:
        detail_ok, _ = check("session-detail", "/api/v1/sessions/" + urllib.parse.quote(str(detail_rows[0]["id"]), safe=""),
                             lambda value: isinstance(value, dict) and isinstance(value.get("session"), dict))
    else:
        detail_ok = True
        checks.append({"name": "session-detail", "ok": True, "skipped": True,
                       "detail": "没有可读取的历史会话"})

    launch = bootstrap.get("capabilities", {}).get("launch") if isinstance(bootstrap, dict) else None
    launch_reason = bootstrap.get("capabilities", {}).get("launchReason") if isinstance(bootstrap, dict) else ""
    launch_ok = bool(launch)
    checks.append({"name": "launch-capability", "ok": launch_ok,
                   **({"detail": launch_reason or "会话启动能力未就绪"} if not launch_ok else {})})
    result = {"ok": all(item["ok"] for item in checks), "started": started,
              "instance": instance, "checks": checks,
              "launch": launch, "launchReason": launch_reason,
              "log": str(state_root / "logs" / "mms-web.log")}
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"MMS doctor：{'PASS' if result['ok'] else 'FAIL'}")
        print(f"Pilot：{base_url}  v{instance.get('version') or '?'}  pid {instance.get('pid') or '?'}")
        for item in checks:
            status = "PASS" if item["ok"] else "FAIL"
            suffix = "（跳过：无历史会话）" if item.get("skipped") else ""
            print(f"{status} {item['name']}{suffix}")
            if not item["ok"]:
                print(f"  {item.get('detail')}")
        if launch is False:
            print("FAIL launch：" + str(launch_reason or "会话启动能力未就绪"))
        print("日志：" + result["log"])
    return 0 if result["ok"] else 1


def start(*, state_root: Path, port_base: int, limit: int, open_browser: bool,
          extra_args: list[str] | None = None, quiet: bool = False) -> dict:
    """Return the running instance, starting one detached when there is none."""
    mine = _mine(discover(port_base, limit, state_root))
    if mine is not None:
        if not quiet:
            print(f"MMS Pilot 已在运行：{mine['url']}")
        if open_browser:
            import webbrowser
            webbrowser.open(mine["url"])
        return mine
    port = _free_port(port_base, limit)
    log_dir = state_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "mms-web.log"
    command = [sys.executable, "-P", "-m", "mms_web", "--state-root", str(state_root), "--port", str(port),
               *(extra_args or [])]
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(source_root()))
    creationflags = 0
    if _is_windows():
        # subprocess ignores start_new_session on Windows, so without these
        # flags the "detached" Pilot keeps the launching console: closing the
        # window or pressing Ctrl+C in it takes the Pilot and every Pi session
        # with it.
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    with log_path.open("ab") as log:
        subprocess.Popen(command, cwd=str(source_root()), env=env, stdin=subprocess.DEVNULL,
                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                         creationflags=creationflags)
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        mine = _mine(discover(port_base, limit, state_root))
        if mine is not None and mine["port"] == port:
            if not quiet:
                print(f"MMS Pilot: {mine['url']}")
                print(f"  后台运行中，日志在 {log_path}")
            if open_browser:
                import webbrowser
                webbrowser.open(mine["url"])
            return mine
        time.sleep(0.5)
    raise SystemExit(f"MMS Pilot 没有在 {START_TIMEOUT}s 内就绪，日志在 {log_path}")


def stop(*, state_root: Path, port_base: int, limit: int, everyone: bool, quiet: bool = False) -> list[dict]:
    """Gracefully request ours (or every Pilot with --all) and wait."""
    targets = [e for e in discover(port_base, limit, state_root) if everyone or e["mine"]]
    targets = [e for e in targets if e["pid"]]
    if not targets:
        if not quiet:
            print("没有需要停止的 Pilot。")
        return []
    for entry in targets:
        try:
            if _is_windows():
                # A detached Pilot has no console to receive CTRL_BREAK and no
                # window for CloseMainWindow, and taskkill /F is a forced kill
                # that would take its Pi sessions with it. Write the request the
                # Pilot itself watches for.
                request = Path(entry["stateRoot"]) / STOP_REQUEST
                try:
                    request.write_text(str(entry["port"]), encoding="utf-8")
                except OSError as error:
                    print(f"无法请求 pid {entry['pid']} 退出（{entry['url']}）：{error}", file=sys.stderr)
            else:
                os.kill(entry["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            print(f"无权停止 pid {entry['pid']}（{entry['url']}）", file=sys.stderr)
    deadline = time.monotonic() + STOP_TIMEOUT
    remaining = list(targets)
    while remaining and time.monotonic() < deadline:
        time.sleep(0.5)
        remaining = [e for e in remaining if _probe(e["port"]) is not None]
    for entry in targets:
        if entry in remaining:
            if _is_windows():
                # Leave no request behind that a later start would consume.
                Path(entry["stateRoot"]).joinpath(STOP_REQUEST).unlink(missing_ok=True)
            print(f"⚠ pid {entry['pid']}（{entry['url']}）在 {STOP_TIMEOUT}s 内没有退出，未强制结束。", file=sys.stderr)
        elif not quiet:
            print(f"已停止 {entry['url']}（pid {entry['pid']}）")
    return [e for e in targets if e not in remaining]


def run(verb: str, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog=f"{command_label()} {verb}")
    parser.add_argument("--state-root", type=Path, default=default_state_root())
    parser.add_argument("--config-root", type=Path, default=None,
                        help="Passed through to the server on start; discovery does not need it")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MMS_WEB_PORT_BASE") or DEFAULT_PORT_BASE),
                        help="First port to probe or bind")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--open", action="store_true", help="start/restart: open the browser afterwards")
    parser.add_argument("--all", action="store_true", help="stop: every Pilot on this machine, not only this state root")
    parser.add_argument("--restart", action="store_true", help="doctor: restart this Pilot before checking it")
    args = parser.parse_args(argv)
    state_root = args.state_root.expanduser().resolve()
    extra = ["--config-root", str(args.config_root.expanduser())] if args.config_root else []
    limit = PORT_SEARCH_LIMIT
    if verb == "status":
        instances = discover(args.port, limit, state_root)
        _print_status(instances, state_root, args.json)
        return 0 if _mine(instances) else 1
    if verb == "url":
        mine = _mine(discover(args.port, limit, state_root))
        if mine is None:
            print("Pilot 没有在运行。启动：mms web start", file=sys.stderr)
            return 1
        print(json.dumps(mine, ensure_ascii=False) if args.json else mine["url"])
        return 0
    if verb == "start":
        mine = start(state_root=state_root, port_base=args.port, limit=limit, open_browser=args.open,
                     extra_args=extra, quiet=args.json)
        if args.json:
            print(json.dumps(mine, ensure_ascii=False))
        return 0
    if verb == "stop":
        stopped = stop(state_root=state_root, port_base=args.port, limit=limit, everyone=args.all, quiet=args.json)
        if args.json:
            print(json.dumps(stopped, ensure_ascii=False))
        return 0
    if verb == "restart":
        stop(state_root=state_root, port_base=args.port, limit=limit, everyone=False, quiet=args.json)
        mine = start(state_root=state_root, port_base=args.port, limit=limit, open_browser=args.open,
                     extra_args=extra, quiet=args.json)
        if args.json:
            print(json.dumps(mine, ensure_ascii=False))
        return 0
    if verb == "doctor":
        return doctor(state_root=state_root, port_base=args.port, limit=limit,
                      restart=args.restart, as_json=args.json)
    parser.error(f"unknown verb {verb}")
    return 2
