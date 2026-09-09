"""Real HTTP/process handoff and rollback; no GitHub/provider/config access."""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
RUNNER=ROOT/'tests/fixtures/mms_web/update_runner.py'


def copy_candidate(destination, *, broken=False):
    destination.mkdir(parents=True)
    files=set(subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines())
    files.update(str(p.relative_to(ROOT)) for p in (ROOT/'mms_web').rglob('*.py'))
    files.update(str(p.relative_to(ROOT)) for p in (ROOT/'mms_web_static').rglob('*') if p.is_file())
    for name in files:
        source=ROOT/name
        if source.is_file() and not source.is_symlink():
            target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    (destination/'mms_version.py').write_text('VERSION = "99.0.0"\n')
    manifest=destination/'mms_web_static/build.json';value=json.loads(manifest.read_text());value['version']='99.0.0';manifest.write_text(json.dumps(value))
    if broken:(destination/'mms_web/__main__.py').write_text('raise RuntimeError("fixture startup failure")\n')


def wait_for(fn, timeout=40):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        try:
            result=fn()
            if result:return result
        except (OSError,ValueError,KeyError):pass
        time.sleep(.1)
    raise AssertionError('timed out waiting for fixture state')


@pytest.mark.parametrize('broken',[False,True])
def test_actual_handoff_or_rollback_preserves_custom_state_cwd_and_history(tmp_path,broken):
    state=tmp_path/'custom-state';candidate=state/'updates/versions/fixture/source'
    copy_candidate(candidate,broken=broken)
    for folder in ('sessions','runtimes/r','config','attachments'):(state/folder).mkdir(parents=True,exist_ok=True)
    (state/'runtimes/r/resume.json').write_text('{}');(state/'runtimes/r/conversation.jsonl').write_text('original-native-history\n')
    (state/'attachments/proof.txt').write_text('original attachment')
    (state/'sessions/s-fixture.json').write_text(json.dumps({'schema':1,'session':{'id':'s-fixture','runtimeRoot':str(state/'runtimes/r'),'cwd':str(tmp_path),'workspaceId':'fixture','harness':'pi'},'state':'completed','events':[{'id':'original-event','kind':'user','text':'Keep my original progress','sequence':1}]}))
    (state/'updates/check.json').write_text(json.dumps({'latest':{'tag':'v99.0.0'}}))
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env=os.environ.copy()
    home=tmp_path/'home';home.mkdir()
    for key in ('HOME','MMS_REAL_HOME','REAL_HOME','ORIGINAL_HOME'):env[key]=str(home)
    for key in ('MMS_CONFIG_ROOT','MMS_PREVIEW_MODE','XDG_DATA_HOME','XDG_CONFIG_HOME','MMS_WEB_PROBATION'):env.pop(key,None)
    env.update(PYTHONPATH=str(ROOT),MMS_WEB_UPDATE_CHECK='0',MMS_WEB_SKIP_ACTIVE='1',MMS_UPDATE_FIXTURE_SOURCE=str(candidate))
    def request(path,body=None,csrf=''):
        req=urllib.request.Request(f'http://127.0.0.1:{port}/api/v1/{path}',data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-MMS-CSRF':csrf})
        with urllib.request.urlopen(req,timeout=3) as response:return json.load(response)
    log=(tmp_path/'old-server.log').open('wb')
    old=subprocess.Popen([sys.executable,str(RUNNER),'--port',str(port),'--state-root',str(state)],cwd=tmp_path,env=env,stdout=log,stderr=log)
    new_pid=None
    try:
        boot=wait_for(lambda:request('bootstrap'));before=request('update/identity')
        started=request('update/start',{'target':'v99.0.0'},boot['csrfToken'])
        assert started['operation']['phase'] in ('preparing','backing-up','restarting')
        expected='rolled-back' if broken else 'complete'
        result=wait_for(lambda:(s if (s:=request('update'))['operation']['phase']==expected else None))
        after=request('update/identity');new_pid=after['processId']
        assert new_pid!=old.pid
        assert result['currentVersion']==(before['version'] if broken else '99.0.0')
        assert after['sessions']==before['sessions']
        assert (state/'runtimes/r/conversation.jsonl').read_text()=='original-native-history\n'
        assert (state/'attachments/proof.txt').read_text()=='original attachment'
        assert request('sessions/s-fixture')['session']['capabilities']['send']
        backups=list((state/'updates/operations').glob('*/backup/sessions/s-fixture.json'))
        assert len(backups)==1 and 'original-event' in backups[0].read_text()
        old.wait(timeout=10)
    finally:
        if new_pid:
            try:os.kill(new_pid,signal.SIGTERM)
            except ProcessLookupError:pass
        else:
            try:
                info=request('update/identity')
                if info['processId']!=old.pid:os.kill(info['processId'],signal.SIGTERM)
            except Exception:pass
        if old.poll() is None:old.terminate();old.wait(timeout=10)
        log.close()
