import test from "node:test";
import assert from "node:assert/strict";
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
