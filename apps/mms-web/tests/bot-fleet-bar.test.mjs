import test from "node:test";
import assert from "node:assert/strict";
import {
  availableFleetFamilies,
  compactModelLabel,
  familyChipLabel,
  fleetPreviewLabel,
  normalizeFleetPolicy,
} from "../src/bot-fleet.ts";

test("normalizeFleetPolicy defaults to two cheap families and keeps pinned families", () => {
  assert.deepEqual(normalizeFleetPolicy(), {
    enabled: true,
    intensity: "opinions",
    maxFamilies: 2,
    families: [],
    models: {},
  });
  assert.equal(normalizeFleetPolicy({ enabled: false, maxFamilies: 9 }).enabled, false);
  assert.equal(normalizeFleetPolicy({ maxFamilies: 9 }).maxFamilies, 9);
  assert.deepEqual(normalizeFleetPolicy({ families: ["Kimi", "Kimi", "GLM", "Qwen", "Grok"] }).families, [
    "Kimi",
    "GLM",
    "Qwen",
    "Grok",
  ]);
});

test("availableFleetFamilies skips unavailable and Other", () => {
  const names = availableFleetFamilies([
    { id: "a", name: "glm-5-turbo", harness: "pi", available: true, family: "GLM" },
    { id: "b", name: "mystery", harness: "pi", available: true },
    { id: "c", name: "k3", harness: "pi", available: false, family: "Kimi" },
    { id: "d", name: "kimi-for-coding-highspeed", harness: "pi", available: true },
  ]);
  assert.deepEqual(names, ["GLM", "Kimi"]);
});

test("fleetPreviewLabel tells the user what the next click will do", () => {
  const policy = normalizeFleetPolicy();
  assert.match(fleetPreviewLabel(policy, ["GLM", "Kimi"]), /默认 2 家/);
  assert.match(fleetPreviewLabel({ ...policy, enabled: false }, ["GLM", "Kimi"]), /已关闭/);
  assert.match(fleetPreviewLabel({ ...policy, families: ["Kimi", "GLM"] }, ["Kimi", "GLM"]), /指定/);
});

test("remembered model becomes the chip label", () => {
  const presets = [
    { id: "web:pi:glm-5.3", name: "glm-5.3", harness: "pi", available: true, family: "GLM" },
    { id: "web:pi:glm-turbo", name: "glm-5-turbo", harness: "pi", available: true, family: "GLM" },
  ];
  const policy = normalizeFleetPolicy({
    families: ["GLM"],
    models: { GLM: "web:pi:glm-5.3" },
  });
  assert.equal(compactModelLabel("glm-5.3"), "glm-5.3");
  assert.equal(familyChipLabel("GLM", policy, presets), "glm-5.3");
  assert.match(fleetPreviewLabel(policy, ["GLM"], presets), /glm-5\.3/);
});
