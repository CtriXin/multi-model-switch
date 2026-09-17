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

function load(rel, mocks = {}) {
  const src = fs.readFileSync(path.resolve(__dirname, rel), "utf-8");
  const transpiled = esbuild.transformSync(src, {
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
      if (req in mocks) return mocks[req];
      return {};
    },
    console,
  };
  vm.createContext(sandbox);
  vm.runInContext(transpiled, sandbox);
  return mod.exports;
}

const {
  replyReaderKey,
  applyReplyReaderAction,
  focusReplyReaderBody,
  ReplyReader,
} = load("../src/ReplyReader.tsx", {
  "lucide-react": {
    X: () => React.createElement("span", { className: "icon-close" }),
  },
  "./clipboard": { copyText: async () => true },
});

const { MessageActions } = load("../src/SessionTools.tsx", {
  "lucide-react": {
    Archive: () => null,
    Copy: () => React.createElement("span", { className: "icon-copy" }),
    Download: () => null,
    Expand: () => React.createElement("span", { className: "icon-expand" }),
    GitBranch: () => React.createElement("span", { className: "icon-branch" }),
    MoreHorizontal: () => null,
    Pencil: () => null,
    RefreshCw: () => null,
    Settings2: () => null,
  },
  "./clipboard": { copyText: async () => true },
  "./api": { request: async () => ({}) },
  "./Recipe": { RecipeExport: () => null },
  "./ContextEvidence": { ContextEvidence: () => null },
  "./MessageQueue": { MessageQueue: () => null },
});

test("Enter copies in the reader; Escape closes; composer Enter is not this path", () => {
  assert.equal(replyReaderKey("Enter", false, "DIV"), "copy");
  assert.equal(replyReaderKey("Enter", false, "BUTTON"), null);
  assert.equal(replyReaderKey("Enter", true, "DIV"), null);
  assert.equal(replyReaderKey("Escape", false, "DIV"), "close");
  assert.equal(replyReaderKey("a", false, "DIV"), null);
});

test("ReplyReader is a modal with a scrollable body of only this reply", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      ReplyReader,
      { text: "# Hello\n\nworld", title: "Pi · glm-5.3", onClose: () => {} },
      React.createElement("p", null, "only this reply"),
    ),
  );
  assert.match(html, /class="reply-reader"/);
  assert.match(html, /aria-labelledby="reply-reader-title"/);
  assert.match(html, /Pi · glm-5.3/);
  assert.match(html, /class="reply-reader-body"/);
  assert.match(html, /only this reply/);
  assert.match(html, /Esc 关闭/);
  assert.match(html, /Enter 复制原文/);
  assert.doesNotMatch(html, /从这里开始新会话/);
});

test("assistant message actions include 专注阅读; user actions do not", () => {
  const detail = {
    session: { id: "s1", state: "idle", harness: "pi" },
  };
  const assistant = renderToStaticMarkup(
    React.createElement(MessageActions, {
      detail,
      eventId: "e1",
      text: "hello",
      onRead: () => {},
      action: async () => true,
    }),
  );
  assert.match(assistant, /专注阅读/);
  assert.match(assistant, /icon-expand/);
  const user = renderToStaticMarkup(
    React.createElement(MessageActions, {
      detail,
      eventId: "e2",
      text: "hello",
    }),
  );
  assert.doesNotMatch(user, /专注阅读/);
});

