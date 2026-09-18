import type { Preset } from "./types";

export function modelKey(preset: Preset) {
  return preset.modelId.startsWith(preset.providerId + ":")
    ? preset.modelId.slice(preset.providerId.length + 1)
    : preset.name;
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
