import test from "node:test";
import assert from "node:assert/strict";
import { applyPersona, createIdentity, identityMatches } from "../src/work-identities.ts";

test("applyPersona prepends a visible identity header only when persona exists", () => {
  const identity = createIdentity({
    name: "写代码",
    presetId: "web:pi:tokyo:kimi",
    effort: "high",
    persona: "只改相关文件，先给结论。",
  });
  assert.ok(identity);
  assert.equal(
    applyPersona("修这个 bug", identity),
    "（工作身份：写代码）\n只改相关文件，先给结论。\n\n修这个 bug",
  );
  assert.equal(applyPersona("修这个 bug", { ...identity, persona: "  " }), "修这个 bug");
  assert.equal(applyPersona("修这个 bug", undefined), "修这个 bug");
});

test("identityMatches requires both preset and effort", () => {
  const identity = createIdentity({
    name: "写代码",
    presetId: "a",
    effort: "low",
    persona: "",
  });
  assert.equal(identityMatches(identity, "a", "low"), true);
  assert.equal(identityMatches(identity, "a", "high"), false);
  assert.equal(identityMatches(identity, "b", "low"), false);
  assert.equal(identityMatches(undefined, "a", "low"), false);
});

test("createIdentity rejects empty names and trims persona", () => {
  assert.equal(createIdentity({ name: "  ", presetId: "a", effort: "", persona: "x" }), null);
  const identity = createIdentity({
    name: "  生活管家  ",
    presetId: "a",
    effort: "",
    persona: "  直奔主题  ",
  });
  assert.equal(identity?.name, "生活管家");
  assert.equal(identity?.persona, "直奔主题");
});
