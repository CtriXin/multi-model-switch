"""Regression probes for independently reproduced v4 release blockers."""
import io
import json
import signal
import subprocess
from types import SimpleNamespace

from mms_web.drivers.pi_rpc import PiRpcDriver
from mms_web.sessions import SessionService, _LiveSession


def test_close_escalates_after_process_wait_timeout():
    calls = []
    def wait(timeout=None):
        calls.append(('wait', timeout))
        if not any(item == ('signal', signal.SIGKILL) for item in calls):
            raise subprocess.TimeoutExpired('test-owned-process', timeout)
        return -9
    driver = object.__new__(PiRpcDriver)
    driver._exit_code = None
    driver._proc = SimpleNamespace(stdin=io.StringIO(), wait=wait)
    driver._terminate_group = lambda sig: calls.append(('signal',sig))
    driver._notify_exit = lambda: calls.append(('reaped',True))
    driver.close(graceful_timeout=0)
    assert ('signal',signal.SIGTERM) in calls and ('signal',signal.SIGKILL) in calls
    assert calls[-1] == ('reaped',True)


def test_every_stream_split_hides_secret_and_keeps_normal_text(tmp_path):
    secret = 'synthetic-private-key-1234567890'
    for field in ('text','thinking'):
        for split in range(1,len(secret)):
            session = _LiveSession({'id':'test-session','harness':'pi','modelName':'fixture'})
            session.secrets = [secret]
            service = object.__new__(SessionService)
            service._state_dir = tmp_path
            service._now = lambda: '2026-09-09T00:00:00Z'
            service._apply_driver_event(session, {'id':'a','kind':'assistant',field+'Append':'before '+secret[:split]})
            assert session.events[0][field] == 'before '
            # Potential secret prefixes are never persisted or sent to Web.
            assert secret[:split] not in json.loads((tmp_path/'test-session.json').read_text())['events'][0][field]
            service._apply_driver_event(session, {'id':'a','kind':'assistant',field+'Append':secret[split:]+' after'})
            assert session.events[0][field] == 'before [已隐藏密钥] after'
            assert secret not in (tmp_path/'test-session.json').read_text()
            service._apply_driver_event(session, {'id':'a','kind':'assistant',field:'ordinary text ending in syn'})
            assert session.events[0][field] == 'ordinary text ending in syn'
