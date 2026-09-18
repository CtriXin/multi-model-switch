import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import esbuild from "esbuild";
import {
  applyTreeKey,
  BusyNotice,
  busyNotice,
  BUSY_BROWSE,
  BUSY_SELECT,
  dismissWorkspaceDialog,
  FolderTree,
  FOLDER_TREE_CLASS,
  parentRowIndex,
  scheduleWorkspaceSearchFocus,
  toggleExpanded,
  TREE_TRUNCATED_HINT,
  USE_FOLDER_LABEL,
  visibleRows,
  WORKSPACE_SEARCH_AUTOFOCUS,
  WorkspaceDialogBody,
} from "../src/folder-tree.ts";

const launchSource = readFileSync(new URL("../src/LaunchOptions.tsx", import.meta.url), "utf8");
const studioCss = readFileSync(new URL("../src/studio.css", import.meta.url), "utf8");

const noop = () => {};
const sampleRows = visibleRows(
  [
    { name: "Documents", path: "/Users/xin/Documents", kind: "folder" },
    { name: "Downloads", path: "/Users/xin/Downloads", kind: "folder" },
  ],
  ["/Users/xin/Documents"],
  {
    "/Users/xin/Documents": [{ name: "Projects", path: "/Users/xin/Documents/Projects" }],
  },
);

function renderPicker(overrides = {}) {
  return renderToStaticMarkup(
    createElement(WorkspaceDialogBody, {
      query: "",
      onQueryChange: noop,
      onQueryKeyDown: noop,
      browsing: false,
      busy: "",
      status: "最近和常用的文件夹",
      error: "",
      shown: [],
      choice: 0,
      onHighlightShown: noop,
      onSelectShown: noop,
      rows: [],
      activeIndex: 0,
      truncated: false,
      onHighlightRow: noop,
      onToggleRow: noop,
      onTreeKeyDown: noop,
      onUseFolder: noop,
      onOpenBrowser: noop,
      ...overrides,
    }),
  );
}

test("WorkspaceDialog mounts WorkspaceDialogBody", () => {
  assert.match(launchSource, /<WorkspaceDialogBody/);
  assert.match(launchSource, /scheduleWorkspaceSearchFocus\(inputRef\.current\)/);
});

test("browsing dialog body renders the tree and the confirm button", () => {
  const html = renderPicker({ browsing: true, rows: sampleRows, truncated: false });
  assert.match(html, /role="tree"/);
  assert.match(html, /Documents/);
  assert.match(html, new RegExp(USE_FOLDER_LABEL));
});

test("busy dialog body renders the in-flight notice", () => {
  const html = renderPicker({ busy: "browse" });
  assert.match(html, /workspace-busy/);
  assert.match(html, new RegExp(BUSY_BROWSE));
});

test("folder tree markup includes visible rows and the tree role", () => {
  const html = renderToStaticMarkup(
    createElement(FolderTree, {
      rows: sampleRows,
      activeIndex: 0,
      onHighlight() {},
      onToggle() {},
    }),
  );
  assert.match(html, /role="tree"/);
  assert.match(html, /Documents/);
  assert.match(html, /Projects/);
  assert.match(html, new RegExp(`id="${FOLDER_TREE_CLASS}"`));
});

test("expand handler adds and removes the path", () => {
  assert.deepEqual(toggleExpanded([], "/tmp/a"), ["/tmp/a"]);
  assert.deepEqual(toggleExpanded(["/tmp/a"], "/tmp/a"), []);
  const rows = visibleRows(
    [{ name: "a", path: "/tmp/a" }],
    toggleExpanded([], "/tmp/a"),
    { "/tmp/a": [{ name: "child", path: "/tmp/a/child" }] },
  );
  assert.equal(rows.some((row) => row.name === "child"), true);
});

test("busy notice renders the in-flight copy", () => {
  assert.equal(busyNotice("select"), BUSY_SELECT);
  assert.equal(busyNotice("browse"), BUSY_BROWSE);
  const html = renderToStaticMarkup(createElement(BusyNotice, { busy: "select" }));
  assert.match(html, new RegExp(BUSY_SELECT));
  assert.match(html, /role="status"/);
});

