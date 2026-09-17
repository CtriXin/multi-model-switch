"""Which POST routes must not hold the global mutation lock.

configuration/discover (httpx probe, 15s timeout) and the read-only
model-settings probes (subprocess worker, 90s timeout) run outside
mutation_lock so a slow or dead target cannot freeze every other POST.
model-settings/preview and model-settings/apply write config and must stay
locked. These tests pin that boundary: the probe tries to acquire
mutation_lock from a *separate* thread (RLock re-entry would make a
same-thread check useless), so it reports True only when the caller really
does not hold the lock.
"""
import json
import threading
import time
from types import SimpleNamespace

import pytest

from mms_web.catalog import CatalogService
from mms_web.errors import WebError
from mms_web.model_settings import ModelSettings
from mms_web.server import WebApplication


@pytest.fixture
def app(tmp_path):
    from unittest.mock import patch
    with patch("mms_web.server._adapter", return_value=None):
        application = WebApplication(state_root=tmp_path / "state")
    try:
        yield application
    finally:
        application.close()


def _probe_mutation_lock(app, observed):
    """Record, from a helper thread, whether mutation_lock can be acquired."""
    result = []

    def attempt():
        acquired = app.mutation_lock.acquire(blocking=False)
        result.append(acquired)
        if acquired:
            app.mutation_lock.release()

    helper = threading.Thread(target=attempt)
    helper.start()
    helper.join(timeout=5)
    observed.append(result[0] if result else False)


def _settings(app, tmp_path):
    config_root = tmp_path / "config"
    config_root.mkdir(exist_ok=True)
    (config_root / "config.toml").write_text("# test root\n")
    catalog = CatalogService(config_root=config_root, state_root=tmp_path / "settings-state")
    service = ModelSettings(catalog)
    app.model_settings = service
    return service


def test_configuration_discover_does_not_hold_mutation_lock(app, monkeypatch):
    app.catalog = SimpleNamespace(capabilities=lambda: {"configure": True})
    observed = []

    class _Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def iter_bytes(self):
            yield json.dumps({"data": [{"id": "probe-model"}]}).encode("utf-8")

    class _Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def stream(self, method, url, headers=None):
            # Inside the (stubbed) slow HTTP call: the caller must not hold
            # the global mutation lock.
            _probe_mutation_lock(app, observed)
            return _Response()

    monkeypatch.setattr("httpx.Client", _Client)
    result = app.post(["configuration", "discover"],
                      {"service": {"baseUrl": "http://127.0.0.1:9", "apiKey": "k", "protocol": "openai"}})
    assert result["models"] == ["probe-model"]
    assert observed == [True]


def test_model_settings_discover_does_not_hold_mutation_lock(app, tmp_path, monkeypatch):
    service = _settings(app, tmp_path)
    observed = []

    def fake_worker(self, payload, *, write=False):
        _probe_mutation_lock(app, observed)
        return {"ok": True, "action": payload.get("action")}

    monkeypatch.setattr(ModelSettings, "worker", fake_worker)
    result = app.post(["model-settings", "discover"], {"fingerprint": service.fingerprint()})
    assert result["ok"] is True
    assert observed == [True]


def test_slow_model_settings_check_does_not_block_other_posts(app, tmp_path, monkeypatch):
    service = _settings(app, tmp_path)
    fingerprint = service.fingerprint()

    def slow_worker(self, payload, *, write=False):
        time.sleep(2)
        return {"ok": True}

    monkeypatch.setattr(ModelSettings, "worker", slow_worker)
    finished = []
    errors = []

    def run_check():
        try:
            app.post(["model-settings", "check"], {"fingerprint": fingerprint})
            finished.append("check")
        except Exception as exc:  # pragma: no cover - diagnostic
            errors.append(exc)

    slow = threading.Thread(target=run_check)
    started = time.monotonic()
    slow.start()
    time.sleep(0.3)  # let the slow check get inside the stubbed worker
    app.post(["ui-preferences"], {"showHints": True})
    elapsed = time.monotonic() - started
    slow.join(timeout=10)
    assert not errors
    assert finished == ["check"]
    assert elapsed < 1.5, f"unrelated POST waited {elapsed:.2f}s for the slow read-only probe"


def test_model_settings_apply_and_preview_still_hold_mutation_lock(app, tmp_path, monkeypatch):
    _settings(app, tmp_path)
    observed = []

    def probe_method(name):
        def fake(self, payload):
            _probe_mutation_lock(app, observed)
            return {"ok": True, "method": name}
        return fake

    monkeypatch.setattr(ModelSettings, "apply", probe_method("apply"))
    monkeypatch.setattr(ModelSettings, "preview", probe_method("preview"))
    app.post(["model-settings", "apply"], {"previewId": "p", "confirmPhrase": "写入预览DB"})
    app.post(["model-settings", "preview"], {"fingerprint": "whatever"})
    assert observed == [False, False]


def test_config_stale_still_enforced_outside_the_lock(app, tmp_path, monkeypatch):
    service = _settings(app, tmp_path)
    calls = []

    def fake_worker(self, payload, *, write=False):
        calls.append(payload.get("action"))
        return {"ok": True}

    monkeypatch.setattr(ModelSettings, "worker", fake_worker)

    # Stale fingerprint up front: rejected before the worker runs.
    with pytest.raises(WebError) as caught:
        app.post(["model-settings", "discover"], {"fingerprint": "stale"})
    assert caught.value.code == "CONFIG_STALE"
    assert calls == []

    # Fingerprint changes while the worker runs: rejected by the second check.
    def mutating_worker(self, payload, *, write=False):
        calls.append(payload.get("action"))
        (service.root / "config.toml").write_text("# changed during probe\n")
        return {"ok": True}

    monkeypatch.setattr(ModelSettings, "worker", mutating_worker)
    with pytest.raises(WebError) as caught:
        app.post(["model-settings", "refresh"], {"fingerprint": service.fingerprint()})
    assert caught.value.code == "CONFIG_STALE"
    assert calls == ["refresh"]
