import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const srcDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
const source = fs.readFileSync(path.join(srcDir, "RemoteAccess.tsx"), "utf-8");
const css = fs.readFileSync(path.join(srcDir, "remote-access.css"), "utf-8");

function enabledBlock() {
  const start = source.indexOf("{state?.enabled && (");
  const end = source.indexOf("className=\"remote-away\"");
  assert.ok(start >= 0, "the switch still gates the expanded panel");
  assert.ok(end > start, "going-out sits inside the enabled panel");
  return { start, end, before: source.slice(0, start), inside: source.slice(start) };
}

test("going out is a sub-option of the open switch, not a sibling row", () => {
  const { start, before, inside } = enabledBlock();
  assert.doesNotMatch(before, /出门也要用/);
  assert.doesNotMatch(before, /交给 Pilot 配/);
  assert.match(inside, /className="remote-access"/);
  assert.match(inside, /出门也要用/);
  assert.match(inside, /交给 Pilot 配/);
  assert.equal([...inside.matchAll(/交给 Pilot 配/g)].length, 1);
  const away = source.indexOf("出门也要用");
  const sibling = source.lastIndexOf("<div className=\"preference-row\">", away);
  assert.ok(sibling < start, "the going-out heading is not in a preference-row");
});

test("the closed switch says every path starts here", () => {
  assert.match(
    source,
    /已关闭 —— 只有这台电脑能打开。同一网络、虚拟网、或你自己的公网通道，都从这里开。/,
  );
});

test("an overlay address gets a one-line hint, not a third switch", () => {
  assert.match(source, /way\.kind === "address" && way\.detail\.includes\("虚拟网"\)/);
  assert.match(source, /列表里的虚拟网地址，对面设备装了同一个网就能用，不必再配公网通道。/);
  assert.doesNotMatch(source, /Tailscale 开关/);
});

test("the wizard receives names and listen addresses the page already has", () => {
  assert.match(source, /tunnelTask\(state\.port,\s*\{\s*hostnames: state\.hostnames,\s*listening: state\.listening,/);
});

test("remembered names change the going-out copy", () => {
  assert.match(source, /state\.hostnames\.length > 0/);
  assert.match(source, /已经记住公网名字/);
  assert.match(source, /有现成名字就贴进上面的隧道域名/);
});

test("going-out styles reuse tokens and do not add hex", () => {
  assert.match(css, /\.remote-away\s*\{/);
  const added = css.slice(css.indexOf(".remote-away"));
  assert.doesNotMatch(added, /#[0-9a-fA-F]{3,8}/);
});
