import io
import tarfile
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from mms_web.update_safety import backup_state, file_manifest, session_safety
from mms_web.update_stage import unpack_release, validate_bundle


def fixture_session(**kwargs):
    return SimpleNamespace(lock=threading.RLock(), alive=lambda: True, can_resume=lambda: True,
        approvals={}, pending_prompts={}, state='idle', meta={'id':'fixture'},
        driver=Mock(request=Mock(return_value={'success':True, 'data':{'isStreaming':False, 'isCompacting':False, 'pendingMessageCount':0}})), **kwargs)


def test_native_state_busy_unknown_approval_queue_and_archived_are_not_skipped():
    s = fixture_session()
    service = SimpleNamespace(_lock=threading.RLock(), _sessions={'fixture':s}, _requests={})
    assert not session_safety(service)['blockers']
    for data in ({'isStreaming':True}, {'isCompacting':True}, {'pendingMessageCount':1}, None):
        s.driver.request.return_value={'success':True,'data':data}
        assert session_safety(service)['blockers']
    s.driver.request.return_value={'success':True,'data':{'isStreaming':False,'isCompacting':False,'pendingMessageCount':0}}
    s.approvals={'approval':{}}
    assert session_safety(service)['blockers']
    s.approvals={};s.pending_prompts={'message':'queued'}
    assert session_safety(service)['blockers']
    s.pending_prompts={};s.state='running';s.meta['archived']=True
    assert session_safety(service)['blockers']
    s.state='idle';service._requests={'r':{'pending':True}}
    assert session_safety(service)['blockers']


def test_backup_preserves_all_sessions_runtimes_attachments_and_external_links(tmp_path):
    root=tmp_path/'state';root.mkdir()
    for name in ['sessions/one.json','runtimes/r/conversation.jsonl','runtimes/r/resume.json','attachments/image.png','config/config.toml','workspaces.json']:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name)
    (root/'external').symlink_to(tmp_path/'not-copied')
    (root/'updates').mkdir();(root/'updates/cached').write_text('not recursive')
    old=file_manifest(root)
    destination=root/'updates/backups/one'
    assert backup_state(root,destination)==old
    assert file_manifest(root)==old
    assert file_manifest(destination)==old
    assert not (destination/'updates').exists()


def make_archive(path, members):
    with tarfile.open(path,'w:gz') as tf:
        for name,kind,content in members:
            info=tarfile.TarInfo(name);info.type=kind
            if kind==tarfile.REGTYPE: info.size=len(content)
            else: info.linkname=content
            tf.addfile(info, io.BytesIO(content) if kind==tarfile.REGTYPE else None)


@pytest.mark.parametrize('name,kind,value', [('release/../../escape',tarfile.REGTYPE,b'bad'),('release/link',tarfile.SYMTYPE,'/etc'),('release/hard',tarfile.LNKTYPE,'release/other')])
def test_archive_rejects_escape_and_links(tmp_path,name,kind,value):
    archive=tmp_path/'archive.tgz';make_archive(archive,[(name,kind,value)])
    with pytest.raises(ValueError):unpack_release(archive,tmp_path/'unpack')
    assert not (tmp_path/'escape').exists()


def test_archive_skips_only_the_optional_agent_rules_link(tmp_path):
    archive=tmp_path/'archive.tgz';make_archive(archive,[('release/file',tarfile.REGTYPE,b'good'),('release/agent-rules',tarfile.SYMTYPE,'../rules')])
    unpack_release(archive,tmp_path/'unpack')
    assert (tmp_path/'unpack/file').read_bytes()==b'good'
    assert not (tmp_path/'unpack/agent-rules').is_symlink()


def test_bundle_integrity_and_matching_version_are_required(tmp_path):
    import hashlib,json
    public=tmp_path/'mms_web_static';public.mkdir();(public/'index.html').write_text('fixture')
    (tmp_path/'mms_web').mkdir();(tmp_path/'mms_web/update_handoff.py').write_text('PROTOCOL = 1')
    manifest={'version':'9.0.0','files':{'index.html':hashlib.sha256(b'fixture').hexdigest()}}
    (public/'build.json').write_text(json.dumps(manifest))
    validate_bundle(tmp_path,'v9.0.0')
    with pytest.raises(ValueError):validate_bundle(tmp_path,'v8.0.0')
    (public/'index.html').write_text('tampered')
    with pytest.raises(ValueError):validate_bundle(tmp_path,'v9.0.0')
