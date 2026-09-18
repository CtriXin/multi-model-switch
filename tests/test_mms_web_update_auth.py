"""Guardian entrypoints must cross the real remote-access HTTP gate."""
import json
import os
import random
import threading
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mms_version import VERSION
from mms_web import server as transport, update_handoff as handoff
from mms_web.runtime import private_json
from mms_web.updates import read_json


@pytest.fixture
def guardian_service(tmp_path, monkeypatch, request):
    monkeypatch.setattr(transport, "_adapter", lambda *a, **k: None)
    monkeypatch.setattr(transport.access.RemoteAccess, "extra_binds", lambda self: [])
    app = transport.WebApplication(state_root=tmp_path / "state", config_root=tmp_path / "config", listen=getattr(request, "param", "lan"))
    app.state_root.mkdir(exist_ok=True)
    for port in random.sample(range(61000, 62000), 30):
        try:
            server = transport.create_server(app, tmp_path, port)
            break
        except OSError:
            continue
    else:
        pytest.fail("no isolated test port available")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    source = str(Path(transport.__file__).resolve().parent.parent)
    armed = tmp_path / "armed"
    armed.touch()
    backup = tmp_path / "backup"
    backup.mkdir()
    spec = dict(id="auth-fixture", target=f"v{VERSION}", oldVersion=VERSION,
                source=source, oldSource=source, state=str(app.state_root),
                config=str(app.config_root), cwd=os.getcwd(), port=port,
                sessions={}, token="fixture-update-token", armed=str(armed),
                backup=str(backup), operation=str(app.state_root / "updates/operation.json"))
    # Bound failure paths without stubbing either HTTP or the actual server.
    clock = SimpleNamespace(value=0)
    monkeypatch.setattr(handoff, "time", SimpleNamespace(
        monotonic=lambda: clock.value,
        sleep=lambda seconds: setattr(clock, "value", clock.value + 61)))
    from mms_web import install_lock
    monkeypatch.setattr(install_lock, "acquire_runtime_lease",
                        lambda _: os.open(tmp_path / "lease", os.O_CREAT | os.O_RDWR, 0o600))
    try:
        yield app, spec, tmp_path
    finally:
        server.shutdown()
        server.server_close()
        app.close()
        thread.join(2)


def run_guardian(spec, root):
    path = root / "handoff.json"
    private_json(path, spec)
    handoff.run(path)
    return read_json(spec["operation"])


@pytest.mark.parametrize("guardian_service", ["loopback", "lan"], indirect=True)
def test_guardian_ready_and_commit_use_selected_states_token(guardian_service, monkeypatch):
    app, spec, root = guardian_service
    app.instance = spec["id"]
    app.probation_token = spec["token"]
    app.maintenance = True
    process = Mock()
    process.poll.return_value = None
    monkeypatch.setattr(handoff, "launch", lambda *a, **k: process)
    monkeypatch.setattr(handoff, "install_alongside", lambda _: False)
    result = run_guardian(spec, root)
    assert result["phase"] == "complete"
    assert app.probation_token == "" and app.maintenance is False
    process.terminate.assert_not_called()
    if app.access.required:
        assert app.access.token not in json.dumps(result)
    else:
        assert not (app.state_root / "remote-access-token").exists()


@pytest.mark.parametrize("guardian_service", ["loopback", "lan"], indirect=True)
def test_guardian_can_verify_authenticated_rollback(guardian_service, monkeypatch):
    app, spec, root = guardian_service
    app.instance = spec["id"] + "-rollback"
    process = Mock()
    process.poll.return_value = None
    monkeypatch.setattr(handoff, "launch", Mock(side_effect=[OSError("candidate failed"), process]))
    assert run_guardian(spec, root)["phase"] == "rolled-back"


def test_token_is_not_taken_from_another_state_or_created(guardian_service):
    app, spec, root = guardian_service
    wrong = root / "wrong-state"
    wrong.mkdir()
    token = wrong / "remote-access-token"
    for value in (None, "wrong-token"):
        if value is not None:
            token.write_text(value)
        with pytest.raises(urllib.error.HTTPError) as exc:
            handoff.http(spec["port"], "update/identity", state_root=wrong)
        assert exc.value.code == 401
        assert token.exists() is (value is not None)
    assert handoff.http(spec["port"], "update/identity", state_root=app.state_root)["version"] == VERSION
