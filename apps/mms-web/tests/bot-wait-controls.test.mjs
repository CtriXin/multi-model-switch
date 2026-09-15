// Guards for the two wait-control fixes on top of T3d-ui:
//   - the legacy "结束等待" button must not fire twice or swallow its error;
//   - a task that already has a question card must not be prompted twice.
// Bot.tsx renders these inline in JSX, so the invariants are asserted against
// the source the same way settings-runtime-updates.test.mjs does.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

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
