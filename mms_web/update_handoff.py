"""Detached update guardian. Only probationary Web processes are stopped on failure."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from .runtime import private_json
from .updates import read_json
from .update_stage import candidate_environment

PROTOCOL = 1


def path_identity(source, state, config, cwd):
    return hashlib.sha256('|'.join(str(Path(p).resolve()) for p in (source, state, config, cwd)).encode()).hexdigest()


def session_inventory(service):
    if service is None:
        return {}
    with service._lock:
        sessions = list(service._sessions.values())
    result = {}
    for session in sessions:
        with session.lock:
            result[session.meta['id']] = {'runtime': session.meta.get('runtimeRoot'), 'resume': session.can_resume(), 'events': [e['id'] for e in session.events]}
    return result


def inventory_matches(expected, actual):
    if not isinstance(actual, dict) or set(actual) != set(expected):
        return False
    for sid, previous in expected.items():
        current = actual[sid]
        if not isinstance(current, dict):
            return False
        if current.get('runtime') != previous.get('runtime') or current.get('resume') != previous.get('resume'):
            return False
        if not set(previous.get('events', [])).issubset(current.get('events', [])):
            return False
    return True


def http(port, path, body=None, csrf=''):
    req = urllib.request.Request(f'http://127.0.0.1:{port}/api/v1/{path}', data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type':'application/json', 'X-MMS-CSRF':csrf})
    with urllib.request.urlopen(req, timeout=3) as response:
        return json.load(response)


def launch(spec, source, *, probation):
    env = candidate_environment(Path(source))
    env['MMS_WEB_UPDATE_CHECK'] = spec['updateCheck']
    env['MMS_WEB_INSTANCE'] = spec['id'] if probation else spec['id'] + '-rollback'
    if probation:
        env['MMS_WEB_PROBATION'] = spec['token']
    else:
        env.pop('MMS_WEB_PROBATION', None)
    cmd = [spec['python'], '-P', '-m', 'mms_web', '--port', str(spec['port']), '--state-root', spec['state'], '--static-root', str(Path(source) / 'mms_web_static')]
    if Path(spec['config']).is_dir():
        cmd += ['--config-root', spec['config']]
    with Path(spec['log']).open('ab') as log:
        return subprocess.Popen(cmd, cwd=spec['cwd'], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)


def ready(spec, process, source, *, probation):
    expected = path_identity(source, spec['state'], spec['config'], spec['cwd'])
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return None
        try:
            data = http(spec['port'], 'update/identity')
            instance = spec['id'] if probation else spec['id'] + '-rollback'
            if (data.get('instance') == instance and data.get('identity') == expected
                    and data.get('version') == (spec['target'].removeprefix('v') if probation else spec['oldVersion'])
                    and inventory_matches(spec['sessions'], data.get('sessions'))):
                return http(spec['port'], 'bootstrap')['csrfToken']
        except Exception:
            pass
        time.sleep(.2)
    return None


def run(spec_path):
    spec = read_json(spec_path)
    from .install_lock import acquire_runtime_lease
    # Keep the original install protected across the old/new server gap.
    install_lease = acquire_runtime_lease(Path(spec.get('oldSource', '.')))
    try:
        _run(spec, spec_path)
    finally:
        os.close(install_lease)


def _run(spec, spec_path):
    operation = Path(spec['operation'])
    def status(phase, message):
        private_json(operation, {'id':spec['id'], 'target':spec['target'], 'phase':phase, 'message':message, 'cancellable':False})
    # Parent explicitly closes its listening socket before arming this helper.
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and not Path(spec['armed']).exists():
        time.sleep(.1)
    if not Path(spec['armed']).exists():
        status('error', '切换未开始，当前服务和会话保持原状。')
        return
    candidate, csrf = None, None
    try:
        candidate = launch(spec, spec['source'], probation=True)
        csrf = ready(spec, candidate, spec['source'], probation=True)
    except OSError:
        pass
    if csrf:
        private_json(Path(spec['state'])/'updates/active.json', {'source':spec['source'], 'version':spec['target']})
        try:
            http(spec['port'], 'update/commit', {'token':spec['token']}, csrf)
        except Exception:
            # Commit may have succeeded despite a lost response. Never roll back
            # a process that might now be accepting user work.
            if read_json(operation).get('phase') != 'complete':
                status('attention', '新版本已启动，但更新确认尚未返回。会话数据保留，请重新连接查看。')
        return
    if candidate is not None and candidate.poll() is None:
        # The candidate has accepted no user mutations or model launches.
        candidate.terminate()
        try:
            candidate.wait(timeout=10)
        except subprocess.TimeoutExpired:
            status('error', '新版未能正常退出，已停止自动切换。备份已保留，请检查本地服务。')
            return
    # Retain the candidate's attempted state as evidence; copy prior files back.
    from .update_safety import backup_state
    import shutil
    state, backup = Path(spec['state']), Path(spec['backup'])
    backup_state(state, Path(spec_path).parent/'failed-candidate-state')
    previous_files = Path(spec_path).parent/'candidate-files'
    previous_files.mkdir(mode=0o700)
    for item in backup.iterdir():
        target = state/item.name
        if target.exists() or target.is_symlink():
            target.rename(previous_files/item.name)
        if item.is_symlink():
            target.symlink_to(os.readlink(item))
        elif item.is_dir():
            shutil.copytree(item, target, symlinks=True)
        else:
            shutil.copy2(item, target)
    try:
        old = launch(spec, spec['oldSource'], probation=False)
        restored = ready(spec, old, spec['oldSource'], probation=False)
    except OSError:
        restored = None
    if restored:
        status('rolled-back', '新版未通过启动检查，已恢复原版本；会话历史和备份均已保留。')
    else:
        status('error', '自动恢复未完成。原版本、会话数据和备份仍保留，请检查本地服务。')


if __name__ == '__main__':
    run(Path(sys.argv[1]))
