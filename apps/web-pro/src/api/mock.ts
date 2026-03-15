/**
 * Mock data for standalone development.
 * Covers models, presets, sessions, and simulated streaming responses.
 */
import type {
  ModelMeta, Preset, Session, BootstrapConfig,
  Phase1Summary, Phase2Review,
} from '@mms/contracts'

export const MOCK_MODELS: ModelMeta[] = [
  {
    id: 'claude-opus-4-6', name: 'Claude Opus 4.6', provider: 'anthropic',
    category: 'Claude', tier: 2, priceInput: 15, priceOutput: 75,
    tags: ['reasoning', 'recommended'], contextWindow: 200000,
  },
  {
    id: 'claude-sonnet-4-6', name: 'Claude Sonnet 4.6', provider: 'anthropic',
    category: 'Claude', tier: 1, priceInput: 3, priceOutput: 15,
    tags: ['fast', 'recommended', 'coding'], contextWindow: 200000,
  },
  {
    id: 'claude-haiku-4-5', name: 'Claude Haiku 4.5', provider: 'anthropic',
    category: 'Claude', tier: 0, priceInput: 0.8, priceOutput: 4,
    tags: ['fast'], contextWindow: 200000,
  },
  {
    id: 'gpt-4o', name: 'GPT-4o', provider: 'openai',
    category: 'OpenAI', tier: 1, priceInput: 2.5, priceOutput: 10,
    tags: ['fast', 'vision'], contextWindow: 128000,
  },
  {
    id: 'o3', name: 'o3', provider: 'openai',
    category: 'OpenAI', tier: 2, priceInput: 10, priceOutput: 40,
    tags: ['reasoning'], contextWindow: 200000,
  },
  {
    id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', provider: 'google',
    category: 'Google', tier: 1, priceInput: 1.25, priceOutput: 10,
    tags: ['reasoning', 'vision'], contextWindow: 1000000,
  },
  {
    id: 'deepseek-r1', name: 'DeepSeek R1', provider: 'deepseek',
    category: 'DeepSeek', tier: 1, priceInput: 0.55, priceOutput: 2.19,
    tags: ['reasoning', 'coding'], contextWindow: 64000,
  },
  {
    id: 'deepseek-v3', name: 'DeepSeek V3', provider: 'deepseek',
    category: 'DeepSeek', tier: 0, priceInput: 0.27, priceOutput: 1.1,
    tags: ['fast', 'coding'], contextWindow: 64000,
  },
  {
    id: 'moonshot-v1-128k', name: 'Kimi (128K)', provider: 'moonshot',
    category: '国产', tier: 0, priceInput: 0.8, priceOutput: 0.8,
    tags: ['fast'], contextWindow: 128000,
  },
]

export const MOCK_PRESETS: Preset[] = [
  { id: 'flagship', name: '旗舰对决', models: ['claude-opus-4-6', 'o3', 'gemini-2.5-pro'], builtin: true, icon: '🏆' },
  { id: 'fast', name: '快速三巨头', models: ['claude-sonnet-4-6', 'gpt-4o', 'deepseek-v3'], builtin: true, icon: '⚡' },
  { id: 'reasoning', name: '推理专家', models: ['claude-opus-4-6', 'o3', 'deepseek-r1'], builtin: true, icon: '🧠' },
  { id: 'budget', name: '高性价比', models: ['claude-haiku-4-5', 'deepseek-v3', 'moonshot-v1-128k'], builtin: true, icon: '💰' },
]

export const MOCK_SESSIONS: Session[] = [
  {
    id: 'sess-1', mode: 'chat', title: 'API 网关设计方案对比',
    models: ['claude-opus-4-6', 'gpt-4o', 'gemini-2.5-pro'],
    createdAt: '2026-03-15T10:30:00Z', updatedAt: '2026-03-15T11:45:00Z', messageCount: 8,
  },
  {
    id: 'sess-2', mode: 'discuss', title: '微服务拆分策略讨论',
    models: ['claude-sonnet-4-6', 'o3', 'deepseek-r1'],
    createdAt: '2026-03-14T14:00:00Z', updatedAt: '2026-03-14T15:30:00Z', messageCount: 12,
  },
  {
    id: 'sess-3', mode: 'chat', title: 'React vs Vue 性能测试',
    models: ['claude-sonnet-4-6', 'gpt-4o'],
    createdAt: '2026-03-13T09:00:00Z', updatedAt: '2026-03-13T09:45:00Z', messageCount: 4,
  },
  {
    id: 'sess-4', mode: 'discuss', title: '数据库选型：PostgreSQL vs CockroachDB',
    models: ['claude-opus-4-6', 'o3', 'gemini-2.5-pro'],
    createdAt: '2026-03-12T16:00:00Z', updatedAt: '2026-03-12T17:20:00Z', messageCount: 15,
  },
]

