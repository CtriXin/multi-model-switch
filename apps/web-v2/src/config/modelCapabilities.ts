import type { ModelCapabilitySource } from '@/stores/app'

export interface ResolvedModelCapabilities {
  supportsVision: boolean
  supportsNativeWebSearch: boolean
  supportsTools: boolean
  capabilitySource: ModelCapabilitySource
  capabilityVerifiedAt: string | null
}

interface ModelCapabilityOverride {
  supportsVision?: boolean
  supportsNativeWebSearch?: boolean
  supportsTools?: boolean
  capabilitySource?: ModelCapabilitySource
  capabilityVerifiedAt?: string | null
}

interface ResolveModelCapabilitiesInput {
  compoundId: string
  rawModelId: string
  providerId: string
  supportsVision: boolean
}

// Placeholder registry for future manual capability curation.
// Keep it empty until there is a verified source of truth.
const MODEL_CAPABILITY_OVERRIDES: Record<string, ModelCapabilityOverride> = {}

export function resolveModelCapabilities(
  input: ResolveModelCapabilitiesInput,
): ResolvedModelCapabilities {
  const override = getModelCapabilityOverride(input)
  if (!override) {
    return {
      supportsVision: input.supportsVision,
      supportsNativeWebSearch: false,
      supportsTools: false,
      capabilitySource: input.supportsVision ? 'heuristic' : 'default',
      capabilityVerifiedAt: null,
    }
  }

  return {
    supportsVision: override.supportsVision ?? input.supportsVision,
    supportsNativeWebSearch: override.supportsNativeWebSearch ?? false,
    supportsTools: override.supportsTools ?? false,
    capabilitySource: override.capabilitySource ?? 'registry',
    capabilityVerifiedAt: override.capabilityVerifiedAt ?? null,
  }
}

function getModelCapabilityOverride(
  input: ResolveModelCapabilitiesInput,
): ModelCapabilityOverride | undefined {
  return (
    MODEL_CAPABILITY_OVERRIDES[input.compoundId]
    ?? MODEL_CAPABILITY_OVERRIDES[`${input.providerId}/${input.rawModelId}`]
    ?? MODEL_CAPABILITY_OVERRIDES[input.rawModelId]
  )
}
