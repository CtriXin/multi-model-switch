import test from 'node:test';
import assert from 'node:assert/strict';
import { mountModule, text } from './helpers/component-hook-harness.mjs';

const detail = { session: { id:'s:1', title:'布局任务', workspaceId:'w', cwd:'/tmp/work', presetId:'p', owner:'web', state:'error', capabilities:{send:true} }, recovery:{suggested:true,retryExhausted:true} };
const packet = {sourceSessionId:'s:1', title:'布局任务', workspaceId:'w', cwd:'/tmp/work', prompt:'先核对文件，禁止重放 /tmp/old.jsonl', nativeHistoryAvailable:true};
const data = { workspaces:[{id:'w',name:'工作目录',path:'/tmp/work'},{id:'u',name:'未登记',path:'/tmp/unregistered',unregistered:true}], presets:[{id:'p',name:'模型甲',harness:'pi',available:true},{id:'q',name:'模型乙',harness:'pi',available:true}], models:[], capabilities:{launch:true} };
async function setup(options={}) {
  const reads=[], actions=[], drafts=[], copied=[];
  let closed=0;
  const view=mountModule('./SessionRecovery', async path=>{reads.push(path); if(options.loadError) throw Error('本地服务断连'); return packet;}, {
    './components':{Dialog:'Dialog'}, './LaunchOptions':{ModelPicker:'ModelPicker'},
    './clipboard':{copyText:async value=>{if(options.copyError) throw Error('denied'); copied.push(value);}},
  });
  await view.mount(options.entry?'SessionRecovery':'RecoveryDialog', {
    detail: options.detail||detail, data, favorites:[], toggleFavorite(){}, busy:false,
    action:async(path,body)=>{actions.push([path,body]);return options.switchFailed ? false : true;},
    prepare:draft=>drafts.push(draft),close:()=>closed++,
  });
  const button=label=>view.one(n=>n.type==='button'&&text(n)===label);
  return {view,button,reads,actions,drafts,copied,get closed(){return closed;}};
}

test('production recovery dialog loads without model calls; editing/copying/preparing never executes',async()=>{
  const h=await setup();
  assert.deepEqual(h.reads,['/sessions/s%3A1/recovery']);
  assert.equal(h.actions.length,0);
  const preview=h.view.one(n=>n.type==='textarea');
  preview.props.onChange({target:{value:'核对之后继续，不部署'}}); await h.view.settle();
  h.view.one(n=>n.type==='ModelPicker').props.change('q'); await h.view.settle();
  await h.button('复制接续信息').props.onClick(); await h.view.settle();
  assert.deepEqual(h.copied,['核对之后继续，不部署']);
  assert.equal(h.button('在新会话中准备接续').props.disabled,false);
  h.button('在新会话中准备接续').props.onClick();
  assert.equal(h.drafts[0].prompt,'核对之后继续，不部署');
  assert.equal(h.drafts[0].presetId,'q');
  assert.equal(h.drafts[0].workspaceId,'w');
  assert.equal(h.actions.length,0);
  assert.equal(h.closed,1);
});

test('copy failure retains editable packet, and model switch sends no prompt',async()=>{
  const h=await setup({copyError:true});
  await h.button('复制接续信息').props.onClick(); await h.view.settle();
  assert.match(text(h.view.tree),/复制失败/);
  assert.equal(h.view.one(n=>n.type==='textarea').props.value,packet.prompt);
  await h.button('在原会话切换模型').props.onClick(); await h.view.settle();
  assert.deepEqual(JSON.parse(JSON.stringify(h.actions)),[['/sessions/s%3A1/model',{presetId:'p'}]]);
  assert.equal(h.drafts.length,0);
});

test('live execution blocks continuation but leaves local copy available',async()=>{
  const h=await setup({detail:{...detail,session:{...detail.session,state:'running'}}});
  assert.equal(h.button('在新会话中准备接续').props.disabled,true);
  assert.equal(h.button('在原会话切换模型').props.disabled,true);
  h.button('在新会话中准备接续').props.onClick();
  assert.equal(h.drafts.length,0);
  assert.equal(h.button('复制接续信息').props.disabled,undefined);
});

test('CLI rescue requires explicit model and registered folder; never adopts automatically',async()=>{
  const h=await setup({detail:{...detail,session:{...detail.session,owner:'cli',cwd:'/tmp/unregistered',workspaceId:'u',presetId:undefined}}});
  assert.equal(h.button('在新会话中准备接续').props.disabled,true);
  assert.doesNotMatch(text(h.view.tree),/在原会话切换模型/);
  const select=h.view.one(n=>n.type==='select');
  assert.equal(select.props.value,'');
  select.props.onChange({target:{value:'w'}});
  h.view.one(n=>n.type==='ModelPicker').props.change('q'); await h.view.settle();
  assert.equal(h.button('在新会话中准备接续').props.disabled,false);
  assert.match(text(h.view.tree),/新会话将在/);
});

test('load failure is retryable and cannot create an empty rescue',async()=>{
  const h=await setup({loadError:true});
  assert.match(text(h.view.tree),/接续资料暂时无法读取/);
  assert.equal(h.button('在新会话中准备接续').props.disabled,true);
  h.button('重新读取资料').props.onClick(); await h.view.settle();
  assert.equal(h.reads.length,2);
  assert.equal(h.actions.length,0);
});

test('production entry distinguishes model retry exhaustion and remains available on healthy session',async()=>{
  const failed=await setup({entry:true});
  assert.match(text(failed.view.tree),/模型自动重试已用尽/);
  const healthy=await setup({entry:true,detail:{...detail,session:{...detail.session,state:'idle'},recovery:{suggested:false}}});
  assert.doesNotMatch(text(healthy.view.tree),/失败|用尽/);
  assert.ok(healthy.button('接续工作'));
  assert.equal(healthy.reads.length,0);
});

test('asynchronous packet focuses the actual rendered preview after it mounts',async()=>{
  const h=await setup();
  assert.ok(h.view.calls.some(([kind,element])=>kind==='focus' && element==='textarea'));
});

test('production App navigation preserves the active recovery draft when returning home',async()=>{
  const {readFileSync}=await import('node:fs');
  const {runInNewContext}=await import('node:vm');
  const source=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
  const start=source.indexOf('  function navigate(');
  const end=source.indexOf('  function beginGuideStep(',start);
  assert.ok(start>0 && end>start);
  const {createRequire}=await import('node:module');
  const require=createRequire(new URL('../package.json',import.meta.url));
  const compiled=require('esbuild').transformSync(source.slice(start,end),{loader:'ts'}).code;
  let draft={key:'recovery:source:original',prompt:'我的编辑'},page='session';
  runInNewContext(compiled+'\nnavigate("new");',{
    requestNavigation:fn=>fn(),setGuideStep(){},setSettingsOpen(){},setNavOpen(){},
    setPage:value=>page=value,setSelectedId(){},setDetail(){},currentSelection:{current:'source'},
    setRecoveryDraft:value=>draft=value,history:{replaceState(){}},location:{pathname:'/',search:''},
  });
  assert.equal(page,'new');
  assert.equal(draft.key,'recovery:source:original');
  assert.equal(draft.prompt,'我的编辑');
});
