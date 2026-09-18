import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
test('shared-origin Anthropic and OpenAI paths keep correct protocol and do not leak request secrets',async()=>{
  const dir=fs.mkdtempSync(path.join(tmpdir(),'dsh-transport-'));
  const file=path.join(dir,'routes.json');const evidence=path.join(dir,'evidence.jsonl');
  fs.writeFileSync(file,JSON.stringify({route_source:'mms:test',revisions:{bundle:'test'},routes:[
    {base_url:'https://example.test',protocol:'anthropic_messages',model:'deepseek',provider_id:'cn'},
    {base_url:'https://example.test/v1',protocol:'openai_responses',model:'gpt-test',provider_id:'gpt'}]}));
  process.env.MMS_DSH_ROUTES=file;process.env.MMS_DSH_EVIDENCE=evidence;
  const original=globalThis.fetch;globalThis.fetch=async()=>new Response('ok',{status:200});
  try{
    await import('./observe.mjs');
    await fetch('https://example.test/v1/responses',{body:JSON.stringify({model:'gpt-test',reasoning:{effort:'high'},input:'private-prompt'}),headers:{Authorization:'Bearer private-key'}});
    const text=fs.readFileSync(evidence,'utf8');const row=JSON.parse(text);
    assert.equal(row.protocol,'openai_responses');assert.equal(row.provider_id,'gpt');assert.equal(row.request_path,'/v1/responses');assert.equal(row.reasoning_effort,'high');
    assert(!text.includes('private-prompt'));assert(!text.includes('private-key'));
  }finally{globalThis.fetch=original;delete process.env.MMS_DSH_ROUTES;delete process.env.MMS_DSH_EVIDENCE;fs.rmSync(dir,{recursive:true});}
});
