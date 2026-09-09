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
        assert {s['id'] for s in skills} == {s['id'] for s in starter_skills()}
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
