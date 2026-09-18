from __future__ import annotations
import copy
import hashlib
import json
import stat
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parent))
from config import convert_bundle, configure, read_config, safe_url
from run import launch_env
from mms_consumer_bundle import EXPECTED_BUNDLE_FILES, ConsumerBundleError


def payload():
    return {'component_revisions': {'bundle': 'test-bundle'}, 'payloads': {
        'router': {'runtime_ready': True, 'routes': {'deepseek-test': {'primary': {
            'provider_id': 'test', 'model_id': 'upstream-alias', 'api_key': 'test-private-value',
            'anthropic_base_url': 'https://example.test/anthropic', 'openai_base_url': 'https://example.test/v1'}}}},
        'policy': {'models': {}}, 'profile': {'profiles': {}}, 'lineup': {'routes': {}},
        'capabilities': {'models': [{'model': 'deepseek-test', 'supports_thinking': True, 'supports_vision': True,
            'context_window_tokens': 200000, 'max_output_tokens': 16000,
            'thinking_control': {'allowed_values': ['low','high'], 'supported': True}}]}}}


def bundle_dir(tmp_path, data):
    root = tmp_path/'mms'; g=root/'generated';g.mkdir(parents=True)
    manifest={'schema':'mms.model_registry.latest_approved.v1', 'files':{}}
    for k in ['bundle','model_registry','route','policy','profile','capability']:
        manifest[k+'_revision']='test-'+k
    for name, contract in EXPECTED_BUNDLE_FILES.items():
        relative, sensitivity=contract['canonical_path'],contract['sensitivity']
        f=root/relative;f.write_text(json.dumps(data['payloads'][name]))
        manifest['files'][name]={'canonical_path':relative,'sensitivity':sensitivity,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
    (g/'model-registry.latest-approved.json').write_text(json.dumps(manifest))
    return root


def test_selected_identity_protocol_and_effort_preserved():
    c=convert_bundle(payload()); r=c['routes'][0];p=c['providers'][r['provider']]
    assert p['api']=='anthropic-messages' and p['models'][0]['id']=='upstream-alias'
    assert p['models'][0]['reasoningEfforts']=={'low':'low','high':'high'}
    assert p['models'][0]['input']==['text','image']
    assert 'test-private-value' not in json.dumps({k:v for k,v in c.items() if k!='credentials'})


def test_missing_credentials_no_ambient_or_automatic_fallback():
    d=payload(); group=d['payloads']['router']['routes']['deepseek-test']
    backup=copy.deepcopy(group['primary']);backup['provider_id']='backup'
    group['primary']['api_key']='';group['fallbacks']=[backup]
    c=convert_bundle(d)
    assert len(c['routes'])==1 and c['routes'][0]['rank']==1
    assert len(c['excluded'])==1
    group['fallbacks']=[]
    with pytest.raises(ConsumerBundleError): convert_bundle(d)


def test_invalid_bundle_never_reads_legacy(tmp_path):
    root=bundle_dir(tmp_path,payload())
    (root/'model-routes.json').write_text('{}')
    (root/'generated/model-routes.json').write_text('{}')
    with pytest.raises(ConsumerBundleError,match='hash mismatch'): read_config(root)
    with pytest.raises(ConsumerBundleError,match='missing'): read_config(tmp_path/'missing')


def test_private_configuration_and_model_policy(tmp_path):
    d=payload();root=bundle_dir(tmp_path,d);instance=tmp_path/'instance'
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    configure(root,instance,'deepseek-test')
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
    assert stat.S_IMODE((instance/'home/.credentials.yaml').stat().st_mode)==0o600
    assert 'test-private-value' not in (instance/'mms.patch.yml').read_text()
    assert 'test-private-value' not in (instance/'routes.json').read_text()
    d['payloads']['policy']['models']['deepseek-test']={'visible':False}
    with pytest.raises(ConsumerBundleError): convert_bundle(d)


def test_clean_environment(tmp_path,monkeypatch):
    for k in ['ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_HOME','CLAUDE_CONFIG_DIR','NODE_OPTIONS','MMS_CONFIG_ROOT','MMS_REAL_HOME']:
        monkeypatch.setenv(k,'must-not-inherit')
    e=launch_env(tmp_path,Path('/usr/bin/node'))
    assert 'must-not-inherit' not in e.values()
    assert e['HOME']==str(tmp_path/'user-home')


@pytest.mark.parametrize('url',['https://secret@example.test/v1','https://example.test/v1?key=secret'])
def test_endpoint_rejects_credential_leaks(url):
    with pytest.raises(ValueError): safe_url(url)


def test_restart_preserves_user_dsh_credentials(tmp_path):
    root=bundle_dir(tmp_path,payload());instance=tmp_path/'instance'
    configure(root,instance,'deepseek-test')
    with pytest.raises(ValueError,match='must be parsed'):
        configure(root,instance,'deepseek-test')
    previous={'version':1,'refs':{'USER_OWN_KEY':'user-only-secret','MMS_DSH_STALE':'removed'},'records':{}}
    configure(root,instance,'deepseek-test',previous_credentials=previous)
    stored=json.loads((instance/'home/.credentials.yaml').read_text())
    assert stored['refs']['USER_OWN_KEY']=='user-only-secret'
    assert 'MMS_DSH_STALE' not in stored['refs']


@pytest.mark.parametrize('base,anth,expected',[
    ('https://example.test','https://example.test','https://example.test/v1'),
    ('https://example.test/v1','https://example.test','https://example.test/v1'),
    ('https://example.test/openai','https://example.test/anthropic','https://example.test/openai'),
])
def test_openai_endpoint_matches_mms_sdk_root(base,anth,expected):
    from config import protocol_for
    protocol,url,_=protocol_for('gpt-test',{'openai_base_url':base,'anthropic_base_url':anth})
    assert protocol=='openai_responses' and url==expected


def test_mms_shipped_capabilities_fill_missing_metadata_but_never_override_policy():
    d=payload();group=d['payloads']['router']['routes'].pop('deepseek-test')
    group['primary']['model_id']='gpt-5.6-sol';d['payloads']['router']['routes']['gpt-5.6-sol']=group
    c=convert_bundle(d);model=next(iter(c['providers'].values()))['models'][0]
    assert model['contextWindow']==1050000 and 'image' in model['input']
    assert 'high' in model['reasoningEfforts']
    d['payloads']['policy']['models']['gpt-5.6-sol']={'capabilities':{'vision':False}}
    assert next(iter(convert_bundle(d)['providers'].values()))['models'][0]['input']==['text']
