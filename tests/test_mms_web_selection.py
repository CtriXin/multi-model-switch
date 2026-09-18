"""First-message choices must reach actual Pi and survive resume."""
import json
from pathlib import Path
import pytest
from mms_web.errors import WebError
from mms_web.launch_options import supported_levels
from test_mms_web_interactions import local_app, native, settle


def test_prelaunch_inherits_mms_effort_and_override_reaches_provider(native):
    app, workspace, records = native
    prefs = app.catalog._config_root / 'preferences.toml'
    prefs.write_text('[launch.cli.pi]\nreasoning_effort = "medium"\n')
    before = prefs.read_bytes()
    payload = {'presetId':'web:pi:local-vision:gpt-5','workspaceId':workspace['id']}
    options = app.post(['launch-options'], payload)
    assert options['defaultThinkingLevel'] == 'medium'
    assert 'api_key' not in json.dumps(options) and 'base_url' not in json.dumps(options)
    assert not list((app.state_root / 'runtimes').iterdir())
    detail = app.post(['sessions'], {**payload,'requestId':'selected-effort','prompt':'first effort request','thinkingLevel':'low'})
    sid = detail['session']['id']; settle(app,sid)
    assert records[-1]['reasoning_effort'] == 'low'
    assert app.get(['sessions',sid,'runtime'])['thinkingLevel'] == 'low'
    app.sessions._get(sid).driver.close()
    app.post(['sessions',sid,'messages'], {'requestId':'resume-effort','text':'continue effort'})
    settle(app,sid)
    assert records[-1]['reasoning_effort'] == 'low'
    assert prefs.read_bytes() == before
    second = app.post(['sessions'], {**payload,'requestId':'inherited-effort','prompt':'inherited request'})
    settle(app,second['session']['id'])
    assert records[-1]['reasoning_effort'] == 'medium'
    count=len(records)
    with pytest.raises(WebError):
        app.post(['sessions'], {**payload,'requestId':'invalid-effort','prompt':'should never run','thinkingLevel':'max'})
    assert len(records)==count


def test_skills_use_project_precedence_and_first_message(native, monkeypatch, tmp_path):
    app, workspace, records = native
    root = Path(workspace['path']);(root/'.git').mkdir()
    def skill(base,marker):
        directory=base/'demo';directory.mkdir(parents=True);(directory/'SKILL.md').write_text('---\nname: demo\ndescription: |\n  Test skill with multiline description.\n---\n'+marker)
    home=tmp_path/'home';skill(home/'.agents/skills','GLOBAL-SKILL-LOSER')
    skill(root/'.pi/skills','PI-SKILL-LOSER')
    skill(root/'.agents/skills','PROJECT-SKILL-WINNER')
    catalog=app.post(['skills'],{'workspaceId':workspace['id']})
    chosen=next(s for s in catalog['skills'] if s['name']=='demo')
    assert chosen['source']=='项目'
    detail=app.post(['sessions'],{'presetId':'web:pi:local-vision:gpt-5','workspaceId':workspace['id'],'requestId':'first-skill','prompt':'use chosen skill','skills':[chosen['id']]})
    sid=detail['session']['id'];detail=settle(app,sid)
    sent=json.dumps(records[-1]['messages'])
    assert 'PROJECT-SKILL-WINNER' in sent and 'GLOBAL-SKILL-LOSER' not in sent and 'PI-SKILL-LOSER' not in sent
    assert any(e.get('skills',[{}])[0].get('name')=='demo' for e in detail['events'] if e.get('skills'))
    count=len(records)
    with pytest.raises(WebError):
        app.post(['sessions',sid,'messages'],{'requestId':'bad-skill','text':'no send','skills':['../../etc/passwd']})
    assert len(records)==count


def test_pi_supported_effort_uses_null_maps():
    assert supported_levels({'reasoning':False}) == ['off']
    assert supported_levels({'reasoning':True,'thinkingLevelMap':{'minimal':None,'low':None,'medium':None,'high':'high','xhigh':'max'}})==['off','high','xhigh']
    assert supported_levels({'reasoning':True,'thinkingLevelMap':{**{l:None for l in ['off','minimal','low','medium','high','xhigh']},'max':'max'}})==['max']
