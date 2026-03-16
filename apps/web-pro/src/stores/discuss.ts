import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { ModelMeta } from '@mms/contracts'
import {
  buildRoleModelAssignments,
  COMMITTEE_ROLES,
  buildCommitteeSynthesis,
  createPendingDebate,
  createPendingSummary,
  generateDebateExchange,
  generateRoleSummary,
  getCommitteeRole,
  streamText,
  type CommitteeMode,
  type CommitteePhase,
  type CommitteeSynthesis,
  type DebateExchange,
  type PhaseStatus,
  type RoleModelAssignment,
  type RoleSummary,
} from '@/features/committee'

interface StartDiscussPayload {
  promptText: string
  modelPool: ModelMeta[]
  mode: CommitteeMode
  roleIds: string[]
}

export const useDiscussStore = defineStore('discuss', () => {
  const prompt = ref('')
  const isActive = ref(false)
  const isStreaming = ref(false)
  const currentPhase = ref<CommitteePhase>(1)
  const phaseStatus = ref<PhaseStatus>('waiting')
  const sessionMode = ref<CommitteeMode>('broadcast')
  const activeRoleIds = ref<string[]>(COMMITTEE_ROLES.map((role) => role.id))
  const phase1Summaries = ref<RoleSummary[]>([])
  const phase2Reviews = ref<DebateExchange[]>([])
  const phase3Content = ref('')
  const synthesizer = ref<string | null>(null)
  const committeeSynthesis = ref<CommitteeSynthesis | null>(null)
  const committeeContributions = ref<CommitteeSynthesis['contributions']>([])
  const roleAssignments = ref<RoleModelAssignment[]>([])

  const activeRoleCount = computed(() => activeRoleIds.value.length)
  const hasDebatePhase = computed(() => sessionMode.value === 'debate')
  const hasCommitteePhase = computed(() => sessionMode.value === 'committee')

  const phaseProgress = computed(() => {
    if (currentPhase.value === 1) {
      return {
        current: phase1Summaries.value.filter((summary) => summary.ok).length,
        total: phase1Summaries.value.length || 1,
      }
    }
    if (currentPhase.value === 2) {
      return {
        current: phase2Reviews.value.filter((review) => review.ok).length,
        total: phase2Reviews.value.length || 1,
      }
    }
    return {
      current: phase3Content.value ? 1 : 0,
      total: hasCommitteePhase.value ? 1 : 0,
    }
  })

  function getAssignedModelId(roleId: string) {
    return roleAssignments.value.find((item) => item.roleId === roleId)?.modelId || 'unbound'
  }

  async function runSummaries(roleIds: string[]) {
    phase1Summaries.value = roleIds.map((roleId) =>
      createPendingSummary(roleId, getAssignedModelId(roleId))
    )

    const tasks = roleIds.map(async (roleId, index) => {
      const role = getCommitteeRole(roleId)
      if (!role) return
      const modelId = getAssignedModelId(roleId)
      const summary = await generateRoleSummary(role, prompt.value, modelId)
      phase1Summaries.value.splice(index, 1, summary)
    })

    await Promise.all(tasks)
  }

  async function runDebate(roleIds: string[]) {
    const exchanges = roleIds
      .map((roleId) => {
        const role = getCommitteeRole(roleId)
        const target = role ? getCommitteeRole(role.debatePartnerId) : undefined
        if (!role || !target || !roleIds.includes(target.id) || role.id > target.id) {
          return null
        }
        return createPendingDebate(role.id, target.id)
      })
      .filter((item): item is DebateExchange => !!item)

    phase2Reviews.value = exchanges

    const tasks = exchanges.map(async (exchange, index) => {
      const role = getCommitteeRole(exchange.roleId)
      const target = getCommitteeRole(exchange.targetRoleId)
      if (!role || !target) return
      const targetSummary = phase1Summaries.value.find((item) => item.roleId === target.id)
      const review = await generateDebateExchange(role, target, targetSummary)
      phase2Reviews.value.splice(index, 1, review)
    })

    await Promise.all(tasks)
  }

  async function runCommittee() {
    const synthesis = buildCommitteeSynthesis(prompt.value, phase1Summaries.value.filter((item) => item.ok))
    committeeSynthesis.value = synthesis
    synthesizer.value = synthesis.moderator
    committeeContributions.value = synthesis.contributions

    await new Promise<void>((resolve) => {
      streamText(
        synthesis.content,
        (chunk) => {
          phase3Content.value += chunk
        },
        () => resolve(),
      )
    })
  }

  async function startDiscuss({ promptText, modelPool, mode, roleIds }: StartDiscussPayload) {
    prompt.value = promptText
    sessionMode.value = mode
    activeRoleIds.value = roleIds
    roleAssignments.value = buildRoleModelAssignments(roleIds, modelPool)
    isActive.value = true
    isStreaming.value = true
    currentPhase.value = 1
    phaseStatus.value = 'running'
    phase1Summaries.value = []
    phase2Reviews.value = []
    phase3Content.value = ''
    synthesizer.value = null
    committeeSynthesis.value = null
    committeeContributions.value = []

    await runSummaries(roleIds)

    if (mode === 'debate') {
      currentPhase.value = 2
      await runDebate(roleIds)
    }

    if (mode === 'committee') {
      currentPhase.value = 3
      await runCommittee()
    }

    phaseStatus.value = 'completed'
    isStreaming.value = false
  }

  function clearSession() {
    prompt.value = ''
    isActive.value = false
    isStreaming.value = false
    currentPhase.value = 1
    phaseStatus.value = 'waiting'
    phase1Summaries.value = []
    phase2Reviews.value = []
    phase3Content.value = ''
    synthesizer.value = null
    committeeSynthesis.value = null
    committeeContributions.value = []
    roleAssignments.value = []
  }

  return {
    prompt,
    isActive,
    isStreaming,
    currentPhase,
    phaseStatus,
    sessionMode,
    activeRoleIds,
    phase1Summaries,
    phase2Reviews,
    phase3Content,
    synthesizer,
    committeeSynthesis,
    committeeContributions,
    roleAssignments,
    activeRoleCount,
    hasDebatePhase,
    hasCommitteePhase,
    phaseProgress,
    startDiscuss,
    clearSession,
  }
})
