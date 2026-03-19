import type {
  CanonEngineLiteState,
  CasePacket,
  CheckpointDimension,
  CheckpointHint,
  EvidenceFactPair,
  FinalReconstruction,
  RevealGate,
  ValidationResult,
} from './types'

const DEFAULT_EXPLANATION_LIMIT = 280

function toUniqueSet<T extends string>(values: T[]) {
  return new Set(values.filter(Boolean))
}

function clampUnit(value: number) {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(1, value))
}

function countIntersection(left: string[], right: string[]) {
  const rightSet = toUniqueSet(right)
  return left.filter((item) => rightSet.has(item)).length
}

function pairKey(pair: EvidenceFactPair) {
  return `${pair.evidenceId}::${pair.factId}`
}

function buildTimelineAccuracy(expected: string[], actual: string[]) {
  const submitted = actual.filter((factId) => expected.includes(factId))
  if (submitted.length < 2) return 0

  const indexMap = new Map(expected.map((factId, index) => [factId, index]))
  let totalPairs = 0
  let correctPairs = 0

  for (let left = 0; left < submitted.length; left += 1) {
    for (let right = left + 1; right < submitted.length; right += 1) {
      totalPairs += 1
      const leftIndex = indexMap.get(submitted[left]) ?? -1
      const rightIndex = indexMap.get(submitted[right]) ?? -1
      if (leftIndex >= 0 && rightIndex >= 0 && leftIndex < rightIndex) {
        correctPairs += 1
      }
    }
  }

  if (!totalPairs) return 0
  return clampUnit(correctPairs / totalPairs)
}

function buildEvidenceAccuracy(expected: EvidenceFactPair[], actual: EvidenceFactPair[]) {
  if (!actual.length) return 0
  const expectedKeys = new Set(expected.map(pairKey))
  const actualKeys = [...new Set(actual.map(pairKey))]
  const correctPairs = actualKeys.filter((key) => expectedKeys.has(key)).length
  return clampUnit(correctPairs / actualKeys.length)
}

function buildMissingDimensions(packet: CasePacket, state: CanonEngineLiteState): CheckpointDimension[] {
  const missing: CheckpointDimension[] = []
  const discoveredFacts = toUniqueSet(state.discoveredFactIds)
  const discoveredCoreFacts = packet.groundTruth.requiredFactIds.filter((factId) => discoveredFacts.has(factId))
  const discoveredCategories = new Set(
    packet.facts
      .filter((fact) => discoveredFacts.has(fact.id))
      .map((fact) => fact.category),
  )

  if (!discoveredCategories.has('timeline') || discoveredCoreFacts.length < 2) {
    missing.push('timeline')
  }

  if (!discoveredCategories.has('motive')) {
    missing.push('motive')
  }

  if (state.discoveredEvidenceIds.length < packet.validation.minimumEvidencePairs) {
    missing.push('evidence')
  }

  return missing
}

export function isRevealGateSatisfied(gate: RevealGate, state: CanonEngineLiteState) {
  if (gate.type === 'evidence_count') {
    return state.discoveredEvidenceIds.length >= (gate.threshold ?? 0)
  }

  const requiredFacts = gate.requiredFactIds ?? []
  if (!requiredFacts.length) return false
  const discoveredFacts = toUniqueSet(state.discoveredFactIds)
  return requiredFacts.every((factId) => discoveredFacts.has(factId))
}

export function getUnlockedFactIds(packet: CasePacket, state: CanonEngineLiteState) {
  const unlocked = new Set(packet.sceneZero.initialKnownFactIds)
  for (const factId of state.discoveredFactIds) unlocked.add(factId)

  for (const gate of packet.revealGates) {
    if (isRevealGateSatisfied(gate, state)) {
      for (const factId of gate.unlocksFactIds ?? []) unlocked.add(factId)
    }
  }

  return [...unlocked]
}

export function getUnlockedEvidenceIds(packet: CasePacket, state: CanonEngineLiteState) {
  const unlocked = new Set(state.discoveredEvidenceIds)
  for (const gate of packet.revealGates) {
    if (isRevealGateSatisfied(gate, state)) {
      for (const evidenceId of gate.unlocksEvidenceIds ?? []) unlocked.add(evidenceId)
    }
  }
  return [...unlocked]
}

export function getUnlockedWitnessIds(packet: CasePacket, state: CanonEngineLiteState) {
  const unlocked = new Set(state.unlockedWitnessIds)
  for (const lead of packet.sceneZero.startingLeads) {
    if (lead.type === 'witness') unlocked.add(lead.id)
  }
  for (const gate of packet.revealGates) {
    if (isRevealGateSatisfied(gate, state)) {
      for (const witnessId of gate.unlocksWitnessIds ?? []) unlocked.add(witnessId)
    }
  }
  return [...unlocked]
}