test("closing the workspace dialog is allowed while busy", () => {
  let closed = 0;
  let aborted = 0;
  dismissWorkspaceDialog(() => { closed += 1; }, () => { aborted += 1; });
  assert.equal(closed, 1);
  assert.equal(aborted, 1);
  assert.match(launchSource, /dismissWorkspaceDialog\(close/);
  assert.doesNotMatch(launchSource, /if\s*\(\s*!busy\s*\)\s*close\s*\(\s*\)/);
});

test("search field keeps autoFocus and the 4.22.2 focus scheduler", () => {
  assert.equal(WORKSPACE_SEARCH_AUTOFOCUS, true);
  const html = renderPicker();
  assert.match(html, /autofocus/i);
  let n = 0;
  const input = { focus() { n += 1; } };
  const raf = globalThis.requestAnimationFrame;
  const cancel = globalThis.cancelAnimationFrame;
  globalThis.requestAnimationFrame = (fn) => { fn(); return 1; };
  globalThis.cancelAnimationFrame = () => {};
  try {
    const stop = scheduleWorkspaceSearchFocus(input);
    stop();
    assert.ok(n >= 1);
  } finally {
    if (raf) globalThis.requestAnimationFrame = raf;
    else delete globalThis.requestAnimationFrame;
    if (cancel) globalThis.cancelAnimationFrame = cancel;
    else delete globalThis.cancelAnimationFrame;
  }
});

test("tree keyboard expands, collapses, and moves", () => {
  assert.equal(applyTreeKey("ArrowDown", 0, 3), 1);
  assert.equal(applyTreeKey("ArrowUp", 0, 3), 0);
  assert.equal(applyTreeKey("Enter", 1, 3), "expand");
  assert.equal(applyTreeKey("ArrowRight", 1, 3), "expand");
  assert.equal(applyTreeKey("ArrowLeft", 1, 3), "collapse");
  const rows = [
    { path: "/a", name: "a", depth: 0, expanded: true, kind: "folder" },
    { path: "/a/b", name: "b", depth: 1, expanded: false, kind: "folder" },
  ];
  assert.equal(parentRowIndex(rows, 1), 0);
});

test("native folder dialog path is gone from the dialog", () => {
  assert.doesNotMatch(launchSource, /\/workspaces\/choose/);
  assert.match(launchSource, /\/workspaces\/browse/);
  const html = renderPicker();
  assert.match(html, /浏览其他文件夹/);
});

test("truncated listings surface a visible hint", () => {
  const html = renderToStaticMarkup(
    createElement(FolderTree, {
      rows: sampleRows,
      activeIndex: 0,
      truncated: true,
      onHighlight() {},
      onToggle() {},
    }),
  );
  assert.match(html, new RegExp(TREE_TRUNCATED_HINT));
  const browsing = renderPicker({ browsing: true, rows: sampleRows, truncated: true });
  assert.match(browsing, new RegExp(TREE_TRUNCATED_HINT));
});

test("tree row click expands and the chevron rule does not freeze the label", () => {
  const html = renderToStaticMarkup(
    createElement(FolderTree, {
      rows: sampleRows,
      activeIndex: 0,
      onHighlight() {},
      onToggle() {},
    }),
  );
  assert.match(html, /workspace-folder-label/);
  assert.match(studioCss, /\.workspace-matches \.workspace-folder-row > \.workspace-folder-chevron/);
  assert.doesNotMatch(studioCss, /\.workspace-matches \.workspace-folder-row > span\s*\{/);
  assert.match(studioCss, /\.workspace-folder-label[\s\S]*flex:\s*1/);
  const treeSource = readFileSync(new URL("../src/folder-tree.ts", import.meta.url), "utf8");
  assert.match(treeSource, /onHighlight\(index\);\s*onToggle\(row\.path\)/);
});


test("a keydown from a cached tree row invokes the bubbling handler exactly once", () => {
  let expanded = [];
  const root = FolderTree({ rows: sampleRows, activeIndex: 0,
    onHighlight() {}, onToggle() {},
    onKeyDown(event) { event.preventDefault(); expanded = toggleExpanded(expanded, "/cached"); },
  });
  const row = root.props.children[0];
  const event = { key: "ArrowRight", preventDefault() {} };
  // Replay React's target -> parent bubbling against the rendered handlers.
  row.props.onKeyDown?.(event);
  root.props.onKeyDown?.(event);
  assert.deepEqual(expanded, ["/cached"]);
});

// --- Executable tests: the following tests compile and run the real source,
// so hollowing out a handler (keeping the shell, changing the behavior) fails.

function sliceFunction(source, signature) {
  const start = source.indexOf(signature);
  assert.ok(start >= 0, `${signature} must exist in the source`);
  // The parameter list may carry inline object types with braces; match the
  // parameter parentheses first, then the function body braces.
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
  let depth = 0;
  for (let index = bodyOpen; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    else if (source[index] === "}") {
      depth -= 1;
      if (!depth) return source.slice(start, index + 1);
    }
  }
  throw new Error(`unbalanced braces after ${signature}`);
}

function cssBlock(css, marker) {
  const start = css.indexOf(marker);
  assert.ok(start >= 0, `CSS rule ${marker} must exist`);
  const open = css.indexOf("{", start);
  let depth = 0;
  for (let index = open; index < css.length; index += 1) {
    if (css[index] === "{") depth += 1;
    else if (css[index] === "}") {
      depth -= 1;
      if (!depth) return css.slice(open + 1, index);
    }
  }
  throw new Error(`unbalanced braces after ${marker}`);
}

test("tree keydown handler in LaunchOptions executes the real expand/collapse semantics", () => {
  const fnSource = sliceFunction(launchSource, "function onTreeKey");
  const code = esbuild.transformSync(`result = (${fnSource});`, { loader: "ts" }).code;
  const rows = [
    { path: "/a", name: "a", depth: 0, expanded: true, kind: "folder" },
    { path: "/a/b", name: "b", depth: 1, expanded: false, kind: "folder" },
  ];
  const harness = (activeIndex, expanded) => {
    const calls = [];
    const context = {
      result: null,
      applyTreeKey,
      toggleExpanded,
      parentRowIndex,
      rows,
      activeIndex,
      expanded,
      toggle: (path) => calls.push(["toggle", path]),
      setExpanded: (next) => calls.push(["setExpanded", next]),
      setActiveIndex: (next) => calls.push(["setActiveIndex", next]),
    };
    vm.runInNewContext(code, context);
    return { onTreeKey: context.result, calls };
  };
  // Repeated ArrowRight on an expanded row must stay expanded (no toggle).
  const repeat = harness(0, ["/a"]);
  repeat.onTreeKey({ key: "ArrowRight", preventDefault() {} });
  assert.deepEqual(repeat.calls, []);
  // Enter toggles even when expanded; ArrowRight expands a collapsed row.
  const enter = harness(0, ["/a"]);
  enter.onTreeKey({ key: "Enter", preventDefault() {} });
  assert.deepEqual(enter.calls, [["toggle", "/a"]]);
  const expand = harness(1, ["/a"]);
  expand.onTreeKey({ key: "ArrowRight", preventDefault() {} });
  assert.deepEqual(expand.calls, [["toggle", "/a/b"]]);
  // ArrowLeft collapses an expanded row in place.
  const collapse = harness(0, ["/a"]);
  collapse.onTreeKey({ key: "ArrowLeft", preventDefault() {} });
  assert.deepEqual(collapse.calls, [["setExpanded", []]]);
  // ArrowLeft on a collapsed child jumps to the parent row.
  const jump = harness(1, ["/a"]);
  jump.onTreeKey({ key: "ArrowLeft", preventDefault() {} });
  assert.deepEqual(jump.calls, [["setActiveIndex", 0]]);
});

test("chevron renders, stops bubbling, and toggles the row", () => {
  let highlighted = -1;
  let toggled = "";
  const tree = FolderTree({
    rows: sampleRows,
    activeIndex: 0,
    onHighlight: (index) => { highlighted = index; },
    onToggle: (path) => { toggled = path; },
  });
  const row = tree.props.children[0];
  const chevron = row.props.children[0];
  assert.equal(chevron.props.className, "workspace-folder-chevron");
  let prevented = false;
  let stopped = false;
  chevron.props.onClick({
    preventDefault() { prevented = true; },
    stopPropagation() { stopped = true; },
  });
  assert.equal(prevented, true);
  assert.equal(stopped, true);
  assert.equal(highlighted, 0);
  assert.equal(toggled, "/Users/xin/Documents");
  const html = renderToStaticMarkup(
    createElement(FolderTree, { rows: sampleRows, activeIndex: 0, onHighlight() {}, onToggle() {} }),
  );
  assert.match(html, /workspace-folder-chevron/);
});

test("aria-expanded follows each row's real expanded state", () => {
  const html = renderToStaticMarkup(
    createElement(FolderTree, { rows: sampleRows, activeIndex: 0, onHighlight() {}, onToggle() {} }),
  );
  const states = [...html.matchAll(/aria-expanded="(true|false)"/g)].map((match) => match[1]);
  // Documents is expanded; its child Projects and Downloads are not.
  assert.deepEqual(states, ["true", "false", "false"]);
});

test("small-screen media rule keeps the scroll box and one-line paths", () => {
  const block = cssBlock(studioCss, "@media (max-width: 390px)");
  assert.match(block, /\.workspace-matches\s*\{\s*max-height:\s*min\(48dvh,\s*280px\)/);
  assert.match(block, /\.workspace-folder-label small\s*\{[^}]*white-space:\s*nowrap/);
  assert.match(block, /\.workspace-folder-label small\s*\{[^}]*text-overflow:\s*ellipsis/);
});

test("chevron keeps its 44px touch target", () => {
  const block = cssBlock(studioCss, ".workspace-matches .workspace-folder-row > .workspace-folder-chevron");
  assert.match(block, /min-width:\s*44px/);
  assert.match(block, /min-height:\s*44px/);
});

test("folder tree and rows keep their overflow guards", () => {
  const tree = cssBlock(studioCss, ".workspace-folder-tree");
  assert.match(tree, /min-width:\s*0/);
  assert.match(tree, /overflow-x:\s*hidden/);
  const row = cssBlock(studioCss, ".workspace-folder-row");
  assert.match(row, /min-width:\s*0/);
});

test("truncation hint follows the truncated level", () => {
  const rows = visibleRows(
    [
      { name: "a", path: "/a" },
      { name: "z", path: "/z" },
    ],
    ["/a"],
    { "/a": [{ name: "b", path: "/a/b" }] },
  );
  const html = renderToStaticMarkup(
    createElement(FolderTree, {
      rows,
      activeIndex: 0,
      truncatedPaths: ["/a"],
      onHighlight() {},
      onToggle() {},
    }),
  );
  const hints = html.match(/workspace-folder-truncated/g) || [];
  assert.equal(hints.length, 1);
  const hintAt = html.indexOf("workspace-folder-truncated");
  assert.ok(hintAt > html.indexOf("/a/b"), "hint renders after the truncated level's children");
  assert.ok(hintAt < html.indexOf("/z"), "hint renders before the next level, not at the bottom");
  // The root listing (empty path) still lands at the bottom of the tree.
  const root = renderToStaticMarkup(
    createElement(FolderTree, {
      rows,
      activeIndex: 0,
      truncatedPaths: [""],
      onHighlight() {},
      onToggle() {},
    }),
  );
  assert.ok(root.indexOf("workspace-folder-truncated") > root.indexOf("/z"));
  // LaunchOptions wires the per-path map instead of the any-level boolean.
  assert.match(launchSource, /truncatedPaths=\{truncatedPaths\}/);
  assert.match(launchSource, /Object\.keys\(truncatedAt\)\.filter/);
});


test("nested truncated levels stay distinct and collapsed children show no hint", () => {
  const roots = [{ name: "alpha", path: "/a" }, { name: "zeta", path: "/z" }];
  const children = { "/a": [{ name: "beta", path: "/a/b" }], "/a/b": [{ name: "child", path: "/a/b/c" }] };
  const render = (expanded) => renderToStaticMarkup(createElement(FolderTree, {
    rows: visibleRows(roots, expanded, children), activeIndex: 0,
    truncatedPaths: ["/a", "/a/b"], onHighlight() {}, onToggle() {},
  }));
  const nested = render(["/a", "/a/b"]);
  assert.equal((nested.match(/workspace-folder-truncated/g) || []).length, 2);
  assert.match(nested, /alpha：/);
  assert.match(nested, /beta：/);
  assert.ok(nested.indexOf("beta：") < nested.indexOf("alpha："));
  assert.equal((render(["/a"]).match(/workspace-folder-truncated/g) || []).length, 1);
  assert.doesNotMatch(render([]), /workspace-folder-truncated/);
});
