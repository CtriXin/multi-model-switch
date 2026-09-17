import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const read = (rel) => readFileSync(resolve(__dirname, rel), "utf8");

test("composer builds interval rules with intervalSecondsFromHours, not a silent unit mixup", () => {
  const source = read("../src/Bot.tsx");
  assert.match(source, /一次/);
  assert.match(source, /每天/);
  assert.match(source, /每周/);
  assert.match(source, /每 N 小时/);
  assert.match(source, /intervalSecondsFromHours\(/);
  assert.match(source, /composerRuleFromForm\(/);
  assert.match(source, /onceLocalToIso\(/);
  assert.match(source, /timezone:\s*localTimezone\(\)/);
  assert.doesNotMatch(
    source,
    /everySeconds:\s*[^\n]*\*\s*60\b/,
    "composer must not convert hours with * 60",
  );
  assert.match(source, /定时间隔最短 5 分钟/);
  assert.match(source, /schedulePopoverOpen/);
});

test("pause and resume go through /enable and /disable, never an edit POST with enabled", () => {
  const source = read("../src/BotSchedulePanel.tsx");
  assert.match(source, /function scheduleEnablePath/);
  assert.match(
    source,
    /\$\{action\}/,
  );
  assert.match(source, /enabled \? "enable" : "disable"/);
  assert.match(source, /scheduleEnablePath\(bot\.id, schedule\.id, !schedule\.enabled\)/);
  assert.match(source, /mutate\(scheduleEnablePath\(/);
  assert.match(source, /mutate\(scheduleEditPath\(/);
  assert.match(source, /prompt:\s*trimmed/);
  assert.match(source, /overlapPolicy/);
  assert.doesNotMatch(
    source,
    /mutate\(scheduleEditPath\([^)]*\),\s*\{[^}]*enabled/,
  );
  assert.doesNotMatch(source, /enabled:\s*(true|false|schedule\.enabled)/);
  assert.match(source, /已经跑出来的任务会保留/);
  assert.match(source, /window\.confirm/);
  assert.match(source, /isDirty/);
  assert.match(source, /document\.addEventListener\("pointerdown", handlePointerDown\)/);
  assert.match(source, /e\.key === "Escape"/);
  assert.match(source, /\[aria-label="打开定时面板"\], \[title="定时"\]/);
});

test("management list keeps the four run states and does not collapse them into overdue", () => {
  const panel = read("../src/BotSchedulePanel.tsx");
  const logic = read("../src/bot-schedules.ts");
  assert.match(panel, /scheduleRunState\(/);
  assert.match(panel, /\{state\.label\}/);
  assert.match(panel, /wakeEnabled: bot\.wakeEnabled/);
  assert.match(panel, /这不是单条「已暂停」/);
  assert.match(logic, /被自动唤醒总闸拦住/);
  assert.match(panel, /skipNote\(/);
  assert.doesNotMatch(panel, /逾期/);
  assert.match(logic, /kind: "upcoming"/);
  assert.match(logic, /kind: "held"/);
  assert.match(logic, /kind: "gated"/);
  assert.match(logic, /label: "已到点但被挂起"/);
  assert.match(logic, /label: "已执行完"/);
  assert.match(logic, /label: "记录损坏"/);
  assert.match(logic, /skip\?\.reason === "paused"/);
  assert.match(logic, /skip\?\.reason === "busy"/);
  assert.match(logic, /skip\?\.reason === "invalid"/);
  assert.doesNotMatch(logic, /逾期/);
  const disabledAt = logic.indexOf("if (!schedule.enabled)");
  const futureAt = logic.indexOf("if (future)");
  assert.ok(disabledAt >= 0 && futureAt > disabledAt, "!enabled must win over a future nextRunAt");
});

test("BotStudio wakeEnabled default aligns with backend true via nullish coalescing", () => {
  const source = read("../src/BotStudio.tsx");
  assert.match(source, /bot\?\.wakeEnabled \?\? true/);
  assert.doesNotMatch(source, /bot\?\.wakeEnabled \|\| false/);
  assert.match(source, /这个 Bot 的定时到点后自动开始/);
  assert.match(source, /定时不会触发，只在你手动唤醒时执行/);
  assert.match(source, /isScheduleCreateResult\(/);
  assert.match(source, /kind:\s*"schedule"/);
});

test("AutoWakeControl copy and schedule panel mount are actually in Bot.tsx JSX", () => {
  const source = read("../src/Bot.tsx");
  assert.match(source, /这个 Bot 的定时到点后自动开始/);
  assert.match(source, /定时不会触发，只在你手动唤醒时执行/);
  assert.match(source, /<BotSchedulePanel/);
  assert.match(source, /aria-label="打开定时面板"/);
  assert.match(source, /createdScheduleNotice\(/);
  assert.match(source, /由定时触发/);
});
