from pathlib import Path
from types import SimpleNamespace
import pytest
from mms_web.workspace_search import search_workspaces
from mms_web.errors import WebError


def test_search_uses_zoxide_without_shell_and_deduplicates(tmp_path, monkeypatch):
    recent = tmp_path / 'multi-model-switch'; recent.mkdir()
    other = tmp_path / 'runtimia'; other.mkdir()
    catalog = SimpleNamespace(_workspaces=lambda: [{'id': 'w-known', 'name': '我的 multi', 'path': str(recent)}])
    monkeypatch.setattr('mms_web.workspace_search.shutil.which', lambda _: '/fake/zoxide')
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=f'{recent}\n{other}\n{tmp_path}/missing\n')
    monkeypatch.setattr('mms_web.workspace_search.subprocess.run', run)
    result = search_workspaces(catalog, {'query': 'multi'})['workspaces']
    assert [w['path'] for w in result] == [str(recent), str(other)]
    assert result[0]['id'] == 'w-known'
    assert calls[0][0] == ['/fake/zoxide', 'query', '--list', '--', 'multi']
    assert 'shell' not in calls[0][1] and calls[0][1]['timeout'] == 2


def test_search_still_finds_known_and_explicit_paths_without_zoxide(tmp_path, monkeypatch):
    folder = tmp_path / 'runtimia'; folder.mkdir()
    catalog = SimpleNamespace(_workspaces=lambda: [{'id': 'r', 'name': 'Runtimia', 'path': str(folder)}])
    monkeypatch.setattr('mms_web.workspace_search.shutil.which', lambda _: None)
    monkeypatch.setattr('mms_web.workspace_search.os.access', lambda *_: False)
    assert search_workspaces(catalog, {'query': 'RUNTI'})['workspaces'][0]['id'] == 'r'
    assert search_workspaces(catalog, {'query': str(folder)})['workspaces'][0]['path'] == str(folder)
    assert search_workspaces(catalog, {'query': 'not found'})['workspaces'] == []
    with pytest.raises(WebError): search_workspaces(catalog, {'query': 'bad\x00query'})
