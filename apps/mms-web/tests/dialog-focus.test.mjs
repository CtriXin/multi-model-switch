import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { scheduleDialogAutofocus } from "../src/dialog-focus.ts";

const srcDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");

test("scheduleDialogAutofocus focuses the autofocus field and selects filled text", () => {
  const calls = [];
  const node = {
    tagName: "INPUT",
    type: "text",
    value: "旧名字",
    focus() { calls.push("focus"); },
    select() { calls.push("select"); },
  };
  const root = { querySelector() { return node; }, querySelectorAll() { return []; } };
  const raf = globalThis.requestAnimationFrame;
  const cancel = globalThis.cancelAnimationFrame;
  globalThis.requestAnimationFrame = (fn) => { fn(); return 1; };
  globalThis.cancelAnimationFrame = () => {};
  try {
    const stop = scheduleDialogAutofocus(root);
    stop();
    assert.ok(calls.includes("focus"));
    assert.ok(calls.includes("select"));
  } finally {
    if (raf) globalThis.requestAnimationFrame = raf;
    else delete globalThis.requestAnimationFrame;
    if (cancel) globalThis.cancelAnimationFrame = cancel;
    else delete globalThis.cancelAnimationFrame;
  }
});

test("empty fields are focused but not selected", () => {
  const calls = [];
  const node = {
    tagName: "INPUT",
    type: "text",
    value: "",
    focus() { calls.push("focus"); },
    select() { calls.push("select"); },
  };
  const raf = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = (fn) => { fn(); return 1; };
  try {
    const stop = scheduleDialogAutofocus({ querySelector() { return node; }, querySelectorAll() { return []; } });
    stop();
    assert.equal(calls.filter((name) => name === "focus").length >= 1, true);
    assert.ok(!calls.includes("select"));
  } finally {
    if (raf) globalThis.requestAnimationFrame = raf;
    else delete globalThis.requestAnimationFrame;
  }
});

test("a dialog with one text field is focused even without data-autofocus", () => {
  const calls = [];
  const node = {
    tagName: "INPUT",
    type: "text",
    value: "hi",
    disabled: false,
    focus() { calls.push("focus"); },
    select() { calls.push("select"); },
  };
  const raf = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = (fn) => { fn(); return 1; };
  try {
    const stop = scheduleDialogAutofocus({
      querySelector() { return null; },
      querySelectorAll() { return [node]; },
    });
    stop();
    assert.ok(calls.includes("focus"));
    assert.ok(calls.includes("select"));
  } finally {
    if (raf) globalThis.requestAnimationFrame = raf;
    else delete globalThis.requestAnimationFrame;
  }
});

test("Dialog reclaims focus after showModal", () => {
  const source = fs.readFileSync(path.join(srcDir, "components.tsx"), "utf-8");
  const body = source.slice(source.indexOf("export function Dialog"), source.indexOf("export { Composer }"));
  assert.match(body, /showModal\(\)/);
  assert.match(body, /scheduleDialogAutofocus\(dialog\)/);
});

test("rename and search fields mark where typing should start", () => {
  const app = fs.readFileSync(path.join(srcDir, "App.tsx"), "utf-8");
  assert.match(app, /data-autofocus=""\s*\n\s*aria-label="会话名称"/);
  assert.match(app, /data-autofocus=""\s*\n\s*aria-label="搜索全部会话"/);
});
