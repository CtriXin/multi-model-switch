import type { Model, Preset, Service } from "./types";

export function modelKey(preset: Preset) {
  return preset.modelId.startsWith(preset.providerId + ":")
    ? preset.modelId.slice(preset.providerId.length + 1)
    : preset.name;
}

/** Friendly channel name for daily UI. Never prefer a raw provider slug when a display name exists. */
export function channelLabel(
  preset: Pick<Preset, "channel" | "providerId"> | undefined,
  models: Model[] = [],
  services: Service[] = [],
) {
  if (!preset) return "";
  const id = preset.channel || preset.providerId;
  const service = services.find((item) => item.id === id || item.id === preset.providerId);
  if (service?.name) return service.name;
  const model = models.find(
    (item) => item.providerId === id || item.providerId === preset.providerId,
  );
  if (model?.providerName) return model.providerName;
  return id;
}

export function availableRoutesForModel(presets: Preset[], preset: Preset | undefined) {
  if (!preset) return [];
  const key = modelKey(preset);
  return presets.filter((item) => modelKey(item) === key && item.available && item.harness === preset.harness);
}

export function availableHarnesses(presets: Preset[], preset: Preset | undefined) {
  if (!preset) return [];
  const key = modelKey(preset);
  return [...new Set(presets.filter((item) => modelKey(item) === key && item.available).map((item) => item.harness))];
}

export function siblingHarnessPreset(presets: Preset[], preset: Preset | undefined, harness: string) {
  if (!preset) return undefined;
  return presets.find((item) => item.available && item.harness === harness && item.modelId === preset.modelId && item.providerId === preset.providerId)
    || presets.find((item) => item.available && item.harness === harness && modelKey(item) === modelKey(preset));
}

/** Keep the explorer's existing preference order; reselecting a model keeps its current route. */
export function selectModelRoute(
  routes: Preset[],
  favorites: string[],
  preferences: Record<string, { preferred?: boolean }>,
  currentId = "",
) {
  return routes.find(p => p.available && p.id === currentId)
    || routes.find(p => p.available && preferences[p.id]?.preferred)
    || routes.find(p => p.available && favorites.includes(p.modelId))
    || routes.find(p => p.available)
    || routes[0];
}
