import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface Phase1Summary {
  modelId: string
  approach: string
  reasoning: string
  confidence: number
}

export interface Phase2Review {
  reviewerId: string
  targetId: string
  critique: string
  suggestions: string[]
}

export interface Phase3Synthesis {
  synthesizerId: string
  consensus: string[]
  disagreements: string[]
  recommendation: string
}

export const useDiscussStore = defineStore('discuss', () => {
  const prompt = ref('')
  const currentPhase = ref<0 | 1 | 2 | 3>(0)
  const isProcessing = ref(false)

  const phase1Summaries = ref<Phase1Summary[]>([])
  const phase2Reviews = ref<Phase2Review[]>([])
  const phase3Synthesis = ref<Phase3Synthesis | null>(null)

  const phaseName = computed(() => {
    const names = {
      0: '准备阶段',
      1: '独立方案',
      2: '交叉审查',
      3: '综合结论'
    }
    return names[currentPhase.value]
  })

  const progress = computed(() => {
    return (currentPhase.value / 3) * 100
  })

  async function startDiscussion(modelIds: string[], userPrompt: string) {
    prompt.value = userPrompt
    currentPhase.value = 1
    isProcessing.value = true

    // Phase 1: Simulate summaries
    await simulatePhase1(modelIds)

    // Phase 2: Simulate cross-reviews
    currentPhase.value = 2
    await simulatePhase2(modelIds)

    // Phase 3: Simulate synthesis
    currentPhase.value = 3
    await simulatePhase3(modelIds)

    isProcessing.value = false
  }

  async function simulatePhase1(modelIds: string[]) {
    phase1Summaries.value = []

    const mockSummaries: Record<string, Phase1Summary> = {
      'claude-4': {
        modelId: 'claude-4',
        approach: '采用微服务架构，使用事件驱动模式进行服务间通信',
        reasoning: '这种架构能够支持高并发和独立扩展，适合长期发展',
        confidence: 0.85
      },
      'gpt-5': {
        modelId: 'gpt-5',
        approach: '单体应用 + 模块化设计，优先保证开发效率',
        reasoning: '对于早期阶段，单体架构更易于调试和维护',
        confidence: 0.78
      },
      'gemini-3': {
        modelId: 'gemini-3',
        approach: '混合架构：核心功能单体 + 边缘服务微服务化',
        reasoning: '在复杂度和扩展性之间取得平衡',
        confidence: 0.82
      }
    }

    for (const id of modelIds) {
      await delay(800)
      phase1Summaries.value.push(mockSummaries[id] || {
        modelId: id,
        approach: '基于现有信息分析...',
        reasoning: '需要更多上下文来做出精准判断',
        confidence: 0.65
      })
    }
  }

  async function simulatePhase2(modelIds: string[]) {
    phase2Reviews.value = []

    for (let i = 0; i < modelIds.length; i++) {
      await delay(600)
      const reviewer = modelIds[i]
      const target = modelIds[(i + 1) % modelIds.length]

      phase2Reviews.value.push({
        reviewerId: reviewer,
        targetId: target,
        critique: '方案整体可行，但有几个需要注意的点...',
        suggestions: [
          '建议增加错误处理机制',
          '考虑添加回退策略',
          '可以进一步优化性能'
        ]
      })
    }
  }

  async function simulatePhase3(modelIds: string[]) {
    await delay(1000)

    phase3Synthesis.value = {
      synthesizerId: modelIds[0],
      consensus: [
        '需要分阶段实施',
        '保持架构简洁',
        '优先验证核心假设'
      ],
      disagreements: [
        '技术栈选择（单体 vs 微服务）',
        '时间预估范围'
      ],
      recommendation: '建议采用混合架构方案，以 4 周为周期完成 MVP，包含核心功能验证。第一周搭建基础框架，第二周实现核心逻辑，第三周进行集成测试，第四周优化和文档。'
    }
  }

  function delay(ms: number) {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  function reset() {
    prompt.value = ''
    currentPhase.value = 0
    isProcessing.value = false
    phase1Summaries.value = []
    phase2Reviews.value = []
    phase3Synthesis.value = null
  }

  return {
    prompt,
    currentPhase,
    isProcessing,
    phase1Summaries,
    phase2Reviews,
    phase3Synthesis,
    phaseName,
    progress,
    startDiscussion,
    reset
  }
})
