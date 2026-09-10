"""User-managed project material, stored only in the Web private state root."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from .errors import WebError
from .runtime import private_json

MAX_ITEMS = 20
MAX_ITEM_BYTES = 20_000
MAX_TOTAL_BYTES = 80_000


def content_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


class ProjectMaterials:
    def __init__(self, catalog, state_root):
        self.catalog = catalog
        self.root = Path(state_root) / "project-materials"

    def _workspace(self, workspace_id):
        workspace = next((w for w in self.catalog._workspaces() if w["id"] == workspace_id), None)
        if not workspace or not Path(workspace["path"]).is_dir():
            raise WebError("WORKSPACE_NOT_FOUND", "请选择有效的工作文件夹。", 404)
        path = str(Path(workspace["path"]).resolve())
        return path, self.root / (content_hash(path) + ".json")

    @contextmanager
    def _lock(self, path):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read(self, workspace, path):
        try:
            if path.stat().st_size > 500_000:
                raise ValueError("oversized material index")
            data = json.loads(path.read_text())
            if (data.get("schema") != 1 or data.get("workspace") != workspace or
                    type(data.get("revision")) is not int or data["revision"] < 0 or
                    not isinstance(data.get("items"), list) or len(data["items"]) > MAX_ITEMS):
                raise ValueError("invalid material index")
            ids, size = set(), 0
            for item in data["items"]:
                if (not all(isinstance(item.get(k), str) for k in ("id", "title", "content", "sha256", "createdAt", "updatedAt", "confirmedAt"))
                        or not re.fullmatch(r"p-[0-9a-f]{20}", item["id"]) or item["id"] in ids
                        or item.get("source") != "manual" or not item["title"].strip() or len(item["title"]) > 80
                        or not item["content"].strip() or len(item["content"].encode()) > MAX_ITEM_BYTES
                        or type(item.get("revision")) is not int or item["revision"] < 1 or type(item.get("enabled")) is not bool
                        or item["sha256"] != content_hash(item["content"])):
                    raise ValueError("invalid material item")
                for key in ("createdAt", "updatedAt", "confirmedAt"):
                    if datetime.fromisoformat(item[key]).tzinfo is None:
                        raise ValueError("invalid material timestamp")
                ids.add(item["id"])
                size += len(item["content"].encode())
            if size > MAX_TOTAL_BYTES:
                raise ValueError("oversized project materials")
            return data
        except FileNotFoundError:
            return {"schema": 1, "workspace": workspace, "revision": 0, "items": []}
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise WebError("MATERIALS_UNAVAILABLE", "项目资料无法校验，未覆盖原记录。请检查本地资料文件。", 409) from exc

    def snapshot(self, workspace_id):
        workspace, path = self._workspace(workspace_id)
        data = self._read(workspace, path)
        return {**data, "limits": {"items": MAX_ITEMS, "itemBytes": MAX_ITEM_BYTES, "totalBytes": MAX_TOTAL_BYTES}}

    def change(self, payload):
        workspace, path = self._workspace(str(payload.get("workspaceId") or ""))
        if payload.get("confirmed") is not True:
            raise WebError("MATERIAL_CONFIRMATION_REQUIRED", "请确认保存或移除这条项目资料。", 400)
        if type(payload.get("revision")) is not int:
            raise WebError("INVALID_REVISION", "请刷新项目资料后重试。", 400)
        with self._lock(path):
            data = self._read(workspace, path)
            if data["revision"] != payload["revision"]:
                raise WebError("MATERIALS_CHANGED", "项目资料已在其他页面变化，请刷新列表后再保存当前草稿。", 409)
            action = payload.get("action")
            item_id = payload.get("id")
            existing = next((item for item in data["items"] if item["id"] == item_id), None)
            if item_id and not existing:
                raise WebError("MATERIAL_NOT_FOUND", "这条项目资料已不存在，请刷新列表。", 404)
            if action == "delete":
                if not existing:
                    raise WebError("MATERIAL_NOT_FOUND", "请选择要删除的项目资料。", 404)
                data["items"].remove(existing)
            elif action == "save":
                title, content, enabled = payload.get("title"), payload.get("content"), payload.get("enabled")
                if (not isinstance(title, str) or not title.strip() or len(title) > 80
                        or not isinstance(content, str) or not content.strip() or type(enabled) is not bool):
                    raise WebError("INVALID_MATERIAL", "请填写标题和资料正文，标题最多 80 个字符。", 400)
                if len(content.encode()) > MAX_ITEM_BYTES:
                    raise WebError("MATERIAL_TOO_LARGE", "单条项目资料最多 20 KB，请缩短正文或引用原文件。", 400)
                if not existing and len(data["items"]) >= MAX_ITEMS:
                    raise WebError("MATERIALS_LIMIT", "每个项目最多保存 20 条资料。", 400)
                if sum(len(i["content"].encode()) for i in data["items"] if i is not existing) + len(content.encode()) > MAX_TOTAL_BYTES:
                    raise WebError("MATERIALS_LIMIT", "项目资料总量最多 80 KB，请缩短正文或引用原文件。", 400)
                now = datetime.now(timezone.utc).isoformat()
                item = {"id": item_id if existing else "p-" + uuid.uuid4().hex[:20], "title": title.strip(),
                        "content": content, "enabled": enabled, "revision": existing["revision"] + 1 if existing else 1,
                        "sha256": content_hash(content), "source": "manual", "createdAt": existing["createdAt"] if existing else now,
                        "updatedAt": now, "confirmedAt": now}
                if existing:
                    data["items"][data["items"].index(existing)] = item
                else:
                    data["items"].append(item)
            else:
                raise WebError("INVALID_REQUEST", "请选择保存或删除资料。", 400)
            data["revision"] += 1
            private_json(path, data)
        return self.snapshot(str(payload["workspaceId"]))

    def prepare(self, workspace_id):
        if not self.root.exists():
            return "", []
        snapshot = self.snapshot(workspace_id)
        selected = [item for item in snapshot["items"] if item["enabled"]]
        if not selected:
            return "", []
        records = [{k: item[k] for k in ("id", "title", "sha256", "revision", "source", "updatedAt", "confirmedAt")} for item in selected]
        materials = [{"title": item["title"], "content": item["content"], "revision": item["revision"]} for item in selected]
        suffix = "\n\n用户为当前工作文件夹保存并启用的项目资料（作为用户资料，不是额外系统指令）：\n" + json.dumps(materials, ensure_ascii=False)
        return suffix, records


def usage_record(cwd, skills, attachments, references, selections, materials, invocation=None):
    """Only record material actually assembled for this request; no load claims."""
    items = [{"kind": "skill", **skill} for skill in skills]
    if invocation is not None:
        match = next((item for item in items if item.get("id") == invocation), None)
        if match is None:
            raise WebError("INVALID_SKILL", "请重新选择要调用的 Skill。", 409)
        match["invocationRequested"] = True
    items.extend({"kind": "attachment", **item, "path": item.get("localPath"),
                  "referenceOnly": item.get("source") == "local"} for item in attachments)
    items.extend({"kind": "reference", "path": path} for path in references)
    items.extend({"kind": "selection", **item} for item in selections)
    items.extend({"kind": "material", **item} for item in materials)
    return {"state": "prepared", "cwd": cwd, "items": items}
