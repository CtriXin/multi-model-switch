// Execute the actual dialog -> body -> tree -> keyboard callback chain.
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const app = fileURLToPath(new URL("../", import.meta.url));
const requireFromApp = createRequire(path.join(app, "package.json"));
const React = requireFromApp("react");
const esbuild = requireFromApp("esbuild");
const tree = await import(pathToFileURL(path.join(app, "src/folder-tree.ts")));
test("actual folder dialog forwards keyboard and truncation through its rendered tree", () => {
const roots = [{ name: "a", path: "/a" }];
const children = {
  "/a": [{ name: "b", path: "/a/b" }],
  "/a/b": [{ name: "c", path: "/a/b/c" }],
};

// These slots match WorkspaceDialog, not ModelPicker. Effects intentionally do
// not run: the test uses cached listings and does not need DOM, network or ports.
const states = ["", [], 0, false, "", "", true, roots, children,
  ["/a", "/a/b"], 0, { "/a": true, "/a/b": true }];
let cursor = 0;
let changes = [];
const hooks = {
  useState(initial) {
    const index = cursor++;
    return [states[index] ?? initial, next => {
      states[index] = typeof next === "function" ? next(states[index]) : next;
      changes.push([index, states[index]]);
    }];
  },
  useRef: initial => ({ current: initial }),
  useEffect() {},
};
const mod = { exports: {} };
vm.runInNewContext(esbuild.transformSync(
  fs.readFileSync(path.join(app, "src/LaunchOptions.tsx"), "utf8"),
  { loader: "tsx", format: "cjs" },
).code, {
  module: mod, exports: mod.exports, React, AbortController,
  require: name => name === "react" ? hooks
    : name === "./folder-tree" ? tree
    : name === "./components" ? { Dialog: "Dialog" } : {},
});
const nodes = value => !value || typeof value !== "object" ? []
  : Array.isArray(value) ? value.flatMap(nodes)
    : [value, ...nodes(value.props?.children)];
function mounted() {
  cursor = 0;
  const dialog = mod.exports.WorkspaceDialog({ close() {} });
  const body = nodes(dialog).find(node => node.type === tree.WorkspaceDialogBody);
  assert(body, "WorkspaceDialog must mount the real WorkspaceDialogBody");
  const actualBody = tree.WorkspaceDialogBody(body.props);
  const renderedTree = nodes(actualBody).find(node => node.type === tree.FolderTree);
  assert(renderedTree, "WorkspaceDialogBody must mount the real FolderTree");
  return { body, root: tree.FolderTree(renderedTree.props) };
}

let view = mounted();
assert.deepEqual(JSON.parse(JSON.stringify(view.body.props.truncatedPaths)), ["/a", "/a/b"]);
view.root.props.onKeyDown({ key: "ArrowRight", preventDefault() {} });
assert.equal(changes.length, 0, "repeat ArrowRight must keep an expanded parent");
view.root.props.onKeyDown({ key: "ArrowLeft", preventDefault() {} });
assert.deepEqual(states[9], ["/a/b"], "actual forwarded callback must collapse parent");

states[9] = ["/a", "/a/b"];
states[10] = 2;
changes = [];
view = mounted();
view.root.props.onKeyDown({ key: "ArrowLeft", preventDefault() {} });
assert.equal(states[10], 1, "actual forwarded callback must jump to parent");
});
