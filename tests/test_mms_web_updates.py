"""Offline checks: scheduling, failure isolation, concurrency and API security."""
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mms_web.runtime import private_json
from mms_web.updates import CHECK_INTERVAL, UpdateService, version_tuple
from mms_web.update_guidance import upgrade_guidance, release_policy, INSTALL_COMMAND
from mms_web.server import WebApplication


def service(tmp_path, fetcher=None):
    return UpdateService(SimpleNamespace(state_root=tmp_path), fetcher=fetcher or Mock(return_value={'tag': 'v99.0.0', 'notes': 'new'}), clock=lambda: 100000)


def test_numeric_versions_and_stable_only():
    assert version_tuple('4.10.0') > version_tuple('v4.9.9')
    assert version_tuple('v4.9.0-rc1') is None
    assert version_tuple('../9.0.0') is None


def test_upgrade_policy_is_explicit_and_never_accepts_a_command(tmp_path):
    notes = '<!-- mms-upgrade-policy: {"manualBelow":"4.20.0","reason":"先运行安装器"} -->'
    assert release_policy(notes) == {'manualBelow': '4.20.0', 'reason': '先运行安装器'}
    guidance = upgrade_guidance('4.19.1', {'tag': 'v4.20.0', 'upgradePolicy': release_policy(notes)})
    assert guidance['required'] is True
    assert guidance['command'] == INSTALL_COMMAND
    assert upgrade_guidance('4.20.0', {'tag': 'v4.21.0', 'upgradePolicy': release_policy(notes)}) is None


def test_upgrade_guidance_uses_actual_legacy_root_and_staged_install(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    monkeypatch.setenv('MMS_REAL_HOME', str(home))
    legacy = home / '.config' / 'mms'
    next_root = home / '.config' / 'mms-next'
    latest = {'tag': 'v4.19.2'}
    assert upgrade_guidance('4.19.1', latest, config_root=legacy)['required'] is True
    assert upgrade_guidance('4.19.1', latest, config_root=next_root) is None
    assert upgrade_guidance('4.19.1', latest, config_root=tmp_path / 'custom' / 'mms') is None
    staged = {'manualInstallRequired': True, 'reason': '当前服务跑的是暂存副本。'}
    assert upgrade_guidance('4.19.1', latest, installation=staged)['required'] is True


def test_status_exposes_manual_policy_and_disables_one_click_update(tmp_path):
    s = service(tmp_path, Mock(return_value={'tag': 'v99.0.0', 'notes': 'new',
                                              'upgradePolicy': {'manualBelow': '4.20.0', 'reason': '迁移'}}))
    with patch('mms_web.updates.VERSION', '4.19.1'):
        result = s.check()
    assert result['upgradeGuidance']['required'] is True
    assert result['canUpgrade'] is False


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


def test_whats_new_reads_the_notes_shipped_with_this_version(tmp_path):
    """After an update the page reloads owing the user what changed.

    Read from the install rather than the release API: the answer must not
    depend on the network, and must not drift to a newer release that this
    machine is not running.
    """
    from mms_version import VERSION
    from mms_web.updates import release_notes

    notes = release_notes(VERSION)
    assert notes.startswith(f"# v{VERSION}"), notes[:80]

    whats_new = service(tmp_path).status()['whatsNew']
    assert whats_new['version'] == VERSION
    assert whats_new['notes'] == notes
    # The costs of the upgrade are pulled out of the notes, as the confirm step
    # already does, so the panel can lead with them.
    assert whats_new['upgradeNotice']
    assert whats_new['upgradeNotice'] in notes
    assert '## 升级须知' not in whats_new['upgradeNotice']


def test_whats_new_will_not_read_outside_the_release_notes_directory():
    from mms_web.updates import release_notes

    for value in ('../../etc/passwd', 'v4.16.0', '4.16', '', None, '4.16.0/../../x'):
        assert release_notes(value) == '', value


def test_ui_preferences_remember_which_notes_were_read(tmp_path):
    from mms_web.ui_preferences import UiPreferences

    prefs = UiPreferences(tmp_path)
    assert prefs.read()['whatsNewSeenVersion'] == ''

    prefs.update({'whatsNewSeenVersion': '4.16.0'})
    assert UiPreferences(tmp_path).read()['whatsNewSeenVersion'] == '4.16.0'

    # Still a flag store for the tour; the two must not overwrite each other.
    prefs.update({'tourSeen': True})
    reread = UiPreferences(tmp_path).read()
    assert reread['tourSeen'] is True
    assert reread['whatsNewSeenVersion'] == '4.16.0'

    prefs.update({'whatsNewSeenVersion': 'x' * 200})
    assert len(UiPreferences(tmp_path).read()['whatsNewSeenVersion']) == 64
