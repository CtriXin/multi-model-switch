import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from mms_hook_retirement import cleanup_payload, is_retired_automatic_hook, process_file

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('command', [
    '/Users/me/.mms/hooks/nsr-codex-hook.sh',
    'MMS_REAL_HOME="/Users/me" /bin/bash "/Users/me/auto-skills/CtriXin-repo/multi-model-switch/hooks/claude-map-auto-index.sh"',
    'python3 /Users/me/.mms/hooks/nsr-stop-wrapper.py codex',
    'bash /Users/me/auto-skills/CtriXin-repo/multi-model-switch/hooks/claude-map-auto-index.sh',
    '/bin/bash /Users/me/.claude/hooks/map-auto-index.sh',
    '/Users/me/.claude/hooks/codegraph-auto-index.sh',
])
def test_owned_automatic_match(command):
    assert is_retired_automatic_hook(command)


@pytest.mark.parametrize('command', [
    '/tmp/custom/nsr-codex-hook.sh', 'map .', 'codegraph index .',
    'MMS_REAL_HOME=/Users/me EXTRA=1 /bin/bash /Users/me/.mms/hooks/nsr-codex-hook.sh',
    'MMS_REAL_HOME=relative /bin/bash /Users/me/.mms/hooks/nsr-codex-hook.sh',
    'MMS_REAL_HOME=/Users/me /bin/bash /Users/me/.mms/hooks/nsr-codex-hook.sh | cat',
    'MMS_REAL_HOME="/Users/$(id)" /bin/bash /Users/me/.mms/hooks/nsr-codex-hook.sh',
    'python3 /Users/me/.mms/hooks/nsrctl.py enable .',
    'bash -c "echo /Users/me/.mms/hooks/nsr-codex-hook.sh"',
    '/Users/me/.mms/hooks/nsr-codex-hook.sh && echo keep',
    '/Users/me/.mms/hooks/nsr-codex-hook.sh.backup',
])
def test_other_commands_preserved(command):
    assert not is_retired_automatic_hook(command)


def payload():
    return {'env': {'private': 'must-not-print'}, 'hooks': {'Stop': [
        {'matcher': '', 'tag': 7, 'hooks': [
            {'type': 'command', 'command': '/Users/me/.mms/hooks/nsr-codex-hook.sh'},
            {'type': 'command', 'command': '/tmp/custom/notify.sh'},
        ]}, {'custom': 'keep-empty', 'hooks': []},
    ], 'SessionEnd': [{'hooks': [{'command': '/tmp/keep.sh'}]}]}}


def test_cleanup_preserves_other_fields_and_idempotent():
    original = payload()
    expected = payload()
    expected['hooks']['Stop'][0]['hooks'].pop(0)
    result, removed = cleanup_payload(original)
    assert result == expected
    assert original == payload()
    assert len(removed) == 1
    assert cleanup_payload(result) == (result, [])


def test_cli_dry_run_cas_apply_mode_backup(tmp_path):
    path = tmp_path / 'settings.json'
    original = json.dumps(payload()).encode()
    path.write_bytes(original)
    path.chmod(0o600)
    cmd = [sys.executable, '-B', str(ROOT/'mms_hook_retirement.py'), '--file', str(path)]
    plan = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert 'must-not-print' not in plan.stdout
    assert path.read_bytes() == original
    bad = subprocess.run(cmd + ['--apply', '--expected-sha256', '0'*64, '--backup-dir', str(tmp_path/'journal')], capture_output=True, text=True)
    assert bad.returncode == 2
    assert path.read_bytes() == original
    ok = subprocess.run(cmd + ['--apply', '--expected-sha256', hashlib.sha256(original).hexdigest(), '--backup-dir', str(tmp_path/'journal')], capture_output=True, text=True, check=True)
    result = json.loads(ok.stdout)['files'][0]
    assert Path(result['backup']).read_bytes() == original
    assert Path(result['backup']).stat().st_mode & 0o777 == 0o600
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_bytes()) == cleanup_payload(payload())[0]
    assert process_file(path)['removed'] == []


@pytest.mark.parametrize('host', ['codex','claude'])
def test_managed_merge_cannot_restore_retired_hooks(monkeypatch, host):
    import mms_launchers as launchers
    managed = {'Stop': [{'hooks': [{'type': 'command', 'command': '/Users/me/.mms/hooks/nsr-codex-hook.sh'}]}],
               'SessionStart': [{'hooks': [{'type': 'command', 'command': '/Users/me/.claude/hooks/codegraph-auto-index.sh'}, {'command': '/tmp/custom/notify.sh'}]}]}
    monkeypatch.setattr(launchers, '_load_managed_session_hooks', lambda: managed)
    monkeypatch.setattr(launchers, '_filter_missing_managed_hook_commands', lambda value: value)
    monkeypatch.setattr(launchers, '_nsr_available_for_cli', lambda *_: pytest.fail('retired runtime discovery'))
    if host == 'codex':
        result = launchers._build_codex_session_hooks(enable_nsr=True).get('hooks', {})
    else:
        result = launchers._merge_mms_session_hooks(launchers._configure_claude_nsr_hooks({}, enable_nsr=True))
    assert 'nsr-codex-hook.sh' not in json.dumps(result)
    assert 'codegraph-auto-index.sh' not in json.dumps(result)
    assert '/tmp/custom/notify.sh' in json.dumps(result)


@pytest.mark.parametrize('script', ['nsr-codex-hook.sh','nsr-claude-hook.sh','nsr-stop-wrapper.py','nsr-builtin-hook.py','claude-map-auto-index.sh','claude-codegraph-auto-index.sh'])
def test_retired_wrapper_no_subprocess_state_or_input_wait(tmp_path, script):
    # Existing marker/state must survive, even with old activation env.
    marker = tmp_path/'marker'
    marker.write_text('historical user marker')
    trap = tmp_path/'trap'
    trap.write_text('#!/bin/sh\nprintf invoked >> "'+str(tmp_path/'called')+'"\nexit 99\n')
    trap.chmod(0o755)
    env = dict(os.environ, NSR_ENABLED='1', NSR_LOOP_HOOK=str(trap), NSRCTL=str(trap), CODEGRAPH_BIN=str(trap), LOOP_STATE_FILE=str(tmp_path/'state'))
    command = [sys.executable,'-B',str(ROOT/'hooks'/script),'codex'] if script.endswith('.py') else ['/bin/sh',str(ROOT/'hooks'/script)]
    proc = subprocess.Popen(command, cwd=tmp_path, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        # Leave stdin open and empty: retired hooks must not wait for payload EOF.
        assert proc.wait(timeout=1) == 0
        assert proc.stdout.read().strip() in (b'', b'{}')
    finally:
        proc.stdin.close()
        if proc.poll() is None: proc.kill()
    assert marker.read_text() == 'historical user marker'
    assert not (tmp_path/'called').exists()
    assert not (tmp_path/'state').exists()
