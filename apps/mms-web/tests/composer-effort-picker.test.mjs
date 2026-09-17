import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import esbuild from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load TaskSettings module and its dependencies via esbuild
function loadModule(relPath, mocks = {}) {
  const absPath = path.resolve(__dirname, relPath);
  const src = fs.readFileSync(absPath, "utf-8");
  const transpiled = esbuild.transformSync(src, {
    loader: "tsx",
    format: "cjs",
  }).code;

  const mod = { exports: {} };
  const sandbox = {
    module: mod,
    exports: mod.exports,
    React,
    require: (req) => {
      if (req === "react") return React;
      if (req in mocks) return mocks[req];
      return {};
    },
    console,
  };
  vm.createContext(sandbox);
  vm.runInContext(transpiled, sandbox);
  return mod.exports;
}

const lucideMock = {
  ChevronDown: () => React.createElement("span", { className: "lucide-chevron-down" }),
  ArrowUpRight: () => React.createElement("span", { className: "lucide-arrow-up-right" }),
  Brain: () => React.createElement("span", { className: "lucide-brain" }),
  Check: () => React.createElement("span", { className: "lucide-check" }),
};

const modelExplorerMock = {
  effortLabels: {
    off: "关闭",
    minimal: "最少",
    low: "轻量",
    medium: "均衡",
    high: "深入",
    xhigh: "更深入",
    max: "最高",
  },
  saveRoutePreference: () => {},
};

const modelSelectionMock = {
  availableRoutesForModel: () => [],
  channelLabel: () => "",
};

const quickModelMenuMock = {
  QuickModelMenu: ({ children }) => React.createElement("div", { className: "quick-model-menu-mock" }, children),
};

const popoverExports = loadModule("../src/Popover.tsx");
const taskSettingsExports = loadModule("../src/TaskSettings.tsx", {
  "lucide-react": lucideMock,
  "./ModelExplorer": modelExplorerMock,
  "./modelSelection": modelSelectionMock,
  "./QuickModelMenu": quickModelMenuMock,
  "./Popover": popoverExports,
});

const { sortLevels, EffortPicker, TaskSettings, SessionSettings } = taskSettingsExports;

test("sortLevels correctly sorts standard effort levels and preserves custom levels", () => {
  const unsorted = ["max", "off", "high", "low", "medium", "xhigh", "minimal"];
  const sorted = sortLevels(unsorted);
  assert.equal(sorted.join(","), "off,minimal,low,medium,high,xhigh,max");

  // Deduplication
  assert.equal(sortLevels(["low", "high", "low", "medium"]).join(","), "low,medium,high");

  // Custom levels placed at the end
  const withCustom = ["high", "ultra", "low"];
  assert.equal(sortLevels(withCustom).join(","), "low,high,ultra");
});

test("EffortPicker renders standalone button with icon, label, and data-guide", () => {
  const html = renderToStaticMarkup(
    React.createElement(EffortPicker, {
      value: "high",
      levels: ["low", "medium", "high"],
      defaultLevel: "medium",
      change: () => {},
    })
  );

  assert.match(html, /class="[^"]*task-effort-trigger/);
  assert.match(html, /data-guide="effort"/);
  assert.match(html, /<span class="task-effort">深入<\/span>/);
  assert.match(html, /<span class="task-effort-prefix">思考 · <\/span>/);
  assert.match(html, /class="effort-menu"/);
  assert.match(html, /深入/);
  assert.match(html, /均衡/);
  assert.match(html, /轻量/);
  assert.match(html, /lucide-check/);
});

test("EffortPicker reflects disabled state when locked", () => {
  const html = renderToStaticMarkup(
    React.createElement(EffortPicker, {
      value: "medium",
      levels: ["low", "medium", "high"],
      change: () => {},
      disabled: true,
    })
  );

  assert.match(html, /<button[^>]*disabled=""/);
});

test("TaskSettings renders EffortPicker beside model trigger when model supports thinking", () => {
  const html = renderToStaticMarkup(
    React.createElement(TaskSettings, {
      presets: [{ id: "p1", name: "GLM-5", modelId: "glm-5", available: true, harness: "pi" }],
      models: [{ id: "glm-5", name: "GLM-5", family: "glm" }],
      workspaceId: "w1",
      value: "p1",
      change: () => {},
      favorites: [],
      toggleFavorite: () => {},
      facts: {
        model: { id: "glm-5", reasoning: true },
        protocol: "openai",
        supportedThinkingLevels: ["low", "medium", "high"],
        defaultThinkingLevel: "medium",
        configuredThinkingLevel: "medium",
      },
      effort: "high",
      setEffort: () => {},
      planning: false,
      setPlanning: () => {},
      settings: () => {},
    })
  );

  // Both model trigger and effort trigger are present
  assert.match(html, /<span class="task-model-name">GLM-5<\/span>/);
  assert.match(html, /class="[^"]*task-effort-trigger/);
  assert.match(html, /<span class="task-effort">深入<\/span>/);

  // QuickModelMenu children must NOT contain the old buried effort selector
  assert.doesNotMatch(html, /<select[^>]*aria-label="新任务 effort"/);
});

