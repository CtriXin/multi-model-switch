// T8h: a 5.x install that checks the stable channel finds 4.x, which the
// updater cannot install. The dialog used to answer "已是最新 4.x 稳定版" —
// a false statement about the machine in front of the user. The row text and
// the installer notice are rendered here for real; the wiring inside
// UpdateCenter.tsx is asserted at the bottom so neither export can be
// orphaned while the dialog keeps saying something else.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  isCrossLine,
  lineLabel,
  updateHeadline,
  UpdateStatusLine,
  UpgradeGuidanceNotice,
  versionLine,
} from "../src/update-channel.ts";

const source = readFileSync(new URL("../src/UpdateCenter.tsx", import.meta.url), "utf8");
const crossLineGuidance = JSON.parse(
  readFileSync(new URL("./fixtures/cross-line-guidance.json", import.meta.url), "utf8"),
);

function state(overrides = {}) {
  return {
    currentVersion: "4.23.0",
    channel: "stable",
    latest: { tag: "v4.23.0" },
    updateAvailable: false,
    checkedAt: 100000,
    error: "",
    checking: false,
    ...overrides,
  };
}

function renderLine(overrides) {
  return renderToStaticMarkup(createElement(UpdateStatusLine, { state: state(overrides) }));
}

test("version lines come from the tag major, not from string order", () => {
  assert.equal(versionLine("v5.1.0"), 5);
  assert.equal(versionLine("4.23.0"), 4);
  assert.equal(versionLine("5.1.0-rc1"), null);
  assert.equal(versionLine(""), null);
  assert.equal(versionLine(undefined), null);
  assert.equal(lineLabel("preview"), "5.x 预览版");
  assert.equal(lineLabel(undefined), "4.x 稳定版");
  assert.equal(isCrossLine(state({ currentVersion: "5.1.0", latest: { tag: "v4.23.0" } })), true);
  assert.equal(isCrossLine(state({ currentVersion: "4.23.0", latest: { tag: "v4.23.0" } })), false);
});

test("a 5.x install checking the stable channel is not told it is up to date", () => {
  const html = renderLine({ currentVersion: "5.1.0", latest: { tag: "v4.23.0" } });
  assert.doesNotMatch(html, /已是最新/);
  assert.match(html, /当前 v5\.1\.0 不在 4\.x 稳定版 线上/);
});

test("the cross-line state renders the installer command with its copy button", () => {
  const html = renderToStaticMarkup(
    createElement(UpgradeGuidanceNotice, { guidance: crossLineGuidance, copied: false, onCopy: () => {} }),
  );
  assert.ok(html.includes(crossLineGuidance.command), "the install command must be on screen");
  assert.match(html, /复制命令/);
  assert.match(html, /回到 4\.x 稳定线要用安装器/);
  assert.match(html, /mms-web/);
  const copied = renderToStaticMarkup(
    createElement(UpgradeGuidanceNotice, { guidance: crossLineGuidance, copied: true, onCopy: () => {} }),
  );
  assert.match(copied, /已复制/);
});

test("an update on the same line still reports an update, and up-to-date when it is", () => {
  assert.match(
    renderLine({ currentVersion: "4.22.4", latest: { tag: "v4.23.0" }, updateAvailable: true }),
    /发现新版 v4\.23\.0/,
  );
  assert.match(renderLine({ currentVersion: "4.23.0" }), /已是最新 4\.x 稳定版/);
});

test("without a readable tag the row does not claim the install is current", () => {
  assert.equal(updateHeadline(state({ currentVersion: "5.1.0", latest: {} })), "已检查，未发现可安装的更新");
  assert.equal(updateHeadline(state({ checkedAt: 0 })), "检查 4.x 稳定版");
  assert.equal(updateHeadline(state({ error: "网络不可用" })), "检查 4.x 稳定版");
  assert.equal(updateHeadline(state({ checking: true })), "正在检查…");
});

test("the dialog renders the shared row and notice instead of its own copy", () => {
  assert.match(source, /<UpdateStatusLine state=\{data\} \/>/);
  assert.match(source, /<UpgradeGuidanceNotice guidance=\{data\.upgradeGuidance\}/);
  assert.doesNotMatch(source, /已是最新/);
});
