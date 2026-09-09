"""Version reporting and in-place upgrade for MMS Web.

The upgrade replaces ~/.mms, which contains the code this server is running
from, so it cannot be performed in-process. Instead a detached helper script
runs the installer, stops this server and starts the new one on the same port.
The page notices the gap by polling and reconnects on its own.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RELEASES_URL = "https://api.github.com/repos/CtriXin/multi-model-switch/releases/latest"
INSTALL_SCRIPT_URL = (
    "https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh"
)
# GitHub allows 60 unauthenticated calls an hour per IP, shared with everything
# else on this machine. One check every six hours is plenty for a release feed.
MIN_CHECK_INTERVAL_SECONDS = 6 * 60 * 60
NETWORK_TIMEOUT_SECONDS = 6
TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _parse_tag(tag: str) -> tuple[int, int, int] | None:
    match = TAG_PATTERN.match(str(tag or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _env_flag(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return str(raw).strip().lower() not in {"", "0", "false", "no", "off"}


class UpgradeService:
    def __init__(self, *, state_root: Path, config_root: Path | None):
        self._state_root = Path(state_root)
        self._config_root = Path(config_root) if config_root else None
        self._cache_path = self._state_root / "update-check.json"
        self._log_path = self._state_root / "upgrade.log"
        self._marker_path = self._state_root / "upgrade-running.json"
        self.port: int | None = None

    # ── installed side ────────────────────────────────────────────────────

    def _version_metadata(self) -> dict:
        if not self._config_root:
            return {}
        path = self._config_root / "version.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def installed(self) -> dict:
        meta = self._version_metadata()
        return {
            "ref": str(meta.get("installed_ref") or ""),
            "version": str(meta.get("installed_version") or ""),
            "channel": str(meta.get("install_channel") or ""),
            "installedAt": str(meta.get("installed_at") or ""),
        }

    # ── remote side ───────────────────────────────────────────────────────

    def _read_cache(self) -> dict:
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_cache(self, payload: dict) -> None:
        try:
            self._state_root.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            pass

    def _fetch_latest(self) -> tuple[str, str]:
        """Return (tag, error). Network failures are reported, never raised."""
        request = urllib.request.Request(
            RELEASES_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "mms-web"},
        )
        try:
            with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in {403, 429}:
                return "", "GitHub 暂时限制了版本查询频率，稍后会自动重试。"
            return "", f"版本查询失败（HTTP {error.code}）。"
        except Exception:
            return "", "无法连接到 GitHub，网络恢复后会自动重试。"
        tag = str((payload or {}).get("tag_name") or "").strip()
        if not _parse_tag(tag):
            return "", "GitHub 返回的版本号无法识别。"
        return tag, ""

    def check_enabled(self) -> bool:
        override = _env_flag("MMS_WEB_UPDATE_CHECK")
        return True if override is None else override

    # ── status ────────────────────────────────────────────────────────────

    def refresh(self, *, force: bool = False) -> dict:
        """Query GitHub when the cache is stale. Callers must not be serving a
        page: this touches the network."""
        if not self.check_enabled():
            return self.status()
        cache = self._read_cache()
        checked_at = float(cache.get("checkedAt") or 0)
        if not force and (time.time() - checked_at) < MIN_CHECK_INTERVAL_SECONDS:
            return self.status()
        latest, error = self._fetch_latest()
        self._write_cache({"latest": latest, "checkedAt": time.time(), "error": error})
        return self.status()

    def start_background_refresh(self) -> None:
        """One daemon thread, so the first page load never waits on GitHub."""
        if not self.check_enabled():
            return

        def loop() -> None:
            while True:
                try:
                    self.refresh()
                except Exception:
                    pass
                time.sleep(MIN_CHECK_INTERVAL_SECONDS)

        thread = threading.Thread(target=loop, name="mms-web-update-check", daemon=True)
        thread.start()

    # status() is served on the request path, so it only reads the cache.
    def status(self) -> dict:
        installed = self.installed()
        cache = self._read_cache()
        latest = str(cache.get("latest") or "")
        checked_at = float(cache.get("checkedAt") or 0)
        error = str(cache.get("error") or "")
        if not self.check_enabled():
            latest, error, checked_at = "", "", 0.0

        installed_parts = _parse_tag(installed["version"])
        latest_parts = _parse_tag(latest)
        # A source checkout has no comparable version. Say nothing rather than
        # nag a developer to "upgrade" over their own working tree.
        comparable = bool(installed_parts and latest_parts)
        update_available = bool(comparable and latest_parts > installed_parts)

        blocked = self._upgrade_blocked_reason()
        return {
            "installed": installed,
            "latest": latest,
            "checkedAt": int(checked_at) if checked_at else 0,
            "checkEnabled": self.check_enabled(),
            "comparable": comparable,
            "updateAvailable": update_available,
            "upgradeRunning": self.upgrade_running(),
            "canUpgrade": bool(update_available and not blocked),
            "blockedReason": blocked,
            "logPath": str(self._log_path),
            "error": error,
        }

    # ── upgrade ───────────────────────────────────────────────────────────

    def upgrade_running(self) -> bool:
        try:
            data = json.loads(self._marker_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        pid = int(data.get("pid") or 0)
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _upgrade_blocked_reason(self) -> str:
        if not self._config_root:
            return "这个 MMS Web 没有连接到 MMS 配置，无法升级。"
        if not shutil.which("bash"):
            return "找不到 bash，无法运行安装脚本。"
        if not self.port:
            return "还没拿到本地服务端口，稍后重试。"
        return ""

    def start(self, *, live_sessions: int) -> dict:
        status = self.status()
        if status["upgradeRunning"]:
            return {"started": False, "reason": "升级已经在进行中。"}
        if not status["updateAvailable"]:
            return {"started": False, "reason": "当前已经是最新版本。"}
        blocked = self._upgrade_blocked_reason()
        if blocked:
            return {"started": False, "reason": blocked}
        if live_sessions > 0:
            return {
                "started": False,
                "reason": f"还有 {live_sessions} 个会话在运行。升级会重启服务，请先结束它们。",
            }

        script = self._write_upgrade_script(status["latest"])
        self._state_root.mkdir(parents=True, exist_ok=True)
        log = open(self._log_path, "ab", buffering=0)  # noqa: SIM115 - handed to the child
        try:
            process = subprocess.Popen(
                ["bash", str(script)],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
                cwd=str(self._state_root),
            )
        finally:
            log.close()
        self._marker_path.write_text(
            json.dumps({"pid": process.pid, "startedAt": int(time.time()), "target": status["latest"]})
            + "\n",
            encoding="utf-8",
        )
        return {"started": True, "target": status["latest"], "port": self.port, "logPath": str(self._log_path)}

    def _write_upgrade_script(self, target: str) -> Path:
        """The upgrade cannot run in-process: the installer overwrites the code
        this server is executing. The helper installs first, and only then
        replaces the running server."""
        scripts_dir = self._state_root / "upgrade"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        script = scripts_dir / "run-upgrade.sh"
        web_command = shutil.which("mms-web") or str(Path.home() / ".local/bin/mms-web")
        script.write_text(
            "\n".join(
                [
                    "#!/bin/bash",
                    "set -o pipefail",
                    f'echo "=== upgrade to {target} at $(date -u +%FT%TZ) ==="',
                    'installer="$(mktemp "${TMPDIR:-/tmp}/mms-upgrade.XXXXXX")"',
                    f'if ! curl -fsSL "{INSTALL_SCRIPT_URL}" -o "$installer"; then',
                    '  echo "download failed"; rm -f "$installer"; exit 1',
                    "fi",
                    # No shell rc writes and no launch prompt: this runs unattended.
                    'if ! bash "$installer" --no-launch-web --no-shell-rc; then',
                    '  echo "install failed"; rm -f "$installer"; exit 1',
                    "fi",
                    'rm -f "$installer"',
                    f'kill {os.getpid()} 2>/dev/null || true',
                    "sleep 2",
                    f'exec "{web_command}" --config-root "{self._config_root}" --port {self.port}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        script.chmod(0o700)
        return script
