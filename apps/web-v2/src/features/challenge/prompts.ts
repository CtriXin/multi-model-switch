// Daily Challenge prompt templates

import type { DailyCategory, TopicCandidate, UserProfile, DebateMessage } from './types'

export function buildTopicGeneratorPrompt(opts: {
  dateSeed: string
  categories: DailyCategory[]
  historyDigest: string
  exclusions: string[]
  profile?: UserProfile | null
}): string {
  const exclusionList = opts.exclusions.length
    ? `最近 7 天已用话题（必须避开）：\n${opts.exclusions.map(t => `- ${t}`).join('\n')}`
    : '无需排重。'

  const profileHint = opts.profile ? buildProfileHint(opts.profile) : ''

  return `你是一个辩论话题生成器。根据以下信息生成 6 个有争议性的思辨话题。

日期种子：${opts.dateSeed}
用户偏好品类：${opts.categories.join(', ')}
${exclusionList}

用户近期讨论摘要：
${opts.historyDigest || '暂无历史。'}
${profileHint}
要求：
- 每个话题必须有明确的正反两面
- 不涉及敏感政治或宗教争议
- 适合 3 分钟思考
- 6 个话题中：4 个命中用户偏好品类，2 个来自非偏好品类（保持新鲜感）
- 话题要具体，不要太抽象
- hook 字段：一句话（≤15字）勾住用户兴趣，要有冲突感
- difficulty：casual=日常话题 / deep=需要深入思考 / philosophical=涉及价值观
- controversy：1-5，5=极度有争议
- whyRecommended：如果有用户画像，简短说明为什么推荐这个话题

严格按以下 JSON 格式输出，不要其他内容：
{
  "candidates": [
    {
      "id": "topic-1",
      "title": "话题标题（10-20字）",
      "prompt": "一句话描述这个辩题的核心张力",
      "sideA": "正方立场（一句话）",
      "sideB": "反方立场（一句话）",
      "category": "tech",
      "hook": "≤15字的冲突勾子",
      "difficulty": "casual|deep|philosophical",
      "controversy": 3,
      "whyRecommended": "推荐理由（可选）"
    }
  ]
}`
}

function buildProfileHint(profile: UserProfile): string {
  const parts: string[] = ['\n用户画像（用于个性化推荐）：']

  // Category preference
  const catEntries = Object.entries(profile.categoryHits).sort((a, b) => (b[1] as number) - (a[1] as number))
  if (catEntries.length) {
    parts.push(`- 最常参与品类：${catEntries.slice(0, 3).map(([k, v]) => `${k}(${v}次)`).join(', ')}`)
  }

  // Dismissed categories
  const dismissEntries = Object.entries(profile.categoryDismisses).sort((a, b) => (b[1] as number) - (a[1] as number))
  if (dismissEntries.length) {
    parts.push(`- 常跳过品类：${dismissEntries.slice(0, 3).map(([k, v]) => `${k}(${v}次)`).join(', ')}`)
  }

  // Keywords
  if (profile.topKeywords.length) {
    parts.push(`- 关注关键词：${profile.topKeywords.slice(0, 8).join(', ')}`)
  }

  // Stance
  const total = profile.stanceDistribution.support + profile.stanceDistribution.oppose + profile.stanceDistribution.mixed
  if (total > 2) {
    const dominant = profile.stanceDistribution.support > profile.stanceDistribution.oppose ? '偏支持' : '偏反对'
    parts.push(`- 立场倾向：${dominant}（可以出一些挑战其惯性立场的话题）`)
  }

  // Thinking axes
  const axisEntries = Object.entries(profile.avgAxes)
  if (axisEntries.length) {
    const extreme = axisEntries.filter(([_, v]) => Math.abs((v as number) - 50) > 15)
    if (extreme.length) {
      parts.push(`- 思维偏向：${extreme.map(([k, v]) => `${k}=${v}`).join(', ')}（可以出挑战这些倾向的话题）`)
    }
  }

  return parts.length > 1 ? parts.join('\n') : ''
}

