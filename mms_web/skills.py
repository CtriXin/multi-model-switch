"""Read the same effective skills as MMS Pi, using Pi's native parser."""
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from .drivers.launch_bridge import pi_runtime
from .errors import WebError
from .runtime import real_home
from .starter_skills import starter_skills


def effective_paths(cwd, home):
    return [item["path"] for item in effective_entries(cwd, home)]


def effective_entries(cwd, home):
    # Matches mms_pi_support._pi_materialize_skill_overlay: top-level names
    # override global -> repository root -> cwd, with .agents after .pi.
    directories = []
    current = Path(cwd).resolve()
    while True:
        directories.append(current)
        if (current / ".git").exists() or current.parent == current:
            break
        current = current.parent
    sources = [(Path(home) / ".agents/skills", False, "共享")]
    for directory in reversed(directories):
        sources.extend([(directory / ".pi/skills", True, "项目"), (directory / ".agents/skills", False, "项目")])
    entries = {}
    for root, markdown, scope in sources:
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if not entry.name.startswith(".") and not (entry.is_file() and not markdown):
                previous = entries.get(entry.name)
                if previous and previous["path"] == str(entry):
                    continue
                entries[entry.name] = {"path": str(entry), "source": scope, "sourceRoot": str(root),
                                       "overrides": [*previous["overrides"], previous["path"]] if previous else []}
    return list(entries.values())


class SkillCatalog:
    def __init__(self, catalog, state_root):
        self.catalog, self.root = catalog, Path(state_root) / "skill-reader"

    def snapshot(self, workspace_id):
        workspace = next((w for w in self.catalog._workspaces() if w["id"] == workspace_id), None)
        if not workspace or not Path(workspace["path"]).is_dir():
            raise WebError("WORKSPACE_NOT_FOUND", "请选择有效的工作文件夹。", 404)
        executable, node = pi_runtime()
        if not node:
            raise WebError("SKILLS_UNAVAILABLE", "需要可用的 Pi 才能读取 skills。", 409)
        dist = next((p for p in Path(executable).resolve().parents if p.name == "dist"), None)
        module = dist / "core/skills.js" if dist else Path("/nonexistent")
        if not module.is_file():
            raise WebError("SKILLS_UNAVAILABLE", "当前 Pi 版本未提供 skills 读取接口。", 409)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        origins = effective_entries(workspace["path"], real_home())
        with tempfile.TemporaryDirectory(dir=self.root, prefix="overlay-") as temporary:
            overlay = Path(temporary)
            for origin in origins:
                entry = origin["path"]
                (overlay / Path(entry).name).symlink_to(entry)
            result = subprocess.run([node, str(Path(__file__).with_name("skill_catalog.mjs"))],
                input=json.dumps({"module":str(module), "cwd":workspace["path"], "agentDir":str(self.root), "paths":[str(overlay)]}),
                text=True, capture_output=True, timeout=15, env={**os.environ, "HOME":str(self.root)})
        if result.returncode:
            raise WebError("SKILLS_UNAVAILABLE", "无法读取当前 Pi skills，请检查安装。", 409)
        result = json.loads(result.stdout)
        for skill in result["skills"]:
            skill["id"] = hashlib.sha256(skill["filePath"].encode()).hexdigest()[:24]
            actual = Path(skill["filePath"]).resolve()
            matches = [origin for origin in origins if actual == Path(origin["path"]).resolve()
                       or actual.is_relative_to(Path(origin["path"]).resolve())]
            if len(matches) == 1:
                skill.update({key: matches[0][key] for key in ("source", "sourceRoot", "overrides")})
            else:
                skill.update(source="多个入口" if matches else "来源未确认", sourceRoot="", overrides=[])
        # Keep custom installed names first for existing slash commands. Built-in
        # entries have stable, separate IDs and are only injected when selected.
        result["skills"].extend(starter_skills())
        return result

    def prepare(self, ids, workspace_id):
        if not isinstance(ids, list) or len(ids) > 20 or any(not isinstance(i, str) for i in ids):
            raise WebError("INVALID_SKILLS", "每次最多选择 20 个 skills。", 400)
        if not ids:
            return "", []
        available = {s["id"]: s for s in self.snapshot(workspace_id)["skills"]}
        parts, selected = [], []
        for id_ in dict.fromkeys(ids):
            if id_ not in available:
                raise WebError("SKILL_NOT_FOUND", "所选 skill 已不在当前工作文件夹中，请重新选择。", 409)
            skill = available[id_]
            path = Path(skill["filePath"])
            if path.stat().st_size > 100_000:
                raise WebError("SKILL_TOO_LARGE", f"{skill['name']} 超过 100 KB，请使用文件引用。", 400)
            body = path.read_text(encoding="utf-8")
            parts.append(f"\n\n用户为本次任务选择 skill：{skill['name']}\nSkill 文件：{path}\n相对路径基准：{skill['baseDir']}\n\n{body}")
            selected.append({**{k:skill[k] for k in ("id", "name", "source", "filePath", "baseDir", "sourceRoot", "overrides")},
                             "sha256": hashlib.sha256(body.encode()).hexdigest()})
        content = "".join(parts)
        if len(content.encode()) > 200_000:
            raise WebError("SKILLS_TOO_LARGE", "所选 skills 内容过多，请减少选择。", 400)
        return content, selected