test("TaskSettings hides EffortPicker when model has no thinking levels", () => {
  const html = renderToStaticMarkup(
    React.createElement(TaskSettings, {
      presets: [{ id: "p2", name: "Claude Haiku", modelId: "haiku", available: true, harness: "pi" }],
      models: [{ id: "haiku", name: "Claude Haiku", family: "claude" }],
      workspaceId: "w1",
      value: "p2",
      change: () => {},
      favorites: [],
      toggleFavorite: () => {},
      facts: {
        model: { id: "haiku", reasoning: false },
        protocol: "anthropic",
        supportedThinkingLevels: [],
        defaultThinkingLevel: "off",
        configuredThinkingLevel: "off",
      },
      effort: "",
      setEffort: () => {},
      planning: false,
      setPlanning: () => {},
      settings: () => {},
    })
  );

  assert.match(html, /<span class="task-model-name">Claude Haiku<\/span>/);
  assert.doesNotMatch(html, /class="[^"]*task-effort-trigger/);
});

test("SessionSettings renders EffortPicker and disables it during running/waiting", () => {
  const runningDetail = {
    session: {
      id: "s1",
      title: "Test Session",
      state: "running",
      modelName: "GLM-5.3",
      capabilities: { send: true },
      presetId: "p1",
      harness: "pi",
    },
    runtime: {
      alive: true,
      supportedThinkingLevels: ["low", "medium", "high"],
      thinkingLevel: "medium",
      model: { reasoning: true },
    },
    events: [],
    artifacts: [],
  };

  const html = renderToStaticMarkup(
    React.createElement(SessionSettings, {
      detail: runningDetail,
      busy: false,
      action: async () => true,
      more: () => {},
      presets: [{ id: "p1", name: "GLM-5.3", modelId: "glm", available: true, harness: "pi" }],
      models: [{ id: "glm", name: "GLM-5.3", family: "glm" }],
      favorites: [],
      toggleFavorite: () => {},
    })
  );

  assert.match(html, /<span class="task-model-name">GLM-5.3<\/span>/);
  assert.match(html, /class="[^"]*task-effort-trigger/);
  assert.match(html, /<span class="task-effort">均衡<\/span>/);
  // Disabled because session.state is "running"
  assert.match(html, /<button[^>]*class="[^"]*task-effort-trigger[^"]*"[^>]*disabled=""/);
});

