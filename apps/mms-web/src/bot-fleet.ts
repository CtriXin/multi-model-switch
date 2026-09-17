import type { Preset } from "./types";

export type FleetIntensity = "opinions" | "intense";
export interface BotFleetPolicy {
  enabled: boolean;
  intensity: FleetIntensity;
  maxFamilies: number;
  families: string[];
  models: Record<string, string>;
  hintShown: boolean;
}

export const DEFAULT_FLEET_POLICY: BotFleetPolicy = {
  enabled: true,
  intensity: "opinions",
  maxFamilies: 2,
  families: [],
  models: {},
  hintShown: false,
};

export function normalizeFleetPolicy(raw?: Partial<BotFleetPolicy> | null): BotFleetPolicy {
  const intensity = raw?.intensity === "intense" ? "intense" : "opinions";
  const max = Math.min(12, Math.max(1, Number(raw?.maxFamilies) || 2));
  const families: string[] = [];
  const seen = new Set<string>();
  for (const name of raw?.families || []) {
    const trimmed = String(name || "").trim();
    if (!trimmed || seen.has(trimmed) || trimmed === "Other") continue;
    seen.add(trimmed);
    families.push(trimmed);
    if (families.length >= 12) break;
  }
  const models: Record<string, string> = {};
  const rawModels = raw?.models && typeof raw.models === "object" ? raw.models : {};
  for (const [family, presetId] of Object.entries(rawModels)) {
    const key = String(family || "").trim();
    const value = String(presetId || "").trim();
    if (!key || !value || key === "Other") continue;
    models[key] = value.slice(0, 500);
  }
  return {
    enabled: raw?.enabled !== false,
    intensity,
    maxFamilies: families.length ? Math.max(max, families.length) : max,
    families,
    models,
    hintShown: raw?.hintShown === true,
  };
}

export function familyFromPreset(preset: Preset): string {
  const given = String(preset.family || "").trim();
  if (given && given !== "Other" && given !== "其他") return given;
  return "Other";
}

export function availableFleetFamilies(presets: Preset[]): string[] {
  const names = new Set<string>();
  for (const preset of presets) {
    if (preset.harness !== "pi" || !preset.available) continue;
    const family = familyFromPreset(preset);
    if (family !== "Other") names.add(family);
  }
  return [...names].sort((a, b) => a.localeCompare(b));
}

export function modelsForFamily(presets: Preset[], family: string): Preset[] {
  const byName = new Map<string, Preset>();
  for (const preset of presets) {
    if (preset.harness !== "pi" || !preset.available) continue;
    if (familyFromPreset(preset) !== family) continue;
    const key = String(preset.name || preset.modelName || preset.id);
    const current = byName.get(key);
    if (!current) {
      byName.set(key, preset);
    }
  }
  return [...byName.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export function compactModelLabel(name: string): string {
  return String(name || "")
    .trim()
    .replace(/\s+/g, "")
    .replace(/-thinking$/i, "")
    .replace(/\(high\)$/i, "");
}

export function familyChipLabel(
  family: string,
  policy: BotFleetPolicy,
  presets: Preset[],
): string {
  const remembered = policy.models[family];
  if (!remembered) return family;
  const options = modelsForFamily(presets, family);
  const match =
    options.find((item) => item.id === remembered) ||
    options.find((item) => item.name === remembered);
  return match ? compactModelLabel(match.name) : family;
}

export function fleetPreviewLabel(policy: BotFleetPolicy, families: string[], presets: Preset[] = []): string {
  if (!policy.enabled) return "";
  if (policy.families.length) {
    const names = policy.families.map((family) => familyChipLabel(family, policy, presets));
    return `场外 ${names.length} 家：${names.join("、")} · ${policy.intensity === "intense" ? "认真" : "轻量"}`;
  }
  const auto = families.slice(0, policy.maxFamilies);
  if (auto.length < 2) return "场外凑不够两家，会自己看并标明不是多方";
  return `发送即问场外 · 默认 ${policy.maxFamilies} 家${policy.intensity === "intense" ? "认真" : "轻量"}`;
}
