"""Offline checks: scheduling, failure isolation, concurrency and API security."""
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mms_web.runtime import private_json
from mms_web.updates import CHECK_INTERVAL, UpdateService, version_tuple
from mms_web.server import WebApplication


def service(tmp_path, fetcher=None):
    return UpdateService(SimpleNamespace(state_root=tmp_path), fetcher=fetcher or Mock(return_value={'tag': 'v99.0.0', 'notes': 'new'}), clock=lambda: 100000)


def test_numeric_versions_and_stable_only():
    assert version_tuple('4.10.0') > version_tuple('v4.9.9')
    assert version_tuple('v4.9.0-rc1') is None
    assert version_tuple('../9.0.0') is None


def test_due_manual_and_auto_checks_share_a_persistent_cache(tmp_path):
    s = service(tmp_path)
    assert not tmp_path.joinpath('updates').exists()
    assert s.check()['updateAvailable']
    s.check(); s.check(manual=True)
    assert s.fetcher.call_count == 1
    s.clock = lambda: 100060
    s.check(manual=True)
    assert s.fetcher.call_count == 2
    s.clock = lambda: 100060 + CHECK_INTERVAL
    s.check()
    assert s.fetcher.call_count == 3
    assert service(tmp_path).status()['latest']['tag'] == 'v99.0.0'


def test_disabled_auto_check_allows_explicit_manual_check(tmp_path, monkeypatch):
    s = service(tmp_path)
    s.preferences({'enabled': False})
    s.check()
    assert s.fetcher.call_count == 0
    s.check(manual=True)
    assert s.fetcher.call_count == 1
    monkeypatch.setenv('MMS_WEB_UPDATE_CHECK', '0')
    assert not s.preferences({'enabled': True})['enabled']


def test_failure_keeps_last_release_and_does_not_expose_exception(tmp_path):
    s = service(tmp_path)
    s.check()
    s.clock = lambda: 200000
    s.fetcher.side_effect = RuntimeError('secret-token')
    result = s.check()
    assert result['latest']['tag'] == 'v99.0.0'
    assert result['error'] and 'secret-token' not in json.dumps(result)
    s.check()
    assert s.fetcher.call_count == 2


def test_corrupt_timestamp_and_future_clock_do_not_disable_checks(tmp_path):
    s = service(tmp_path)
    for timestamp in ('bad', 1000000000000000, 200000):
        private_json(s.root / 'check.json', {'checkedAt': timestamp})
        s.check()
    assert s.fetcher.call_count == 3


def test_concurrent_check_issues_only_one_request(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def fetch():
        entered.set()
        assert release.wait(2)
        return {'tag': 'v99.0.0'}
    s = service(tmp_path, Mock(side_effect=fetch))
    worker = threading.Thread(target=s.check)
    worker.start()
    assert entered.wait(2)
    assert s.check()['checking']
    release.set(); worker.join(2)
    assert s.fetcher.call_count == 1


def test_application_creation_and_read_never_call_network(tmp_path):
    with patch('mms_web.server._adapter', return_value=None):
        app = WebApplication(state_root=tmp_path / 'state')
    assert app.get(['update'])['operation']['phase'] == 'idle'
    assert not (tmp_path / 'state').exists()
    app.close()
