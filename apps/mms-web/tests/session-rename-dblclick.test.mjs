import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import esbuild from "esbuild";

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

// --- Executable tests: compile and run the real handlers, so hollowing out a
// body (keeping the shell, changing the behavior) fails instead of passing.

function sliceBalanced(source, start, openChar, closeChar) {
  let depth = 0;
  for (let index = start; index < source.length; index += 1) {
    if (source[index] === openChar) depth += 1;
    else if (source[index] === closeChar) {
      depth -= 1;
      if (!depth) return source.slice(start, index + 1);
    }
  }
  throw new Error("unbalanced slice");
}

function sliceFunction(source, signature) {
  const start = source.indexOf(signature);
  assert.ok(start >= 0, `${signature} must exist in the source`);
  const paramsOpen = source.indexOf("(", start);
  let parens = 0;
  let bodyOpen = -1;
  for (let index = paramsOpen; index < source.length; index += 1) {
    const char = source[index];
    if (char === "(") parens += 1;
    else if (char === ")") parens -= 1;
    else if (char === "{" && parens === 0) { bodyOpen = index; break; }
  }
  assert.ok(bodyOpen > 0, `${signature} must have a body`);
  return source.slice(start, bodyOpen) + sliceBalanced(source, bodyOpen, "{", "}");
}

test("double-click on a session row actually starts the rename", () => {
  const marker = src.indexOf("onDoubleClick={", src.indexOf('"session-link "'));
  assert.ok(marker > 0, "the session row keeps its double-click handler");
  const arrowStart = src.indexOf("(event) =>", marker);
  const bodyOpen = src.indexOf("{", arrowStart);
  const handler = src.slice(arrowStart, bodyOpen) + sliceBalanced(src, bodyOpen, "{", "}");
  const code = esbuild.transformSync(`result = (${handler});`, { loader: "ts" }).code;
  const calls = [];
  const session = { id: "s1", title: "Demo", owner: "web" };
  const context = {
    result: null,
    s: session,
    beginSessionRename: (value) => calls.push(value),
  };
  vm.runInNewContext(code, context);
  let prevented = false;
  context.result({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true, "double-click selection is suppressed");
  assert.deepEqual(calls, [session], "double-click must reach beginSessionRename");
});

test("beginSessionRename blocks cli sessions and opens the dialog otherwise", () => {
  const fnSource = sliceFunction(src, "function beginSessionRename");
  const code = esbuild.transformSync(`result = (${fnSource});`, { loader: "ts" }).code;
  const run = (session) => {
    const notices = [];
    const renames = [];
    const context = {
      result: null,
      setWorkspaceNotice: (value) => notices.push(value),
      setRenameSession: (value) => renames.push(value),
    };
    vm.runInNewContext(code, context);
    context.result(session);
    return { notices, renames };
  };
  const cli = run({ id: "s1", title: "终端", owner: "cli" });
  assert.deepEqual(cli.notices, ["终端会话不能在这里改名"]);
  assert.equal(cli.renames.length, 0, "a terminal session must not open the rename dialog");
  const web = run({ id: "s2", title: "Demo", owner: "web" });
  assert.deepEqual(web.notices, []);
  assert.equal(web.renames.length, 1);
  assert.equal(web.renames[0].id, "s2");
  assert.equal(web.renames[0].title, "Demo");
});
