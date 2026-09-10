"""Model discovery reads only the explicitly supplied endpoint; no inference or config."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from mms_web.connections import discover_models
from mms_web.errors import WebError


@pytest.fixture
def model_service():
    records = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            records.append((self.path, self.headers.get('Authorization')))
            code = int(self.path.split('/')[1]) if self.path.split('/')[1].isdigit() else 200
            self.send_response(code)
            if code == 302: self.send_header('Location', '/should-never-be-requested')
            self.end_headers()
            payload = {'data': [{'id': 'z-model'}, {'id': 'a-model'}, {'id':'z-model'}, {'id':'bad\nmodel'}, {}, {'id':None}]}
            if self.path.startswith('/invalid/'): payload = {'error':'upstream private body'}
            self.wfile.write(json.dumps(payload).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}', records
    server.shutdown(); server.server_close(); thread.join()


def test_discovery_exact_path_and_no_inference(model_service, monkeypatch):
    url, records = model_service
    monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:1')
    result = discover_models({'service':{'baseUrl':url+'/gateway/v1/', 'apiKey':'task-key', 'protocol':'openai'}})
    assert result['models'] == ['a-model', 'z-model']
    assert result['requestUrl'] == url+'/gateway/v1/models'
    assert result['generationVerified'] is False
    assert records == [('/gateway/v1/models','Bearer task-key')]


@pytest.mark.parametrize('path,code', [('401','SERVICE_AUTH_FAILED'), ('403','SERVICE_AUTH_FAILED'), ('429','SERVICE_RATE_LIMITED'), ('302','SERVICE_REDIRECT'), ('404','MODELS_ENDPOINT_MISSING'), ('500','SERVICE_UNAVAILABLE'), ('invalid','INVALID_MODEL_LIST')])
def test_discovery_failure_does_not_retry_or_expose_upstream(model_service, path, code):
    url, records = model_service
    with pytest.raises(WebError) as caught:
        discover_models({'service':{'baseUrl':url+'/'+path, 'apiKey':'task-secret'}})
    assert caught.value.code == code
    assert 'task-secret' not in str(caught.value) and 'private body' not in str(caught.value)
    assert len(records) == 1


@pytest.mark.parametrize('override,code', [({'protocol':'anthropic'}, 'MODELS_MANUAL_REQUIRED'), ({'baseUrl':'https://key@example.test'},'INVALID_SERVICE_URL'), ({'baseUrl':'https://example.test/v1?key=secret'},'INVALID_SERVICE_URL'), ({'baseUrl':'file:///tmp'},'INVALID_SERVICE_URL'), ({'baseUrl':'http://localhost:wrong'},'INVALID_SERVICE_URL'), ({'apiKey':''}, 'INVALID_SERVICE_KEY'), ({'apiKey':'key\nx'},'INVALID_SERVICE_KEY')])
def test_invalid_inputs_do_not_issue_requests(model_service, override, code):
    url, records = model_service
    with pytest.raises(WebError) as caught:
        discover_models({'service':{'baseUrl':url, 'apiKey':'task-key', **override}})
    assert caught.value.code == code
    assert not records