/** 多轮辩论 prompt — 包含历史消息上下文 */
export function buildRoundDebaterPrompt(opts: {
  topic: TopicCandidate
  stance: 'pro' | 'con'
  round: number
  history: DebateMessage[]
}): string {
  const side = opts.stance === 'pro' ? opts.topic.sideA : opts.topic.sideB
  const roleLabel = opts.stance === 'pro' ? '正方' : '反方'
  const roundLabel = opts.round === 1 ? '一辩' : '二辩'

  const historyText = opts.history
    .filter(m => m.status === 'done')
    .map(m => `【${m.label}${m.isUser ? '（用户）' : '（AI）'}】\n${m.text}`)
    .join('\n\n')

  return `你是一场辩论中的${roleLabel}${roundLabel}。

辩题：${opts.topic.title}
${opts.topic.prompt}

你的立场：${side}

${historyText ? `前面的辩论记录：\n${historyText}\n` : ''}
${opts.round === 1
  ? `这是开场。请用 80-120 字阐述你的核心论点，列出 3 个要点。`
  : `这是第二轮。请针对对方上一轮的发言进行回应，指出其漏洞，强化你的论点。80-120 字核心回应 + 2-3 个反驳要点。`
}

要求：
- 像真人辩手一样说话，有锋芒有逻辑
- 直接回应对方的具体论点，不要空泛
- 不要使用 XML 标签（如 <BRIEF>）或 JSON 格式
- 直接输出你的辩论发言，不需要标题`
}

export function buildModeratorTaggerPrompt(opts: {
  topic: TopicCandidate
  proText: string
  conText: string
  userStance: string
  userReason: string
}): string {
  return `你同时扮演两个角色：辩论裁判 + 思维观察者。

辩题：${opts.topic.title}
${opts.topic.prompt}

正方发言：
${opts.proText}

反方发言：
${opts.conText}

用户立场：${opts.userStance}
用户理由：${opts.userReason}

任务 1 - 裁判总结：
- strongestPointFor：正方最强论点（一句话）
- strongestPointAgainst：反方最强论点（一句话）
- decisiveQuestion：这场辩论的关键决策问题（一句话）
- oneLineVerdict：一句话总结（不偏袒任何一方）

任务 2 - 思维快照（基于用户的立场选择和理由推断）：
对用户的 4 个思维维度打分（0-100，50 为中性）：
- evidence_intuition：0=纯直觉 100=纯证据驱动
- decisive_exploratory：0=极度果断 100=极度探索
- risk_seeking_risk_aware：0=极度冒险 100=极度谨慎
- self_systems：0=纯自我聚焦 100=纯系统思维

每个维度附带 confidence（0-1）和 note（一句话解释）。
最后给出 summary（一句话总结用户的思维倾向）和 dominantAxes（偏离 50 最远的 1-2 个轴 ID）。

严格按以下 JSON 格式输出，不要其他内容：
{
  "takeaway": {
    "strongestPointFor": "...",
    "strongestPointAgainst": "...",
    "decisiveQuestion": "...",
    "oneLineVerdict": "..."
  },
  "thinkingSnapshot": {
    "axes": {
      "evidence_intuition": { "score": 65, "confidence": 0.7, "note": "..." },
      "decisive_exploratory": { "score": 40, "confidence": 0.6, "note": "..." },
      "risk_seeking_risk_aware": { "score": 55, "confidence": 0.5, "note": "..." },
      "self_systems": { "score": 70, "confidence": 0.6, "note": "..." }
    },
    "dominantAxes": ["self_systems"],
    "summary": "..."
  }
}`
}

export function buildWeeklyReflectorPrompt(cardSummaries: string): string {
  return `你是一位思维教练，需要根据用户本周的 7 张观点卡摘要，生成一句话周度回顾。

本周观点卡摘要：
${cardSummaries}

要求：
- 不超过 50 字
- 用鼓励但诚实的语气
- 聚焦于本周最明显的思维特征变化
- 不要使用"成长"这个词，用"清晰"或"轮廓"

只输出一句话，不要其他内容。`
}
