import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  resolveAvatarColor,
  getStatusBadgeText,
  waitReasonLabel,
  formatScheduledTaskTime,
  getBotSecondLine,
  getIndicatorStatus,
} from "../src/bot-visual-system.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("avatar color resolution maps default palette to CSS semantic variables", () => {
  assert.equal(resolveAvatarColor("#b9a5ff"), "var(--bot-avatar-1)");
  assert.equal(resolveAvatarColor("#ff9f91"), "var(--bot-avatar-2)");
  assert.equal(resolveAvatarColor("#73dfc7"), "var(--bot-avatar-3)");
  assert.equal(resolveAvatarColor("#ffd77d"), "var(--bot-avatar-4)");
  assert.equal(resolveAvatarColor("#8bb8ff"), "var(--bot-avatar-5)");
  assert.equal(resolveAvatarColor("#f18bd5"), "var(--bot-avatar-6)");
  assert.equal(resolveAvatarColor(), "var(--bot-avatar-1)");
  assert.equal(resolveAvatarColor("oklch(0.6 0.2 180)"), "oklch(0.6 0.2 180)");
});

test("status badge labels follow refined human-friendly visual system", () => {
  assert.equal(getStatusBadgeText("idle"), "待命");
  assert.equal(getStatusBadgeText("busy"), "执行中");
  assert.equal(getStatusBadgeText("running"), "执行中");
  assert.equal(getStatusBadgeText("waiting"), "等待你");
  assert.equal(getStatusBadgeText("queued"), "已排队");
  assert.equal(getStatusBadgeText("scheduled"), "已排队");
  assert.equal(getStatusBadgeText("starting"), "正在启动");
  assert.equal(getStatusBadgeText("paused"), "已暂停");
  assert.equal(getStatusBadgeText("completed"), "已完成");
  assert.equal(getStatusBadgeText("failed"), "执行失败");
});

test("waitReasonLabel translates system wait reasons into natural prompts", () => {
  assert.equal(waitReasonLabel("needs_approval"), "等待你在会话中确认");
  assert.equal(waitReasonLabel("reconnecting"), "等待模型服务恢复连接");
  assert.equal(waitReasonLabel("stopping"), "正在停止，稍后刷新状态");
  assert.equal(waitReasonLabel("schedule"), "已安排在指定时间运行");
  assert.equal(waitReasonLabel("manual"), "等待你手动唤醒");
});

test("formatScheduledTaskTime formats relative dates accurately", () => {
  const refNow = new Date(2026, 8, 12, 12, 0, 0); // 2026-09-12
  const todayTask = new Date(2026, 8, 12, 15, 30, 0).toISOString();
  const tomorrowTask = new Date(2026, 8, 13, 9, 0, 0).toISOString();

  assert.equal(formatScheduledTaskTime(todayTask, refNow), "今天 15:30");
  assert.equal(formatScheduledTaskTime(tomorrowTask, refNow), "明天 09:00");
});

test("getBotSecondLine follows strict priority order and returns null when empty", () => {
  const bot = { id: "bot-1", status: "idle", description: "默认描述" };
  const refNow = new Date(2026, 8, 12, 12, 0, 0);

  // 1. Running task priority
  const runningTask = { botId: "bot-1", prompt: "正在处理用户请求", status: "running" };
  const waitTask = { botId: "bot-1", prompt: "待确认任务", status: "waiting", waitReason: "needs_approval" };
  assert.equal(getBotSecondLine(bot, undefined, [runningTask, waitTask], refNow), "正在处理用户请求");

  // 2. waitReason priority
  assert.equal(getBotSecondLine(bot, undefined, [waitTask], refNow), "等待你在会话中确认");

  // 3. Next schedule priority ("明天 09:00 · 任务前 12 字")
  const scheduledTask = {
    botId: "bot-1",
    prompt: "超长定时任务名称用来测试前十二个字截断",
    status: "scheduled",
    runAt: new Date(2026, 8, 13, 9, 0, 0).toISOString(),
  };
  assert.equal(getBotSecondLine(bot, undefined, [scheduledTask], refNow), "明天 09:00 · 超长定时任务名称用来测试");

  // 4. outcome.summary priority
  const finishedTask = {
    botId: "bot-1",
    prompt: "已完成任务",
    status: "completed",
    outcome: { summary: "成功生成了报告并交付" },
  };
  assert.equal(getBotSecondLine(bot, undefined, [finishedTask], refNow), "成功生成了报告并交付");

  // 5. description
  assert.equal(getBotSecondLine(bot, undefined, [], refNow), "默认描述");

  // 6. null when none exist (no description, no tasks)
  const emptyBot = { id: "bot-2", status: "idle", description: "" };
  assert.equal(getBotSecondLine(emptyBot, undefined, [], refNow), null);
});

