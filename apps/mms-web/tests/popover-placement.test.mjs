import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import React from "react";
import esbuild from "esbuild";
import * as placement from "../src/popover-placement.ts";
import { popoverPlacement } from "../src/popover-placement.ts";
import { keyboardInset } from "../src/viewport.ts";

test("narrow viewports dock the popover as a bottom sheet", () => {
  const style = popoverPlacement(
    { top: 500, bottom: 540, right: 80 },
    { width: 390, height: 700, keyboardInset: 0 },
  );
  assert.equal(style.left, 12);
  assert.equal(style.width, 366);
  assert.equal(style.top, "auto");
  assert.equal(style.bottom, 12);
  assert.ok(style.maxHeight <= 700);
});

test("the sheet sits above the keyboard inset", () => {
  const style = popoverPlacement(
    { top: 200, bottom: 240, right: 80 },
    { width: 390, height: 400, keyboardInset: 280 },
  );
  assert.equal(style.bottom, 292);
  assert.ok(style.maxHeight >= 160);
});

test("wide screens keep the panel next to the trigger and on-screen", () => {
  const style = popoverPlacement(
    { top: 80, bottom: 110, right: 70 },
    { width: 1280, height: 800 },
  );
  assert.ok(style.left >= 12);
  assert.ok(style.left + style.width <= 1280 - 12);
  assert.equal(style.top, 120);
});

test("keyboard inset is the layout viewport minus the visible viewport", () => {
  assert.equal(keyboardInset(800, { height: 500, offsetTop: 0 }), 300);
  assert.equal(keyboardInset(800, { height: 500, offsetTop: 40 }), 260);
  assert.equal(keyboardInset(800, { height: 800, offsetTop: 0 }), 0);
});

// Wiring test: run the real Popover component and its click handler, so a
// call site that stops using popoverPlacement (e.g. back to fixed right
// alignment) fails even though the pure function itself is fine.
function loadPopover() {
  const srcDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
  const code = esbuild.transformSync(
    fs.readFileSync(path.join(srcDir, "Popover.tsx"), "utf-8"),
    { loader: "tsx", format: "cjs" },
  ).code;
  const mod = { exports: {} };
  const setters = [];
  const reactMock = {
    ...React,
    useId: () => "p1",
    useRef: () => ({ current: null }),
    useState: (initial) => {
      const slot = { value: initial };
      setters.push(slot);
      return [initial, (next) => { slot.value = next; }];
    },
  };
  const sandbox = {
    module: mod,
    exports: mod.exports,
    React: reactMock,
    require: (req) => {
      if (req === "react") return reactMock;
      if (req === "./popover-placement") return placement;
      throw new Error(`unexpected require: ${req}`);
    },
    console,
  };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return { Popover: mod.exports.Popover, setters };
}

test("Popover places its panel through popoverPlacement on click", () => {
  const { Popover, setters } = loadPopover();
  const previousWindow = globalThis.window;
  globalThis.window = { innerWidth: 390, innerHeight: 700 };
  try {
    const tree = Popover({ label: "打开", title: "面板", children: "内容" });
    const [trigger] = tree.props.children;
    assert.equal(setters.length, 2, "Popover keeps its style and open state slots");
    trigger.props.onClick({
      currentTarget: { getBoundingClientRect: () => ({ top: 500, bottom: 540, right: 80 }) },
    });
    const style = setters[0].value;
    // On a 390px phone the panel must dock as a bottom sheet: this is the
    // style popoverPlacement computes, not the old right-aligned one.
    assert.equal(style.left, 12);
    assert.equal(style.width, 366);
    assert.equal(style.bottom, 12);
    assert.equal(style.top, "auto");
    assert.equal(style.right, undefined, "the panel must not fall back to right alignment");
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});
