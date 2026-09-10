from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mms_web.errors import WebError
from mms_web.skills import SkillCatalog
from mms_web.starter_skills import starter_skills


def test_new_user_gets_bundled_skills_without_installing_global_entries(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    home = tmp_path / 'home'
    home.mkdir()
    catalog = SkillCatalog(SimpleNamespace(_workspaces=lambda: [{'id': 'p', 'path': str(project)}]), tmp_path / 'state')
    with patch('mms_web.skills.real_home', return_value=home):
        result = catalog.snapshot('p')
        skills = result['skills']
        assert {s['id'] for s in skills} >= {s['id'] for s in starter_skills()}
        # Bundled session skills (weber, grill-me, toon) show as built-in too; nothing else leaks in.
        extra = [s for s in skills if not s.get('starter')]
        assert extra and all(s['source'] == 'Pilot 内置' for s in extra)
        assert {s['name'] for s in extra} <= {'weber', 'grill-me', 'toon'}
        assert not result['diagnostics']
        prompt, selected = catalog.prepare(['pilot:offduty', 'pilot:offduty'], 'p')
        assert len(selected) == 1 and selected[0]['source'] == 'Pilot 内置'
        assert '保存进度' in prompt and '不会关闭会话或进程' in prompt
        assert len(selected[0]['sha256']) == 64
        assert list(home.iterdir()) == [] and list(project.iterdir()) == []
        with pytest.raises(WebError, match='所选 skill 已不在'):
            catalog.prepare(['pilot:not-shipped'], 'p')


def test_custom_same_name_keeps_its_own_identity_and_prompt(tmp_path):
    project = tmp_path / 'project'
    skill = project / '.agents/skills/offduty/SKILL.md'
    skill.parent.mkdir(parents=True)
    skill.write_text('---\nname: offduty\ndescription: My custom checkpoint\n---\nCustom instruction marker.\n')
    catalog = SkillCatalog(SimpleNamespace(_workspaces=lambda: [{'id': 'p', 'path': str(project)}]), tmp_path / 'state')
    with patch('mms_web.skills.real_home', return_value=tmp_path / 'home'):
        found = [s for s in catalog.snapshot('p')['skills'] if s['name'] == 'offduty']
        assert len(found) == 2
        assert found[0]['source'] == '项目' and found[1]['id'] == 'pilot:offduty'
        prompt, selected = catalog.prepare([found[0]['id']], 'p')
        assert 'Custom instruction marker.' in prompt and len(selected) == 1
        assert selected[0]['filePath'] == str(skill)


def test_every_starter_has_portable_content_and_explicit_selection():
    entries = starter_skills()
    assert len(entries) == 5
    for entry in entries:
        body = Path(entry['filePath']).read_text()
        assert 'disable-model-invocation: true' in body
        assert '/Users/xin/' not in body
        assert entry['manualOnly'] and entry['example'] and entry['title']


def _external_home(tmp_path):
    home = tmp_path / 'home'
    for root, name in (('.claude/skills', 'claude-only'), ('.codex/skills', 'codex-only'),
                       ('.config/opencode/skills', 'opencode-only'), ('.agents/skills', 'shared-only')):
        skill = home / root / name / 'SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text(f'---\nname: {name}\ndescription: from {root}\n---\nBody.\n')
    return home


def test_external_skill_roots_stay_hidden_until_merge_is_enabled(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    home = _external_home(tmp_path)
    catalog = SkillCatalog(SimpleNamespace(_workspaces=lambda: [{'id': 'p', 'path': str(project)}]), tmp_path / 'state')
    assert catalog.preferences() == {'mergeExternal': False}
    with patch('mms_web.skills.real_home', return_value=home):
        names = {s['name'] for s in catalog.snapshot('p')['skills']}
        assert 'shared-only' in names
        assert not {'claude-only', 'codex-only', 'opencode-only'} & names
        assert catalog.set_preferences({'mergeExternal': True}) == {'mergeExternal': True}
        assert catalog.preferences() == {'mergeExternal': True}
        merged = {s['name']: s for s in catalog.snapshot('p')['skills']}
        assert {'claude-only', 'codex-only', 'opencode-only', 'shared-only'} <= set(merged)
        assert merged['claude-only']['source'] == 'Claude 全局'
        assert merged['codex-only']['source'] == 'Codex 全局'
        assert merged['opencode-only']['source'] == 'OpenCode 全局'
        assert catalog.set_preferences({'mergeExternal': 'yes'}) == {'mergeExternal': False}
        assert catalog.set_preferences(None) == {'mergeExternal': False}
    # Reading never writes into the real home; the switch lives under the Pilot state root.
    assert sorted(p.name for p in home.iterdir()) == ['.agents', '.claude', '.codex', '.config']
    assert (tmp_path / 'state/skill-reader/preferences.json').is_file()


def test_project_and_shared_skills_override_merged_external_same_name(tmp_path):
    project = tmp_path / 'project'
    shared = project / '.agents/skills/claude-only/SKILL.md'
    shared.parent.mkdir(parents=True)
    shared.write_text('---\nname: claude-only\ndescription: project wins\n---\nProject body.\n')
    home = _external_home(tmp_path)
    catalog = SkillCatalog(SimpleNamespace(_workspaces=lambda: [{'id': 'p', 'path': str(project)}]), tmp_path / 'state')
    catalog.set_preferences({'mergeExternal': True})
    with patch('mms_web.skills.real_home', return_value=home):
        found = [s for s in catalog.snapshot('p')['skills'] if s['name'] == 'claude-only']
        assert len(found) == 1 and found[0]['source'] == '项目'
        assert found[0]['overrides'] == [str(home / '.claude/skills/claude-only')]


def test_bundled_session_skills_show_as_builtin_and_yield_to_user_copies(tmp_path):
    from mms_web.skills import effective_entries

    bundled_weber = tmp_path / "bundle" / "weber"
    bundled_grill = tmp_path / "bundle" / "grill-me"
    home = tmp_path / "home"
    user_weber = home / ".agents" / "skills" / "weber"
    project = tmp_path / "project"
    project.mkdir()
    for skill in (bundled_weber, bundled_grill, user_weber):
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {skill.name}\ndescription: x\n---\n", encoding="utf-8")
    with patch("mms_web.skills.bundled_skill_roots", return_value=[("weber", str(bundled_weber)), ("grill-me", str(bundled_grill))]):
        found = {Path(e["path"]).name: e for e in effective_entries(str(project), home)}
    assert found["grill-me"]["source"] == "Pilot 内置" and found["grill-me"]["path"] == str(bundled_grill)
    assert found["weber"]["source"] == "共享" and found["weber"]["path"] == str(user_weber)
    assert found["weber"]["overrides"] == [str(bundled_weber)]


def test_bundled_skill_roots_come_from_the_pi_overlay_contract(tmp_path):
    import mms_pi_support
    from mms_web import skills

    bundled = tmp_path / "grill-me"
    bundled.mkdir()
    (bundled / "SKILL.md").write_text("# grill-me\n", encoding="utf-8")
    with patch.object(mms_pi_support, "_resolve_weber_root", return_value=""), \
         patch.object(mms_pi_support, "_resolve_grill_me_root", return_value=str(bundled)), \
         patch.object(mms_pi_support, "_resolve_toon_root", return_value=str(tmp_path / "missing")):
        assert skills.bundled_skill_roots() == [("grill-me", str(bundled))]