test("getIndicatorStatus resolves running, waiting, failed, and idle states", () => {
  assert.equal(getIndicatorStatus({ id: "b1", status: "busy" }), "running");
  assert.equal(getIndicatorStatus({ id: "b1", status: "idle" }, { botId: "b1", prompt: "x", status: "running" }), "running");
  assert.equal(getIndicatorStatus({ id: "b1", status: "paused" }), "waiting");
  assert.equal(getIndicatorStatus({ id: "b1", status: "idle" }, { botId: "b1", prompt: "x", waitReason: "needs_approval" }), "waiting");
  assert.equal(getIndicatorStatus({ id: "b1", status: "failed" }), "failed");
  assert.equal(getIndicatorStatus({ id: "b1", status: "idle" }, { botId: "b1", prompt: "x", status: "failed" }), "failed");
  assert.equal(getIndicatorStatus({ id: "b1", status: "idle" }), "idle");
});

test("CSS token gate: hex count across bot*.css is <= 12 and strictly scoped to avatar tokens", () => {
  const srcDir = path.resolve(__dirname, "../src");
  const files = ["bot.css", "bot-memory.css", "bot-communications.css"];
  let totalHex = 0;
  const hexRegex = /#[0-9a-fA-F]{3,8}/g;

  for (const file of files) {
    const filePath = path.join(srcDir, file);
    const fileContent = fs.readFileSync(filePath, "utf-8");
    const matches = fileContent.match(hexRegex) || [];
    if (file !== "bot.css") {
      assert.equal(matches.length, 0, `${file} must contain 0 hex colors`);
    } else {
      assert.equal(matches.length, 12, `bot.css must contain exactly 12 hex colors for avatar tokens`);
    }
    totalHex += matches.length;
  }

  assert.ok(totalHex <= 12, `Total hex count across bot*.css must be <= 12, got ${totalHex}`);
});

test("bot.css defines --bot-gutter: 40px content baseline and layout specs", () => {
  const botCss = fs.readFileSync(path.resolve(__dirname, "../src/bot.css"), "utf-8");
  assert.match(botCss, /--bot-gutter:\s*40px/);
  // .pixel-avatar-mini definition (31px square, 10px radius, 75% grid)
  assert.match(botCss, /\.pixel-avatar-mini\s*\{[^}]*width:\s*31px/);
  assert.match(botCss, /\.pixel-avatar-mini\s*\{[^}]*height:\s*31px/);
  assert.match(botCss, /\.pixel-avatar-mini\s*\{[^}]*border-radius:\s*10px/);
  assert.match(botCss, /\.pixel-avatar-mini \.pixel-avatar-grid\s*\{[^}]*width:\s*75%/);

  // .bot-card 56px height, 36px avatar
  assert.match(botCss, /\.bot-card\s*\{[^}]*height:\s*56px/);
  assert.match(botCss, /\.bot-card \.pixel-avatar\s*\{[^}]*width:\s*36px/);
  assert.match(botCss, /\.bot-card-status-dot\s*\{[^}]*width:\s*8px/);

  // .bot-chat-stream responsive clamp formula
  assert.match(botCss, /\.bot-chat-stream\s*\{[^}]*clamp\(24px,\s*7vw,\s*140px\)/);
  assert.match(botCss, /\.bot-chat-composer-container\s*\{[^}]*clamp\(24px,\s*7vw,\s*140px\)/);
});
