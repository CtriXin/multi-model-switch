// Guards for the two wait-control fixes on top of T3d-ui:
//   - the legacy "结束等待" button must not fire twice or swallow its error;
//   - a task that already has a question card must not be prompted twice.
// Bot.tsx renders these inline in JSX, so the invariants are asserted against
// the source the same way settings-runtime-updates.test.mjs does.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import esbuild from "esbuild";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.resolve(__dirname, "../src/Bot.tsx"), "utf-8");
const css = fs.readFileSync(path.resolve(__dirname, "../src/bot.css"), "utf-8");

function legacyDismissBlock() {
  const start = source.indexOf('className="bot-legacy-wait-dismiss"');
  assert.ok(start > 0, "legacy dismiss button should exist");
  const end = source.indexOf("</button>", start);
  assert.ok(end > start, "legacy dismiss button should be closed");
  return source.slice(start, end);
}

test("legacy dismiss button disables itself while the request is in flight", () => {
  const block = legacyDismissBlock();
  assert.match(block, /disabled=\{legacyDismissingTaskId === conversationTask\.id\}/);
  assert.match(block, /setLegacyDismissingTaskId\(conversationTask\.id\)/);
  assert.match(block, /setLegacyDismissingTaskId\(null\)/);
  assert.match(block, /finally/);
});

test("legacy dismiss button refuses a second click for the same task", () => {
  const block = legacyDismissBlock();
  assert.match(block, /if \(legacyDismissingTaskId === conversationTask\.id\) return;/);
});