export function buildCheckpointHint(packet: CasePacket, state: CanonEngineLiteState): CheckpointHint {
  const missingDimensions = buildMissingDimensions(packet, state)
  const discoveredFacts = countIntersection(state.discoveredFactIds, packet.groundTruth.requiredFactIds)
  const readyForReconstruction =
    state.discoveredEvidenceIds.length >= packet.validation.checkpointThresholds.evidenceCount &&
    discoveredFacts >= packet.validation.checkpointThresholds.coreFactsDiscovered &&
    missingDimensions.length === 0

  if (readyForReconstruction) {
    return {
      readyForReconstruction: true,
      missingDimensions: [],
      message: '证据链已经足够支撑一次正式交卷，可以进入最终还原。',
    }
  }

  const dimensionLabels: Record<CheckpointDimension, string> = {
    timeline: '时间线',
    motive: '动机',
    evidence: '关键证据',
  }

  return {
    readyForReconstruction: false,
    missingDimensions,
    message: missingDimensions.length
      ? `证据链仍不完整，建议继续补强：${missingDimensions.map((item) => dimensionLabels[item]).join('、')}`
      : '还可以继续调查，补齐更多可验证事实后再交卷会更稳。',
  }
}

export function validateFinalReconstruction(
  packet: CasePacket,
  submission: FinalReconstruction,
  state?: CanonEngineLiteState,
): ValidationResult {
  const unlockedFacts = state ? new Set(getUnlockedFactIds(packet, state)) : null
  const unlockedEvidence = state ? new Set(getUnlockedEvidenceIds(packet, state)) : null

  const contradictions: string[] = []

  if (!submission.culpritId) contradictions.push('未指认嫌疑人。')
  if (!submission.motiveId) contradictions.push('未选择动机。')
  if (submission.explanation.length > DEFAULT_EXPLANATION_LIMIT) {
    contradictions.push(`解释文字超出 ${DEFAULT_EXPLANATION_LIMIT} 字限制。`)
  }

  if (unlockedFacts) {
    const lockedTimelineFacts = submission.timelineFactIds.filter((factId) => !unlockedFacts.has(factId))
    if (lockedTimelineFacts.length) {
      contradictions.push(`时间线中包含未解锁事实：${lockedTimelineFacts.join('、')}`)
    }
  }

  if (unlockedEvidence) {
    const lockedEvidencePairs = submission.evidencePairs.filter((pair) => !unlockedEvidence.has(pair.evidenceId))
    if (lockedEvidencePairs.length) {
      contradictions.push(`证据链中包含未解锁证据：${lockedEvidencePairs.map((pair) => pair.evidenceId).join('、')}`)
    }
  }

  const culpritCorrect = submission.culpritId === packet.groundTruth.culpritId
  const motiveCorrect = submission.motiveId === packet.groundTruth.motiveId
  const timelineAccuracy = buildTimelineAccuracy(packet.groundTruth.timelineFactIds, submission.timelineFactIds)
  const evidenceAccuracy = buildEvidenceAccuracy(packet.groundTruth.decisiveEvidencePairs, submission.evidencePairs)
  const matchedCoreFactIds = packet.groundTruth.requiredFactIds.filter((factId) =>
    submission.timelineFactIds.includes(factId) ||
    submission.evidencePairs.some((pair) => pair.factId === factId),
  )
  const missingCoreFactIds = packet.groundTruth.requiredFactIds.filter((factId) => !matchedCoreFactIds.includes(factId))

  const score = {
    culprit: culpritCorrect ? packet.validation.weights.culprit : 0,
    timeline: Math.round(packet.validation.weights.timeline * timelineAccuracy),
    evidence: Math.round(packet.validation.weights.evidence * evidenceAccuracy),
    motive: motiveCorrect ? packet.validation.weights.motive : 0,
    total: 0,
  }
  score.total = score.culprit + score.timeline + score.evidence + score.motive

  let grade: ValidationResult['grade'] = 'failure'
  if (culpritCorrect && score.total >= packet.validation.optimalThreshold) {
    grade = 'optimal'
  } else if (culpritCorrect && score.total >= packet.validation.hiddenThreshold) {
    grade = 'hidden'
  } else if (culpritCorrect && score.total >= packet.validation.successThreshold) {
    grade = 'normal'
  }

  const checkpointState = state ?? {
    caseId: packet.id,
    discoveredFactIds: submission.timelineFactIds,
    discoveredEvidenceIds: submission.evidencePairs.map((pair) => pair.evidenceId),
    unlockedWitnessIds: [],
    triggeredGateIds: [],
  }

  return {
    success: grade !== 'failure' && contradictions.length === 0,
    grade,
    culpritCorrect,
    motiveCorrect,
    timelineAccuracy,
    evidenceAccuracy,
    matchedCoreFactIds,
    missingCoreFactIds,
    contradictions,
    score,
    checkpoint: buildCheckpointHint(packet, checkpointState),
    revealedTruth: {
      culpritId: packet.groundTruth.culpritId,
      motiveId: packet.groundTruth.motiveId,
      timelineFactIds: packet.groundTruth.timelineFactIds,
      decisiveEvidencePairs: packet.groundTruth.decisiveEvidencePairs,
    },
  }
}
