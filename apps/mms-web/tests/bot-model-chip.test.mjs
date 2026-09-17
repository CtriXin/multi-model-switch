import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import esbuild from 'esbuild';
import React from 'react';

const code=esbuild.transformSync(fs.readFileSync(new URL('../src/BotModelPicker.tsx',import.meta.url),'utf8'),{loader:'tsx',format:'cjs'}).code;
const mod={exports:{}};
vm.runInNewContext(code,{module:mod,exports:mod.exports,React,require:()=>({})});
const {BotModelPicker}=mod.exports;
for(const disabled of [false,true]) test(`Bot model chip forwards native pointer/keyboard disabled=${disabled}`,()=>{
  const tree=BotModelPicker({bot:{model:'current',pendingPresetId:'next'},presets:[{id:'next',name:'Next model'}],models:[],disabled,change:async()=>{}});
  assert.equal(tree.props.disabled,disabled);
  assert.equal(tree.props.title,'切换 Bot 模型');
  assert.equal(tree.props.label,'当前 current · 下一轮 Next model');
  const menu=tree.props.children(()=>{},true);
  assert.equal(menu.props.value,'next');
  assert.equal(menu.props.disabled,disabled);
});
test('quick Bot model selection waits for the API and propagates rejection',async()=>{
  let resolve,reject;
  const calls=[];
  const tree=BotModelPicker({bot:{presetId:'old'},presets:[],models:[],change:id=>{calls.push(id);return new Promise((a,b)=>{resolve=a;reject=b;});}});
  const menu=tree.props.children(()=>{},true);
  let settled=false;
  const result=menu.props.change('new').then(()=>{settled=true;});
  await Promise.resolve();assert.equal(settled,false);assert.deepEqual(calls,['new']);
  resolve();await result;assert.equal(settled,true);
  const failed=menu.props.change('bad');reject(new Error('fixture rejection'));
  await assert.rejects(failed,/fixture rejection/);
});

import { botModelSelectionPatch } from '../src/bot-model-switch.ts';
test('actual header and settings callbacks replace pending instead of mutating the running model', async () => {
  for (const file of ['Bot.tsx','BotPresetPanel.tsx']) {
    const source=fs.readFileSync(new URL('../src/'+file,import.meta.url),'utf8');
    const callback=source.match(/change=\{(async \(?presetId\)? => \{[\s\S]*?botModelSelectionPatch[\s\S]*?\})\}/)?.[1];
    assert.ok(callback, file+' must use the next-round boundary');
    for (const chosen of ['new','current']) {
      const calls=[];
      const context={bot:{id:'b',presetId:'current',pendingPresetId:'old-pending',status:'running'},botModelSelectionPatch,onUpdateBot:async (...args)=>calls.push(args)};
      const fn=vm.runInNewContext('('+callback+')',context);
      await fn(chosen);
      assert.deepEqual(calls,[['b',{pendingPresetId:chosen==='current'?'':chosen}]]);
    }
  }
});
