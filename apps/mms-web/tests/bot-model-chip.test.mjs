import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import esbuild from 'esbuild';

const source = fs.readFileSync(new URL('../src/Bot.tsx', import.meta.url), 'utf8');
const marker = source.indexOf('className="bot-chat-model-line"');
assert.ok(marker > 0, 'the model chip must remain in the actual Bot header');
const start = source.lastIndexOf('<p', marker);
const end = source.indexOf('</p>', marker) + 4;
const code = esbuild.transformSync(`result = (${source.slice(start, end)});`, {loader:'tsx'}).code;

for (const [event, key, editable, opens] of [
  ['click', '', true, true], ['key', 'Enter', true, true], ['key', ' ', true, true],
  ['key', 'Escape', true, false], ['click', '', false, false], ['key', 'Enter', false, false],
]) {
  test(`actual Bot model chip ${event}/${key || 'pointer'} editable=${editable}`, () => {
    const calls = [];
    const context = {React:{createElement:(_tag,props)=>props},result:null,
      onUpdateBot:editable ? ()=>{} : undefined,
      bot:{model:'current',pendingPresetId:'next'},presets:[{id:'next',name:'Next model'}],
      setOnboardingEditing:value=>calls.push(['settings',value]),
      setSchedulePanelOpen:value=>calls.push(['schedule',value]),
      setTimeout:callback=>callback(),
      document:{getElementById:id=>{
        assert.equal(id,'bot-preset-model-section');
        return {scrollIntoView:()=>calls.push(['scroll']),querySelector:selector=>{
          assert.match(selector,/model-picker-trigger/);return {focus:()=>calls.push(['focus'])};
        }};
      }},
    };
    vm.runInNewContext(code,context);
    assert.equal(context.result.role,editable ? 'button' : undefined);
    assert.equal(context.result.tabIndex,editable ? 0 : -1);
    let prevented = false;
    if(event==='click')context.result.onClick();
    else context.result.onKeyDown({key,preventDefault:()=>{prevented=true;}});
    assert.deepEqual(calls,opens ? [['settings',true],['schedule',false],['scroll'],['focus']] : []);
    assert.equal(prevented,event==='key' && opens);
  });
}
