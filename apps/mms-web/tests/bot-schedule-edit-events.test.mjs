import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import React from "react";
import esbuild from "esbuild";
import * as schedules from "../src/bot-schedules.ts";

function harness(schedule) {
  const states = []; let cursor = 0; const calls = [];
  const hooks = { ...React,
    useState(initial) { const i = cursor++; if (!(i in states)) states[i] = typeof initial === "function" ? initial() : initial;
      return [states[i], value => { states[i] = typeof value === "function" ? value(states[i]) : value; }]; },
    useRef(initial) { const [ref] = hooks.useState(() => ({current: initial})); return ref; },
    useMemo(fn) { return fn(); }, useEffect() {},
  };
  const mod = {exports: {}};
  const source = esbuild.transformSync(readFileSync(new URL("../src/BotSchedulePanel.tsx", import.meta.url), "utf8"), {loader: "tsx", format: "cjs"}).code;
  vm.runInNewContext(source, {module: mod, exports: mod.exports, React: hooks, console,
    require(name) {
      if (name === "react") return hooks;
      if (name === "./bot-schedules") return schedules;
      if (name === "./api") return {mutate: async (path, body) => { calls.push({path,body: JSON.parse(JSON.stringify(body))}); }};
      if (name === "./bot-visual-system.ts") return {formatScheduledTaskTime: value => value};
      return new Proxy({}, {get: () => () => null});
    },
  });
  function render() { cursor = 0; return mod.exports.BotSchedulePanel({bot: {id: "b", name: "Test"}, schedules: [schedule], onClose() {}}); }
  function all(node, pred) { return !node || typeof node !== "object" ? [] : [ ...(pred(node) ? [node] : []), ...React.Children.toArray(node.props?.children).flatMap(child => all(child,pred)) ]; }
  const find = (tree,pred) => { const nodes = all(tree,pred); assert.equal(nodes.length,1); return nodes[0]; };
  return {render,find,calls};
}

for (const rule of [{kind: "daily", atLocalTime: "09:00"}, {kind: "interval", everySeconds: 3600}]) {
  test(`actual edit/save handlers preserve ${rule.kind} timing on prompt edits and emit intentional rule changes`, async () => {
    const h = harness({id: "s", botId: "b", prompt: "old", rule, timezone: "America/New_York", enabled: true, overlapPolicy: "skip", nextRunAt: "2099-01-01T00:00:00Z"});
    let tree = h.render();
    h.find(tree, n => n.type === "button" && n.props.children === "编辑").props.onClick();
    tree = h.render();
    h.find(tree, n => n.type === "textarea").props.onChange({target: {value: "new prompt"}});
    tree = h.render();
    h.find(tree, n => n.type === "button" && n.props.children === "保存").props.onClick();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(h.calls, [{path: "/bots/b/schedules/s", body: {prompt: "new prompt", overlapPolicy: "skip"}}]);
    tree = h.render();
    h.find(tree, n => n.type === "button" && n.props.children === "编辑").props.onClick();
    tree = h.render();
    const label = rule.kind === "daily" ? "每天时间" : "间隔小时";
    h.find(tree, n => n.type === "input" && n.props["aria-label"] === label).props.onChange({target: {value: rule.kind === "daily" ? "11:00" : "2"}});
    tree = h.render();
    h.find(tree, n => n.type === "button" && n.props.children === "保存").props.onClick();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(h.calls[1].body.rule, rule.kind === "daily" ? {kind:"daily",atLocalTime:"11:00"} : {kind:"interval",everySeconds:7200});
    assert.equal("timezone" in h.calls[1].body, false);
  });
}
