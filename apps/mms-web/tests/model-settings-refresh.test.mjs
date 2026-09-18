// Exercise production App -> SettingsPage -> Models -> ChannelModels callbacks
// and the real useLaunchFacts effect. Only browser plumbing/API are doubles.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const appDir = fileURLToPath(new URL("../", import.meta.url));
const require = createRequire(path.join(appDir, "package.json"));
const React = require("react");
const esbuild = require("esbuild");
const nodes = value => !value || typeof value !== "object" ? []
  : Array.isArray(value) ? value.flatMap(nodes)
    : [value, ...nodes(value.props?.children)];
const text = value => Array.isArray(value) ? value.map(text).join("")
  : value && typeof value === "object" ? text(value.props?.children)
    : value == null || typeof value === "boolean" ? "" : String(value);

function fixture({ failSave = false, preference = "" } = {}) {
  const preset = { id: "web:pi:channel-a:glm-5.3", name: "glm-5.3", modelId: "channel-a:glm-5.3", providerId: "channel-a", available: true };
  const boot = { version: "1", mode: "live", csrfToken: "fixture", capabilities: { launch: true, configure: true, modelSettings: true },
    workspaces: [{ id: "workspace", name: "project", path: "/fixture" }], presets: [preset], models: [], services: [], sessions: [], diagnostics: [] };
  const storage = new Map([["mms-web-preset", JSON.stringify(preset.id)], ["mms-web-workspace", '"workspace"'],
    ["mms-web-route-preferences", JSON.stringify({ [preset.id]: { effort: preference } })]]);
  let savedEffort = "max", draft, current;
  const calls = [], modules = new Map(), runners = [];
  const api = {
    isPreview: false, includeCliSessions() {}, bootstrap: async () => structuredClone(boot), listSessions: async () => [],
    async mutate(route, body) { calls.push({ route, body }); return { session: { id: "created", state: "stopped" }, events: [], artifacts: [] }; },
    async request(route, body) {
      calls.push({ route, body });
      if (route === "/launch-options") return { model: { id: "glm-5.3", contextWindow: 1000000 },
        defaultThinkingLevel: savedEffort === "max" ? "xhigh" : savedEffort, supportedThinkingLevels: ["high", "xhigh"], protocol: "openai" };
      if (route === "/model-settings") return { fingerprint: savedEffort, revision: savedEffort, configScope: "standalone", providers: [{
        id: "channel-a", name: "channel-a", models: [{ id: "glm-5.3", visible: true, effort: savedEffort, effortLevels: ["high", "max"], vision: false }],
      }] };
      if (route === "/model-settings/preview") { draft = body; return { previewId: "preview", changes: [{ kind: "effort", model: "glm-5.3", before: savedEffort, after: "high" }] }; }
      if (route === "/model-settings/apply") {
        if (failSave) throw new Error("fixture save rejected");
        assert.equal(body.confirmed, true);
        savedEffort = draft.efforts["glm-5.3"];
        return { applied: true, runtimeReady: true };
      }
      return {};
    },
  };
  const hooks = {
    useState(initial) {
      const runner = current, i = runner.cursor++;
      if (!runner.slots[i]) {
        const slot = { value: typeof initial === "function" ? initial() : initial };
        slot.set = next => { slot.value = typeof next === "function" ? next(slot.value) : next; };
        runner.slots[i] = slot;
      }
      const slot = runner.slots[i]; return [slot.value, slot.set];
    },
    useRef(initial) { const [ref] = hooks.useState(() => ({ current: initial })); return ref; },
    useMemo(fn, deps) {
      const runner = current, i = runner.cursor++, old = runner.slots[i];
      if (!old || deps.some((d, j) => !Object.is(d, old.deps[j]))) runner.slots[i] = { value: fn(), deps };
      return runner.slots[i].value;
    },
    useCallback(fn, deps) { return hooks.useMemo(() => fn, deps); },
    useEffect(fn, deps) {
      const runner = current, i = runner.cursor++, old = runner.slots[i];
      if (!old || !deps || deps.some((d, j) => !Object.is(d, old.deps?.[j]))) {
        runner.effects.push(() => { old?.cleanup?.(); runner.slots[i].cleanup = fn(); });
        runner.slots[i] = { deps };
      }
    },
  };
  const noop = () => {};
  const browser = {
    React, console, AbortController, URLSearchParams,
    location: { hash: "", pathname: "/", search: "" }, history: { replaceState: noop },
    localStorage: { getItem: k => storage.get(k) || null, setItem: (k, v) => storage.set(k, v) },
    matchMedia: () => ({ matches: false, addEventListener: noop, removeEventListener: noop }),
    getComputedStyle: () => ({ getPropertyValue: () => "" }),
    document: { hidden: false, createElement: () => ({ getContext: () => null }),
      documentElement: { dataset: {}, style: { setProperty: noop } }, addEventListener: noop, removeEventListener: noop,
      querySelectorAll: () => [], querySelector: () => null },
    window: { addEventListener: noop, removeEventListener: noop },
    setTimeout: () => 1, clearTimeout: noop, setInterval: () => 1, clearInterval: noop,
  };
  const actual = new Set(["App", "ModelExplorer", "SettingsPage", "Models", "ChannelModels", "TaskSettings", "connection-state", "modelSelection"]);
  function load(name) {
    if (modules.has(name)) return modules.get(name).exports;
    const mod = { exports: {} }; modules.set(name, mod);
    const filename = path.join(appDir, "src", name + (["connection-state", "modelSelection"].includes(name) ? ".ts" : ".tsx"));
    const code = esbuild.transformSync(fs.readFileSync(filename, "utf8"), { loader: "tsx", format: "cjs" }).code;
    vm.runInNewContext(code, { ...browser, module: mod, exports: mod.exports, require: spec => {
      if (spec === "react") return hooks;
      if (spec === "react-dom") return { flushSync: fn => fn() };
      if (spec === "./api") return api;
      if (spec.endsWith(".css")) return {};
      const local = spec.replace(/^\.\//, "");
      if (actual.has(local)) return load(local);
      if (spec === "./Recipe") return { readRecipeDraft: () => null, saveRecipeDraft: noop, RecipeImport: "RecipeImport" };
      if (spec === "./SideQuestions") return { useSideQuestions: () => ({}), SideQuestions: "SideQuestions" };
      if (spec === "./SessionAttention") return { useSessionAttention: () => ({ unread: {}, flashes: {} }) };
      return new Proxy({}, { get: (_, key) => key === "__esModule" ? true : String(key) });
    } }, { filename });
    return mod.exports;
  }
  function mount(component, props = {}) {
    const runner = { component, props, slots: [], cursor: 0, effects: [], tree: null };
    runner.render = () => { current = runner; runner.cursor = 0; runner.tree = runner.component(runner.props); return runner.tree; };
    runners.push(runner); runner.render(); return runner;
  }
  async function flush() {
    for (let i = 0; i < 8; i++) {
      for (const runner of runners) { runner.render(); for (const effect of runner.effects.splice(0)) effect(); }
      await Promise.resolve(); await Promise.resolve();
    }
  }
  const find = (runner, predicate) => { const found = nodes(runner.tree).find(predicate); assert.ok(found, "production rendered node missing"); return found; };
  const button = (runner, label) => find(runner, n => n.type === "button" && text(n) === label);
  const root = mount(load("App").App);
  const taskSettings = () => find(root, n => n.type === load("TaskSettings").TaskSettings);
  function effortView() {
    const settings = mount(taskSettings().type, taskSettings().props).tree;
    const picker = nodes(settings).find(n => n.type === load("TaskSettings").EffortPicker);
    assert.ok(picker, "production effort picker missing");
    const popover = mount(picker.type, picker.props).tree;
    const items = nodes(popover.props.children(noop, true)).filter(n => n.props?.role === "menuitemradio");
    const selected = items.find(n => n.props["aria-checked"]);
    assert.ok(selected, "production effort selection missing");
    const code = nodes(selected).find(n => n.props?.className === "effort-menu-item-code");
    return { defaultText: text(items[0]), value: text(code) === "默认" ? "" : text(code) };
  }
  async function editAndSave() {
    taskSettings().props.settings(); await flush();
    const settingsNode = find(root, n => n.type === load("SettingsPage").SettingsPage);
    const settings = mount(settingsNode.type, settingsNode.props);
    const modelsNode = find(settings, n => n.type === load("Models").Models);
    const models = mount(modelsNode.type, modelsNode.props);
    button(models, "管理通道模型").props.onClick(); await flush();
    const channelNode = find(models, n => n.type === load("ChannelModels").ChannelModels);
    const channel = mount(channelNode.type, channelNode.props); await flush();
    find(channel, n => n.props?.["aria-label"] === "glm-5.3 MMF 默认 effort").props.onChange({ target: { value: "high" } });
    await flush(); button(channel, "检查并保存").props.onClick(); await flush();
    button(channel, "保存设置").props.onClick(); await flush();
    if (!failSave) settingsNode.props.back();
    await flush(); return channel;
  }
  return { root, calls, flush, editAndSave, effortView, taskSettings, find,
    close() { for (const r of runners) for (const s of r.slots) s?.cleanup?.(); } };
}

test("saving shared GLM effort refreshes the actual new-task default without reload", async () => {
  const f = fixture();
  try {
    await f.flush();
    assert.match(f.effortView().defaultText, /MMS 默认 · 更深入/);
    await f.editAndSave();
    assert.match(f.effortView().defaultText, /MMS 默认 · 深入/);
    assert.equal(f.effortView().value, "");
    const composer = f.find(f.root, n => n.type === "Composer");
    await composer.props.send("fixture prompt", { mode: "followUp" });
    assert.equal(f.calls.find(c => c.route === "/sessions").body.thinkingLevel, undefined, "follow the newly saved server default");
  } finally { f.close(); }
});

test("shared save refreshes facts while preserving explicit task and browser effort", async () => {
  for (const kind of ["task", "browser"]) {
    const f = fixture({ preference: kind === "browser" ? "xhigh" : "" });
    try {
      await f.flush();
      if (kind === "task") { f.taskSettings().props.setEffort("xhigh"); await f.flush(); }
      await f.editAndSave();
      assert.match(f.effortView().defaultText, /MMS 默认 · 深入/);
      assert.equal(f.effortView().value, "xhigh");
      await f.find(f.root, n => n.type === "Composer").props.send("fixture prompt", { mode: "followUp" });
      assert.equal(f.calls.find(c => c.route === "/sessions").body.thinkingLevel, "xhigh");
    } finally { f.close(); }
  }
});

test("failed save leaves the previous default and surfaces the error", async () => {
  const f = fixture({ failSave: true });
  try {
    await f.flush(); const before = f.calls.filter(c => c.route === "/launch-options").length;
    const channel = await f.editAndSave();
    assert.match(text(channel.tree), /fixture save rejected/);
    assert.match(f.effortView().defaultText, /MMS 默认 · 更深入/);
    assert.equal(f.calls.filter(c => c.route === "/launch-options").length, before);
  } finally { f.close(); }
});
