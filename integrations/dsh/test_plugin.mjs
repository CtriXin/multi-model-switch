import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const {checkRequirements, apply} = await import(process.env.MMS_DSH_TEST_PLUGIN);
const recipe = {modelRequirements:{image:true,reasoning:true},requiredSkills:['test-skill']};
const info = {inputModalities:['text','image'],reasoning:{efforts:[{id:'high'}]}};
const skills = [{name:'test-skill',invocation:{modelInvocable:true}}];
test('required model capabilities and actual skill availability fail closed',()=>{
  checkRequirements(recipe,info,skills);
  assert.throws(()=>checkRequirements(recipe,{...info,inputModalities:['text']},skills),/图片/);
  assert.throws(()=>checkRequirements(recipe,{...info,reasoning:undefined},skills),/推理/);
  assert.throws(()=>checkRequirements(recipe,info,[]),/Skill/);
  assert.throws(()=>checkRequirements(recipe,info,[...skills,...skills]),/Skill/);
});
test('plugin restores persisted requirements and checks the frozen actual request',async()=>{
  const root=mkdtempSync(join(tmpdir(),'mms-dsh-recipe-'));
  const fs=await import('node:fs');
  let hook, command, queued=[];
  const agent={status:'idle',session:{id:'test-session',header:{cwd:'/tmp'}},ctx:{skills:{list:async()=>[]}},followup:m=>queued.push(m)};
  const ctx={on:(name,callback)=>{assert.equal(name,'agent/request');hook=callback;},
    skills:{list:async()=>[]},commands:{register:c=>command=c},llm:{resolveModelInfo:async(p,m)=>{assert.equal(p,'actual-provider');return {inputModalities:m==='vision'?['image','text']:['text']};}}};
  const config={root,recipeCore:new URL('../../apps/mms-web/src/recipe-core.ts',import.meta.url).href};
  await apply(ctx,config);
  fs.writeFileSync(join(root,'recipes','demo.json'),JSON.stringify({format:'mms-work-recipe-v2',title:'test',prompt:'请整理 {{goal}}',variables:['goal'],modelRequirements:{image:true}}));
  assert.equal((await command.handler({agent,rawInput:'use demo {"goal":"反馈"}'})).kind,'success');
  assert.equal(queued.length,1);
  await assert.rejects(()=>hook({agent},async()=>({provider:'actual-provider',model:'text'})),/图片/);
  assert.equal((await hook({agent},async()=>({provider:'actual-provider',model:'vision'}))).model,'vision');
  await apply(ctx,config); // New plugin instance, same persisted session.
  await assert.rejects(()=>hook({agent},async()=>({provider:'actual-provider',model:'text'})),/图片/);
  assert.equal((await command.handler({agent,rawInput:'clear'})).kind,'success');
  assert.equal((await hook({agent},async()=>({provider:'actual-provider',model:'text'}))).model,'text');
  rmSync(root,{recursive:true});
});
