import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import esbuild from "esbuild";

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

// Executable test: run the real confirm effect, so keeping the strings while
// gutting the calls fails.
test("entering confirm really scrolls to top and moves focus", () => {
  const marker = source.indexOf("if (!confirming) return;");
  assert.ok(marker > 0, "the confirm effect must exist");
  const arrowStart = source.lastIndexOf("() => {", marker);
  assert.ok(arrowStart > 0);
  const bodyOpen = source.indexOf("{", arrowStart);
  let depth = 0;
  let bodyEnd = -1;
  for (let index = bodyOpen; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    else if (source[index] === "}") {
      depth -= 1;
      if (!depth) { bodyEnd = index + 1; break; }
    }
  }
  const arrow = source.slice(arrowStart, bodyEnd);
  const code = esbuild.transformSync(`result = (${arrow});`, { loader: "ts" }).code;
  const run = (confirming) => {
    const calls = { selectors: [], scrollTo: [], focus: 0 };
    const context = {
      result: null,
      confirming,
      dialog: {
        current: {
          querySelector(selector) {
            calls.selectors.push(selector);
            if (selector === ".update-body") return { scrollTo: (arg) => calls.scrollTo.push(arg) };
            return { focus: () => { calls.focus += 1; } };
          },
        },
      },
    };
    vm.runInNewContext(code, context);
    context.result();
    return calls;
  };
  const entered = run(true);
  assert.deepEqual(entered.selectors, [".update-body", ".update-confirm h3"]);
  assert.equal(entered.scrollTo.length, 1, "the body must scroll back to the top");
  assert.equal(entered.scrollTo[0].top, 0);
  assert.equal(entered.focus, 1, "the confirm heading must receive focus");
  const resting = run(false);
  assert.deepEqual(resting.selectors, []);
  assert.equal(resting.scrollTo.length, 0);
  assert.equal(resting.focus, 0);
});
