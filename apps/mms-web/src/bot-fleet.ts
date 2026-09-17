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
  const byId = new Map<string, Preset>();
  for (const preset of presets) {
    if (preset.harness !== "pi" || !preset.available) continue;
    if (familyFromPreset(preset) !== family) continue;
    byId.set(preset.id, preset);
  }
  return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
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
  if (!remembered) return availableFleetFamilies(presets).includes(family) ? family : `${family}（已失效）`;
  const options = modelsForFamily(presets, family);
  const match = options.find((item) => item.id === remembered);
  return match ? compactModelLabel(match.name) : `${family}（已失效）`;
}

export function fleetPreviewLabel(policy: BotFleetPolicy, families: string[], presets: Preset[] = []): string {
  if (!policy.enabled) return "";
  if (policy.families.length) {
    const names = policy.families.map((family) => familyChipLabel(family, policy, presets));
    return `再问 ${names.length} 家：${names.join("、")} · ${policy.intensity === "intense" ? "问仔细" : "听听"}`;
  }
  const auto = families.slice(0, policy.maxFamilies);
  if (auto.length < 2) return "凑不齐两家，我自己看，不当成多方";
  return `发出去会再问 ${policy.maxFamilies} 家${policy.intensity === "intense" ? "，问仔细" : ""}`;
}
