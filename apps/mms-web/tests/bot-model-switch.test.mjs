// 对话里换模型的匹配与头部显示守卫。
// 匹配样例与后端 tests/test_mms_bot_model_switch.py 读同一份 fixture
// （fixtures/model-match-cases.json），任何一端漂移都会在这里或对面变红。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  normalizeModelQuery,
  matchAvailablePresets,
  resolveModelSwitch,
} from "../src/bot-model-switch.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "fixtures/model-match-cases.json"), "utf-8"),
);
const PRESETS = fixture.presets;

test("matchAvailablePresets agrees with the shared fixture on every case", () => {
  assert.ok(fixture.cases.length >= 15, "fixture should pin at least 15 cases");
  for (const item of fixture.cases) {
    assert.deepEqual(
      matchAvailablePresets(item.query, PRESETS).map((p) => p.id),
      item.expect,
      `query ${JSON.stringify(item.query)}`,
    );
  }
});

test("matchAvailablePresets only searches launchable pi presets", () => {
  // A non-pi harness and an unavailable preset never match, even by name.
  assert.deepEqual(matchAvailablePresets("codex", PRESETS), []);
  assert.deepEqual(matchAvailablePresets("down", PRESETS), []);
});

test("resolveModelSwitch switches on exactly one match, effective next round", () => {
  const reply = resolveModelSwitch("Beta 吧", PRESETS);
  assert.deepEqual(reply.patch, { pendingPresetId: "pi:beta" });
  assert.match(reply.message, /下一轮起使用 Beta · 主通道/);
  assert.match(reply.message, /本轮仍是当前模型/);
});

test("resolveModelSwitch lists candidates on multiple matches instead of picking first", () => {
  const reply = resolveModelSwitch("gamma", PRESETS);
  assert.equal(reply.patch, null);
  assert.match(reply.message, /Gamma Pro · 备用/);
  assert.match(reply.message, /Gamma Mini · 备用/);
  assert.match(reply.message, /说得更具体/);
});

test("resolveModelSwitch lists available models when nothing matches", () => {
  const reply = resolveModelSwitch("不存在的模型", PRESETS);
  assert.equal(reply.patch, null);
  assert.match(reply.message, /我没找到「不存在的模型」/);
  assert.match(reply.message, /当前可用：/);
});

test("resolveModelSwitch does not patch when the match is the current model", () => {
  const reply = resolveModelSwitch("alpha", PRESETS, "pi:alpha");
  assert.equal(reply.patch, null);
  assert.match(reply.message, /已经在用 Alpha 了/);
});

test("normalizeModelQuery strips separators and trailing particles", () => {
  assert.equal(normalizeModelQuery("Gamma Pro 吧"), "gammapro");
  assert.equal(normalizeModelQuery("kimi-k3 1M。"), "kimik31m");
});

// bot-chat-model-line 是用户唯一看得见「当前 X · 下一轮 Y」的位置；删掉整块
// JSX 时必须由这条断言变红（同 bot-wait-controls.test.mjs 的源码块范式）。
const botSource = fs.readFileSync(path.resolve(__dirname, "../src/Bot.tsx"), "utf-8");

test("bot chat header renders the current and next-round model line", () => {
  const start = botSource.indexOf('className="bot-chat-model-line"');
  assert.ok(start > 0, "bot-chat-model-line should exist in the chat header");
  const end = botSource.indexOf("</p>", start);
  assert.ok(end > start, "bot-chat-model-line should be closed");
  const block = botSource.slice(start, end);
  assert.match(block, /当前 /);
  assert.match(block, /下一轮 /);
  assert.ok(block.includes("bot.pendingPresetId"), "next-round model comes from pendingPresetId");
  assert.ok(block.includes("bot.model"), "current model comes from bot.model");
});