test("legacy dismiss failure is shown to the user, not only logged", () => {
  const block = legacyDismissBlock();
  assert.doesNotMatch(block, /console\.error/);
  assert.match(block, /setLegacyDismissError\(/);
  assert.match(block, /结束等待失败，请稍后重试。/);
  assert.match(source, /className="bot-legacy-wait-error"/);
  assert.match(css, /\.bot-legacy-wait-error\s*\{/);
});

test("the in-flight label tells the user the dismiss is running", () => {
  assert.match(
    source,
    /legacyDismissingTaskId === conversationTask\.id \? "正在结束…" : "结束等待"/,
  );
});

test("a task with a question card does not also show the old wait notice", () => {
  const anchor = source.indexOf('<div className="bot-chat-notice">');
  assert.ok(anchor > 0, "the plain wait notice should still exist for older tasks");
  const guard = source.slice(Math.max(0, anchor - 500), anchor);
  assert.match(
    guard,
    /!\(conversationTask\.waitQuestion && bot\?\.pendingQuestion\?\.taskId === conversationTask\.id\)/,
  );
});

test("the old wait notice is kept for a waiting task without a question", () => {
  // The guard only subtracts the question-card case; the legacy branch and the
  // notice itself are untouched.
  assert.match(source, /!legacyDismissedTaskIds\.includes\(conversationTask\.id\) &&/);
  assert.match(source, /waitReasonLabel\(conversationTask\.waitReason\)/);
});

test("唤醒 is not offered next to the question card for the same task", () => {
  const anchor = source.indexOf('{task.status === "scheduled" ? "立即唤醒" : "唤醒"}');
  assert.ok(anchor > 0, "the wake button should still exist");
  const guard = source.slice(Math.max(0, anchor - 700), anchor);
  assert.match(
    guard,
    /!\(task\.waitQuestion && bot\?\.pendingQuestion\?\.taskId === task\.id\)/,
  );
});

// --- Executable tests: compile and run the real Bot.tsx source, so hollowing
// out a handler or a display condition fails instead of passing.

function sliceBalanced(text, start, openChar, closeChar) {
  let depth = 0;
  for (let index = start; index < text.length; index += 1) {
    if (text[index] === openChar) depth += 1;
    else if (text[index] === closeChar) {
      depth -= 1;
      if (!depth) return text.slice(start, index + 1);
    }
  }
  throw new Error("unbalanced slice");
}

function sliceFunction(text, signature) {
  const start = text.indexOf(signature);
  assert.ok(start >= 0, `${signature} must exist in the source`);
  const paramsOpen = text.indexOf("(", start);
  let parens = 0;
  let bodyOpen = -1;
  for (let index = paramsOpen; index < text.length; index += 1) {
    const char = text[index];
    if (char === "(") parens += 1;
    else if (char === ")") parens -= 1;
    else if (char === "{" && parens === 0) { bodyOpen = index; break; }
  }
  assert.ok(bodyOpen > 0, `${signature} must have a body`);
  return text.slice(start, bodyOpen) + sliceBalanced(text, bodyOpen, "{", "}");
}

function loadWaitHandler(signature) {
  const fnSource = sliceFunction(source, signature);
  return esbuild.transformSync(`result = (${fnSource});`, { loader: "ts" }).code;
}

function handlerHarness(code, { busy = false, disabled = false } = {}) {
  const calls = { request: [], dismissed: [], value: [], busy: [], error: [] };
  const context = {
    result: null,
    busy,
    disabled,
    encodeURIComponent,
    request: async (url, payload) => { calls.request.push([url, payload]); },
    setBusy: (value) => calls.busy.push(value),
    setError: (value) => calls.error.push(value),
    setDismissedPendingTaskIds: (fn) => calls.dismissed.push(fn(["prev"])),
    setValue: (value) => calls.value.push(value),
  };
  vm.runInNewContext(code, context);
  return { fn: context.result, calls };
}

test("handleAnswerWait posts the answer to the wait endpoint", async () => {
  const { fn, calls } = handlerHarness(loadWaitHandler("async function handleAnswerWait"));
  await fn("task-1", "  好的  ");
  assert.equal(calls.request.length, 1, "a valid answer must reach the server");
  assert.equal(calls.request[0][0], "/tasks/task-1/wait");
  assert.equal(calls.request[0][1].action, "answer");
  assert.equal(calls.request[0][1].text, "好的");
  assert.equal(JSON.stringify(calls.dismissed), '[["prev","task-1"]]');
  assert.deepEqual(calls.value, [""], "the composer clears after answering");
});

test("handleAnswerWait ignores empty answers and busy state", async () => {
  const code = loadWaitHandler("async function handleAnswerWait");
  const empty = handlerHarness(code);
  await empty.fn("task-1", "   ");
  assert.equal(empty.calls.request.length, 0);
  const busyRun = handlerHarness(code, { busy: true });
  await busyRun.fn("task-1", "好的");
  assert.equal(busyRun.calls.request.length, 0);
});

test("handleDismissWait posts the dismiss action", async () => {
  const { fn, calls } = handlerHarness(loadWaitHandler("async function handleDismissWait"));
  await fn("task-2");
  assert.equal(calls.request.length, 1, "dismiss must reach the server");
  assert.equal(calls.request[0][0], "/tasks/task-2/wait");
  assert.equal(calls.request[0][1].action, "dismiss");
  assert.equal(JSON.stringify(calls.dismissed), '[["prev","task-2"]]');
});

function legacyWaitRowExpression() {
  const marker = source.indexOf("{conversationTask.waitReason && (");
  assert.ok(marker > 0, "the legacy wait block must exist in Bot.tsx");
  const parenOpen = source.indexOf("(", marker);
  const expression = source.slice(marker + 1, parenOpen) + sliceBalanced(source, parenOpen, "(", ")");
  return esbuild.transformSync(`result = (${expression});`, { loader: "tsx" }).code;
}

function renderLegacyWait(conversationTask, { dismissed = [], botValue = null } = {}) {
  const context = {
    result: null,
    React: { createElement: (tag, props, ...children) => ({ tag, props: props || {}, children }) },
    Timer: "Timer",
    conversationTask,
    bot: botValue,
    legacyDismissedTaskIds: dismissed,
    legacyDismissingTaskId: null,
    legacyDismissError: "",
    setLegacyDismissingTaskId: () => {},
    setLegacyDismissError: () => {},
    setLegacyDismissedTaskIds: () => {},
    request: async () => {},
    encodeURIComponent,
    waitReasonLabel: (reason) => `label:${reason}`,
  };
  vm.runInNewContext(legacyWaitRowExpression(), context);
  return context.result;
}

test("a waiting user task without a question shows the legacy wait row", () => {
  const rendered = renderLegacyWait({ id: "t1", status: "waiting", waitReason: "user" });
  assert.ok(rendered, "the wait row must render");
  assert.match(rendered.props.className, /bot-legacy-wait-row/);
});

test("a dismissed task or a task with a question card shows no legacy wait row", () => {
  const dismissed = renderLegacyWait(
    { id: "t1", status: "waiting", waitReason: "user" },
    { dismissed: ["t1"] },
  );
  assert.equal(dismissed, null);
  const withCard = renderLegacyWait(
    { id: "t2", status: "waiting", waitReason: "user", waitQuestion: "q" },
    { botValue: { pendingQuestion: { taskId: "t2" } } },
  );
  assert.equal(withCard, null);
  // A task with a question but no card keeps the plain notice branch.
  const plain = renderLegacyWait({ id: "t3", status: "waiting", waitReason: "user", waitQuestion: "q" });
  assert.ok(plain);
  assert.equal(plain.props.className, "bot-chat-notice");
});
