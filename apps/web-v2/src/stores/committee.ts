import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getApiKey } from '@/services/keychain'
import { streamChat } from '@/services/api'
import { useAppStore } from './app'
import { useProviderStore } from './provider'
import { usePersonaStore, type PersonaDefinition } from './persona'
import type { ModelMeta } from './app'
import {
  buildFallbackSynthesis,
  buildRoleModelAssignments,
  buildRolePersonaPrompt,
  buildSystemModeratorPrompt,
  createPendingDebate,
  createPendingSummary,
  parseDebateOutput,
  parseModeratorOutput,
  parseRoleOutput,
  pickSynthesizerModel,
  type CommitteeMode,
  type CommitteePhase,
  type CommitteeSynthesis,
  type DebateExchange,
  type PhaseStatus,
  type RoleModelAssignment,
  type RoleSummary,
} from '@/features/committee'

interface StartCommitteePayload {
  promptText: string
  mode: CommitteeMode
  roleIds: string[]
  modelPool: ModelMeta[]
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === 'AbortError'
}

export const useCommitteeStore = defineStore('committee', () => {
  const prompt = ref('')
  const isActive = ref(false)
  const isStreaming = ref(false)
  const stopped = ref(false)
  const currentPhase = ref<CommitteePhase>(1)
  const phaseStatus = ref<PhaseStatus>('waiting')
  const sessionMode = ref<CommitteeMode>('broadcast')
  const activeRoleIds = ref<string[]>([])
  const phase1Summaries = ref<RoleSummary[]>([])
  const phase2Reviews = ref<DebateExchange[]>([])
  const phase3Content = ref('')
  const synthesizer = ref<string | null>(null)
  const committeeSynthesis = ref<CommitteeSynthesis | null>(null)
  const committeeContributions = ref<CommitteeSynthesis['contributions']>([])
  const roleAssignments = ref<RoleModelAssignment[]>([])
  const abortController = ref<AbortController | null>(null)

  const activeRoleCount = computed(() => activeRoleIds.value.length)
  const hasDebatePhase = computed(() => sessionMode.value === 'debate')
  const hasCommitteePhase = computed(() => sessionMode.value === 'committee')
  const isCompleted = computed(() => phaseStatus.value === 'completed' && !isStreaming.value)

  const phaseProgress = computed(() => {
    if (currentPhase.value === 1) {
      const finished = phase1Summaries.value.filter((item) => item.ok || item.error).length
      return { current: finished, total: phase1Summaries.value.length || 1 }
    }
    if (currentPhase.value === 2) {
      const finished = phase2Reviews.value.filter((item) => item.ok || item.error).length
      return { current: finished, total: phase2Reviews.value.length || 1 }
    }
    return {
      current: phase3Content.value ? 1 : 0,
      total: hasCommitteePhase.value ? 1 : 0,
    }
  })

  function clearSession() {
    prompt.value = ''
    isActive.value = false
    isStreaming.value = false
    stopped.value = false
    currentPhase.value = 1
    phaseStatus.value = 'waiting'
    activeRoleIds.value = []
    phase1Summaries.value = []
    phase2Reviews.value = []
    phase3Content.value = ''
    synthesizer.value = null
    committeeSynthesis.value = null
    committeeContributions.value = []
    roleAssignments.value = []
    abortController.value = null
  }

  function stop() {
    stopped.value = true
    isStreaming.value = false
    phaseStatus.value = 'waiting'
    abortController.value?.abort()
    abortController.value = null
  }

  function getActiveRoles(roleIds: string[]) {
    const personaStore = usePersonaStore()
    const roleMap = new Map(personaStore.personas.map((role) => [role.id, role]))
    return roleIds
      .map((roleId) => roleMap.get(roleId))
      .filter((role): role is PersonaDefinition => !!role)
  }

  function getAssignedModelId(roleId: string) {
    return roleAssignments.value.find((item) => item.roleId === roleId)?.modelId || ''
  }

  async function resolveRuntime(modelId: string) {
    const appStore = useAppStore()
    const providerStore = useProviderStore()
    const model = appStore.models.find((item) => item.id === modelId)

    let provider = providerStore.providers.find((item) => item.id === model?.provider)
    if (!provider && modelId.startsWith('demo/')) {
      provider = providerStore.providers.find((item) => item.type === 'mock')
    }
    if (!provider) {
      provider = providerStore.providers.find((item) => item.type === 'openrouter')
    }
    if (!provider) throw new Error('未找到可用的 API 通道')

    const apiKey = provider.type === 'mock' ? 'demo' : await getApiKey(provider.id)
    if (!apiKey) throw new Error(`${provider.name} 未配置 API Key`)

    return { provider, apiKey }
  }

  async function collectStream(modelId: string, systemPrompt: string, userPrompt: string, onChunk?: (chunk: string) => void) {
    const { provider, apiKey } = await resolveRuntime(modelId)
    let raw = ''
    for await (const chunk of streamChat({
      provider,
      apiKey,
      model: modelId,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      signal: abortController.value?.signal,
    })) {
      raw += chunk
      onChunk?.(chunk)
    }
    return raw.trim()
  }

  async function runPhase1(promptText: string, roles: PersonaDefinition[]) {
    phase1Summaries.value = roles.map((role) =>
      createPendingSummary(role.id, getAssignedModelId(role.id))
    )

    const tasks = roles.map(async (role, index) => {
      const modelId = getAssignedModelId(role.id)
      const startedAt = Date.now()
      try {
        const raw = await collectStream(
          modelId,
          buildRolePersonaPrompt(role, { mode: sessionMode.value, prompt: promptText }),
          promptText,
        )
        const parsed = parseRoleOutput(raw)
        phase1Summaries.value.splice(index, 1, {
          roleId: role.id,
          modelId,
          ok: true,
          elapsed: (Date.now() - startedAt) / 1000,
          headline: parsed.headline || `${role.name}先把“${role.focus}”拎成主矛盾`,
          viewpoint: parsed.viewpoint || raw.slice(0, 140),
          tension: parsed.tension || role.nonNegotiable,
          recommendation: parsed.recommendation || `${role.name}要求先守住“${role.focus}”这条线。`,
          content: raw,
        })
      } catch (error) {
        if (isAbortError(error)) return
        phase1Summaries.value.splice(index, 1, {
          roleId: role.id,
          modelId,
          ok: false,
          elapsed: (Date.now() - startedAt) / 1000,
          error: error instanceof Error ? error.message : '生成失败',
        })
      }
    })

    await Promise.allSettled(tasks)
  }

  async function runPhase2(promptText: string, roles: PersonaDefinition[]) {
    const roleMap = new Map(roles.map((role) => [role.id, role]))
    const pairs = roles
      .map((role) => {
        const target = roleMap.get(role.debatePartnerId)
        if (!target || !activeRoleIds.value.includes(target.id) || role.id > target.id) return null
        return { role, target }
      })
      .filter((pair): pair is { role: PersonaDefinition; target: PersonaDefinition } => !!pair)

    phase2Reviews.value = pairs.map((pair) =>
      createPendingDebate(pair.role.id, pair.target.id, getAssignedModelId(pair.role.id))
    )

    const tasks = pairs.map(async ({ role, target }, index) => {
      const modelId = getAssignedModelId(role.id)
      const targetSummary = phase1Summaries.value.find((item) => item.roleId === target.id)
      const startedAt = Date.now()
      try {
        const raw = await collectStream(
          modelId,
          buildRolePersonaPrompt(role, {
            mode: 'debate',
            prompt: promptText,
            targetRoleName: target.name,
            targetViewpoint: targetSummary?.viewpoint,
            peerSummaries: targetSummary?.viewpoint ? [{
              roleName: target.name,
              viewpoint: targetSummary.viewpoint,
              tension: targetSummary.tension || '对方认为这里有关键冲突',
            }] : undefined,
          }),
          promptText,
        )
        const parsed = parseDebateOutput(raw)
        phase2Reviews.value.splice(index, 1, {
          roleId: role.id,
          targetRoleId: target.id,
          modelId,
          ok: true,
          elapsed: (Date.now() - startedAt) / 1000,
          rebuttal: parsed.rebuttal || `${role.name}不接受${target.name}把问题只压成“${target.focus}”视角。`,
          keepBelief: parsed.keepBelief || `我的立场不变：${role.coreBelief}`,
          integration: parsed.integration || `我愿意吸收${target.name}的一部分提醒，但前提是先守住“${role.nonNegotiable}”。`,
          raw,
        })
      } catch (error) {
        if (isAbortError(error)) return
        phase2Reviews.value.splice(index, 1, {
          roleId: role.id,
          targetRoleId: target.id,
          modelId,
          ok: false,
          elapsed: (Date.now() - startedAt) / 1000,
          error: error instanceof Error ? error.message : '辩论失败',
        })
      }
    })

    await Promise.allSettled(tasks)
  }

  async function runPhase3(promptText: string, roles: PersonaDefinition[], modelPool: ModelMeta[]) {
    const goodSummaries = phase1Summaries.value.filter((item) => item.ok)
    const fallback = buildFallbackSynthesis(promptText, goodSummaries, roles)
    const moderatorModel = pickSynthesizerModel(modelPool, roleAssignments.value)

    if (!moderatorModel) {
      committeeSynthesis.value = fallback
      committeeContributions.value = fallback.contributions
      synthesizer.value = fallback.moderator
      phase3Content.value = fallback.content
      return
    }

    synthesizer.value = moderatorModel.name
    phase3Content.value = ''

    try {
      const raw = await collectStream(
        moderatorModel.id,
        buildSystemModeratorPrompt(promptText, goodSummaries, roles),
        `请基于以上角色观点，生成本轮锦囊团结论。议题：${promptText}`,
        (chunk) => { phase3Content.value += chunk },
      )
      const parsed = parseModeratorOutput(raw, roles, {
        ...fallback,
        moderator: moderatorModel.name,
      })
      committeeSynthesis.value = parsed
      committeeContributions.value = parsed.contributions
      phase3Content.value = raw
    } catch (error) {
      if (isAbortError(error)) return
      committeeSynthesis.value = {
        ...fallback,
        moderator: moderatorModel.name,
      }
      committeeContributions.value = committeeSynthesis.value.contributions
      phase3Content.value = fallback.content
    }
  }

  async function startCommittee(payload: StartCommitteePayload) {
    const roles = getActiveRoles(payload.roleIds)

    prompt.value = payload.promptText
    sessionMode.value = payload.mode
    activeRoleIds.value = payload.roleIds
    roleAssignments.value = buildRoleModelAssignments(payload.roleIds, roles, payload.modelPool)
    isActive.value = true
    isStreaming.value = true
    stopped.value = false
    currentPhase.value = 1
    phaseStatus.value = 'running'
    phase1Summaries.value = []
    phase2Reviews.value = []
    phase3Content.value = ''
    synthesizer.value = null
    committeeSynthesis.value = null
    committeeContributions.value = []
    abortController.value = new AbortController()

    try {
      await runPhase1(payload.promptText, roles)
      if (stopped.value) return

      if (payload.mode === 'debate') {
        currentPhase.value = 2
        await runPhase2(payload.promptText, roles)
      }
      if (stopped.value) return

      if (payload.mode === 'committee') {
        currentPhase.value = 3
        await runPhase3(payload.promptText, roles, payload.modelPool)
      }
      if (stopped.value) return

      phaseStatus.value = 'completed'
    } finally {
      if (!stopped.value) {
        isStreaming.value = false
      }
      abortController.value = null
    }
  }

  return {
    prompt,
    isActive,
    isStreaming,
    stopped,
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
    isCompleted,
    phaseProgress,
    startCommittee,
    stop,
    clearSession,
  }
})
