import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import esbuild from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const lucide = {
  Check: () => React.createElement("span", { className: "icon-check" }),
  Circle: () => React.createElement("span", { className: "icon-circle" }),
  CircleAlert: () => React.createElement("span", { className: "icon-alert" }),
  Pause: () => React.createElement("span", { className: "icon-pause" }),
  CircleHelp: () => React.createElement("span", { className: "icon-help" }),
  WifiOff: () => React.createElement("span", { className: "icon-wifi-off" }),
  LoaderCircle: () => React.createElement("span", { className: "icon-loader" }),
  Wrench: () => React.createElement("span", { className: "icon-wrench" }),
};

const source = fs.readFileSync(
  path.resolve(__dirname, "../src/SessionStatus.tsx"),
  "utf-8",
);
const transpiled = esbuild.transformSync(source, {
  loader: "tsx",
  format: "cjs",
}).code;
const mod = { exports: {} };
const sandbox = {
  React,
  module: mod,
  exports: mod.exports,
  require: (req) => {
    if (req === "react") return React;
    if (req === "lucide-react") return lucide;
    return {};
  },
  console,
};
vm.createContext(sandbox);
vm.runInContext(transpiled, sandbox);
const { Status } = mod.exports;

const idle = { state: "idle", activity: null, capabilities: { send: true } };
const tool = {
  state: "running",
  activity: { phase: "tool", toolName: "bash" },
  capabilities: { send: true },
};

test("Status maps unread complete to Check and pending to Circle", () => {
  const unread = renderToStaticMarkup(
    React.createElement(Status, { session: idle, compact: true, unread: true }),
  );
  assert.match(unread, /data-phase="completed"/);
  assert.match(unread, /icon-check/);
  assert.doesNotMatch(unread, /icon-pause/);
  assert.doesNotMatch(unread, /icon-help/);

  const read = renderToStaticMarkup(
    React.createElement(Status, { session: idle, compact: true, unread: false }),
  );
  assert.match(read, /data-phase="pending"/);
  assert.match(read, /icon-circle/);
  assert.doesNotMatch(read, /icon-check/);

  const running = renderToStaticMarkup(
    React.createElement(Status, { session: tool, compact: true }),
  );
  assert.match(running, /data-phase="tool"/);
  assert.match(running, /icon-wrench/);
  assert.doesNotMatch(running, /icon-help/);
});

test("unread complete is success and bold; pending is muted", () => {
  const css = fs.readFileSync(
    path.resolve(__dirname, "../src/states.css"),
    "utf-8",
  );
  const completed = css.match(/\.session-phase\.completed\s*\{[^}]+\}/);
  assert.ok(completed, "defines .session-phase.completed");
  assert.match(completed[0], /color:\s*var\(--success\)/);
  assert.match(completed[0], /font-weight:\s*650/);
  const pendingBlock = css.slice(css.indexOf(".session-phase.pending"));
  const pending = pendingBlock.match(/\.session-phase\.pending[\s\S]*?\{[^}]+\}/);
  assert.ok(pending, "defines .session-phase.pending");
  assert.match(pending[0], /color:\s*var\(--muted\)/);
});
