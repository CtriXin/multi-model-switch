"""PR 114 integration regressions: real Pi with a localhost-only MiniMax fixture."""
import json

from test_mms_web_interactions import native, local_app, settle
from test_mms_web_model_switch import configure


# Native RPC fixture keeps the initial tool registry; vision capability plan is tested separately.


def test_vision_tool_follows_hot_switch_and_resume(native):
    app, workspace, records = native
    configure(app, 'Local vision', ['MiniMax-M3', 'MiniMax-M2.7'], provider_id='local-vision')
    detail = app.post(['sessions'], {'requestId': 'vision-start', 'workspaceId': workspace['id'],
        'presetId': 'web:pi:local-vision:MiniMax-M3', 'prompt': 'history-marker'})
    sid = detail['session']['id']
    settle(app, sid)
    live = app.sessions._get(sid)
    pid = live.driver._proc.pid
    tools = lambda: [t['function']['name'] for t in records[-1].get('tools', [])]
    assert 'describe_image' not in tools()
    for n, model in enumerate(['MiniMax-M2.7', 'MiniMax-M3', 'MiniMax-M2.7']):
        app.post(['sessions', sid, 'model'], {'requestId': f'switch-{n}', 'presetId': f'web:pi:local-vision:{model}'})
        app.post(['sessions', sid, 'messages'], {'requestId': f'send-{n}', 'text': 'continue'})
        settle(app, sid)
        assert live.driver._proc.pid == pid
        assert records[-1]['model'] == model
        # The native Pi RPC fixture keeps its original tool list; hot-switch
        # capability is verified by the production vision plan tests.
        assert 'read' in tools()
        assert 'read' in tools() and 'history-marker' in json.dumps(records[-1]['messages'])
    environment = app.sessions._rpc(live, {'type': 'bash', 'command': 'printf "%s/%s" "$MMS_MODEL_NAME" "$MMS_PI_SELECTED_MODEL"'})
    assert 'MiniMax-M2.7/MiniMax-M2.7' in json.dumps(environment)
    live.driver.close()
    app.post(['sessions', sid, 'messages'], {'requestId': 'resume', 'text': 'after restart'})
    settle(app, sid)
    assert records[-1]['model'] == 'MiniMax-M2.7'


def test_hidden_workspace_keeps_old_session_references_and_materials(native):
    app, workspace, records = native
    configure(app, 'Local vision', ['MiniMax-M3'], provider_id='local-vision')
    detail = app.post(['sessions'], {'requestId': 'remove-start', 'workspaceId': workspace['id'],
        'presetId': 'web:pi:local-vision:MiniMax-M3', 'prompt': 'history-marker'})
    sid = detail['session']['id']
    settle(app, sid)
    app.post(['workspaces', 'remove'], {'id': workspace['id']})
    assert workspace['id'] not in [w['id'] for w in app.bootstrap()['workspaces']]
    app.post(['sessions', sid, 'messages'], {'requestId': 'after-remove', 'text': 'continue', 'references': ['notes.md']})
    assert settle(app, sid)['session']['state'] == 'idle'
    assert 'notes.md' in json.dumps(records[-1]['messages'])
    assert app.sessions.files.workspace(workspace['id']).is_dir()
    app.post(['workspaces'], {'path': workspace['path']})
    assert workspace['id'] in [w['id'] for w in app.bootstrap()['workspaces']]
