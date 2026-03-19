import type { EndingGrade, HistoryEntry, PlayModeSessionEnvelope } from '../shared'

export type FactId = string
export type EvidenceId = string
export type WitnessId = string
export type MotiveId = string
export type RevealGateId = string

export type CaseReconstructionPhase =
  | 'case_select'
  | 'scene_zero'
  | 'investigation_turn'
  | 'checkpoint'
  | 'final_reconstruction'
  | 'verdict'
  | 'ended'

export type FactTier = 'surface' | 'gated' | 'hidden'
export type FactCategory = 'timeline' | 'motive' | 'means' | 'access' | 'alibi' | 'context'
export type EvidenceKind = 'physical' | 'document' | 'forensic' | 'digital'
export type WitnessDemeanor = 'cooperative' | 'guarded' | 'evasive'
export type RevealGateType = 'evidence_count' | 'fact_discovered'
export type CheckpointDimension = 'timeline' | 'motive' | 'evidence'

export interface RevealGate {
  id: RevealGateId
  label: string
  type: RevealGateType
  threshold?: number
  requiredFactIds?: FactId[]
  unlocksFactIds?: FactId[]
  unlocksEvidenceIds?: EvidenceId[]
  unlocksWitnessIds?: WitnessId[]
}

export interface CaseFact {
  id: FactId
  label: string
  summary: string
  tier: FactTier
  category: FactCategory
  gateId?: RevealGateId
  source: 'scene_zero' | 'witness' | 'evidence' | 'analysis'
}

export interface CaseEvidence {
  id: EvidenceId
  label: string
  kind: EvidenceKind
  summary: string
  supportsFactIds: FactId[]
  isRedHerring?: boolean
}

export interface WitnessTestimony {
  id: string
  promptLabel: string
  summary: string
  revealsFactIds: FactId[]
  unlockGateId?: RevealGateId
}

export interface CaseWitness {
  id: WitnessId
  name: string
  role: 'witness' | 'suspect'
  publicProfile: string
  demeanor: WitnessDemeanor
  testimony: WitnessTestimony[]
}

export interface CaseMotive {
  id: MotiveId
  label: string
  summary: string
}

export interface SceneLead {
  id: string
  label: string
  type: 'witness' | 'evidence'
}

export interface SceneZeroPayload {
  openingMoment: string
  playerRole: string
  initialKnownFactIds: FactId[]
  startingLeads: SceneLead[]
  cautionNote?: string
}

export interface EvidenceFactPair {
  evidenceId: EvidenceId
  factId: FactId
}

export interface FinalReconstruction {
  culpritId: WitnessId | null
  timelineFactIds: FactId[]
  evidencePairs: EvidenceFactPair[]
  motiveId: MotiveId | null
  explanation: string
}

export interface ScoreBreakdown {
  culprit: number
  timeline: number
  evidence: number
  motive: number
  total: number
}

export interface CheckpointHint {
  readyForReconstruction: boolean
  missingDimensions: CheckpointDimension[]
  message: string
}

export interface ValidationResult {
  success: boolean
  grade: EndingGrade
  culpritCorrect: boolean
  motiveCorrect: boolean
  timelineAccuracy: number
  evidenceAccuracy: number
  matchedCoreFactIds: FactId[]
  missingCoreFactIds: FactId[]
  contradictions: string[]
  score: ScoreBreakdown
  checkpoint: CheckpointHint
  revealedTruth: {
    culpritId: WitnessId
    motiveId: MotiveId
    timelineFactIds: FactId[]
    decisiveEvidencePairs: EvidenceFactPair[]
  }
}

export interface CanonEngineLiteState {
  caseId: string
  discoveredFactIds: FactId[]
  discoveredEvidenceIds: EvidenceId[]
  unlockedWitnessIds: WitnessId[]
  triggeredGateIds: RevealGateId[]
}

export interface CasePacket {
  id: string
  title: string
  difficulty: 'easy' | 'medium' | 'hard'
  estimatedMinutes: number
  playerRole: string
  sceneZero: SceneZeroPayload
  motives: CaseMotive[]
  facts: CaseFact[]
  evidence: CaseEvidence[]
  witnesses: CaseWitness[]
  revealGates: RevealGate[]
  groundTruth: {
    culpritId: WitnessId
    motiveId: MotiveId
    timelineFactIds: FactId[]
    decisiveEvidencePairs: EvidenceFactPair[]
    requiredFactIds: FactId[]
  }
  validation: {
    successThreshold: number
    hiddenThreshold: number
    optimalThreshold: number
    minimumEvidencePairs: number
    minimumTimelineFacts: number
    checkpointThresholds: {
      evidenceCount: number
      coreFactsDiscovered: number
    }
    weights: ScoreBreakdown
  }
}

export interface CanonEngineLite {
  facts: CaseFact[]
  revealGates: RevealGate[]
  state: CanonEngineLiteState
  isGateSatisfied(gate: RevealGate): boolean
  validate(submission: FinalReconstruction): ValidationResult
}

export interface InvestigationTurnPayload {
  lead: {
    headline: string
    availableActions: string[]
    keyObservation?: string
  }
  witness?: {
    speaker: string
    statement: string
  }
  stateDelta: {
    factIds: FactId[]
    evidenceIds: EvidenceId[]
    witnessIds: WitnessId[]
  }
}

export interface CaseReconstructionSessionMeta {
  phase: CaseReconstructionPhase
  caseState: CanonEngineLiteState
  currentCaseId?: string | null
  latestCheckpoint?: CheckpointHint | null
}

export interface CaseReconstructionSessionEnvelope extends PlayModeSessionEnvelope {
  mode: 'case-reconstruction'
  meta: CaseReconstructionSessionMeta & Record<string, unknown>
  history: Array<HistoryEntry & { type: 'investigation_turn' | 'special_event' | 'summary_snapshot' }>
}
