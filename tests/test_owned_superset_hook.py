"""Terminal owner guard with fake curl; never invokes the host app or network."""
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('case,payload,owner,calls', [
    ('no_owner_open_stdin', None, '', 0),
    ('generic_session', {'session_id': 'generic', 'hook_event_name': 'Stop'}, '', 0),
    ('resource_id_only', {'resourceId': 'resource', 'hook_event_name': 'Stop'}, '', 0),
    ('owned_terminal', {'session_id': 'generic', 'hook_event_name': 'Stop'}, 'synthetic-tab', 1),
    ('owned_malformed', {'session_id': 'generic'}, 'synthetic-tab', 0),
])
def test_owned_terminal_notifies_only_with_app_context(tmp_path, case, payload, owner, calls):
    hook = tmp_path / '.superset/hooks/notify.sh'
    hook.parent.mkdir(parents=True)
    # Synthetic app boundary retains the real script's event-dependent curl
    # behavior. Separate private probe also exercises the original 104-line
    # script copy; never vendor an app-owned private file into MMS.
    hook.write_text('''#!/bin/bash
INPUT="${1:-$(cat)}"
case "$INPUT" in
  *'"hook_event_name": "Stop"'*) curl --connect-timeout 1 --max-time 2 http://127.0.0.1:1/hook/complete ;;
esac
exit 0
''')
    bin_dir = tmp_path/'bin'; bin_dir.mkdir()
    marker = tmp_path/'curl-called'
    curl = bin_dir/'curl'
    curl.write_text('#!/bin/sh\nprintf called >> "'+str(marker)+'"\nexit 0\n')
    curl.chmod(0o700)
    env = {k:v for k,v in os.environ.items() if not k.startswith('SUPERSET_')}
    env.update(MMS_REAL_HOME=str(tmp_path), SUPERSET_TAB_ID=owner, PATH=str(bin_dir)+':/usr/bin:/bin')
    command = ['/bin/sh', str(ROOT/'hooks/owned-superset-notify.sh')]
    if payload is None:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        try:
            assert proc.wait(timeout=1) == 0
        finally:
            if proc.poll() is None: proc.kill()
            proc.stdin.close()
    else:
        result = subprocess.run(command, input=json.dumps(payload), text=True, capture_output=True, env=env, timeout=2)
        assert result.returncode == 0
    assert (1 if marker.exists() else 0) == calls
