"""Real Pi: switch within one conversation and across isolated channels."""
import json
from pathlib import Path
import pytest
from mms_web.errors import WebError
from test_mms_web_interactions import native, local_app, settle


def configure(app, name, models, key='test-owned-key', provider_id=None):
    url = next(p for p in app.get(['model-settings'])['providers'] if p['id'] == 'local-vision')['connection']['openaiBaseUrl']
    payload = {'service': {'name': name, 'baseUrl': url, 'apiKey': key, 'models': models, 'protocol': 'openai'}}
    if provider_id: payload['service']['id'] = provider_id
    preview = app.post(['configuration', 'preview'], payload)
    app.post(['configuration', 'apply'], {'previewId': preview['previewId'], 'revision': preview['revision']})


def test_native_switch_preserves_pid_history_effort_and_resume(native):
    app, workspace, records = native
    configure(app, 'Local vision', ['gpt-5', 'gpt-4.1'], provider_id='local-vision')
    expected = app.post(['launch-options'], {'workspaceId': workspace['id'], 'presetId': 'web:pi:local-vision:gpt-4.1'})['defaultThinkingLevel']
    detail = app.post(['sessions'], {'requestId': 'start-switch', 'workspaceId': workspace['id'], 'presetId': 'web:pi:local-vision:gpt-5', 'prompt': 'original-history-marker'})
    sid = detail['session']['id']; settle(app, sid)
    live = app.sessions._get(sid)
    pid = live.driver._proc.pid
    native_id = app.sessions._rpc(live, {'type': 'get_state'})['sessionId']
    switched = app.post(['sessions', sid, 'model'], {'requestId': 'switch-1', 'presetId': 'web:pi:local-vision:gpt-4.1'})
    assert switched['session']['id'] == sid and switched['session']['modelName'] == 'gpt-4.1'
    assert live.driver._proc.pid == pid
    assert switched['runtime']['model']['id'] == 'gpt-4.1'
    assert switched['runtime']['thinkingLevel'] == expected
    assert all(e['modelName'] == 'gpt-5' for e in switched['events'] if e['kind'] == 'assistant')
    app.post(['sessions', sid, 'messages'], {'requestId': 'second-model-message', 'text': 'continue-marker'})
    settle(app, sid)
    assert records[-1]['model'] == 'gpt-4.1' and 'original-history-marker' in json.dumps(records[-1]['messages'])
    assert app.sessions._rpc(live, {'type': 'get_state'})['sessionId'] == native_id
    live.driver.close()
    app.post(['sessions', sid, 'messages'], {'requestId': 'resume-switched', 'text': 'after-restart'})
    settle(app, sid)
    assert records[-1]['model'] == 'gpt-4.1' and 'continue-marker' in json.dumps(records[-1]['messages'])


def test_cross_channel_same_model_updates_key_and_preserves_context(native, monkeypatch):
    app, workspace, records = native
    configure(app, 'Second route', ['gpt-5'], key='second-route-test-key')
    first = app.post(['sessions'], {'requestId': 'cross-start', 'workspaceId': workspace['id'], 'presetId': 'web:pi:local-vision:gpt-5', 'prompt': 'cross-history-marker'})
    sid = first['session']['id']; settle(app, sid)
    live = app.sessions._get(sid); pid = live.driver._proc.pid
    old_root = live.meta['runtimeRoot']
    native_id = app.sessions._rpc(live, {'type': 'get_state'})['sessionId']
    switched = app.post(['sessions', sid, 'model'], {'requestId': 'cross-switch', 'presetId': 'web:pi:second-route:gpt-5'})
    assert switched['session']['channel'] == 'second-route'
    assert live.driver._proc.pid != pid and live.meta['runtimeRoot'] != old_root
    app.post(['sessions', sid, 'messages'], {'requestId': 'cross-send', 'text': 'new-route-marker'})
    settle(app, sid)
    assert records[-1]['_testAuthorization'] == 'Bearer second-route-test-key'
    assert 'cross-history-marker' in json.dumps(records[-1]['messages'])
    assert app.sessions._rpc(live, {'type': 'get_state'})['sessionId'] == native_id
    # A rejected target never replaces the functioning session.
    current_pid = live.driver._proc.pid
    with pytest.raises(WebError):
        app.post(['sessions', sid, 'model'], {'requestId': 'invalid-target', 'presetId': 'web:pi:missing:invalid'})
    assert live.driver._proc.pid == current_pid and live.alive()
    live.state = 'running'
    with pytest.raises(WebError) as error:
        app.post(['sessions', sid, 'model'], {'requestId': 'busy-switch', 'presetId': 'web:pi:local-vision:gpt-5'})
    assert error.value.code == 'SESSION_BUSY'
    live.state = 'idle'
    # A second cross-channel switch must detach the previous deferred sink.
    app.post(['sessions', sid, 'model'], {'requestId': 'switch-back', 'presetId': 'web:pi:local-vision:gpt-5'})
    app.post(['sessions', sid, 'messages'], {'requestId': 'back-send', 'text': 'original-route-again'})
    settled = settle(app, sid)
    assert settled['session']['state'] != 'error'
    assert records[-1]['_testAuthorization'] == 'Bearer test-owned-key'
    assert 'new-route-marker' in json.dumps(records[-1]['messages'])


@pytest.mark.parametrize("cross_channel", [False, True])
def test_switch_save_failure_rolls_back_live_and_durable_selection(native, monkeypatch, cross_channel):
    app, workspace, records = native
    configure(app, 'Local vision', ['gpt-5', 'gpt-4.1'], provider_id='local-vision')
    configure(app, 'Second route', ['gpt-5'], key='second-route-test-key')
    detail = app.post(['sessions'], {'requestId':'rollback-start', 'workspaceId':workspace['id'], 'presetId':'web:pi:local-vision:gpt-5', 'prompt':'rollback-history'})
    sid=detail['session']['id'];settle(app,sid)
    session=app.sessions._get(sid);old_driver=session.driver
    root=Path(session.meta['runtimeRoot']);before=(root/'resume.json').read_bytes()
    previous_meta=json.loads(json.dumps(session.meta));previous_events=json.loads(json.dumps(session.events))
    save=session.persist
    def fail(_): raise OSError('synthetic storage failure')
    monkeypatch.setattr(session, 'persist', fail)
    target='web:pi:second-route:gpt-5' if cross_channel else 'web:pi:local-vision:gpt-4.1'
    with pytest.raises(WebError, match='原选择'):
        app.post(['sessions',sid,'model'], {'requestId':'rollback-switch','presetId':target})
    monkeypatch.setattr(session,'persist',save)
    assert session.driver is old_driver and old_driver.alive()
    assert session.meta['modelName'] == previous_meta['modelName'] and session.meta['runtimeRoot'] == str(root)
    assert session.events == previous_events and (root/'resume.json').read_bytes() == before
    assert app.sessions._rpc(session, {'type':'get_state'})['model']['id'] == 'gpt-5'
    app.post(['sessions',sid,'messages'], {'requestId':'after-failed-switch','text':'continue-original'})
    settle(app,sid)
    assert records[-1]['_testAuthorization'] == 'Bearer test-owned-key'