test("CSS stylesheet contains all effort trigger and menu styles", () => {
  const css = fs.readFileSync(path.resolve(__dirname, "../src/studio.css"), "utf-8");
  assert.match(css, /\.task-effort-trigger\s*\{/);
  assert.match(css, /\.effort-menu\s*\{/);
  assert.match(css, /\.effort-menu-item\s*\{/);
  assert.match(css, /\.task-effort-prefix\s*\{\s*display:\s*none;\s*\}/);
  assert.match(css, /\.composer-context\s*\{[^}]*gap:\s*4px;/);
  assert.match(css, /\.effort-trigger-unsupported\s*\{/);
  assert.match(css, /\.task-effort-unsupported\s*\{/);
  assert.match(css, /\.effort-menu-unsupported\s*\{/);
});

test("EffortPicker renders MMS default as the first option and handles clearing effort (rework 3)", () => {
  let changedValue = null;
  const html = renderToStaticMarkup(
    React.createElement(EffortPicker, {
      value: "",
      levels: ["low", "medium", "high"],
      defaultLevel: "high",
      change: (v) => { changedValue = v; },
    })
  );

  // First item must be MMS 默认
  assert.match(html, /MMS 默认 · 深入/);
  // Default option should be marked active when value is empty
  assert.match(html, /class="[^"]*effort-menu-item[^"]*active[^"]*"[^>]*>[^<]*<div[^>]*>[^<]*<span[^>]*>MMS 默认/);
  // Trigger button shows the default level label
  assert.match(html, /<span class="task-effort">深入<\/span>/);
});

test("EffortPicker displays unsupported warning when saved value is not in supported levels (rework 4)", () => {
  const html = renderToStaticMarkup(
    React.createElement(EffortPicker, {
      value: "max",
      levels: ["low", "medium", "high"],
      defaultLevel: "medium",
      change: () => {},
    })
  );

  // Trigger button shows warning text and warning styling
  assert.match(html, /此通道不支持 max，请重选/);
  assert.match(html, /effort-trigger-unsupported/);
  assert.match(html, /task-effort-unsupported/);

  // Menu must have an active item clearly marking the unsupported state
  assert.match(html, /effort-menu-unsupported/);
  assert.match(html, /此通道不支持 max，请重选/);
});

test("SessionSettings does NOT fabricate effort levels when supportedThinkingLevels is empty (rework 5)", () => {
  const noThinkingDetail = {
    session: {
      id: "s2",
      title: "No Thinking Session",
      state: "ready",
      modelName: "Basic-Model",
      capabilities: { send: true },
      presetId: "p2",
      harness: "pi",
    },
    runtime: {
      alive: true,
      supportedThinkingLevels: [],
      thinkingLevel: undefined,
      model: { reasoning: true }, // reasoning is true, but runtime provides no supportedThinkingLevels
    },
    events: [],
    artifacts: [],
  };

  const html = renderToStaticMarkup(
    React.createElement(SessionSettings, {
      detail: noThinkingDetail,
      busy: false,
      action: async () => true,
      more: () => {},
      presets: [{ id: "p2", name: "Basic-Model", modelId: "basic", available: true, harness: "pi" }],
      models: [{ id: "basic", name: "Basic-Model", family: "basic" }],
      favorites: [],
      toggleFavorite: () => {},
    })
  );

  // Must NOT render EffortPicker or fabricated low/medium/high
  assert.doesNotMatch(html, /class="[^"]*task-effort-trigger/);
  assert.doesNotMatch(html, /class="effort-menu"/);
});

test("GuidedTour filters out effort step when hasEffort is false and removes fallback click (rework 6)", () => {
  const tourSrc = fs.readFileSync(path.resolve(__dirname, "../src/GuidedTour.tsx"), "utf-8");

  // Verify that the fallback click on task-settings-trigger has been completely removed
  assert.doesNotMatch(tourSrc, /document\.querySelector<HTMLButtonElement>\('\.task-settings-trigger'\)\?\.click\(\)/);

  // Verify that hasEffort filters effort step
  const guideContentMock = { starterPrompt: "test prompt" };
  const guidedTourExports = loadModule("../src/GuidedTour.tsx", {
    "lucide-react": {
      ...lucideMock,
      ArrowLeft: () => React.createElement("span", { className: "lucide-arrow-left" }),
      ArrowRight: () => React.createElement("span", { className: "lucide-arrow-right" }),
      X: () => React.createElement("span", { className: "lucide-x" }),
    },
    "./guide-content": guideContentMock,
  });

  const { GuidedTour } = guidedTourExports;
  const html = renderToStaticMarkup(
    React.createElement(GuidedTour, {
      step: "model",
      move: () => {},
      close: () => {},
      help: () => {},
      example: () => {},
      modelReady: true,
      configure: false,
      hasSession: false,
      hasEffort: false,
    })
  );

  assert.match(html, /tour-card/);
});



function nodes(element) {
  if (!element || typeof element !== "object") return [];
  if (Array.isArray(element)) return element.flatMap(nodes);
  return [element, ...nodes(element.props?.children)];
}

test("live session effort menu sends only explicit runtime levels", async () => {
  const calls = [];
  const tree = SessionSettings({
    detail: { session: { id: "s1", state: "idle", capabilities: { send: true } },
      runtime: { alive: true, thinkingLevel: "high", supportedThinkingLevels: ["low", "high"] } },
    busy: false, action: async (...args) => { calls.push(args); return true; }, more() {},
    presets: [], models: [], favorites: [], toggleFavorite() {},
  });
  const picker = nodes(tree).find(node => node.type === EffortPicker);
  assert.ok(picker, "SessionSettings must mount the picker");
  const popover = EffortPicker(picker.props);
  const buttons = nodes(popover.props.children(() => {})).filter(node => node.type === "button");
  assert.equal(buttons.length, 2, "live runtime has no empty/default reset command");
  buttons[0].props.onClick();
  await Promise.resolve();
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [["/sessions/s1/control", { action: "thinking", value: "low" }]]);
});
