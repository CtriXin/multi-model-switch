import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { resolveAvatarColor, getStatusBadgeText, waitReasonLabel } from "../src/bot-visual-system.ts";

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

test("bot.css defines --bot-gutter: 40px content baseline", () => {
  const botCss = fs.readFileSync(path.resolve(__dirname, "../src/bot.css"), "utf-8");
  assert.match(botCss, /--bot-gutter:\s*40px/);
});
