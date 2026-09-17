
import json, os, pathlib, socket, subprocess, sys
root=pathlib.Path(os.environ['MMS_CONFIG_ROOT'])
import mms_core, mms_launchers, mms_capability_resolver, mms_registry_cli
# No network or child processes are permitted during this local bootstrap seam.
def forbidden(*args,**kwargs):
    raise AssertionError('external network/process invocation blocked by review harness')
socket.socket.connect=forbidden
socket.create_connection=forbidden
subprocess.Popen=forbidden
class QuietConsole:
    def print(self,*a,**kw): pass
class Input:
    def isatty(self): return True
mms_core.sys.stdin=Input()
mms_core._ensure_rich=lambda:None
mms_core.console=QuietConsole()
mms_core.Panel=lambda *a,**kw:None
mms_core._prompt_provider_credentials=lambda provider:('https://bootstrap.example.invalid/v1','sk-synthetic-review-only','https://bootstrap.example.invalid/v1','')
mms_core._probe_models=lambda provider:{'models':['deepseek-chat'],'working_url':'https://bootstrap.example.invalid/v1'}
rt={'id':'review','api_key':'sk-synthetic-review-only','openai_base_url':'https://bootstrap.example.invalid/v1','protocols':['openai_chat_completions'],'supported_clis':['opencode']}
result={'root_absent_before':not root.exists(),'initial_runtime':mms_core._load_config_or_preview_bundle()}
try:
    mms_launchers._build_opencode_config_content(rt,'deepseek-chat')
except mms_capability_resolver.CapabilityBundleError:
    result['missing_bundle_blocked']=True
else: result['missing_bundle_blocked']=False
cfg=mms_core._bootstrap_preview_root_config('en')
result['bootstrap_loaded']=bool(cfg)
assert cfg, 'first-run setup did not load runtime'
result['config_source']=cfg.get('_mms_config_source')
result['verified']=bool(mms_registry_cli.verify_approved_bundle(config_dir=root).get('verified'))
runtime=mms_core.get_provider_definition(cfg)
exports=mms_launchers.get_export_env('opencode',runtime,model_info={'model':'deepseek-chat'})
export_path=exports['OPENCODE_CONFIG']
export=json.loads(pathlib.Path(export_path).read_text())
result.update({'model':export['model'],'export_path':str(export_path),'models':list(export['provider']['mms']['models']),'endpoint':export['provider']['mms']['options']['baseURL'],'synthetic_key_matched':exports.get('MMS_OPENCODE_API_KEY')=='sk-synthetic-review-only','config_uses_env_key':export['provider']['mms']['options']['apiKey']=='{env:MMS_OPENCODE_API_KEY}','config_toml_exists':(root/'config.toml').exists(),'bootstrap_plan_leftovers':len(list(root.glob('.bootstrap-plan-*')))})
# Preserve fail-closed: clear caches to model a fresh consumer of a changed payload.
cap=root/'generated'/'model-capabilities.approved.json'
cap.write_text('{"schema":"mms.model_capabilities.approved.v1","models":[],"tampered":true}')
mms_capability_resolver.clear_capability_resolver_caches()
try:
    mms_launchers._build_opencode_config_content(runtime,'deepseek-chat')
except mms_capability_resolver.CapabilityBundleError:
    result['corrupt_bundle_blocked']=True
else: result['corrupt_bundle_blocked']=False
print(json.dumps(result,ensure_ascii=False,indent=2))
