import copy
from types import SimpleNamespace
from mms_web.context_evidence import clean_evidence, consume_prompt, observe_read, prompt_hash

def record(text, id):
    return {'id':id,'kind':'user','text':text,'contextUsage':{'state':'submitted','promptSha256':prompt_hash(text),'items':[{'kind':'skill','filePath':'/project/.agents/skills/guide/SKILL.md'}]}}

def session(*events):
    return SimpleNamespace(events=list(events),event_index={e['id']:e for e in events},meta={'cwd':'/project'})

def test_queue_read_end_stays_with_its_original_turn_and_unconsumed_is_not_loaded():
    a,b=record('first','a'),record('second','b');s=session(a,b)
    s.meta['contextEvidence']=clean_evidence({'version':1,'available':True,'promptSha256':prompt_hash('first'),'skills':[{'name':'guide','path':'/project/.agents/skills/guide/SKILL.md','listed':True}]})
    assert consume_prompt(s,'first')=='a'
    assert not b['contextUsage'].get('consumed')
    tool={'id':'tool-one','kind':'tool','title':'read','arguments':{'path':'.agents/skills/guide/SKILL.md'},'status':'running'}
    observe_read(s,tool)
    assert a['contextUsage']['items'][0]['loadState']=='loading'
    assert consume_prompt(s,'second')=='b'
    tool['status']='error';observe_read(s,tool)
    assert a['contextUsage']['items'][0]['loadState']=='failed'
    assert b['contextUsage']['items'][0]['loadState']=='loaded'
    assert not b['contextUsage']['items'][0].get('invoked')
    assert a['contextUsage']['native']['skills'][0]['loadState']=='failed'
    assert not b['contextUsage']['native']['skills'][0].get('invoked')
    # Unmatched transformations cannot attribute tool reads to a previous turn.
    consume_prompt(s,'unknown transform')
    observe_read(s,{**tool,'id':'unknown','contextEventId':None})
    assert s.meta.get('activeContextEvent') is None

def test_expanded_skill_exact_input_hash_and_repeated_prompts():
    a,b=record('/skill:guide task','a'),record('/skill:guide task','b');s=session(a,b)
    expanded='<skill>body</skill>'
    s.meta['contextEvidence']=clean_evidence({'version':1,'available':True,'promptSha256':prompt_hash(expanded),'sourcePromptSha256':prompt_hash(a['text'])})
    assert consume_prompt(s,expanded)=='a'
    assert consume_prompt(s,expanded)=='b'
    assert consume_prompt(s,expanded) is None

def test_failed_and_cancelled_inputs_cannot_capture_retry_evidence():
    a,b,c=record('retry','a'),record('retry','b'),record('retry','c')
    a['contextUsage']['state']='failed';b['status']='cancelled'
    assert consume_prompt(session(a,b,c),'retry')=='c'

def test_bounded_whitelist_does_not_store_body_or_unverified_invocation():
    value={'version':1,'available':True,'promptSha256':prompt_hash('x'),'systemPrompt':'PRIVATE_SYSTEM','rules':[{'path':'/rules','content':'PRIVATE_BODY','sha256':'bad'}], 'skills':[{'path':'/skill','invoked':True,'body':'PRIVATE_SKILL'}]*201}
    clean=clean_evidence(value)
    assert clean['truncated'] and len(clean['skills'])==200
    assert 'PRIVATE' not in repr(clean)
    assert clean['skills'][0]['state']=='available'
    assert clean_evidence({'version':1,'promptSha256':'bad'}) is None
