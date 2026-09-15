// The failed plan row shows 重试/跳过 next to the status text, and acceptance
// measured the buttons sitting ~5px below the status dot. The dot and the
// trailing controls are laid out by two independent rules, so this test recomputes
// both centres from the stylesheet instead of trusting the numbers by eye.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const css = fs.readFileSync(path.resolve(__dirname, "../src/bot-plan.css"), "utf-8");
const styles = fs.readFileSync(path.resolve(__dirname, "../src/styles.css"), "utf-8");
const globalReset = styles.slice(styles.indexOf("* {"), styles.indexOf("}", styles.indexOf("* {")));

function rule(selector) {
  const at = css.indexOf(`${selector} {`);
  assert.ok(at >= 0, `${selector} should exist`);
  return css.slice(at, css.indexOf("}", at));
}

function px(selector, prop) {
  const found = rule(selector).match(new RegExp(`\\n\\s*${prop}:\\s*(-?[\\d.]+)px`));
  assert.ok(found, `${selector} should declare ${prop} in px`);
  return Number(found[1]);
}

const dotCentre =
  px(".bot-plan-step-dot", "margin-top") + px(".bot-plan-step-dot", "height") / 2;

test("the status dot centre is where the row's first line sits", () => {
  assert.equal(dotCentre, 10);
});

test("the trailing controls are centred on the same line as the dot", () => {
  const trailing = rule(".bot-plan-step-trailing");
  assert.match(trailing, /align-items:\s*center/);
  // A stale margin-top would shift the whole box off the dot centre again.
  assert.doesNotMatch(trailing, /\n\s*margin-top:/);
  assert.equal(px(".bot-plan-step-trailing", "min-height") / 2, dotCentre);
});

test("the 重试/跳过 buttons do not grow past that line box", () => {
  const height = px(".bot-plan-step-btn", "height");
  assert.equal(height, px(".bot-plan-step-trailing", "min-height"));
  // border-box plus a zero vertical padding keeps the declared height honest.
  assert.match(globalReset, /box-sizing:\s*border-box/);
  assert.match(rule(".bot-plan-step-btn"), /padding:\s*0\s/);
  assert.match(rule(".bot-plan-step-btn"), /line-height:\s*1\b/);
});
