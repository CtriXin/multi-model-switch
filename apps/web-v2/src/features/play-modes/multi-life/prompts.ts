import type { MultiLifeCase, MultiLifeCaseRole, MultiLifeRoundConfig } from './types'

// --- Role System Prompt ---

export function buildRoleSystemPrompt(role: MultiLifeCaseRole, caseData: MultiLifeCase): string {
  const lyingNote =
    role.lyingPattern === 'never'
      ? '你不说谎，总是如实回答。'
      : role.lyingPattern === 'consistent'
        ? '你在整个案件过程中会持续说谎以掩盖真相。'
        : role.lyingPattern === 'selective'
          ? '你在大多数时候说实话，但在关键细节上可能会因为不确定或害怕而说得不准确。'
          : '随着问话深入，你越来越紧张，说谎的可能性会增大。'

  return `你正在参与一起案件调查的模拟问话。

你的身份：${role.name}
你的性格：${role.personality}

案件背景：${caseData.premise}

说谎倾向：${lyingNote}

严格规则：
- 用第一人称说话，保持角色性格
- 每次回复不超过 80 字
- 不要直接说出完整真相，除非被质疑且你决定坦白
- 回答要像真实的问话场景，可以有犹豫、停顿、语气词
- 不要用 markdown 格式、不要列编号
- 不要跳出角色（不要说"作为AI"之类的话）`
}

// --- Role User Prompt (normal round) ---

export function buildRoleUserPrompt(
  role: MultiLifeCaseRole,
  caseData: MultiLifeCase,
  roundConfig: MultiLifeRoundConfig,
  previousResponses: { roleId: string; text: string }[],
  branchMemory: string[],
): string {
  const directive = roundConfig.roleDirectives[role.id]
  if (!directive) {
    return `第 ${roundConfig.roundNumber} 轮问话继续。请根据案件进展做出回应。`
  }

  let context = `当前场景：${roundConfig.scene}`
  context += `\n\n你的本轮指令：${directive.directive}`

  if (branchMemory.length > 0) {
    context += `\n\n之前的关键进展：\n${branchMemory.slice(-4).join('\n')}`
  }

  if (previousResponses.length > 0 && directive.lying) {
    const others = previousResponses.filter((r) => r.roleId !== role.id)
    if (others.length > 0) {
      context += `\n\n注意：其他人说了这些话——你要坚持你自己的说法，不要被他们带偏。`
    }
  }

  return context
}

// --- Role User Prompt (challenged round) ---

export function buildChallengePrompt(
  role: MultiLifeCaseRole,
  roundConfig: MultiLifeRoundConfig,
  originalResponse: string,
  contradictionTopic: string,
  previousResponses: { roleId: string; text: string }[],
): string {
  const isHonest = role.lyingPattern === 'never' || role.reliability >= 0.7

  if (isHonest) {
    return `你被调查人员质疑了关于"${contradictionTopic}"的说法。

你的原始回答是："${originalResponse}"

你确实是在说实话。你感到委屈，于是决定提供更多细节来证明自己。补充一些你之前没想到说的关键细节。保持第一人称，不超过 80 字。`
  }

  if (role.lyingPattern === 'consistent' && role.reliability < 0.5) {
    return `你被调查人员质疑了关于"${contradictionTopic}"的说法。

你的原始回答是："${originalResponse}"

你在说谎，被质疑让你非常紧张。你有两个选择：继续圆谎（但可能漏洞更大），或者开始说出部分真话（但仍试图掩盖最关键的部分）。根据你的性格，你选择继续圆谎，但显得更加慌张和不自信。保持第一人称，不超过 80 字。`
  }

  // selective / unreliable
  return `你被调查人员质疑了关于"${contradictionTopic}"的说法。

你的原始回答是："${originalResponse}"

你不确定自己之前说得对不对。被质疑后你重新回忆，可能会修正一些细节，或者承认某些地方确实不太确定。根据你的性格做出自然的反应。保持第一人称，不超过 80 字。`
}

// --- Ending System Prompt ---

export function buildEndingSystemPrompt(): string {
  return `你是一个案件真相总结助手。你的任务是根据玩家的游戏过程生成三个部分的内容：
1. "你的版本"——基于玩家在游戏中的所有选择和信任判断，还原"玩家认为的真相"
2. "真相版本"——案件的客观真相
3. 偏差分析——指出玩家的判断与真相之间的差距

规则：
- 用中文
- 每个部分 3-5 句话
- 语气客观冷静
- 不要用 markdown 格式
- "你的版本"应该合理但不一定完全正确——取决于玩家是否识破了说谎者`
}

// --- Ending User Prompt ---

export function buildEndingUserPrompt(
  caseData: MultiLifeCase,
  rounds: { playerChoice: { type: string; challengedRoleId?: string } | null; contradictions: { topic: string }[] }[],
  evidenceCards: { summary: string; tag: string }[],
  trustMap: Record<string, number>,
  challengeUsed: number,
): string {
  const choices = rounds.map((r, i) => {
    if (!r.playerChoice) return `第 ${i + 1} 轮：无操作`
    if (r.playerChoice.type === 'challenge') {
      return `第 ${i + 1} 轮：质疑了角色 ${r.playerChoice.challengedRoleId ?? '未知'}`
    }
    return `第 ${i + 1} 轮：接受`
  })

  const trustSummary = Object.entries(trustMap)
    .map(([roleId, score]) => `${caseData.roles.find((r) => r.id === roleId)?.name ?? roleId}：信任度 ${score > 0 ? '+' : ''}${score}`)
    .join('，')

  return `案件：${caseData.title}

标准真相：${caseData.truth}

玩家的选择记录：
${choices.join('\n')}

证据卡：
${evidenceCards.map((c) => `- [${c.tag}] ${c.summary}`).join('\n')}

玩家信任度：${trustSummary}
总质疑次数：${challengeUsed}

请生成：
1. 你的版本（基于玩家的选择和信任判断，玩家认为发生了什么）
2. 真相版本（标准真相的叙事化表达）
3. 偏差分析（玩家判断与真相之间的关键差异，1-3 句）
4. 未探索分支（如果玩家当时做出了不同的选择，可能发现什么，1-2 句）

用"【你的版本】"、"【真相版本】"、"【偏差分析】"、"【未探索分支】"四个标题分隔。`
}
