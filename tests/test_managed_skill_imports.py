from __future__ import annotations

import json
import os
from pathlib import Path

import mms_core
import mms_launchers


def _write_skill(root: Path, name: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(f"name: {name}\n# {name}\n", encoding="utf-8")
    return root


def test_import_managed_skill_dry_run_defaults_to_symlink(monkeypatch, tmp_path):
    source_root = _write_skill(tmp_path / "skill-source", "demo-skill")
    managed_root = tmp_path / "managed-assets"
    monkeypatch.setattr(mms_core, "managed_assets_root", lambda: str(managed_root))

    result = mms_core.import_managed_skill(str(source_root / "SKILL.md"), dry_run=True)

    assert result["ok"] is True
    assert result["mode"] == "symlink"
    assert result["status"] == "would_import"
    assert result["skill_name"] == "demo-skill"
    assert result["target_root"] == str(managed_root / "skills" / "demo-skill")
    assert not (managed_root / "skills" / "demo-skill").exists()


def test_handle_config_assets_import_skill_writes_json_result(monkeypatch, tmp_path, capsys):
    source_root = _write_skill(tmp_path / "skill-source", "demo-skill")
    managed_root = tmp_path / "managed-assets"
    monkeypatch.setattr(mms_core, "managed_assets_root", lambda: str(managed_root))

    mms_core.handle_config({}, ["assets.import-skill", str(source_root), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["status"] == "imported"
    assert payload["skill_name"] == "demo-skill"
    assert os.path.islink(managed_root / "skills" / "demo-skill")


def test_managed_dynamic_skill_entries_only_scan_skills_surface(monkeypatch, tmp_path):
    managed_root = tmp_path / "managed-assets"
    _write_skill(managed_root / "skills" / "demo-skill", "demo-skill")
    _write_skill(managed_root / "packages" / "ignored-package", "ignored-package")
    monkeypatch.setattr(mms_launchers, "managed_assets_enabled", lambda: True)
    monkeypatch.setattr(mms_launchers, "managed_assets_root", lambda: str(managed_root))

    entries = mms_launchers._managed_dynamic_skill_entries()

    assert entries == [{"name": "demo-skill", "root": str(managed_root / "skills" / "demo-skill")}]


def test_overlay_managed_dynamic_skill_entries_merges_existing_session_skills(monkeypatch, tmp_path):
    parent_dir = tmp_path / "parent"
    session_home = tmp_path / "session"
    managed_root = tmp_path / "managed-assets"
    imported_skill = _write_skill(managed_root / "skills" / "demo-skill", "demo-skill")
    monkeypatch.setattr(mms_launchers, "managed_assets_enabled", lambda: True)
    monkeypatch.setattr(mms_launchers, "managed_assets_root", lambda: str(managed_root))

    mms_launchers._overlay_managed_dynamic_skill_entries(str(parent_dir), str(session_home))

    linked_skill = parent_dir / "skills" / "demo-skill"
    assert os.path.islink(linked_skill)
    assert linked_skill.resolve() == imported_skill.resolve()


def test_build_confirm_preview_catalog_includes_managed_dynamic_skills(monkeypatch, tmp_path):
    skill_root = _write_skill(tmp_path / "managed-assets" / "skills" / "demo-skill", "demo-skill")

    monkeypatch.setattr(mms_launchers, "_build_codex_session_hooks", lambda _settings: {"hooks": {}})
    monkeypatch.setattr(mms_launchers, "_managed_dynamic_skill_entries", lambda: [{"name": "demo-skill", "root": str(skill_root)}])
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_agent_browser_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_codegraph_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_auto_github_contributor_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_caveman_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_nsr_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_ecc_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_omc_root", lambda: "")

    preview = mms_core._build_confirm_preview_catalog("codex", {"auth_mode": "provider"})

    always_titles = {item["title"] for item in preview["skills"]["always"]}
    assert "demo-skill" in always_titles
    skill_item = next(item for item in preview["skills"]["always"] if item["title"] == "demo-skill")
    assert any(label == "路径" and value.endswith("SKILL.md") for label, value in skill_item["details"])
