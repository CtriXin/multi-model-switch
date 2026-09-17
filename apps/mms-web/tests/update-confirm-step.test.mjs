import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const srcDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
const source = fs.readFileSync(path.join(srcDir, "UpdateCenter.tsx"), "utf-8");
const css = fs.readFileSync(path.join(srcDir, "updates.css"), "utf-8");

test("confirming replaces the notes body instead of appending under it", () => {
  const body = source.slice(source.indexOf('className="update-body"'), source.indexOf("<footer>"));
  const confirm = body.indexOf("className=\"update-confirm\"");
  const notes = body.indexOf("className=\"update-notes\"");
  const ternary = body.indexOf("confirming && data?.canUpgrade && !activePhases.has(phase) ?");
  assert.ok(ternary >= 0, "confirming is a branch of the body, not an extra section");
  assert.ok(confirm > ternary);
  assert.ok(notes > confirm, "notes live in the else branch after the confirm markup");
  assert.doesNotMatch(body.slice(notes), /update-confirm/);
});

test("entering confirm scrolls the body to the top", () => {
  assert.match(source, /querySelector<HTMLElement>\("\.update-body"\)/);
  assert.match(source, /scrollTo\(\{\s*top:\s*0/);
  assert.match(source, /\.update-confirm h3/);
});

test("confirm step is not a nested card", () => {
  const block = css.slice(css.indexOf(".update-confirm {"), css.indexOf(".update-confirm h3"));
  assert.match(block, /background:\s*transparent/);
  assert.doesNotMatch(block, /border:\s*1px solid var\(--line\)/);
  assert.match(css, /\.update-center \{[^}]*overflow:\s*hidden/);
  assert.match(css, /\.update-body \{[^}]*overflow:\s*auto/);
});
