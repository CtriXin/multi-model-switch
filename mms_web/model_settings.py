"""Human-reviewed model configuration, backed by MMF's existing audited writer."""
from __future__ import annotations
import hashlib
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

from .errors import WebError
from .runtime import private_json, require_private_root, snapshot_config


class ModelSettings:
    def __init__(self, catalog):
        self.catalog = catalog
        self.state = require_private_root(catalog._state_root) / "model-settings"
        self.lock = threading.RLock()
        self.secret_drafts = {}

    @property
    def root(self):
        return self.catalog._require_config_root()

    def available(self):
        if not self.catalog._config_root:
            return False
        # This UI edits the dev/preview Registry; a stable installed MMS root
        # must not become writable merely because the worker uses preview mode.
        if self.catalog._is_protected_real_root() and self.root != (self.catalog._real_home() / ".config/mms-next").resolve():
            return False
        return ((self.root / "generated/model-registry.latest-approved.json").is_file()
                or (self.catalog._local_setup() and self.catalog.capabilities()["configure"]
                    and (self.root / "config.toml").is_file()))

    @contextmanager
    def serialized(self):
        # Share the connection editor's lock, including across server processes.
        with self.lock:
            with (self.catalog._state_root / "apply.lock").open("a+") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def confirmation(self):
        return "保存设置" if self.catalog._local_setup() else "写入预览DB"

    def fingerprint(self):
        h = hashlib.sha256()
        for name in ("generated/model-registry.latest-approved.json", "config.toml", "override.toml", "model-policy.json", "credentials.sh", "preferences.toml", "secrets/webui-secrets.json", "secrets/legacy-secrets.json"):
            path = self.root / name
            h.update(name.encode())
            if path.is_file():
                h.update(path.read_bytes())
        return h.hexdigest()

    def worker(self, payload, *, write=False):
        if not self.available():
            raise WebError("CONFIG_UNAVAILABLE", "该配置来源没有已批准的 MMF 模型目录。", 409)
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        snapshot = None if write else snapshot_config(self.root, self.state,
            published_credentials_only=self.catalog._local_setup())
        root = self.root if write else snapshot
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.state / "home"),
               "MMS_CONFIG_ROOT": str(root), "MMS_PREVIEW_MODE": "1", "MMS_COMMAND_NAME": "mmf",
               "MMS_WEB_STANDALONE": "1" if self.catalog._local_setup() else "0"}
        Path(env["HOME"]).mkdir(mode=0o700, exist_ok=True)
        try:
            process = subprocess.run([sys.executable, str(Path(__file__).with_name("model_settings_worker.py"))],
                input=json.dumps({**payload, "root": str(root), "standalone": self.catalog._local_setup()}),
                capture_output=True, text=True, env=env, timeout=90)
            try:
                result = json.loads(process.stdout)
            except ValueError:
                raise WebError("SETTINGS_FAILED", "配置服务没有返回有效结果，请重试。", 500)
            if not result.get("ok"):
                raise WebError(result.get("code", "SETTINGS_FAILED"), result.get("message", "配置操作失败。"), result.get("status", 400))
            return result
        except subprocess.TimeoutExpired:
            raise WebError("SETTINGS_TIMEOUT", "配置操作尚未完成，请稍后重新加载检查。", 504)
        finally:
            if snapshot:
                shutil.rmtree(snapshot)

    def read(self):
        with self.lock:
            before = self.fingerprint()
            result = self.worker({"action": "read"})
            if before != self.fingerprint():
                raise WebError("CONFIG_STALE", "配置刚刚发生变化，请重新加载。", 409)
            return {**result, "fingerprint": before, "configRoot": str(self.root),
                    "configScope": "standalone" if self.catalog._local_setup() else "mmf"}

    def _check(self, payload):
        if payload.get("fingerprint") != self.fingerprint():
            raise WebError("CONFIG_STALE", "MMF 配置已变化，请重新加载后再操作。", 409)

    def discover(self, payload):
        with self.lock:
            self._check(payload)
            result = self.worker({**payload, "action": "discover"})
            self._check(payload)
            return result

    def check(self, payload):
        with self.lock:
            self._check(payload)
            result = self.worker({**payload, "action": "check"})
            self._check(payload)
            return result

    def refresh(self, payload):
        # Reads a capability snapshot and returns proposed edits only. The
        # human still reviews them through preview before anything is written.
        with self.lock:
            self._check(payload)
            result = self.worker({**payload, "action": "refresh"})
            self._check(payload)
            return result

    def auto_refresh(self, provider_id: str, models: list[str] | None = None) -> dict:
        """Apply only trusted capability facts after a new channel is saved."""
        with self.lock:
            snapshot = self.read()
            target = next((p for p in snapshot["providers"] if p["id"] == provider_id), None)
            if target is None:
                return {"synced": False, "applied": 0, "warnings": ["通道保存后未找到对应模型目录。"]}
            model_ids = list(models or [m["id"] for m in target["models"] if m.get("visible")])
            result = self.worker({
                "action": "refresh",
                "providerId": provider_id,
                "models": model_ids,
                # Automatic onboarding uses only local official/approved facts.
                # OpenRouter remains an explicit review action, never a save-time dependency.
                "sources": ["official", "approved"],
                "openrouter_timeout": 3,
                "revision": snapshot["revision"],
            })
            edits = {"visions": {}, "contextWindows": {}, "efforts": {}}
            for item in result.get("proposals", []):
                for field in item.get("fields", []):
                    if field.get("userSet") or field.get("source") == "catalog":
                        continue
                    model = item.get("model")
                    if field.get("field") == "vision":
                        edits["visions"][model] = field.get("value")
                    elif field.get("field") == "context":
                        edits["contextWindows"][model] = field.get("value")
                    elif field.get("field") == "effort":
                        edits["efforts"][model] = field.get("value")
            if not any(edits.values()):
                return {"synced": True, "applied": 0, "reports": result.get("reports", [])}
            draft = {
                "fingerprint": snapshot["fingerprint"],
                "revision": snapshot["revision"],
                "providerId": provider_id,
                "models": model_ids,
                **edits,
            }
            preview = self.preview(draft)
            applied = self.apply({"previewId": preview["previewId"], "confirmed": True})
            return {"synced": True, "applied": len(preview.get("changes", [])),
                    "reports": result.get("reports", []), "result": applied}

    def preview(self, payload):
        with self.lock:
            self._check(payload)
            # Do not preserve caller-supplied action/root/confirmation fields.
            draft = {k: payload.get(k) for k in ("providerId", "models", "efforts", "visions", "contextWindows", "connection", "revision", "fingerprint", "removeProviderId")}
            result = self.worker({**draft, "action": "plan"})
            self._check(payload)
            token = uuid.uuid4().hex
            # New keys live only in process memory until the human applies.
            # A restart intentionally invalidates secret-bearing previews.
            connection = dict(draft.get("connection") or {})
            key = connection.pop("apiKey", None)
            draft["connection"] = connection
            now = time.time()
            self.secret_drafts = {k: v for k, v in self.secret_drafts.items() if now - v[0] < 900}
            if key:
                self.secret_drafts[token] = (now, key)
            record = {"needsKey": bool(key), "draft": draft, "createdAt": time.time(), "changes": result["changes"]}
            private_json(self.state / f"{token}.json", record)
            return {"previewId": token, "changes": result["changes"], "configRoot": str(self.root),
                    "confirmPhrase": self.confirmation(),
                    "writeSummary": "更新列出的通道连接、模型目录或默认值；新 Key 由 MMF 保存到本机凭据库，不会在页面回显。由 MMF 创建备份，发布后校验，失败时回滚。新会话读取新配置。"}

    def apply(self, payload):
        token = str(payload.get("previewId", ""))
        confirmed = payload.get("confirmed") is True
        if not re.fullmatch(r"[a-f0-9]{32}", token) or (not confirmed and payload.get("confirmPhrase") != self.confirmation()):
            raise WebError("CONFIRM_REQUIRED", "请在确认弹窗中确认后保存。", 409)
        with self.serialized():
            path = self.state / f"{token}.json"
            if not path.is_file():
                raise WebError("PREVIEW_MISSING", "变更预览已失效，请重新检查。", 409)
            record = json.loads(path.read_text())
            if record.get("result"):
                return record["result"]
            if record.get("started"):
                raise WebError("APPLY_UNCERTAIN", "上次保存结果待确认，请重新加载配置，避免重复保存。", 409)
            if time.time() - record["createdAt"] > 900:
                raise WebError("PREVIEW_EXPIRED", "变更预览已过期，请重新检查。", 409)
            self._check(record["draft"])
            draft = dict(record["draft"])
            if record.get("needsKey"):
                secret = self.secret_drafts.get(token)
                if not secret:
                    raise WebError("PREVIEW_EXPIRED", "连接预览已失效，请重新填写 Key 并检查变更。", 409)
                draft["connection"] = {**draft.get("connection", {}), "apiKey": secret[1]}
            record["started"] = True
            private_json(path, record)
            result = self.worker({**draft, "action": "apply", "confirmPhrase": "写入预览DB"}, write=True)
            self.secret_drafts.pop(token, None)
            record["result"] = result
            private_json(path, record)
            return result
