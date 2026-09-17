import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
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
