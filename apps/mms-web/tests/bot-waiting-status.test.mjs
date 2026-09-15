import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import esbuild from "esbuild";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const botFile = path.resolve(__dirname, "../src/Bot.tsx");
const source = fs.readFileSync(botFile, "utf-8");

// Transpile pure functions out of Bot.tsx
const transpiled = esbuild.transformSync(source, {
  loader: "tsx",
  format: "cjs",
}).code;

const mod = { exports: {} };
const sandbox = {
  module: mod,
  exports: mod.exports,
  require: (req) => {
    if (req === "react") return { Fragment: () => null, useEffect: () => {}, useMemo: (fn) => fn(), useRef: () => ({ current: null }), useState: (v) => [v, () => {}] };
    if (req === "./types" || req === "./bot-presets" || req === "./api" || req === "./bot-artifact-preview" || req === "./BotCommunications" || req === "./BotPlan" || req === "./components" || req === "lucide-react") return {};
    if (req === "./bot-visual-system.ts") {
      return {
        getStatusBadgeText: (status) => {
          const map = {
            idle: "待命",
            busy: "执行中",
            running: "执行中",
            waiting: "等待你",
            queued: "已排队",
            scheduled: "已排队",
            starting: "正在启动",
            paused: "已暂停",
            completed: "已完成",
            failed: "执行失败",
          };
          return map[status] || status;
        },
        getBotSecondLine: () => null,
        getIndicatorStatus: () => "idle",
        resolveAvatarColor: () => "var(--bot-avatar-1)",
        taskStatusLabels: {},
        waitReasonLabel: () => "",
        formatScheduledTaskTime: () => "",
      };
    }
    return {};
  },
  console,
};
vm.createContext(sandbox);
vm.runInContext(transpiled, sandbox);

const { getBotHeaderStatusText } = mod.exports;

test("getBotHeaderStatusText returns '等你回复' when bot.pendingQuestion is present", () => {
  const botWithQuestion = {
    id: "bot-1",
    status: "idle",
    pendingQuestion: {
      taskId: "task-1",
      question: "需要选择方案 A 还是 B？",
      options: ["方案 A", "方案 B"],
      since: "2026-09-15T10:00:00.000Z",
    },
  };

  // Even with idle status and no tasks, pendingQuestion takes precedence
  assert.equal(getBotHeaderStatusText(botWithQuestion, []), "等你回复");

  // Even if tasks are running or waiting, pendingQuestion takes precedence
  const runningTask = { botId: "bot-1", status: "running" };
  assert.equal(getBotHeaderStatusText(botWithQuestion, [runningTask]), "等你回复");
});

test("getBotHeaderStatusText falls back to task and bot status when no pendingQuestion", () => {
  const botIdle = { id: "bot-1", status: "idle", pendingQuestion: null };

  // Idle bot with no tasks -> 待命
  assert.equal(getBotHeaderStatusText(botIdle, []), "待命");

  // Bot with running task -> 执行中
  const runningTask = { botId: "bot-1", status: "running" };
  assert.equal(getBotHeaderStatusText(botIdle, [runningTask]), "执行中");

  // Bot with starting task -> 执行中
  const startingTask = { botId: "bot-1", status: "starting" };
  assert.equal(getBotHeaderStatusText(botIdle, [startingTask]), "执行中");

  // Bot with waiting task -> 等待你
  const waitingTask = { botId: "bot-1", status: "waiting", waitReason: "user" };
  assert.equal(getBotHeaderStatusText(botIdle, [waitingTask]), "等待你");

  // Bot with failed task -> 执行失败
  const failedTask = { botId: "bot-1", status: "failed" };
  assert.equal(getBotHeaderStatusText(botIdle, [failedTask]), "执行失败");

  // Null or undefined bot -> empty string
  assert.equal(getBotHeaderStatusText(null), "");
  assert.equal(getBotHeaderStatusText(undefined), "");
});
