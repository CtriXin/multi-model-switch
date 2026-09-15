import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import esbuild from "esbuild";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const commFile = path.resolve(__dirname, "../src/BotCommunications.tsx");
const source = fs.readFileSync(commFile, "utf-8");

// Transpile pure functions out of BotCommunications.tsx
const transpiled = esbuild.transformSync(source, {
  loader: "tsx",
  format: "cjs",
}).code;

const mod = { exports: {} };
const sandbox = {
  module: mod,
  exports: mod.exports,
  require: () => ({}),
  console,
};
vm.createContext(sandbox);
vm.runInContext(transpiled, sandbox);

const { groupCommunicationsByTask, groupCommunicationsByDate } = mod.exports;

test("groupCommunicationsByTask groups messages by task, truncates prompt to 60 chars, and places newest task first", () => {
  const longPrompt = "用户指令超过六十个字的用户任务用来测试段头截断效果abcdefghijklmnopqrstuvwxyz1234567890EXTRA";
  const tasks = [
    {
      id: "task-1",
      botId: "bot-current",
      prompt: longPrompt,
      status: "completed",
      createdAt: "2026-09-11T10:00:00.000Z",
      updatedAt: "2026-09-11T10:10:00.000Z",
    },
    {
      id: "task-2",
      botId: "bot-current",
      prompt: "跟大总管打个招呼",
      status: "completed",
      createdAt: "2026-09-15T08:00:00.000Z",
      updatedAt: "2026-09-15T08:05:00.000Z",
    },
  ];

  const messages = [
    {
      id: "msg-1",
      senderBotId: "bot-current",
      recipientBotId: "bot-peer",
      content: "子任务结果内容",
      kind: "result",
      createdAt: "2026-09-11T10:05:00.000Z",
      taskId: "task-1",
      deliveryStatus: "processed",
    },
    {
      id: "msg-2",
      senderBotId: "bot-current",
      recipientBotId: "bot-peer",
      content: "你好 我是调度",
      kind: "message",
      createdAt: "2026-09-15T08:01:00.000Z",
      taskId: "task-2",
      deliveryStatus: "delivered",
    },
    {
      id: "msg-3",
      senderBotId: "bot-peer",
      recipientBotId: "bot-current",
      content: "你好调度，收到",
      kind: "message",
      createdAt: "2026-09-15T08:02:00.000Z",
      replyTo: "msg-2",
      deliveryStatus: "delivered",
    },
    {
      id: "msg-4",
      senderBotId: "bot-peer",
      recipientBotId: "bot-current",
      content: "未关联任务的消息",
      kind: "message",
      createdAt: "2026-09-10T05:00:00.000Z",
      deliveryStatus: "delivered",
    },
  ];

  const groups = groupCommunicationsByTask(messages, tasks, "bot-current");

  // 断言：按 task 正确分段，最新任务排在最前
  assert.equal(groups.length, 3);
  assert.equal(groups[0].taskId, "task-2");
  assert.equal(groups[0].taskTitle, "跟大总管打个招呼");
  assert.equal(groups[0].messages.length, 2); // msg-2 and reply msg-3

  assert.equal(groups[1].taskId, "task-1");
  assert.equal(groups[1].taskTitle, longPrompt.slice(0, 60));
  assert.equal(groups[1].taskTitle.length, 60);
  assert.equal(groups[1].messages.length, 1);

  assert.equal(groups[2].taskId, null);
  assert.equal(groups[2].taskTitle, "未关联任务");
  assert.equal(groups[2].messages[0].id, "msg-4");
});

test("groupCommunicationsByDate separates communications across distinct calendar days", () => {
  const items = [
    { id: "1", createdAt: "2026-09-15T10:00:00.000Z" },
    { id: "2", createdAt: "2026-09-15T12:00:00.000Z" },
    { id: "3", createdAt: "2026-09-11T09:00:00.000Z" },
    { id: "4", createdAt: "2026-09-08T18:00:00.000Z" },
  ];

  const dateGroups = groupCommunicationsByDate(items);

  // 断言：跨天分组成不同日期组，同天归入同组
  assert.equal(dateGroups.length, 3);
  assert.equal(dateGroups[0].items.length, 2);
  assert.equal(dateGroups[1].items.length, 1);
  assert.equal(dateGroups[2].items.length, 1);
  assert.notEqual(dateGroups[0].date, dateGroups[1].date);
});

// Bot.tsx 的两个判定是渲染闭包，取出源码原样求值，保证断言跟真实实现同一份逻辑。
const botFile = path.resolve(__dirname, "../src/Bot.tsx");
const botSource = fs.readFileSync(botFile, "utf-8");

function extractPredicate(name) {
  const start = botSource.indexOf(`const ${name} = (`);
  assert.ok(start > 0, `找不到 ${name}`);
  const end = botSource.indexOf("\n          };", start);
  assert.ok(end > start, `${name} 的函数体没有正常结束`);
  const snippet = botSource.slice(start, end + "\n          };".length);
  const js = esbuild.transformSync(snippet + `\nmodule.exports = ${name};`, {
    loader: "tsx",
    format: "cjs",
  }).code;
  const m = { exports: {} };
  vm.runInNewContext(js, { module: m, exports: m.exports });
  return m.exports;
}

test("ordinary narration that names a peer stays in the main chat", () => {
  const isPeerRelatedEvent = extractPredicate("isPeerRelatedEvent");

  // 只是提到对方名字的普通叙述，不算 peer 事件
  assert.equal(isPeerRelatedEvent({ type: "progress", content: "大总管 给的口径我照着写了一版草稿。" }), false);
  assert.equal(isPeerRelatedEvent({ type: "progress", content: "这一版参考了 调度 之前的结论。" }), false);

  // 真正的往来事件仍然要折叠
  assert.equal(isPeerRelatedEvent({ type: "handoff", content: "" }), true);
  assert.equal(isPeerRelatedEvent({ type: "progress", content: "已向 大总管 发送这一轮结论" }), true);
  assert.ok(!botSource.includes("content.includes(peer.name)"), "不应再用对方名字兜底判定 peer 事件");
});

test("a finished two-way handshake reads as the bot's own explanation", () => {
  const isPeerExplanation = extractPredicate("isPeerExplanation");

  assert.equal(isPeerExplanation("已与 大总管 完成双向消息，结论如上。"), true);
  assert.equal(isPeerExplanation("已向 调度 发送这一轮结论"), true);
  assert.equal(isPeerExplanation("我把报告整理好了，结论写在最后。"), false);
});
