import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import esbuild from "esbuild";
import React from "react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(
  path.resolve(__dirname, "../src/SessionAttention.ts"),
  "utf-8",
);
const transpiled = esbuild.transformSync(source, {
  loader: "ts",
  format: "cjs",
}).code;
const mod = { exports: {} };
const sandbox = {
  module: mod,
  exports: mod.exports,
  require: (req) => {
    if (req === "react") return React;
    if (req === "./api") return { getSession: async () => ({}) };
    return {};
  },
  console,
};
vm.createContext(sandbox);
vm.runInContext(transpiled, sandbox);
const { conversationAtBottom, shouldMarkResultRead } = mod.exports;

test("opening a session is not a read; only the visible bottom counts", () => {
  assert.equal(
    shouldMarkResultRead({
      hasOutputToken: true,
      viewingBottom: false,
      visible: true,
      connected: true,
    }),
    false,
    "in the session window but not at the bottom must stay unread",
  );
  assert.equal(
    shouldMarkResultRead({
      hasOutputToken: true,
      viewingBottom: true,
      visible: true,
      connected: true,
    }),
    true,
    "latest output on screen marks the result read",
  );
  assert.equal(
    shouldMarkResultRead({
      hasOutputToken: true,
      viewingBottom: true,
      visible: false,
      connected: true,
    }),
    false,
    "a hidden tab does not count as having read the result",
  );
  assert.equal(
    shouldMarkResultRead({
      hasOutputToken: false,
      viewingBottom: true,
      visible: true,
      connected: true,
    }),
    false,
    "no settled output token cannot be marked read",
  );
});

test("conversationAtBottom uses the live scrollbar, not selected-row state", () => {
  assert.equal(
    conversationAtBottom({ scrollHeight: 4000, scrollTop: 0, clientHeight: 800 }),
    false,
    "scrolled to the top of a long transcript is not the bottom",
  );
  assert.equal(
    conversationAtBottom({
      scrollHeight: 4000,
      scrollTop: 3101,
      clientHeight: 800,
    }),
    true,
    "within 100px of the end counts as the bottom",
  );
  assert.equal(
    conversationAtBottom({
      scrollHeight: 4000,
      scrollTop: 2000,
      clientHeight: 800,
    }),
    false,
    "mid-transcript is unread even if the session is open",
  );
  assert.equal(
    conversationAtBottom({ scrollHeight: 500, scrollTop: 0, clientHeight: 800 }),
    true,
    "content that fits the viewport is fully visible",
  );
});
