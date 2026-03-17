import type { ModelMeta } from '@/stores/app'

/**
 * Pick a neutral (non-participating) model for evaluation / synthesis / rollup.
 * Prefers the highest-tier model that is NOT in the participant list.
 * Fallback: highest-tier participant (flagged as isSelfEval).
 */
export function pickNeutralModel(
  participantIds: string[],
  allModels: ModelMeta[],
): { modelId: string; isSelfEval: boolean } {
  const participating = new Set(participantIds)

  const nonParticipants = allModels
    .filter((m) => !participating.has(m.id))
    .sort((a, b) => b.tier - a.tier || a.priceInput - b.priceInput)

  if (nonParticipants.length) {
    return { modelId: nonParticipants[0].id, isSelfEval: false }
  }

  // Fallback: pick highest-tier participant
  const participants = participantIds
    .map((id) => allModels.find((m) => m.id === id))
    .filter((m): m is ModelMeta => !!m)
    .sort((a, b) => b.tier - a.tier || a.priceInput - b.priceInput)

  return {
    modelId: participants[0]?.id ?? participantIds[0],
    isSelfEval: true,
  }
}