export const MOCK_BOOTSTRAP: BootstrapConfig = {
  version: '0.3.0',
  features: ['chat', 'discuss', 'multi-model', 'streaming'],
  providers: [
    { id: 'anthropic', name: 'Anthropic', enabled: true, hasOAuth: false, hasApiKey: true },
    { id: 'openai', name: 'OpenAI', enabled: true, hasOAuth: false, hasApiKey: true },
    { id: 'google', name: 'Google', enabled: true, hasOAuth: true, hasApiKey: true },
    { id: 'deepseek', name: 'DeepSeek', enabled: true, hasOAuth: false, hasApiKey: true },
    { id: 'moonshot', name: 'Moonshot', enabled: true, hasOAuth: false, hasApiKey: true },
    { id: 'gateway', name: 'Gateway', enabled: false, hasOAuth: false, hasApiKey: false },
  ],
  accounts: [
    { id: 'acc-1', provider: 'anthropic', name: 'Personal', isActive: true },
    { id: 'acc-2', provider: 'openai', name: 'Team', email: 'team@example.com', isActive: true },
  ],
  presets: MOCK_PRESETS,
  limits: { maxModels: 5, minModelsChat: 2, minModelsDiscuss: 2 },
}

// Simulated streaming content per model
const MOCK_RESPONSES: Record<string, string[]> = {
  'claude-opus-4-6': [
    '## 分析\n\n这是一个很好的问题。让我从几个维度来分析：\n\n',
    '### 1. 架构层面\n\n首先需要考虑系统的整体架构。我建议采用分层设计：\n\n',
    '- **接入层**: 负责协议适配和流量管理\n- **业务层**: 核心逻辑处理\n- **数据层**: 持久化和缓存\n\n',
    '### 2. 性能考量\n\n在高并发场景下，建议：\n\n1. 使用连接池管理\n2. 引入本地缓存 + Redis 二级缓存\n3. 异步处理非关键路径\n\n',
    '### 3. 可扩展性\n\n为了未来扩展，建议预留插件机制和配置热更新能力。\n\n',
    '> 总结：分层 + 缓存 + 异步是关键三板斧。具体方案需要结合实际流量模型来定。',
  ],
  'gpt-4o': [
    '这个问题涉及到几个核心技术选型：\n\n',
    '**方案概述**\n\n我推荐采用事件驱动架构，主要优势在于：\n\n',
    '1. **解耦性强** — 各模块通过事件通信，互不依赖\n2. **可伸缩** — 单独扩展高负载模块\n3. **可观测** — 事件流天然具备审计能力\n\n',
    '**技术栈建议**\n\n- 消息队列: Kafka (高吞吐) 或 NATS (低延迟)\n- 服务框架: gRPC + HTTP Gateway\n- 存储: PostgreSQL + Redis\n\n',
    '**需要注意的坑**\n\n- 事件顺序性保证\n- 幂等处理\n- 死信队列监控\n\n',
    '综合来看，事件驱动 + gRPC 是当前最佳实践。',
  ],
  'gemini-2.5-pro': [
    '让我用一个结构化的方式来回答这个问题。\n\n',
    '## 解决方案框架\n\n| 维度 | 推荐方案 | 备选方案 |\n|------|---------|----------|\n',
    '| 通信 | gRPC | REST + WebSocket |\n| 存储 | NewSQL | 分库分表 |\n| 缓存 | 多级缓存 | CDN + Edge |\n\n',
    '### 详细设计\n\n**核心思路**: 采用 CQRS 模式分离读写路径。\n\n',
    '写路径走消息队列保证最终一致性，读路径走缓存优先策略。\n\n',
    '```\n[Client] -> [API Gateway] -> [Command Bus] -> [Write DB]\n                           -> [Query Service] -> [Read Cache] -> [Read DB]\n```\n\n',
    '这样可以独立优化读写性能，同时保持数据一致性。',
  ],
  'claude-sonnet-4-6': [
    '好的，这个问题我来简洁回答：\n\n',
    '**核心建议**：选择 **模块化单体** 作为起步架构，而非直接上微服务。\n\n',
    '原因：\n- 团队规模可能还不需要微服务的复杂度\n- 单体内模块化可以随时拆分\n- 部署和调试成本低一个数量级\n\n',
    '**具体步骤**：\n1. 先按业务域划分模块边界\n2. 模块间通过接口通信，不直接引用\n3. 数据库按模块分 schema\n4. 当单一模块成为瓶颈时再拆出\n\n',
    '这比一开始就搞微服务务实得多。',
  ],
  'o3': [
    '我来做一个深度推理分析。\n\n',
    '**前提假设**：\n- 系统需要处理 10K+ QPS\n- 数据一致性要求高\n- 团队有 5-10 人\n\n',
    '**推理链**：\n\n第一步，确定系统的 CAP 偏好 → 对于大多数业务系统，CP 优于 AP。\n\n',
    '第二步，CAP 偏好决定了存储选型 → PostgreSQL + 同步复制。\n\n',
    '第三步，存储选型约束了架构模式 → 不适合纯事件溯源，适合 CQRS。\n\n',
    '第四步，CQRS 需要可靠的事件传递 → Kafka 或 Outbox Pattern。\n\n',
    '**结论**：PostgreSQL + CQRS + Outbox Pattern 是最优解。\n比纯事件驱动更可靠，比单体更可扩展。',
  ],
  'deepseek-r1': [
    '这道题我来分步推理：\n\n',
    '💭 **思考过程**\n\n首先，让我理清需求的核心矛盾：高性能 vs 高一致性 vs 低成本。\n\n',
    '根据 CAP 理论，我们需要在 C 和 A 之间做取舍。考虑到是金融/交易类场景，C 优先。\n\n',
    '**方案**：\n\n采用 **Raft 一致性协议** + **列式存储引擎**：\n\n',
    '- Raft 保证强一致性，3 节点即可\n- 列式存储对分析查询友好\n- 写入走 WAL，读取走 MVCC\n\n',
    '**性能预估**：\n- 写入: ~50K TPS (单 Raft 组)\n- 读取: ~200K QPS (缓存命中)\n- P99 延迟: <10ms\n\n',
    '这个方案在一致性和性能之间取得了最佳平衡。',
  ],
  'deepseek-v3': [
    '快速回答：\n\n',
    '推荐 **FastAPI + PostgreSQL + Redis** 技术栈。\n\n',
    '理由简单：\n1. FastAPI 性能好，开发快\n2. PG 是最强开源关系数据库\n3. Redis 做缓存和消息队列\n\n',
    '部署用 Docker Compose 起步，后续迁移 K8s。\n\n就这样，别过度设计。',
  ],
  'moonshot-v1-128k': [
    '这个问题我从实用角度来回答：\n\n',
    '对于中小团队，我建议：\n\n',
    '1. 用现成的 BaaS 服务（如 Supabase）处理 80% 的后端需求\n2. 只对核心业务逻辑自建服务\n3. 前端用 Next.js 做 SSR\n\n',
    '这样能把开发成本压到最低，同时保持足够的灵活性。\n\n',
    '不要重复造轮子，除非轮子是你的核心竞争力。',
  ],
}

