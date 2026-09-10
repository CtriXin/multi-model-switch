import base64
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from mms_web.files import FileService
from mms_web.errors import WebError


def test_large_original_is_referenced_not_copied_or_inlined(tmp_path):
    files = FileService(None, tmp_path / 'state')
    path = tmp_path / 'large.json'
    # Sparse file far larger than either previous upload cap; reference size is irrelevant.
    with path.open('wb') as stream:
        stream.write(b'{"data":"')
        stream.truncate(128 * 1024 * 1024)
    item = files.reference_local({'paths': [str(path)]})['attachments'][0]
    assert item['source'] == 'local' and item['localPath'] == str(path)
    assert {p.name for p in (files.root / item['id']).iterdir()} == {'meta.json'}
    images, items, prompt = files.prepare([item['id']], '', [])
    assert images == [] and items == [item] and len(prompt) < 1000
    assert str(path) in prompt
    path.write_text('{"updated":true}')
    assert files.preview_attachment(item['id'])['content'] == '{"updated":true}'
    assert files.prepare([item['id']], '', [])[1][0]['size'] == path.stat().st_size
    path.unlink()
    with pytest.raises(WebError, match='原文件已移动或删除'):
        files.prepare([item['id']], '', [])


def test_image_reference_previews_without_prompt_image_copy(tmp_path):
    files = FileService(None, tmp_path / 'state')
    path = tmp_path / 'image.png'; data = b'\x89PNG\r\n\x1a\n' + b'fixture'
    path.write_bytes(data)
    item = files.reference_local({'paths': [str(path)]})['attachments'][0]
    preview = files.preview_attachment(item['id'])
    assert preview['dataUrl'] == 'data:image/png;base64,' + base64.b64encode(data).decode()
    assert files.prepare([item['id']], '', [])[0] == []
    assert path.read_bytes() == data
    assert not (files.root / item['id'] / 'content').exists()


def test_reference_validation_and_picker_cancellation(tmp_path):
    files = FileService(None, tmp_path / 'state')
    path = tmp_path / 'data.json'; path.write_text('{}')
    with pytest.raises(WebError): files.reference_local({'paths': ['relative.json']})
    with pytest.raises(WebError): files.reference_local({'paths': [str(path), str(tmp_path / 'missing')]})
    assert not files.root.exists()
    with patch('mms_web.files.sys.platform', 'darwin'), patch('mms_web.files.subprocess.run', return_value=SimpleNamespace(returncode=1,stderr='User canceled (-128)',stdout='')):
        assert files.choose_local({}) == {'attachments': []}
    with patch('mms_web.files.sys.platform', 'darwin'), patch('mms_web.files.subprocess.run', return_value=SimpleNamespace(returncode=0,stderr='',stdout=json.dumps([str(path)]))):
        result = files.choose_local({})
        assert result['attachments'][0]['localPath'] == str(path)
    for bad in ['l-../../etc/passwd', 'l-' + 'x' * 32]:
        with pytest.raises(WebError): files.local_attachment(bad)


def test_dropped_file_becomes_reusable_project_path_without_inlining(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    catalog = SimpleNamespace(_workspaces=lambda: [{'id': 'project', 'path': str(project)}])
    files = FileService(catalog, tmp_path / 'state')
    data = b'{"data":"' + b'x' * (1300 * 1024) + b'"}'
    payload = {'workspaceId': 'project', 'name': '../../dataset.json', 'data': base64.b64encode(data).decode()}
    first = files.import_to_workspace(payload)
    second = files.import_to_workspace(payload)
    path = Path(first['localPath'])
    assert path.is_relative_to(project / '.pilot/attachments')
    assert path.read_bytes() == data and path != Path(second['localPath'])
    assert path.stat().st_mode & 0o777 == 0o600
    images, _, prompt = files.prepare([first['id']], 'project', [])
    assert not images and str(path) in prompt and len(prompt) < 1000
    # A later session can refer to the same ordinary file after state is reopened.
    reopened = FileService(catalog, tmp_path / 'later-state')
    later = reopened.reference_local({'paths': [str(path)]})['attachments'][0]
    assert reopened.prepare([later['id']], 'project', [])[1][0]['localPath'] == str(path)


@pytest.mark.parametrize('part', ['.pilot', 'attachments'])
def test_dropped_file_cannot_follow_project_symlinks(tmp_path, part):
    project = tmp_path / 'project'; project.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    if part == '.pilot': (project / part).symlink_to(outside, target_is_directory=True)
    else:
        (project / '.pilot').mkdir()
        (project / '.pilot' / part).symlink_to(outside, target_is_directory=True)
    files = FileService(SimpleNamespace(_workspaces=lambda: [{'id': 'p', 'path': str(project)}]), tmp_path / 'state')
    with pytest.raises(WebError, match='不能保存附件'):
        files.import_to_workspace({'workspaceId': 'p', 'name': 'test.txt', 'data': 'aGk='})
    assert not list(outside.iterdir())


def test_directory_reference_is_a_path_without_copy_or_workspace_change(tmp_path):
    directory = tmp_path / 'project with spaces'; directory.mkdir()
    nested = directory / 'nested'; nested.mkdir()
    (nested / 'private.txt').write_text('not copied')
    path = tmp_path / 'file.txt'; path.write_text('file')
    files = FileService(None, tmp_path / 'state')
    result = files.reference_local({'paths': [str(directory) + '/', str(path), str(directory)]})
    assert result['directories'] == [str(directory)]
    assert [a['localPath'] for a in result['attachments']] == [str(path)]
    assert not list(files.root.rglob('private.txt'))
    assert not (directory / '.pilot').exists()
    assert (nested / 'private.txt').read_text() == 'not copied'
    assert files.prepare([result['attachments'][0]['id']], '', [])[1][0]['localPath'] == str(path)


def test_directory_and_missing_file_are_validated_before_metadata(tmp_path):
    files = FileService(None, tmp_path / 'state')
    with pytest.raises(WebError):
        files.reference_local({'paths': [str(tmp_path), str(tmp_path / 'missing')]})
    assert not files.root.exists()


def test_imported_attachments_are_pruned_after_30_days_unless_a_session_mentions_them(tmp_path):
    import os
    import time
    from mms_web.files import ATTACHMENT_KEEP_DAYS

    state = tmp_path / 'state'
    files = FileService(None, state)
    workspace = tmp_path / 'project'
    folder = workspace / '.pilot' / 'attachments'
    folder.mkdir(parents=True)
    old_unused = folder / 'aaaa-old.txt'
    old_used = folder / 'bbbb-used.txt'
    fresh = folder / 'cccc-fresh.txt'
    for path in (old_unused, old_used, fresh):
        path.write_text('x', encoding='utf-8')
    stale = time.time() - (ATTACHMENT_KEEP_DAYS + 1) * 86400
    os.utime(old_unused, (stale, stale))
    os.utime(old_used, (stale, stale))
    (state / 'sessions').mkdir(parents=True)
    (state / 'sessions' / 's-1.json').write_text(json.dumps({'events': [{'kind': 'user', 'text': f'看看 {old_used}'}]}), encoding='utf-8')

    removed = files.prune_workspace_attachments(workspace)

    assert removed == [str(old_unused)]
    assert old_used.exists() and fresh.exists()
    # Without any attachments folder the call is a no-op.
    assert files.prune_workspace_attachments(tmp_path / 'empty') == []
