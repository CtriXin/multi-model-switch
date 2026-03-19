import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import {
  CASE_RECONSTRUCTION_DEMO_CASE,
  buildCheckpointHint,
  getUnlockedFactIds,
  getUnlockedWitnessIds,
  isRevealGateSatisfied,
  validateFinalReconstruction,
  type CanonEngineLiteState,
  type CasePacket,
  type CaseReconstructionPhase,
  type CheckpointHint,
  type FinalReconstruction,
  type ValidationResult,
  type WitnessTestimony,
} from '@/features/play-modes/case-reconstruction'

const STORAGE_KEY = 'mms-case-reconstruction-demo-v1'

type InvestigationLogKind = 'scene' | 'evidence' | 'witness' | 'checkpoint' | 'gate' | 'verdict'

export interface InvestigationLogItem {
  id: string
  kind: InvestigationLogKind
  title: string
  summary: string
  createdAt: string
}

interface PersistedRecord {
  phase: CaseReconstructionPhase
  engineState: CanonEngineLiteState
  askedTestimonyIds: string[]
  investigationLog: InvestigationLogItem[]
  latestVerdict: ValidationResult | null
}

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function isoNow() {
  return new Date().toISOString()
}

function unique<T extends string>(values: T[]) {
  return [...new Set(values.filter(Boolean))]
}

function createLogItem(kind: InvestigationLogKind, title: string, summary: string): InvestigationLogItem {
  return {
    id: uid(),
    kind,
    title,
    summary,
    createdAt: isoNow(),
  }
}

function createInitialState(packet: CasePacket): CanonEngineLiteState {
  const sceneWitnessIds = packet.sceneZero.startingLeads
    .filter((lead) => lead.type === 'witness')
    .map((lead) => lead.id)

  return {
    caseId: packet.id,
    discoveredFactIds: [...packet.sceneZero.initialKnownFactIds],
    discoveredEvidenceIds: [],
    unlockedWitnessIds: sceneWitnessIds,
    triggeredGateIds: [],
  }
}

function createInitialLog(packet: CasePacket) {
  return [
    createLogItem('scene', 'Scene Zero', packet.sceneZero.openingMoment),
    createLogItem('scene', '调查提示', packet.sceneZero.cautionNote ?? '先收集证据，再决定何时交卷。'),
  ]
}

function cloneState(state: CanonEngineLiteState): CanonEngineLiteState {
  return {
    caseId: state.caseId,
    discoveredFactIds: unique(state.discoveredFactIds),
    discoveredEvidenceIds: unique(state.discoveredEvidenceIds),
    unlockedWitnessIds: unique(state.unlockedWitnessIds),
    triggeredGateIds: unique(state.triggeredGateIds),
  }
}

