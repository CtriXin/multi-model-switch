"""Regression tests for probe attempts / first-error reporting / evidence request_path.

Reproduces the 2026-09-06 newapi-personal-tokyo incident:
- base_url request got 401 (auth rejected on dashboard-style endpoint)
- alt_url (/v1) request got 404 (path does not exist)
- old code reported only the last exception (404), masking the real 401
- config web evidence recorded the configured models_endpoint instead of the
  actually requested path.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_core():
    import mms_core

    return importlib.reload(mms_core)


class _FakeResponse:
    def __init__(self, status_code: int, url: str, payload: dict | None = None):
        self.status_code = status_code
        self.url = url
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise _FakeHTTPStatusError(self)


class _FakeHTTPStatusError(Exception):
    def __init__(self, response: _FakeResponse):
        super().__init__(f"Client error '{response.status_code} reason' for url '{response.url}'")
        self.response = response


def _provider(**overrides) -> dict:
    provider = {
        "id": "probe-regression",
        "name": "probe-regression",
        "protocols": ["openai_chat_completions"],
        "models_endpoint": "/api/models/info?",
        "openai_base_url": "http://127.0.0.1:4003",
        "api_key": "sk-test-key",
        "fallback_models": [],
        "extra_models": [],
        "hidden_models": [],
    }
    provider.update(overrides)
    return provider


def _install(monkeypatch, tmp_path, router):
    core = _load_core()
    monkeypatch.setattr(core, "_PROBE_FILE_CACHE_DIR", str(tmp_path / "probe-cache"))
    monkeypatch.setattr(core, "_PROBE_CACHE", {})
    monkeypatch.setattr(core, "_runtime_httpx_request", lambda method, url, **kwargs: router(url))
    return core


def test_probe_failure_reports_first_error_not_alt_404(monkeypatch, tmp_path):
    """401 on base_url must not be masked by alt_url's 404."""

    def router(url):
        if "/v1/api/models/info" in url:
            return _FakeResponse(404, url)
        return _FakeResponse(401, url, {"code": "AUTH_UNAUTHORIZED", "message": "Unauthorized, invalid access token"})

    core = _install(monkeypatch, tmp_path, router)
    result = core._probe_models(_provider(), emit_output=False, force_refresh=True, skip_cache=True)

    assert result["error_kind"] == "request_failed"
    # first exception (401) wins; the alt /v1 404 must not be the headline error
    assert "401" in result["error"]
    assert "'/v1/api/models/info" not in result["error"].replace("http://127.0.0.1:4003/v1/api/models/info", "'/v1/api/models/info") or "401" in result["error"]
    assert "/v1/api/models/info" not in result["error"]

    attempts = result["attempts"]
    assert [a["status"] for a in attempts] == ["HTTP 401", "HTTP 404"]
    assert attempts[0]["url"] == "http://127.0.0.1:4003/api/models/info?"
    assert attempts[1]["url"] == "http://127.0.0.1:4003/v1/api/models/info?"
    # no key material in attempts
    assert "sk-test-key" not in str(attempts)

    details_text = "\n".join(result["details"])
    assert "attempts:" in details_text
    assert "HTTP 401" in details_text


def test_probe_success_records_attempt_and_working_url(monkeypatch, tmp_path):
    def router(url):
        if url.endswith("/v1/models"):
            return _FakeResponse(200, url, {"data": [{"id": "m-a"}, {"id": "m-b"}]})
        return _FakeResponse(404, url)

    core = _install(monkeypatch, tmp_path, router)
    result = core._probe_models(
        _provider(models_endpoint="/models"), emit_output=False, force_refresh=True, skip_cache=True
    )

    assert result["error"] is None
    assert result["working_url"] == "http://127.0.0.1:4003/v1"
    assert result["models"] == ["m-a", "m-b"]
    assert [a["status"] for a in result["attempts"]] == ["HTTP 404", "ok (2 models)"]
    assert result["attempts"][-1]["url"] == "http://127.0.0.1:4003/v1/models"


def test_config_web_evidence_uses_actual_request_path(monkeypatch, tmp_path):
    """Evidence request_path must reflect the real attempted path, not the configured endpoint."""

    def router(url):
        if "/v1/api/models/info" in url:
            return _FakeResponse(404, url)
        return _FakeResponse(401, url)

    core = _install(monkeypatch, tmp_path, router)
    import mms_config_web

    payload = {"provider": _provider()}
    result = mms_config_web.test_provider_models({"providers": []}, payload)

    assert result["ok"] is False
    evidence = result["cache_transport_evidence"]
    # first real request path, without query string, without /v1 prefix from alt attempt
    assert evidence["request_path"] == "/api/models/info"
    assert "sk-test-key" not in str(result)


def test_config_web_evidence_prefers_successful_attempt(monkeypatch, tmp_path):
    def router(url):
        if url.endswith("/v1/models"):
            return _FakeResponse(200, url, {"data": [{"id": "m-a"}]})
        return _FakeResponse(404, url)

    core = _install(monkeypatch, tmp_path, router)
    import mms_config_web

    payload = {"provider": _provider(models_endpoint="/models")}
    result = mms_config_web.test_provider_models({"providers": []}, payload)

    assert result["ok"] is True
    assert result["cache_transport_evidence"]["request_path"] == "/v1/models"


def test_config_web_evidence_falls_back_without_attempts(monkeypatch):
    """Old stub probes without attempts keep the legacy derived path (compat)."""

    import mms_config_web

    monkeypatch.setattr(
        mms_config_web,
        "probe_provider_models",
        lambda provider, force_refresh=False: {
            "models": ["m-a"],
            "raw_models": ["m-a"],
            "base_source": "remote",
            "working_url": "https://demo.example/v1",
            "details": ["ok"],
        },
    )
    result = mms_config_web.test_provider_models(
        {"providers": []}, {"provider": {"id": "demo", "openai_base_url": "https://demo.example/v1", "api_key": "sk-x"}}
    )
    assert result["cache_transport_evidence"]["request_path"] == "/models"
