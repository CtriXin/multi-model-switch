"""Read-only MMS approved-bundle to DSH configuration adapter."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from mms_consumer_bundle import ConsumerBundleError, load_verified_consumer_bundle
from mms_capability_resolver import resolve_model_capabilities

DSH_VERSION = '0.1.6-alpha.2'
PROTOCOLS = {'anthropic_messages': 'anthropic-messages', 'openai_chat_completions': 'openai-completions', 'openai_responses': 'openai-responses'}


def safe_url(value: str) -> str:
    p = urlsplit(value)
    if p.scheme not in {'https', 'http'} or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('Endpoint must be an explicit HTTP(S) URL without credentials or query parameters')
    return value.rstrip('/')


def visible(name, policy, project='dsh'):
    item = policy.get('models', {}).get(name, {})
    project_policy = policy.get('projects', {}).get(project, {})
    if item.get('visible') is False or item.get('hidden') is True or item.get('enabled') is False:
        return False
    if name in project_policy.get('deny', []):
        return False
    allowed = project_policy.get('allow')
    return not allowed or name in allowed


def anthropic_root(url):
    value = safe_url(url)
    if value.endswith('/v1/messages'):
        return value[:-12]
    if value.endswith('/v1'):
        return value[:-3]
    return value


def openai_root(route):
    # Same endpoint semantics as MMS _pi_openai_base_url; the OpenAI SDK
    # appends /responses or /chat/completions, unlike Anthropic's /v1/messages.
    value = safe_url(route['openai_base_url'])
    path = urlsplit(value).path.rstrip('/')
    if path.rsplit('/', 1)[-1].lower() == 'v1':
        return value
    anth = anthropic_root(route['anthropic_base_url']) if route.get('anthropic_base_url') else ''
    return value + '/v1' if not path or anth == value else value


def protocol_for(name, route):
    # Explicit route URLs only: do not infer /anthropic from an OpenAI root.
    openai_family = name.lower().startswith(('gpt-', 'o1', 'o3', 'o4', 'codex-'))
    if route.get('anthropic_base_url') and not openai_family:
        return 'anthropic_messages', anthropic_root(route['anthropic_base_url']), ''
    if route.get('openai_base_url'):
        protocol = 'openai_responses' if openai_family else 'openai_chat_completions'
        reason = 'OpenAI-family Responses route' if openai_family else 'Approved route has no Anthropic endpoint'
        return protocol, openai_root(route), reason
    raise ValueError('No supported explicit endpoint in approved route')


def convert_bundle(bundle):
    p = bundle['payloads']
    # Bundle readiness aggregates all leaves; reject unavailable leaves below,
    # while preserving the diagnostic for the user instead of inventing secrets.
    providers, credentials, routes, excluded = {}, {}, [], []
    builtin_path = REPO / 'config/provider-profiles.json'
    builtin_bytes = builtin_path.read_bytes() if builtin_path.exists() else b'{}'
    builtin_profiles = json.loads(builtin_bytes)
    for logical, group in p['router'].get('routes', {}).items():
        if not visible(logical, p['policy']):
            excluded.append({'model': logical, 'reason': 'hidden by MMS policy'})
            continue
        for rank, route in enumerate([group.get('primary', {}), *group.get('fallbacks', [])]):
            provider = route.get('provider_id', '')
            reason = None
            profile = p['profile'].get('profiles', {}).get(provider, {})
            if profile.get('enabled') is False or logical in profile.get('hidden_models', []):
                reason = 'provider disabled or model hidden'
            elif not route.get('api_key'):
                reason = 'No API key in approved route; OAuth is not imported'
            elif not route.get('model_id') or not provider:
                reason = 'Incomplete approved route identity'
            # Image generators are not conversational agent models.
            elif logical.startswith('gpt-image-'):
                reason = 'Image generation endpoint is not an agent conversation API'
            if reason:
                excluded.append({'model': logical, 'provider': provider, 'rank': rank, 'reason': reason})
                continue
            try:
                protocol, endpoint, fallback_reason = protocol_for(logical, route)
                # One explicit route per logical model and source: no ambiguous
                # same-wire-id overwrite, no native pi-ai provider fallback.
                digest = hashlib.sha256(f'{logical}\0{provider}\0{rank}'.encode()).hexdigest()[:12]
                route_id = 'mms-' + digest
                reference = 'MMS_DSH_' + digest.upper()
                caps = resolve_model_capabilities(logical, provider_id=provider, base_url=endpoint, protocol=protocol,
                    approved_facts=p['capabilities'], model_policy=p['policy'], provider_profiles=p['profile'])
                # MMS ships non-secret capability defaults in its versioned profile
                # catalog. Fill only absent approved/policy metadata, never routes,
                # credentials or request-body quirks from this fallback.
                baseline = resolve_model_capabilities(logical, provider_id=provider, base_url=endpoint,
                    protocol=protocol, approved_facts={}, model_policy={}, provider_profiles=builtin_profiles)
                for field in ('context_window_tokens', 'max_output_tokens', 'supports_vision', 'supports_thinking', 'thinking_control'):
                    if caps['sources'][field] == 'conservative_fallback' and baseline['sources'][field] == 'provider_profile':
                        caps[field] = baseline[field]
                        caps['sources'][field] = 'mms_builtin_profile'
                if any(caps.get('body_patch_aliases', {}).get(k) for k in ('body_patches', 'parameter_aliases', 'model_aliases')):
                    raise ValueError('Route needs custom profile request shaping; not silently approximated')
                thinking = caps.get('thinking_control') or {}
                values = thinking.get('allowed_values') or thinking.get('allowed') or []
                if thinking.get('disable_supported') is False:
                    values = [v for v in values if v not in {'none', 'off'}]
                efforts = {('off' if v in {'none', 'off'} else v): (None if v in {'none', 'off'} else v)
                           for v in values if v in {'none', 'off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'}}
                preference = p['policy'].get('models', {}).get(logical, {}).get('capabilities', {}).get('reasoning_effort')
                if not efforts and (caps.get('supports_thinking') or caps['sources']['supports_thinking'] == 'conservative_fallback'):
                    # Expose only a declared MMS preference when no allowed list exists.
                    if preference in {'minimal', 'low', 'medium', 'high', 'xhigh', 'max'}:
                        efforts = {preference: preference}
                        caps['sources']['supports_thinking'] = 'model_policy_preference'
                lineup_group = p['lineup'].get('routes', {}).get(logical, {})
                lineup = ([lineup_group.get('primary', {})] + lineup_group.get('fallbacks', []))
                route_meta = next((m for m in lineup if m.get('provider_id') == provider and m.get('model_id') == route['model_id']), {})
                context = caps['context_window_tokens']
                if caps['sources']['context_window_tokens'] == 'conservative_fallback':
                    context = route_meta.get('max_context_tokens') or context
                model = {'id': route['model_id'], 'name': logical,
                    'contextWindow': context, 'maxTokens': caps['max_output_tokens'],
                    'input': ['text', 'image'] if caps.get('supports_vision') else ['text'],
                    'reasoningEfforts': efforts or False}
                label = f'{logical} · {profile.get("name", provider)}' + (' · 备用' if rank else '')
                item = {'displayName': label, 'apiKeyEnv': reference, 'api': PROTOCOLS[protocol],
                    'baseURL': endpoint, 'models': [model], 'retryPolicy': {'mode': 'normal', 'maxRetries': 1}}
                if protocol == 'openai_chat_completions':
                    item['compat'] = {'supportsDeveloperRole': False}
                if preference in efforts and preference != 'off':
                    item['reasoning'] = preference
                providers[route_id] = item
                credentials[reference] = route['api_key']
                routes.append({'logical_model': logical, 'provider_id': provider, 'provider': route_id,
                    'model': route['model_id'], 'rank': rank, 'protocol': protocol, 'base_url': endpoint,
                    'fallback_reason': fallback_reason, 'credential_ref': reference,
                    'capability_sources': caps['sources'], 'input': model['input'], 'reasoning_efforts': list(efforts)})
            except ValueError as exc:
                excluded.append({'model': logical, 'provider': provider, 'rank': rank, 'reason': str(exc)})
    if not providers:
        raise ConsumerBundleError('No supported credential-bound MMS routes available')
    return {'providers': providers, 'credentials': credentials, 'routes': routes, 'excluded': excluded,
            'builtin_capability_sha256': hashlib.sha256(builtin_bytes).hexdigest(),
            'bundle_runtime_ready': p['router'].get('runtime_ready'),
            'bundle_runtime_ready_reason': p['router'].get('runtime_ready_reason', ''),
            'revisions': bundle['component_revisions'], 'route_source': 'mms:latest-approved:' + bundle['component_revisions']['bundle']}


def read_config(root):
    return convert_bundle(load_verified_consumer_bundle(config_root=root, include_secret=True))


def private_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + '.tmp')
    fd = __import__('os').open(temporary, __import__('os').O_WRONLY | __import__('os').O_CREAT | __import__('os').O_TRUNC, 0o600)
    with __import__('os').fdopen(fd, 'w') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def configure(root: Path, instance: Path, default_model='deepseek-v4-flash', plugin_path=None, previous_credentials=None):
    data = read_config(root)
    choices = [r for r in data['routes'] if r['logical_model'] == default_model and r['rank'] == 0]
    if len(choices) != 1:
        raise ValueError('Requested default model has no supported primary route')
    choice = choices[0]
    dsh_home = instance / 'home'
    dsh_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Dedicated DSH credential store; no keys enter configuration or subprocess env.
    credential_file = dsh_home / '.credentials.yaml'
    if credential_file.exists() and previous_credentials is None:
        raise ValueError('Existing DSH credential store must be parsed before updating MMS references')
    previous = previous_credentials or {'version': 1, 'refs': {}, 'records': {}}
    if previous.get('version') != 1 or not isinstance(previous.get('refs', {}), dict):
        raise ValueError('Unknown DSH credential document; refusing to overwrite')
    kept = {k: v for k, v in previous.get('refs', {}).items() if not k.startswith('MMS_DSH_')}
    private_json(credential_file, {**previous, 'refs': {**kept, **data['credentials']}})
    metadata = {k: v for k, v in data.items() if k not in {'providers', 'credentials'}}
    private_json(instance / 'routes.json', metadata)
    default = {'provider': choice['provider'], 'model': choice['model']}
    preference = data['providers'][choice['provider']].get('reasoning')
    if preference:
        default['reasoningEffort'] = preference
    patch = [
        {'id': 'llm-pi-ai', 'config': {'providers': data['providers']}},
        {'id': 'llm-deepseek', 'disabled': True},
        {'id': 'agent-default-model', 'config': default},
        {'id': 'session-title-llm', 'disabled': True},
        {'id': 'hmr', 'disabled': True},
        {'id': 'directory-picker', 'disabled': True},
        {'insert': [{'id': 'mms-directory-picker', 'name': '@deepseek-ai/dsh-host-directory-picker-browse'},
                    {'id': 'mms-directory-picker-ui', 'name': '@deepseek-ai/dsh-client-ui-directory-picker-browse'}]},
        {'insert': [{'id': 'mms-recipe', 'name': str(plugin_path or Path(__file__).with_name('plugin.mjs')),
                     'config': {'root': str(instance), 'recipeCore': (REPO / 'apps/mms-web/src/recipe-core.ts').as_uri()}}]},
    ]
    private_json(instance / 'mms.patch.yml', patch)
    return metadata