test("applyReplyReaderAction is what close and copy actually call", () => {
  const calls = [];
  applyReplyReaderAction("close", {
    close: () => calls.push("close"),
    copy: () => calls.push("copy"),
  });
  applyReplyReaderAction("copy", {
    close: () => calls.push("close"),
    copy: () => calls.push("copy"),
  });
  applyReplyReaderAction(null, {
    close: () => calls.push("close"),
    copy: () => calls.push("copy"),
  });
  assert.deepEqual(calls, ["close", "copy"]);
  const src = fs.readFileSync(
    path.resolve(__dirname, "../src/ReplyReader.tsx"),
    "utf-8",
  );
  assert.match(src, /if \(act === "close"\) actions\.close\(\)/);
  assert.match(src, /if \(act === "copy"\) actions\.copy\(\)/);
  assert.match(src, /onCancel=\{/);
  assert.match(src, /onKeyDown=\{/);
  assert.match(
    src,
    /applyReplyReaderAction\(\s*replyReaderKey/,
  );
});

test("showModal then focuses the body so the first Enter copies", () => {
  let focused = false;
  const body = {
    tabIndex: 0,
    focus() {
      focused = true;
    },
  };
  const root = {
    querySelector(sel) {
      return sel === ".reply-reader-body" ? body : null;
    },
  };
  assert.equal(focusReplyReaderBody(root), true);
  assert.equal(body.tabIndex, -1);
  assert.equal(focused, true);
  const src = fs.readFileSync(
    path.resolve(__dirname, "../src/ReplyReader.tsx"),
    "utf-8",
  );
  assert.match(src, /showModal\(\)/);
  assert.match(src, /focusReplyReaderBody\(dialog\)/);
  assert.match(src, /tabIndex=\{-1\}/);
});

test("EventView mounts ReplyReader for an assistant reply that is being read", () => {
  const eventView = fs
    .readFileSync(path.resolve(__dirname, "../src/components.tsx"), "utf-8")
    .split("export function EventView")[1]
    .split("function Interaction")[0];
  assert.match(eventView, /<ReplyReader/);
  assert.match(eventView, /onRead=\{/);
  assert.match(eventView, /onClose=\{\(\) => setReading\(false\)\}/);

  const lucide = new Proxy(
    {},
    {
      get: (_t, name) => () =>
        React.createElement("span", { className: "lucide-" + String(name) }),
    },
  );
  const { EventView } = load("../src/components.tsx", {
    "lucide-react": lucide,
    "react-markdown": ({ children }) =>
      React.createElement("div", { className: "markdown" }, children),
    "remark-gfm": {},
    "./remarkReadable": { remarkReadable: () => {} },
    "./clipboard": { copyText: async () => true },
    "./ToolEvent": { ToolEvent: () => null },
    "./ConversationOutline": { messageAnchor: (id) => "m-" + id },
    "./SessionTools": {
      MessageActions: ({ onRead }) =>
        onRead
          ? React.createElement(
              "button",
              { "aria-label": "专注阅读", onClick: onRead },
              "专注阅读",
            )
          : null,
    },
    "./ReplyReader": {
      ReplyReader: ({ title, children }) =>
        React.createElement(
          "dialog",
          { className: "reply-reader" },
          title,
          children,
        ),
    },
    "./MessageMedia": { AttachmentView: () => null },
    "./ContextUsage": { ContextUsage: () => null },
    "./time": {
      formatEventTime: () => "",
      formatEventTimeTitle: () => "",
      turnDuration: () => "",
    },
    "./Composer": { Composer: () => null },
  });
  const detail = {
    session: {
      id: "s1",
      state: "idle",
      harness: "pi",
      modelName: "Kimi K2.5",
      capabilities: { send: true, approve: false },
    },
  };
  const event = {
    id: "e1",
    kind: "assistant",
    text: "only this reply",
    createdAt: "2026-09-17T00:00:00Z",
  };
  const html = renderToStaticMarkup(
    React.createElement(EventView, {
      event,
      detail,
      busy: false,
      approve: () => {},
      startReading: true,
    }),
  );
  assert.match(html, /class="reply-reader"/);
  assert.match(html, /only this reply/);
  assert.match(html, /专注阅读/);
  const closed = renderToStaticMarkup(
    React.createElement(EventView, {
      event,
      detail,
      busy: false,
      approve: () => {},
      startReading: false,
    }),
  );
  assert.doesNotMatch(closed, /class="reply-reader"/);
});

test("reader body is the only scrolling pane", () => {
  const css = fs.readFileSync(
    path.resolve(__dirname, "../src/transcript.css"),
    "utf-8",
  );
  const body = css.match(/\.reply-reader-body\s*\{[^}]+\}/);
  assert.ok(body, "defines .reply-reader-body");
  assert.match(body[0], /overflow-y:\s*auto/);
  assert.match(body[0], /min-height:\s*0/);
  const open = css.match(/dialog\.reply-reader\[open\]\s*\{[^}]+\}/);
  assert.ok(open);
  assert.match(open[0], /flex-direction:\s*column/);
});