export const useCaseReconstructionStore = defineStore('caseReconstruction', () => {
  const packet = ref(CASE_RECONSTRUCTION_DEMO_CASE)
  const phase = ref<CaseReconstructionPhase>('scene_zero')
  const engineState = ref<CanonEngineLiteState>(createInitialState(packet.value))
  const askedTestimonyIds = ref<string[]>([])
  const investigationLog = ref<InvestigationLogItem[]>(createInitialLog(packet.value))
  const latestCheckpoint = ref<CheckpointHint>(buildCheckpointHint(packet.value, engineState.value))
  const latestVerdict = ref<ValidationResult | null>(null)
  const initialized = ref(false)

  const factMap = computed(() => new Map(packet.value.facts.map((fact) => [fact.id, fact])))
  const evidenceMap = computed(() => new Map(packet.value.evidence.map((evidence) => [evidence.id, evidence])))
  const witnessMap = computed(() => new Map(packet.value.witnesses.map((witness) => [witness.id, witness])))
  const motiveMap = computed(() => new Map(packet.value.motives.map((motive) => [motive.id, motive])))

  const unlockedFactIds = computed(() => getUnlockedFactIds(packet.value, engineState.value))
  const unlockedFacts = computed(() => packet.value.facts.filter((fact) => unlockedFactIds.value.includes(fact.id)))
  const unlockedWitnessIds = computed(() => getUnlockedWitnessIds(packet.value, engineState.value))
  const unlockedWitnesses = computed(() =>
    packet.value.witnesses.filter((witness) => unlockedWitnessIds.value.includes(witness.id)),
  )
  const discoveredEvidenceIds = computed(() => unique(engineState.value.discoveredEvidenceIds))
  const discoveredEvidence = computed(() =>
    packet.value.evidence.filter((evidence) => discoveredEvidenceIds.value.includes(evidence.id)),
  )
  const checkpointHint = computed(() => buildCheckpointHint(packet.value, engineState.value))
  const readyForReconstruction = computed(() => checkpointHint.value.readyForReconstruction)
  const timelineFacts = computed(() =>
    unlockedFacts.value.filter((fact) => fact.category !== 'context'),
  )

  function appendLog(kind: InvestigationLogKind, title: string, summary: string) {
    investigationLog.value = [
      createLogItem(kind, title, summary),
      ...investigationLog.value,
    ].slice(0, 36)
  }

  function syncGateState() {
    const nextFacts = new Set(engineState.value.discoveredFactIds)
    const nextWitnesses = new Set(engineState.value.unlockedWitnessIds)
    const nextTriggered: string[] = []

    for (const gate of packet.value.revealGates) {
      if (!isRevealGateSatisfied(gate, engineState.value)) continue
      nextTriggered.push(gate.id)
      for (const factId of gate.unlocksFactIds ?? []) nextFacts.add(factId)
      for (const witnessId of gate.unlocksWitnessIds ?? []) nextWitnesses.add(witnessId)
      if (!engineState.value.triggeredGateIds.includes(gate.id)) {
        appendLog('gate', '线索推进', gate.label)
      }
    }

    engineState.value = {
      ...engineState.value,
      discoveredFactIds: [...nextFacts],
      unlockedWitnessIds: [...nextWitnesses],
      triggeredGateIds: nextTriggered,
    }
    latestCheckpoint.value = buildCheckpointHint(packet.value, engineState.value)
  }

  function resetCase() {
    phase.value = 'scene_zero'
    engineState.value = createInitialState(packet.value)
    askedTestimonyIds.value = []
    investigationLog.value = createInitialLog(packet.value)
    latestVerdict.value = null
    latestCheckpoint.value = buildCheckpointHint(packet.value, engineState.value)
  }

  function hydrate(raw: PersistedRecord) {
    phase.value = raw.phase === 'checkpoint' ? 'investigation_turn' : raw.phase
    engineState.value = cloneState(raw.engineState)
    askedTestimonyIds.value = unique(raw.askedTestimonyIds)
    investigationLog.value = raw.investigationLog?.length ? raw.investigationLog : createInitialLog(packet.value)
    latestVerdict.value = raw.latestVerdict
    syncGateState()
  }

  function init() {
    if (initialized.value) return
    initialized.value = true

    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) {
        syncGateState()
        return
      }

      const parsed = JSON.parse(raw) as PersistedRecord
      if (parsed.engineState?.caseId !== packet.value.id) {
        resetCase()
        return
      }

      hydrate(parsed)
    } catch {
      resetCase()
    }
  }

  function persist() {
    try {
      const payload: PersistedRecord = {
        phase: phase.value,
        engineState: cloneState(engineState.value),
        askedTestimonyIds: [...askedTestimonyIds.value],
        investigationLog: [...investigationLog.value],
        latestVerdict: latestVerdict.value,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    } catch {
      // Ignore persistence failures in MVP.
    }
  }

  function beginInvestigation() {
    phase.value = 'investigation_turn'
    latestCheckpoint.value = buildCheckpointHint(packet.value, engineState.value)
  }

  function inspectEvidence(evidenceId: string) {
    if (engineState.value.discoveredEvidenceIds.includes(evidenceId)) return

    const evidence = evidenceMap.value.get(evidenceId)
    if (!evidence) return

    const nextFacts = new Set(engineState.value.discoveredFactIds)
    for (const factId of evidence.supportsFactIds) {
      const fact = factMap.value.get(factId)
      if (fact && (!fact.gateId || engineState.value.triggeredGateIds.includes(fact.gateId))) {
        nextFacts.add(factId)
      }
    }

    engineState.value = {
      ...engineState.value,
      discoveredEvidenceIds: unique([...engineState.value.discoveredEvidenceIds, evidenceId]),
      discoveredFactIds: [...nextFacts],
    }

    appendLog('evidence', evidence.label, evidence.summary)
    syncGateState()
  }

  function isTestimonyAvailable(testimony: WitnessTestimony) {
    if (!testimony.unlockGateId) return true
    const gate = packet.value.revealGates.find((item) => item.id === testimony.unlockGateId)
    return gate ? isRevealGateSatisfied(gate, engineState.value) : true
  }

  function gateLabelForTestimony(testimony: WitnessTestimony) {
    if (!testimony.unlockGateId) return ''
    return packet.value.revealGates.find((item) => item.id === testimony.unlockGateId)?.label ?? ''
  }

  function askWitness(witnessId: string, testimonyId: string) {
    if (askedTestimonyIds.value.includes(testimonyId)) return

    const witness = witnessMap.value.get(witnessId)
    const testimony = witness?.testimony.find((item) => item.id === testimonyId)
    if (!witness || !testimony || !isTestimonyAvailable(testimony)) return

    engineState.value = {
      ...engineState.value,
      discoveredFactIds: unique([...engineState.value.discoveredFactIds, ...testimony.revealsFactIds]),
    }
    askedTestimonyIds.value = unique([...askedTestimonyIds.value, testimonyId])

    appendLog('witness', `${witness.name} · ${testimony.promptLabel}`, testimony.summary)
    syncGateState()
  }

  function requestCheckpoint() {
    latestCheckpoint.value = buildCheckpointHint(packet.value, engineState.value)
    appendLog('checkpoint', 'Checkpoint', latestCheckpoint.value.message)
  }

  function resumeInvestigation() {
    phase.value = 'investigation_turn'
  }

  function openFinalReconstruction() {
    latestCheckpoint.value = buildCheckpointHint(packet.value, engineState.value)
    if (!latestCheckpoint.value.readyForReconstruction) {
      appendLog('checkpoint', 'Checkpoint', latestCheckpoint.value.message)
      phase.value = 'investigation_turn'
      return
    }

    phase.value = 'final_reconstruction'
  }

  function submitReconstruction(submission: FinalReconstruction) {
    latestVerdict.value = validateFinalReconstruction(packet.value, submission, engineState.value)
    phase.value = 'verdict'

    const verdictSummary = latestVerdict.value.success
      ? `交卷成立，当前评分 ${latestVerdict.value.score.total}。`
      : `交卷未成立，当前评分 ${latestVerdict.value.score.total}。`

    appendLog('verdict', 'Verdict', verdictSummary)
  }

  function reviseSubmission() {
    phase.value = 'final_reconstruction'
  }

  watch(
    [phase, engineState, askedTestimonyIds, investigationLog, latestVerdict],
    () => persist(),
    { deep: true },
  )

  return {
    packet,
    phase,
    engineState,
    askedTestimonyIds,
    investigationLog,
    latestCheckpoint,
    latestVerdict,
    unlockedFacts,
    unlockedFactIds,
    unlockedWitnesses,
    discoveredEvidence,
    discoveredEvidenceIds,
    checkpointHint,
    readyForReconstruction,
    timelineFacts,
    factMap,
    evidenceMap,
    witnessMap,
    motiveMap,
    init,
    resetCase,
    beginInvestigation,
    inspectEvidence,
    isTestimonyAvailable,
    gateLabelForTestimony,
    askWitness,
    requestCheckpoint,
    resumeInvestigation,
    openFinalReconstruction,
    submitReconstruction,
    reviseSubmission,
  }
})
