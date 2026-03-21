import type { ModelMeta } from '@/stores/app'

const FAULT_INJECTION_DEMO_MODEL_IDS = new Set([
  'demo/offline-strategy-agent',
  'demo/throttled-risk-agent',
])

const SHOWCASE_DEMO_MODEL_IDS = [
  'demo/claude-sonnet-4',
  'demo/gpt-4.1',
  'demo/gemini-2.5-pro',
  'demo/claude-haiku-3.5',
  'demo/mistral-large',
  'demo/deepseek-r1',
  'demo/qwen-max',
  'demo/glm-4.5',
]

const showcaseDemoOrder = new Map(
  SHOWCASE_DEMO_MODEL_IDS.map((id, index) => [id, index]),
)

export function isFaultInjectionDemoModel(modelId: string) {
  return FAULT_INJECTION_DEMO_MODEL_IDS.has(modelId)
}

export function isAutoPlayableModel(model: ModelMeta) {
  return !isFaultInjectionDemoModel(model.id)
}

export function filterAutoPlayableModels(models: ModelMeta[]) {
  return models.filter(isAutoPlayableModel)
}

export function preferLiveAutoModels(models: ModelMeta[]) {
  const safePool = filterAutoPlayableModels(models)
  const liveOnly = safePool.filter((model) => !model.id.startsWith('demo/'))
  if (liveOnly.length) return liveOnly
  return [...safePool].sort((left, right) => {
    const leftOrder = showcaseDemoOrder.get(left.id) ?? SHOWCASE_DEMO_MODEL_IDS.length
    const rightOrder = showcaseDemoOrder.get(right.id) ?? SHOWCASE_DEMO_MODEL_IDS.length
    if (leftOrder !== rightOrder) return leftOrder - rightOrder
    return right.tier - left.tier || left.priceInput - right.priceInput
  })
}

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
    .filter((model) => !participating.has(model.id))
    .sort((left, right) => right.tier - left.tier || left.priceInput - right.priceInput)

  if (nonParticipants.length) {
    return { modelId: nonParticipants[0].id, isSelfEval: false }
  }

  const participants = participantIds
    .map((id) => allModels.find((model) => model.id === id))
    .filter((model): model is ModelMeta => !!model)
    .sort((left, right) => right.tier - left.tier || left.priceInput - right.priceInput)

  return {
    modelId: participants[0]?.id ?? participantIds[0],
    isSelfEval: true,
  }
}
