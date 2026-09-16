import test from "node:test";
import assert from "node:assert/strict";
import { tunnelTask } from "../../apps/mms-web/src/tunnel-task.ts";

/** The properties that were measured against real models. Seven models across
 *  seven vendors each asked only the two questions and ran no tools with this
 *  shape; the shape is what these tests hold in place. */
const text = tunnelTask(8815);
const lines = text.split("\n");
const nonEmpty = lines.filter((line) => line.trim());

test("the one instruction is the first thing an agent reads", () => {
  // It used to sit eight lines down, past the goal and the background, which
  // is after a model reading top-down has already decided what to do.
  assert.match(nonEmpty[0], /只做一件事|不要执行/);
  const stop = text.indexOf("不要执行任何命令");
  const firstBranch = text.indexOf("A. 什么都没有");
  assert.ok(stop >= 0 && stop < firstBranch, "the constraint precedes the options");
});

test("both questions come before the background, and are the only ask", () => {
  const separator = text.indexOf("以下是背景");
  assert.ok(separator > 0, "background is fenced off");
  const head = text.slice(0, separator);
  assert.match(head, /有没有域名/);
  assert.match(head, /有没有自己的服务器/);
  // The options must not be in the part read before the questions are asked.
  assert.ok(!head.includes("cloudflared"));
});

test("it restates the constraint at the end", () => {
  assert.match(nonEmpty[nonEmpty.length - 1], /不要动手|只问那两个问题/);
});

test("someone with no domain and no account has a branch", () => {
  const branch = text.slice(text.indexOf("A. 什么都没有"), text.indexOf("B. "));
  assert.match(branch, /不需要账号/);
  assert.match(branch, /不需要域名/);
  // The port has to be the one this Pilot is on, or the command is wrong.
  assert.match(branch, /cloudflared tunnel --url http:\/\/127\.0\.0\.1:8815/);
  assert.match(branch, /地址都会变/, "its cost is stated, not hidden");
});

test("every branch is offered, so the answer does not depend on being lucky", () => {
  for (const letter of ["A.", "B.", "C.", "D."]) {
    assert.ok(text.includes(letter), `${letter} missing`);
  }
  assert.match(text, /Tailscale/);
});

test("nothing consequential happens without asking", () => {
  assert.match(text, /改 DNS/);
  assert.match(text, /每一步都要先问我/);
});

test("it points at the field that accepts a tunnel's own hostname", () => {
  // Without this the quick-tunnel branch ends in a 403 the person cannot fix.
  assert.match(text, /隧道域名/);
  assert.match(text, /不用重启/);
});

test("the port is interpolated, not hardcoded", () => {
  assert.ok(tunnelTask(9999).includes("127.0.0.1:9999"));
  assert.ok(!tunnelTask(9999).includes("127.0.0.1:8815"));
});
