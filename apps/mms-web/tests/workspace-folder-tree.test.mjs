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
  toggleExpanded,
  visibleRows,
  WORKSPACE_SEARCH_AUTOFOCUS,
} from "../src/folder-tree.ts";

const launchSource = readFileSync(new URL("../src/LaunchOptions.tsx", import.meta.url), "utf8");

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

test("search field keeps autoFocus", () => {
  assert.equal(WORKSPACE_SEARCH_AUTOFOCUS, true);
  assert.match(launchSource, /autoFocus=\{WORKSPACE_SEARCH_AUTOFOCUS\}/);
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
  assert.match(launchSource, /浏览其他文件夹/);
});