export function getMockResponse(modelId: string): string[] {
  return MOCK_RESPONSES[modelId] || [
    `[${modelId}] 正在思考这个问题...\n\n`,
    '这是一个需要仔细分析的问题。\n\n',
    '我的建议是从实际需求出发，选择最适合团队的方案。\n\n',
    '详细分析需要更多上下文信息。',
  ]
}

// Simulate streaming with delays
export function simulateStream(
  modelId: string,
  onChunk: (text: string) => void,
  onDone: () => void,
): () => void {
  const chunks = getMockResponse(modelId)
  let cancelled = false
  let index = 0

  function next() {
    if (cancelled || index >= chunks.length) {
      if (!cancelled) onDone()
      return
    }
    const chunk = chunks[index++]
    // Stream character by character with small delays for realism
    let charIndex = 0
    function streamChar() {
      if (cancelled) return
      if (charIndex >= chunk.length) {
        // Small pause between paragraphs
        setTimeout(next, 100 + Math.random() * 200)
        return
      }
      // Send 3-8 chars at a time
      const batchSize = 3 + Math.floor(Math.random() * 6)
      const batch = chunk.slice(charIndex, charIndex + batchSize)
      charIndex += batchSize
      onChunk(batch)
      setTimeout(streamChar, 15 + Math.random() * 25)
    }
    streamChar()
  }

  // Random start delay per model (50-500ms)
  setTimeout(next, 50 + Math.random() * 450)

  return () => { cancelled = true }
}

// Simulate discuss phases
export function simulateDiscussPhase1(
  modelId: string,
): Promise<Phase1Summary> {
  return new Promise((resolve) => {
    const delay = 1500 + Math.random() * 2000
    setTimeout(() => {
      resolve({
        model: modelId,
        ok: true,
        brief: {
          approach: `基于 ${modelId.includes('claude') ? '分层架构' : modelId.includes('gpt') ? '事件驱动' : '模块化设计'} 的解决方案`,
          reasoning: '综合考虑团队规模、业务复杂度和可维护性',
          risks: ['过度工程化', '团队学习成本', '迁移复杂度'],
          keyDecisions: ['技术栈选择', '部署策略', '数据模型设计'],
          nextStep: '搭建 PoC 验证核心假设',
        },
        elapsed: delay / 1000,
      })
    }, delay)
  })
}

export function simulateDiscussPhase2(
  reviewer: string,
  target: string,
): Promise<Phase2Review> {
  return new Promise((resolve) => {
    const delay = 1000 + Math.random() * 1500
    setTimeout(() => {
      resolve({
        reviewer,
        target,
        ok: true,
        agreement: '核心架构方向正确，分层/模块化思路值得采纳',
        challenge: '缺少对团队现有技术栈的兼容性考虑，迁移方案不够具体',
        betterOption: '建议先做一个最小验证原型，用 2 周时间验证核心假设',
      })
    }, delay)
  })
}
