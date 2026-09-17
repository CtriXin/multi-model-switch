import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import esbuild from "esbuild";
import React from "react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(
  path.resolve(__dirname, "../src/SessionAttention.ts"),
  "utf-8",
);
const transpiled = esbuild.transformSync(source, {
  loader: "ts",
  format: "cjs",
}).code;
const mod = { exports: {} };
const sandbox = {
  module: mod,
  exports: mod.exports,
  require: (req) => {
    if (req === "react") return React;
    if (req === "./api") return { getSession: async () => ({}), isPreview: false };
    return {};
  },
  console,
};
vm.createContext(sandbox);
vm.runInContext(transpiled, sandbox);
const {
  conversationAtBottom,
  shouldMarkResultRead,
  writeReadReceipt,
  shouldAdoptBaselineReceipt,
} = mod.exports;

test("viewingBottom is what marks a result read", () => {
  assert.equal(
    shouldMarkResultRead({
      hasOutputToken: true,
      viewingBottom: false,
      visible: true,
      connected: true,
    }),
    false,
    "in the session window but not at the bottom must stay unread",
  );
  assert.equal(
    shouldMarkResultRead({
      hasOutputToken: true,
      viewingBottom: true,
      visible: true,
      connected: true,
    }),
    true,
    "latest output on screen marks the result read",
  );
  assert.equal(
    shouldMarkResultRead({
      hasOutputToken: true,
      viewingBottom: true,
      visible: false,
      connected: true,
    }),
    false,
    "a hidden tab does not count as having read the result",
  );
  assert.equal(
    shouldMarkResultRead({
      hasOutputToken: false,
      viewingBottom: true,
      visible: true,
      connected: true,
    }),
    false,
    "no settled output token cannot be marked read",
  );
});

test("conversationAtBottom uses the live scrollbar, not selected-row state", () => {
  assert.equal(
    conversationAtBottom({ scrollHeight: 4000, scrollTop: 0, clientHeight: 800 }),
    false,
    "scrolled to the top of a long transcript is not the bottom",
  );
  assert.equal(
    conversationAtBottom({
      scrollHeight: 4000,
      scrollTop: 3101,
      clientHeight: 800,
    }),
    true,
    "within 100px of the end counts as the bottom",
  );
  assert.equal(
    conversationAtBottom({
      scrollHeight: 4000,
      scrollTop: 2000,
      clientHeight: 800,
    }),
    false,
    "mid-transcript is unread even if the session is open",
  );
  assert.equal(
    conversationAtBottom({ scrollHeight: 500, scrollTop: 0, clientHeight: 800 }),
    true,
    "content that fits the viewport is fully visible",
  );
});

test("writeReadReceipt stores the token that later clears unread", () => {
  const receipts = {};
  writeReadReceipt(receipts, "s1", "tok-1");
  assert.equal(receipts.s1, "tok-1");
  const src = fs.readFileSync(
    path.resolve(__dirname, "../src/SessionAttention.ts"),
    "utf-8",
  );
  assert.match(src, /receipts\[id\] = token/);
  assert.match(src, /writeReadReceipt\(receipts\.current,\s*id,\s*token\)/);
});

test("first-load baseline swallows already-idle sessions except in preview", () => {
  assert.equal(
    shouldAdoptBaselineReceipt({
      preview: false,
      inBaseline: true,
      hasStoredReceipt: false,
      wasBusy: false,
    }),
    true,
  );
  assert.equal(
    shouldAdoptBaselineReceipt({
      preview: true,
      inBaseline: true,
      hasStoredReceipt: false,
      wasBusy: false,
    }),
    false,
    "preview must keep unread so ?preview=1 can show 已完成",
  );
  assert.equal(
    shouldAdoptBaselineReceipt({
      preview: false,
      inBaseline: true,
      hasStoredReceipt: true,
      wasBusy: false,
    }),
    false,
  );
  assert.equal(
    shouldAdoptBaselineReceipt({
      preview: false,
      inBaseline: true,
      hasStoredReceipt: false,
      wasBusy: true,
    }),
    false,
  );
});

function attentionHarness() {
  const slots = [], effects = [], frames = new Map(), stored = new Map();
  let cursor = 0, nextFrame = 0;
  const document = {visibilityState: "visible", title: "", addEventListener() {}, removeEventListener() {}};
  let latest;
  const hooks = {
    useState(initial) { const i = cursor++; if (!(i in slots)) slots[i] = typeof initial === "function" ? initial() : initial;
      return [slots[i], value => { slots[i] = typeof value === "function" ? value(slots[i]) : value; }]; },
    useRef(initial) { const [ref] = hooks.useState(() => ({current: initial})); return ref; },
    useEffect(fn, deps) { const i = cursor++, old = slots[i];
      if (!old || deps.some((value,index) => !Object.is(value,old.deps[index]))) {
        old?.cleanup?.(); const record = {deps}; slots[i] = record;
        effects.push(() => { record.cleanup = fn(); });
      }
    },
  };
  const module = {exports: {}};
  vm.runInNewContext(transpiled, {module,exports:module.exports,console,AbortController,
    require: name => name === "react" ? hooks : {isPreview:false,getSession:async()=>latest},
    document,window:{addEventListener() {},removeEventListener() {}},
    localStorage:{getItem:key=>stored.get(key),setItem:(key,value)=>stored.set(key,value)},
    requestAnimationFrame: fn => { const id=++nextFrame;frames.set(id,fn);return id; },
    cancelAnimationFrame:id=>frames.delete(id),setTimeout:()=>1,clearTimeout() {},
  });
  function render(sessions, detail, bottom) {
    cursor=0; const result=module.exports.useSessionAttention(sessions,detail,bottom,true);
    effects.splice(0).forEach(fn=>fn()); frames.forEach(fn=>fn());frames.clear();return result;
  }
  return {render,stored,document,setLatest(value){latest=value;}};
}

test("actual attention hook persists bottom-view receipt and clears unread/title", async () => {
  const h=attentionHarness();
  const running={id:"s1",state:"running",updatedAt:"1"};
  const idle={...running,state:"idle",updatedAt:"2"};
  const detail={session:idle,events:[{id:"a1",kind:"assistant",text:"new result"}]};
  h.setLatest(detail);
  h.render([running],null,false);
  h.render([idle],null,false);
  await new Promise(resolve=>setImmediate(resolve));
  let state=h.render([idle],detail,false);
  assert.ok(state.unread.s1);
  assert.equal(h.document.title,"(1) Pilot");
  assert.equal(JSON.parse(h.stored.get("mms-web-read-results-v1")).s1,"");
  h.render([idle],detail,true);
  state=h.render([idle],detail,true);
  const receipt=JSON.parse(h.stored.get("mms-web-read-results-v1")).s1;
  assert.ok(receipt.startsWith("a1:"),"the real hook must write the result token, not only clear its local badge");
  assert.equal(state.unread.s1,undefined);
  assert.equal(h.document.title,"MMS Pilot");
});
