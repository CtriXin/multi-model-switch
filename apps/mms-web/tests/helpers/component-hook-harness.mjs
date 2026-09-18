// Bounded hook replay of whole production modules; no browser/DOM layout claim.
// Entire components are compiled; callbacks are reached only through returned
// elements / registered useEffect. This is a hook replay, not browser evidence.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const web = fileURLToPath(new URL('../../', import.meta.url));
const require = createRequire(path.join(web, 'package.json'));
const esbuild = require('esbuild');
export const elements = tree => {
  if (Array.isArray(tree)) return tree.flatMap(elements);
  if (!tree || typeof tree !== 'object') return [];
  return [tree, ...elements(tree.props?.children)];
};
export const text = tree => Array.isArray(tree) ? tree.map(text).join('') :
  tree && typeof tree === 'object' ? text(tree.props?.children) :
  tree == null || typeof tree === 'boolean' ? '' : String(tree);
const sameDeps = (a,b) => a && b && a.length === b.length && a.every((x,i) => Object.is(x,b[i]));

export function mountModule(filename, request, overrides = {}) {
  let cursor = 0, dirty = false, tree, Component, props;
  const slots = [], effects = [], calls = [];
  const react = {
    Fragment: 'fragment',
    useState(initial) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = { value: typeof initial === 'function' ? initial() : initial };
      const set = value => {
        const next = typeof value === 'function' ? value(slots[i].value) : value;
        if (!Object.is(next, slots[i].value)) { slots[i].value = next; dirty = true; }
      };
      return [slots[i].value, set];
    },
    useRef(initial) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = { current: initial };
      return slots[i];
    },
    useMemo(fn, deps) {
      const i = cursor++;
      if (!(i in slots) || !sameDeps(slots[i].deps,deps)) slots[i] = { value: fn(), deps };
      return slots[i].value;
    },
    useEffect(fn, deps) {
      const i = cursor++;
      if (!(i in slots) || !sameDeps(slots[i].deps,deps)) {
        const previous = slots[i];
        slots[i] = { deps };
        effects.push(() => { previous?.cleanup?.(); slots[i].cleanup = fn(); });
      }
    },
  };
  const jsx = (type, props, key) => ({ type, props: props || {}, key });
  const dom = new Map();
  function attachRefs() {
    for (const node of elements(tree)) {
      const ref = node.props.ref;
      if (!ref || typeof ref !== 'object') continue;
      if (!dom.has(ref)) dom.set(ref, {
        scrollHeight: 0, scrollTop: 0,
        focus() { calls.push(['focus', node.type, node.props.className]); },
        select() {}, scrollIntoView() {},
        showModal() { calls.push(['showModal']); }, close() {},
        querySelector(selector) {
          if (selector === '.update-body') {
            assert.ok(elements(tree).some(n => n.props.className === 'update-body'));
            return { scrollTo(arg) { calls.push(['scrollTo', arg]); } };
          }
          if (selector === '.update-confirm h3') {
            const section = elements(tree).find(n => n.props.className === 'update-confirm');
            const heading = elements(section).find(n => n.type === 'h3');
            return heading ? { focus() { calls.push(['confirmFocus', heading.props.tabIndex]); } } : null;
          }
          throw new Error(`Unexpected DOM query ${selector}`);
        },
      });
      ref.current = dom.get(ref);
    }
  }
  const cache = new Map();
  const jsxRuntime = { jsx, jsxs: jsx, Fragment: 'fragment' };
  const pure = new Set(['bot-presets','bot-schedules','bot-model-switch','bot-fleet','bot-visual-system','bot-artifact-preview']);
  const stubs = {
    './api': { isPreview: false, request, mutate() { throw new Error('Unexpected mutate'); } },
    './clipboard': { copyText() { throw new Error('Unexpected clipboard'); } },
    './components': { RichText: 'RichText' },
    './BotCommunications': { formatDate: String, formatCompactTime: String, kindLabel: String },
    './BotArtifactPreview': { BotArtifactPreview: 'BotArtifactPreview' },
    './BotPlan': { BotPlan: 'BotPlan' },
    './BotModelPicker': { BotModelPicker: 'BotModelPicker' },
    './BotPresetPanel': { BotPresetPanel: 'BotPresetPanel' },
    './BotSchedulePanel': { BotSchedulePanel: 'BotSchedulePanel' },
    ...overrides,
  };
  const globals = {
    console, URL, setTimeout: () => 1, clearTimeout() {},
    window: { addEventListener() {}, removeEventListener() {} },
    document: { activeElement: null },
    location: { reload() { throw new Error('Unexpected reload'); } },
  };
  function load(name) {
    if (name.endsWith('.css')) return {};
    if (name === 'react') return react;
    if (name === 'react/jsx-runtime') return jsxRuntime;
    if (name === 'lucide-react') return new Proxy({}, { get: (_,key) => String(key) });
    if (name === 'react-markdown') return { default: 'Markdown', __esModule: true };
    if (name === 'remark-gfm') return { default: 'remarkGfm', __esModule: true };
    if (name in stubs) return stubs[name];
    if (name === './BotFleetBar') return { ...load('./bot-fleet'), BotFleetBar: 'BotFleetBar' };
    const base = path.basename(name).replace(/\.tsx?$/, '');
    if (!pure.has(base) && name !== filename) throw new Error(`Unapproved import ${name}`);
    if (cache.has(base)) return cache.get(base);
    const target = path.join(web, 'src', base + (fs.existsSync(path.join(web, 'src', base + '.tsx')) ? '.tsx' : '.ts'));
    const source = fs.readFileSync(target, 'utf8');
    const code = esbuild.transformSync(source, { loader: 'tsx', format: 'cjs', jsx: 'automatic' }).code;
    const module = { exports: {} };
    vm.runInNewContext(code, { ...globals, module, exports: module.exports, require: load }, { filename: target });
    cache.set(base, module.exports);
    return module.exports;
  }
  const exports = load(filename);
  function render() {
    cursor = 0; dirty = false;
    tree = Component(props);
    attachRefs();
    for (const effect of effects.splice(0)) effect();
  }
  async function settle() {
    for (let i = 0; i < 8; i++) {
      await Promise.resolve();
      if (dirty) render();
    }
    assert.equal(dirty, false, 'bounded hook replay must settle');
  }
  return {
    calls, get tree() { return tree; },
    async mount(exportName, input) { Component = exports[exportName]; props = input; render(); await settle(); },
    settle,
    one(predicate) {
      const matches = elements(tree).filter(predicate);
      assert.equal(matches.length, 1, 'expected exactly one rendered control');
      return matches[0];
    },
  };
}

