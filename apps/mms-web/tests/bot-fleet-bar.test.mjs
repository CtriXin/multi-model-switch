import test from "node:test";
import assert from "node:assert/strict";
import {
  availableFleetFamilies,
  compactModelLabel,
  familyChipLabel,
  fleetPreviewLabel,
  normalizeFleetPolicy,
  modelsForFamily,
} from "../src/bot-fleet.ts";

test("normalizeFleetPolicy defaults to two cheap families and keeps pinned families", () => {
  assert.deepEqual(normalizeFleetPolicy(), {
    enabled: true,
    intensity: "opinions",
    maxFamilies: 2,
    families: [],
    models: {},
    hintShown: false,
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

test("unavailable remembered IDs stay visibly invalid instead of matching another model name", () => {
  const presets = [{ id: "replacement", name: "old-id", harness: "pi", available: true, family: "Kimi" }];
  const policy = normalizeFleetPolicy({ families: ["Kimi", "GPT"], models: { Kimi: "old-id" } });
  assert.equal(familyChipLabel("Kimi", policy, presets), "Kimi（已失效）");
  assert.equal(familyChipLabel("GPT", policy, presets), "GPT（已失效）");
});

test("same-name presets keep their distinct selectable IDs", () => {
  const presets = ["provider-a", "provider-b"].map((id) => ({ id, name: "k3", harness: "pi", available: true, family: "Kimi" }));
  assert.equal(modelsForFamily(presets, "Kimi").length, 2);
  const policy = normalizeFleetPolicy({ models: { Kimi: "provider-b" } });
  assert.equal(familyChipLabel("Kimi", policy, presets), "k3");
});

test("availableFleetFamilies skips unavailable and Other", () => {
  const names = availableFleetFamilies([
    { id: "a", name: "glm-5-turbo", harness: "pi", available: true, family: "GLM" },
    { id: "b", name: "mystery", harness: "pi", available: true },
    { id: "c", name: "k3", harness: "pi", available: false, family: "Kimi" },
    { id: "d", name: "kimi-for-coding-highspeed", harness: "pi", available: true, family: "Kimi" },
  ]);
  assert.deepEqual(names, ["GLM", "Kimi"]);
});

test("fleetPreviewLabel tells the user what the next click will do", () => {
  const policy = normalizeFleetPolicy();
  assert.match(fleetPreviewLabel(policy, ["GLM", "Kimi"]), /发出去会再问 2 家/);
  assert.equal(fleetPreviewLabel({ ...policy, enabled: false }, ["GLM", "Kimi"]), "");
  assert.match(fleetPreviewLabel({ ...policy, families: ["Kimi", "GLM"] }, ["Kimi", "GLM"]), /再问 2 家/);
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
