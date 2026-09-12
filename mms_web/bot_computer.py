"""Ego-backed screenshots for a task-owned MMS Bot computer.

Only a TaskSpace's documented ``p1`` Page is used.  The module persists the
numeric Ego space id per task, but never stores browser output, cookies, or
other personal browser state.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .errors import WebError
from .browser_provider import BrowserProvider
from .runtime import private_json, require_private_root


_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_BYTES = 8 * 1024 * 1024
_MAX_DIMENSION = 8192
_SUBPROCESS_TIMEOUT = 45
_LOCK_GUARD = threading.Lock()
_TASK_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_SPACE_REGISTRY_LOCK = threading.Lock()


class EgoComputer(BrowserProvider):
    """Capture one browser screenshot in a persistent, task-owned Ego space."""

    provider_id = "ego"

    def __init__(self, state_root: Path, executable: str | None = None):
        self.state_root = require_private_root(Path(state_root))
        self.executable = executable
        self._bot_root = self.state_root / "bots"
        self._spaces_path = self._bot_root / "ego-spaces.json"

    def available(self) -> bool:
        """Return whether the delegated Ego provider is installed."""
        return bool(self.executable or shutil.which("ego-browser"))

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.provider_id,
            "available": self.available(),
            "operations": ["goto", "snapshot", "click", "fill", "press", "screenshot"],
            "scope": "browser",
        }

    def capture(self, task_id: str, url: str | None = None) -> dict[str, Any]:
        self._validate_task_id(task_id)
        normalized_url = self._validate_url(url)
        executable = self._resolve_executable()
        lock = self._task_lock(task_id)
        with lock:
            # Different Bot tasks may capture concurrently. Serialize only
            # registry creation so one task cannot overwrite another's space.
            with _SPACE_REGISTRY_LOCK:
                spaces = self._load_spaces()
                space_id = spaces.get(task_id)
                if space_id is None:
                    marker = self._bot_root / "space-creation" / (task_id + ".json")
                    if marker.exists():
                        raise WebError("EGO_CREATION_UNCERTAIN", "上次浏览器空间创建未确认，请先检查 Ego；不会重复创建。", 409)
                    private_json(marker, {"taskId": task_id, "status": "creating"})
                    space_id = self._create_space(executable, task_id)
                    spaces[task_id] = space_id
                    self._save_spaces(spaces)
                    marker.unlink()
            output = self._output_path(task_id)
            receipt = self._capture_space(executable, space_id, output, normalized_url)
            reported_path = Path(str(receipt.get("path") or output)).resolve()
            if reported_path != output:
                raise WebError("EGO_INVALID_OUTPUT", "浏览器返回了不受允许的截图路径。", 502)
            width, height, digest = self._validate_png(output)
            return {
                "name": output.name,
                "path": str(output),
                "mimeType": "image/png",
                "kind": "screenshot",
                "sha256": digest,
                "spaceId": space_id,
                "page": "p1",
                "width": width,
                "height": height,
            }

    def interact(self, task_id: str, operation: str, target: str | None = None,
                 value: str | None = None) -> dict[str, Any]:
        """Run one bounded browser action in the task's persistent Ego page.

        This deliberately exposes Ego's semantic Page API instead of pretending
        to be an OS-level computer controller.  The same task space/page is
        reused, so a Bot can navigate, inspect, act, and then capture evidence.
        """
        self._validate_task_id(task_id)
        if operation not in {"goto", "snapshot", "click", "fill", "press"}:
            raise WebError("INVALID_BROWSER_ACTION", "不支持这个浏览器动作。", 400)
        if operation == "goto":
            target = self._validate_url(target)
            if not target:
                raise WebError("INVALID_URL", "打开页面需要 http 或 https 地址。", 400)
        elif operation in {"click", "fill", "press"}:
            if not isinstance(target, str) or not target.strip():
                raise WebError("INVALID_BROWSER_TARGET", "浏览器动作需要唯一的 selector 或 snapshot ref。", 400)
        if operation == "fill" and (value is None or not str(value).strip()):
            raise WebError("INVALID_BROWSER_VALUE", "填写动作需要内容。", 400)
        if operation == "press" and (value is None or not str(value).strip()):
            raise WebError("INVALID_BROWSER_VALUE", "按键动作需要 key。", 400)
        executable = self._resolve_executable()
        lock = self._task_lock(task_id)
        with lock:
            with _SPACE_REGISTRY_LOCK:
                spaces = self._load_spaces()
                space_id = spaces.get(task_id)
                if space_id is None:
                    marker = self._bot_root / "space-creation" / (task_id + ".json")
                    if marker.exists():
                        raise WebError("EGO_CREATION_UNCERTAIN", "上次浏览器空间创建未确认，请先检查 Ego；不会重复创建。", 409)
                    private_json(marker, {"taskId": task_id, "status": "creating"})
                    space_id = self._create_space(executable, task_id)
                    spaces[task_id] = space_id
                    self._save_spaces(spaces)
                    marker.unlink()
            result = self._run(executable, self._action_script(space_id, operation, target, value))
            receipt = self._receipt(result)
            if receipt.get("spaceId") != space_id:
                raise WebError("EGO_INVALID_RECEIPT", "浏览器返回的任务空间不匹配。", 502)
            return {"kind": "browser", "operation": operation, "spaceId": space_id,
                    "page": "p1", "result": receipt.get("result")}

    def _resolve_executable(self) -> str:
        executable = self.executable if self.executable is not None else shutil.which("ego-browser")
        if not executable:
            raise WebError("EGO_UNAVAILABLE", "未找到 ego-browser，无法执行浏览器截图。", 409)
        return str(executable)

    @staticmethod
    def _validate_task_id(task_id: str) -> None:
        if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
            raise WebError("INVALID_TASK_ID", "任务 ID 无效。", 400)

    @staticmethod
    def _validate_url(url: str | None) -> str | None:
        if url is None:
            return None
        if not isinstance(url, str) or not url.strip():
            raise WebError("INVALID_URL", "截图 URL 无效。", 400)
        value = url.strip()
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise WebError("INVALID_URL", "只允许 http 或 https 页面地址。", 400)
        return value

    def _task_lock(self, task_id: str) -> threading.Lock:
        key = (str(self.state_root), task_id)
        with _LOCK_GUARD:
            return _TASK_LOCKS.setdefault(key, threading.Lock())

    def _load_spaces(self) -> dict[str, int]:
        if not self._spaces_path.exists():
            return {}
        try:
            payload = json.loads(self._spaces_path.read_text(encoding="utf-8"))
            spaces = payload.get("spaces")
            if not isinstance(spaces, dict):
                raise ValueError("spaces")
            result: dict[str, int] = {}
            for task_id, space_id in spaces.items():
                self._validate_task_id(task_id)
                if not isinstance(space_id, int) or space_id < 1:
                    raise ValueError("space id")
                result[task_id] = space_id
            return result
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise WebError("EGO_STATE_INVALID", "Bot 浏览器状态无法读取，未创建新的浏览器空间。", 409) from exc

    def _save_spaces(self, spaces: dict[str, int]) -> None:
        private_json(self._spaces_path, {"version": 1, "spaces": spaces})

    def _output_path(self, task_id: str) -> Path:
        directory = (self._bot_root / "screenshots" / task_id).resolve()
        allowed = (self._bot_root / "screenshots").resolve()
        if not directory.is_relative_to(allowed):
            raise WebError("INVALID_TASK_ID", "任务截图路径无效。", 400)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        return (directory / f"{uuid.uuid4().hex}.png").resolve()

    def _create_space(self, executable: str, task_id: str) -> int:
        payload = {"operation": "create", "name": f"MMS Bot {task_id}"}
        result = self._run(executable, self._script(payload, create=True))
        receipt = self._receipt(result)
        space_id = receipt.get("spaceId")
        if not isinstance(space_id, int) or space_id < 1:
            raise WebError("EGO_INVALID_RECEIPT", "浏览器没有返回有效的任务空间。", 502)
        return space_id

    def _capture_space(self, executable: str, space_id: int, output: Path, url: str | None) -> dict[str, Any]:
        payload = {"operation": "capture", "spaceId": space_id, "outputPath": str(output), "url": url}
        result = self._run(executable, self._script(payload, create=False))
        return self._receipt(result)

    @staticmethod
    def _action_script(space_id: int, operation: str, target: str | None, value: str | None) -> str:
        encoded = json.dumps({"spaceId": space_id, "operation": operation,
                              "target": target, "value": value}, ensure_ascii=False,
                             separators=(",", ":"))
        return (
            f"const input = {encoded};\n"
            "const task = await taskSpace(input.spaceId);\n"
            "const page = task.page('p1');\n"
            "if (input.operation === 'goto') await page.goto(input.target);\n"
            "if (input.operation === 'click') await page.click(input.target, {label: 'Bot browser click'});\n"
            "if (input.operation === 'fill') await page.fill(input.target, input.value);\n"
            "if (input.operation === 'press') await page.press(input.target, input.value);\n"
            "const result = input.operation === 'snapshot' ? await page.snapshot({scope: 'full_page'}) : {url: await page.url(), title: await page.title()};\n"
            "console.log(JSON.stringify({spaceId: task.spaceId, page: page.label, result}));\n"
        )

    @staticmethod
    def _script(payload: dict[str, Any], *, create: bool) -> str:
        # JSON is emitted as a JavaScript literal, never interpolated into a
        # shell command or an executable expression.
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if create:
            return (
                f"const input = {encoded};\n"
                "const task = await taskSpace(input.name);\n"
                "console.log(JSON.stringify({spaceId: task.spaceId, page: 'p1'}));\n"
            )
        return (
            f"const input = {encoded};\n"
            "const task = await taskSpace(input.spaceId);\n"
            "const page = task.page('p1');\n"
            "if (input.url) await page.goto(input.url);\n"
            "const path = await page.screenshot({path: input.outputPath});\n"
            "console.log(JSON.stringify({spaceId: task.spaceId, page: page.label, path}));\n"
        )

    @staticmethod
    def _run(executable: str, script: str) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                [executable, "nodejs"], input=script, text=True, capture_output=True,
                timeout=_SUBPROCESS_TIMEOUT, check=False,
            )
        except FileNotFoundError as exc:
            raise WebError("EGO_UNAVAILABLE", "未找到 ego-browser，无法执行浏览器截图。", 409) from exc
        except subprocess.TimeoutExpired as exc:
            raise WebError("EGO_TIMEOUT", "浏览器截图超时，任务空间已保留，稍后可继续。", 504) from exc
        except OSError as exc:
            raise WebError("EGO_UNAVAILABLE", "无法启动 ego-browser。", 409) from exc
        if result.returncode != 0:
            combined = f"{result.stdout}\n{result.stderr}".lower()
            if "control" in combined or "handoff" in combined or "ownership" in combined:
                raise WebError("EGO_USER_CONTROL", "浏览器已交给用户控制，无法继续截图。", 409)
            raise WebError("EGO_CAPTURE_FAILED", "浏览器未能完成截图。", 502)
        return result

    @staticmethod
    def _receipt(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        # ego-browser emits console.log receipts on stderr in current builds.
        for line in reversed((result.stdout + "\n" + result.stderr).splitlines()):
            try:
                value = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(value, dict):
                return value
        raise WebError("EGO_INVALID_RECEIPT", "浏览器没有返回有效的截图结果。", 502)

    @staticmethod
    def _validate_png(path: Path) -> tuple[int, int, str]:
        try:
            if not path.is_file() or path.is_symlink() or path.stat().st_size > _MAX_BYTES:
                raise ValueError("file")
            with path.open("rb") as stream:
                header = stream.read(24)
                if len(header) != 24 or header[:8] != _PNG_SIGNATURE or header[12:16] != b"IHDR":
                    raise ValueError("png")
                width = int.from_bytes(header[16:20], "big")
                height = int.from_bytes(header[20:24], "big")
                if not 0 < width <= _MAX_DIMENSION or not 0 < height <= _MAX_DIMENSION:
                    raise ValueError("dimensions")
                digest = hashlib.sha256(header)
                while chunk := stream.read(64 * 1024):
                    digest.update(chunk)
            return width, height, digest.hexdigest()
        except (OSError, ValueError) as exc:
            raise WebError("EGO_INVALID_SCREENSHOT", "浏览器没有生成有效的 PNG 截图。", 502) from exc
