import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface StreamState {
  modelId: string
  content: string
  isComplete: boolean
}

export const useChatStore = defineStore('chat', () => {
  const prompt = ref('')
  const streams = ref<Map<string, StreamState>>(new Map())
  const isStreaming = ref(false)
  const history = ref<Array<{ prompt: string; responses: StreamState[] }>>([])

  const allStreams = computed(() => Array.from(streams.value.values()))

  function startStreaming(modelIds: string[], userPrompt: string) {
    prompt.value = userPrompt
    streams.value.clear()
    isStreaming.value = true

    // Initialize streams
    modelIds.forEach(id => {
      streams.value.set(id, {
        modelId: id,
        content: '',
        isComplete: false
      })
    })

    // Simulate streaming (mock data)
    simulateStreaming(modelIds)
  }

  function simulateStreaming(modelIds: string[]) {
    const mockResponses: Record<string, string[]> = {
      'claude-4': [
        '基于你的问题，我来从规划角度分析...\n\n',
        '首先，我们需要明确几个关键点：\n\n1. **目标明确性** - 你要解决的核心问题是什么？\n\n2. **约束条件** - 有哪些技术或资源限制？\n\n',
        '3. **成功标准** - 如何衡量方案是否成功？\n\n基于以上分析，我建议采用分阶段实施的方式...',
      ],
      'gpt-5': [
        '作为审视者，我需要指出一些潜在风险...\n\n',
        '在考虑这个方案时，我们需要注意：\n\n- **过度复杂化风险** - 方案是否引入了不必要的复杂性？\n\n',
        '- **可维护性** - 后续团队能否轻松接手？\n\n- **扩展性问题** - 方案是否能支撑未来增长？\n\n建议先验证核心假设...',
      ],
      'gemini-3': [
        '从落地实施的角度，我来提供具体步骤...\n\n',
        '推荐的技术栈和实施路径：\n\n```typescript\n// 核心实现框架\nconst solution = {\n  phase1: "基础设施搭建",\n  phase2: "核心功能开发",\n  phase3: "测试与优化"\n}\n```\n\n',
        '预计时间线：2-3周完成 MVP...\n\n需要准备的环境和依赖...',
      ],
      'codex-2': [
        '让我直接给出代码实现方案...\n\n',
        '```rust\nfn main() {\n    // 高性能核心逻辑\n    let config = Config::load()?;\n    let engine = Engine::new(config);\n    engine.run()?;\n}\n```\n\n',
        '关键优化点：\n- 使用异步 IO\n- 内存池管理\n- 编译时检查...',
      ],
      'claude-haiku': [
        '快速综合一下各方观点...\n\n',
        '**共识点**：\n- 需要分阶段实施\n- 保持简洁优先\n\n',
        '**分歧点**：\n- 技术选型（Rust vs TypeScript）\n- 时间预估（2周 vs 4周）\n\n建议下一步：先做技术原型验证...',
      ],
      'gpt-4o-mini': [
        '简要补充几个关键质疑...\n\n',
        '- 数据一致性如何保证？\n- 异常情况的处理策略？\n\n',
        '建议补充：详细的错误处理流程...',
      ]
    }

    modelIds.forEach((modelId, idx) => {
      const chunks = mockResponses[modelId] || ['模拟响应内容...']
      let chunkIndex = 0
      let charIndex = 0

      const interval = setInterval(() => {
        const state = streams.value.get(modelId)
        if (!state || state.isComplete) {
          clearInterval(interval)
          return
        }

        if (chunkIndex < chunks.length) {
          const chunk = chunks[chunkIndex]
          if (charIndex < chunk.length) {
            state.content += chunk[charIndex]
            charIndex++
          } else {
            chunkIndex++
            charIndex = 0
          }
        } else {
          state.isComplete = true
          clearInterval(interval)
          checkAllComplete()
        }
      }, 15 + idx * 5) // Staggered start
    })
  }

  function checkAllComplete() {
    const allComplete = Array.from(streams.value.values()).every(s => s.isComplete)
    if (allComplete) {
      isStreaming.value = false
      history.value.push({
        prompt: prompt.value,
        responses: Array.from(streams.value.values())
      })
    }
  }

  function clear() {
    prompt.value = ''
    streams.value.clear()
    isStreaming.value = false
  }

  return {
    prompt,
    streams,
    isStreaming,
    history,
    allStreams,
    startStreaming,
    clear
  }
})
