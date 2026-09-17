import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { registerHooks } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";
import { dirname, join, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

if (typeof globalThis.location === "undefined") {
  globalThis.location = { search: "", href: "http://127.0.0.1/" };
}

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL && specifier.startsWith(".") && !/[.][a-z0-9]+$/i.test(specifier.split("/").pop() || "")) {
      const parent = dirname(fileURLToPath(context.parentURL));
      for (const ext of [".ts", ".tsx"]) {
        const candidate = join(parent, specifier + ext);
        if (existsSync(candidate)) {
          return { url: pathToFileURL(candidate).href, shortCircuit: true };
        }
      }
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith(".css")) {
      return { format: "module", shortCircuit: true, source: "export default '';" };
    }
    if ((url.endsWith(".tsx") || url.endsWith(".ts")) && url.includes("/apps/mms-web/src/")) {
      const file = fileURLToPath(url);
      const raw = readFileSync(file, "utf8");
      const result = ts.transpileModule(raw, {
        compilerOptions: {
          jsx: ts.JsxEmit.ReactJSX,
          module: ts.ModuleKind.ESNext,
          target: ts.ScriptTarget.ES2022,
        },
        fileName: file,
      });
      return { format: "module", shortCircuit: true, source: result.outputText };
    }
    return nextLoad(url, context);
  },
});

function botFixture(overrides = {}) {
  return {
    id: "bot_1",
    name: "定时验收",
    description: "",
    systemPrompt: "",
    presetId: null,
    workspaceId: null,
    status: "idle",
    wakeEnabled: true,
    ...overrides,
  };
}

function scheduleFixture(overrides) {
  return {
    id: "sch_1",
    botId: "bot_1",
    prompt: "查机票",
    rule: { kind: "daily", atLocalTime: "09:00" },
    timezone: "Asia/Singapore",
    enabled: true,
    overlapPolicy: "skip",
    nextRunAt: "2026-09-18T01:00:00.000Z",
    lastRunAt: null,
    lastTaskId: null,
    lastSkip: null,
    createdAt: "2026-09-16T00:00:00.000Z",
    updatedAt: "2026-09-16T00:00:00.000Z",
    ...overrides,
  };
}

async function loadPanel() {
  return import("../src/BotSchedulePanel.tsx");
}

test("scheduleEnablePath maps desired enabled=false to /disable", async () => {
  const { scheduleEnablePath } = await loadPanel();
  assert.match(scheduleEnablePath("bot_1", "sch_1", false), /\/disable$/);
  assert.match(scheduleEnablePath("bot_1", "sch_1", true), /\/enable$/);
});

test("BotSchedulePanel render shows each run-state label and one row per schedule", async () => {
  const { BotSchedulePanel } = await loadPanel();
  const schedules = [
    scheduleFixture({ id: "sch_up", prompt: "upcoming-row" }),
    scheduleFixture({
      id: "sch_held_p",
      prompt: "held-paused-row",
      rule: { kind: "once", at: "2026-09-16T01:00:00.000Z" },
      nextRunAt: "2026-09-16T01:00:00.000Z",
      lastSkip: { reason: "paused", skipped: 0 },
    }),
    scheduleFixture({
      id: "sch_held_b",
      prompt: "held-busy-row",
      rule: { kind: "once", at: "2026-09-16T01:00:00.000Z" },
      nextRunAt: "2026-09-16T01:00:00.000Z",
      lastSkip: { reason: "busy", skipped: 0 },
    }),
    scheduleFixture({
      id: "sch_done",
      prompt: "completed-row",
      rule: { kind: "once", at: "2026-09-15T01:00:00.000Z" },
      nextRunAt: null,
      lastRunAt: "2026-09-15T01:05:00.000Z",
    }),
    scheduleFixture({
      id: "sch_err",
      prompt: "error-row",
      rule: { kind: "once", at: "2026-09-16T01:00:00.000Z" },
      nextRunAt: "2026-09-16T01:00:00.000Z",
      lastSkip: { reason: "error", skipped: 0 },
    }),
    scheduleFixture({
      id: "sch_bad",
      prompt: "invalid-row",
      enabled: false,
      nextRunAt: null,
      lastSkip: { reason: "invalid", skipped: 0 },
    }),
  ];
  const html = renderToStaticMarkup(
    createElement(BotSchedulePanel, {
      bot: botFixture(),
      schedules,
      onClose() {},
    }),
  );
  assert.equal((html.match(/<li class="bot-schedule-row/g) || []).length, schedules.length);
  assert.match(html, /待触发/);
  assert.match(html, /已到点但被挂起/);
  assert.match(html, /已执行完/);
  assert.match(html, /上次没能建出任务/);
  assert.match(html, /记录损坏/);
  assert.match(html, /upcoming-row/);
  assert.match(html, /held-paused-row/);
  assert.match(html, /completed-row/);
});

test("paused repeating row renders 已暂停, not 待触发", async () => {
  const { BotSchedulePanel } = await loadPanel();
  const html = renderToStaticMarkup(
    createElement(BotSchedulePanel, {
      bot: botFixture(),
      schedules: [
        scheduleFixture({
          id: "sch_paused",
          enabled: false,
          nextRunAt: "2026-09-18T01:00:00.000Z",
          prompt: "paused-future-row",
        }),
      ],
      onClose() {},
    }),
  );
  assert.match(html, /已暂停/);
  assert.doesNotMatch(html, /待触发/);
  assert.match(html, /paused-future-row/);
});

test("gated rows do not keep the 待触发 chip", async () => {
  const { BotSchedulePanel } = await loadPanel();
  const html = renderToStaticMarkup(
    createElement(BotSchedulePanel, {
      bot: botFixture({ wakeEnabled: false }),
      schedules: [scheduleFixture({ id: "sch_gate", prompt: "gated-row" })],
      onClose() {},
    }),
  );
  assert.match(html, /被总闸拦住/);
  assert.match(html, /被自动唤醒总闸拦住/);
  assert.doesNotMatch(html, /待触发/);
});

test("panel render call site still passes !schedule.enabled into scheduleEnablePath", () => {
  const source = readFileSync(resolve(__dirname, "../src/BotSchedulePanel.tsx"), "utf8");
  assert.match(source, /scheduleEnablePath\(bot\.id, schedule\.id, !schedule\.enabled\)/);
});
