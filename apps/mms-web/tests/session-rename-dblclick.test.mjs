import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const src = fs.readFileSync(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src/App.tsx"),
  "utf-8",
);

test("sidebar session rows open the existing rename dialog on double-click", () => {
  const start = src.indexOf('"session-link "');
  assert.ok(start >= 0, "session-link still exists");
  const chunk = src.slice(start, start + 2500);
  assert.match(chunk, /onClick=\{\(\) => openSession\(s\.id\)\}/);
  assert.match(chunk, /onDoubleClick=/);
  assert.match(chunk, /beginSessionRename\(s\)/);
});

test("cli sessions cannot rename from double-click, same as the menu", () => {
  assert.match(src, /function beginSessionRename/);
  const begin = src.slice(src.indexOf("function beginSessionRename"), src.indexOf("async function submitSessionRename"));
  assert.match(begin, /owner === "cli"/);
  assert.match(begin, /终端会话不能在这里改名/);
  assert.match(begin, /setRenameSession\(\{ id: session\.id, title: session\.title \}\)/);
});

test("the overflow menu still uses the same rename entry", () => {
  assert.match(src, /beginSessionRename\(s\);\s*close\(\);/);
});
