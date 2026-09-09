import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from mms_web.server import WebApplication
from mms_web.updates import read_json
from mms_web.runtime import private_json
from mms_web.update_coordinator import UpdateCoordinator
from mms_web.update_handoff import inventory_matches
from mms_web.update_activation import acquire_state_lock


def setup(tmp_path, stager):
    with patch('mms_web.server._adapter', return_value=None):
        app=WebApplication(state_root=tmp_path/'state')
    source=tmp_path/'source'
    c=UpdateCoordinator(app,Mock(),source,source/'mms_web_static',stager=stager)
    app.updates.coordinator=c
    private_json(c.root/'check.json',{'latest':{'tag':'v99.0.0'}})
    return app,c


def test_unavailable_or_unchecked_target_is_rejected(tmp_path):
    app,c=setup(tmp_path,Mock())
    with pytest.raises(Exception):c.start({'target':'v98.0.0'})
    c.stager.assert_not_called()


def test_failed_stage_never_enters_maintenance_or_shutdown(tmp_path):
    app,c=setup(tmp_path,Mock(side_effect=ValueError('fixture')))
    c.start({'target':'v99.0.0'});c._thread.join(2)
    assert c.status()['phase']=='error'
    assert not app.maintenance
    c.server.shutdown.assert_not_called()


def test_busy_state_waits_and_cancel_never_stops_a_process(tmp_path):
    app,c=setup(tmp_path,Mock(return_value=tmp_path/'candidate'))
    with patch('mms_web.update_coordinator.session_safety',return_value={'blockers':['busy'],'live':1}):
        c.start({'target':'v99.0.0'})
        for _ in range(100):
            if c.status()['phase']=='waiting':break
            threading.Event().wait(.01)
        assert c.status()['phase']=='waiting'
        c.cancel();c._thread.join(2)
    assert c.status()['phase']=='cancelled'
    assert not app.maintenance
    c.server.shutdown.assert_not_called()


def test_mutations_are_rejected_in_the_cutover_window(tmp_path):
    app,c=setup(tmp_path,Mock())
    app.maintenance=True
    app._post=Mock()
    with pytest.raises(Exception,match='正在验证更新'):
        app.post(['sessions'],{'prompt':'must not launch'})
    app._post.assert_not_called()


def test_inventory_requires_every_original_session_runtime_and_event():
    old={'s':{'runtime':'private/r','resume':True,'events':['old']}}
    assert inventory_matches(old,{'s':{'runtime':'private/r','resume':True,'events':['old','new']}})
    for new in ({},{'s':{'runtime':'wrong','resume':True,'events':['old']}},{'s':{'runtime':'private/r','resume':False,'events':['old']}},{'s':{'runtime':'private/r','resume':True,'events':[]}}):
        assert not inventory_matches(old,new)


def test_two_services_cannot_open_the_same_state_directory(tmp_path):
    import os
    descriptor=acquire_state_lock(tmp_path)
    try:
        with pytest.raises(RuntimeError):acquire_state_lock(tmp_path)
    finally:os.close(descriptor)
    descriptor=acquire_state_lock(tmp_path);os.close(descriptor)


def test_unrequested_idle_process_exit_is_blocked(tmp_path):
    app,c=setup(tmp_path,Mock(return_value=tmp_path/'candidate'))
    with patch('mms_web.update_coordinator.session_safety',return_value={'blockers':[],'live':1}):
        c.start({'target':'v99.0.0'})
        for _ in range(100):
            if c.status()['phase']=='waiting':break
            threading.Event().wait(.01)
        assert c.status()['phase']=='waiting'
        assert '空闲 Pi' in c.status()['message']
        c.cancel();c._thread.join(2)
    c.server.shutdown.assert_not_called()


def test_state_drift_before_backup_aborts_and_reopens_mutations(tmp_path):
    app,c=setup(tmp_path,Mock(return_value=tmp_path/'candidate'))
    with patch('mms_web.update_coordinator.session_safety',return_value={'blockers':[],'live':0}), patch('mms_web.update_coordinator.backup_state',side_effect=ValueError('changed')):
        c.start({'target':'v99.0.0'});c._thread.join(2)
    assert c.status()['phase']=='error' and not app.maintenance
    c.server.shutdown.assert_not_called()


def test_guardian_spawn_failure_attempts_original_version(tmp_path):
    import json
    from mms_web.update_handoff import run
    state=tmp_path/'state';state.mkdir();backup=tmp_path/'backup';backup.mkdir()
    arm=tmp_path/'armed';arm.touch()
    spec={'id':'fixture','target':'v99.0.0','source':'candidate','oldSource':'old','operation':str(tmp_path/'operation.json'),'armed':str(arm),'state':str(state),'backup':str(backup)}
    spec_path=tmp_path/'handoff.json';spec_path.write_text(json.dumps(spec))
    with patch('mms_web.update_handoff.launch',side_effect=[OSError('missing executable'),Mock()]) as launch, patch('mms_web.update_handoff.ready',return_value='csrf'):
        run(spec_path)
    assert launch.call_count==2
    assert read_json(tmp_path/'operation.json')['phase']=='rolled-back'
