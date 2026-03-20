import { STORY_LITE_V2_ROLES, type StoryLiteV2Role } from './types'

/**
 * 构建每个 AI 角色的 prompt
 */
export function buildStoryLiteV2SystemPrompt(role: StoryLiteV2Role): string {
  return STORY_LITE_V2_ROLES[role].systemPrompt
}

export function buildStoryLiteV2UserPrompt(
  seedLabel: string,
  round: number,
  premise: string,
  lastChoice?: { role: string; label: string },
): string {
  const context = lastChoice
    ? `上一轮用户选择了回应${lastChoice.role}："${lastChoice.label}"\n`
    : ''

  return `当前剧情设定：${seedLabel}
${context}
当前情境：${premise}

现在是第${round}轮，请根据你的角色定位输出回复。`
}

/**
 * Mock 数据 - 多 AI 版本
 */
export const STORY_LITE_V2_MOCK_SCENES: Record<string, import('./types').StoryLiteV2Scene> = {
  start: {
    id: 'start',
    chapter: '第 1 幕',
    title: '故事的开始',
    premise: '你站在一个陌生的十字路口，四周弥漫着薄雾。口袋里有一张皱巴巴的纸条，上面写着一个地址和一行小字："不要相信穿红衣服的人"。',
    responses: [
      {
        role: 'guide',
        modelId: 'mock-1',
        modelName: 'Claude',
        text: '纸条上的地址在老城区，距离你 2.3 公里。建议尽快前往，天色暗下来后这片区域会更危险。',
        tone: '冷静',
      },
      {
        role: 'partner',
        modelId: 'mock-2',
        modelName: 'GPT-4',
        text: '等等...你有没有觉得有人在盯着我们？先别急着走，看看周围有没有可疑的人。',
        tone: '紧张',
      },
      {
        role: 'variable',
        modelId: 'mock-3',
        modelName: 'Gemini',
        text: '有趣...那张纸条的背面，你翻过来看过了吗？有时候真正的信息藏在看不见的地方。',
        tone: '神秘',
      },
    ],
    choices: [
      {
        id: 'check-paper',
        label: '翻到纸条背面看看',
        targetRole: 'variable',
        risk: 'risky',
        hint: '可能发现隐藏信息，也可能错过最佳时机',
      },
      {
        id: 'follow-address',
        label: '直接按地址走',
        targetRole: 'guide',
        risk: 'safe',
        hint: '听从指引，最稳妥的选择',
      },
      {
        id: 'look-around',
        label: '先观察周围环境',
        targetRole: 'partner',
        risk: 'safe',
        hint: '谨慎的做法，但可能浪费时间',
      },
    ],
  },
  // === 翻纸条路线 ===
  'check-paper': {
    id: 'check-paper',
    chapter: '第 2 幕',
    title: '背面的秘密',
    premise: '你翻到纸条背面，发现用铅笔写着一串数字：「0315」。这是某个保险箱的密码，还是别的什么？',
    responses: [
      {
        role: 'guide',
        modelId: 'mock-1',
        modelName: 'Claude',
        text: '0315 可能是日期（3 月 15 日），也可能是密码。地址附近的银行保险箱值得调查。',
        tone: '分析',
      },
      {
        role: 'partner',
        modelId: 'mock-2',
        modelName: 'GPT-4',
        text: '这太巧了吧...等等，3 月 15 日不就是今天吗？！',
        tone: '震惊',
      },
      {
        role: 'variable',
        modelId: 'mock-3',
        modelName: 'Gemini',
        text: '你知道吗，用铅笔写字的人，通常...不打算让它保存太久。',
        tone: '暗示',
      },
    ],
    choices: [
      {
        id: 'find-bank',
        label: '寻找附近的银行',
        targetRole: 'guide',
        risk: 'safe',
        hint: '按指引行动',
      },
      {
        id: 'ask-variable',
        label: '追问变量知道什么',
        targetRole: 'variable',
        risk: 'dangerous',
        hint: '高风险，可能获得关键信息',
      },
      {
        id: 'calm-partner',
        label: '先安抚伙伴情绪',
        targetRole: 'partner',
        risk: 'safe',
        hint: '稳定团队状态',
      },
    ],
  },
  // === 直接走路线 ===
  'follow-address': {
    id: 'follow-address',
    chapter: '第 2 幕',
    title: '陌生的街道',
    premise: '地址指向老城区的一栋废弃洋楼。门虚掩着，里面传来微弱的灯光。纸条上的地址就是这里。',
    responses: [
      {
        role: 'guide',
        modelId: 'mock-1',
        modelName: 'Claude',
        text: '目标确认。建议先侦察再进入，注意不要暴露行踪。',
        tone: '专业',
      },
      {
        role: 'partner',
        modelId: 'mock-2',
        modelName: 'GPT-4',
        text: '那灯...有人在里面？我们要不要先报警？',
        tone: '担忧',
      },
      {
        role: 'variable',
        modelId: 'mock-3',
        modelName: 'Gemini',
        text: '你有没有想过，可能有人...一直在等你来到这里？',
        tone: '诡异',
      },
    ],
    choices: [
      {
        id: 'knock-door',
        label: '敲门',
        targetRole: 'guide',
        risk: 'safe',
        hint: '礼貌但可能打草惊蛇',
      },
      {
        id: 'sneak-in',
        label: '偷偷进去',
        targetRole: 'variable',
        risk: 'risky',
        hint: '可能发现秘密，也可能被发现',
      },
      {
        id: 'reassure-partner',
        label: '让伙伴在外面等',
        targetRole: 'partner',
        risk: 'risky',
        hint: '保护伙伴，但可能让他担心',
      },
    ],
  },
  // === 观察环境路线 ===
  'look-around': {
    id: 'look-around',
    chapter: '第 2 幕',
    title: '意外的发现',
    premise: '你在附近转悠，发现一个穿红衣服的人匆匆走过。他似乎没注意到你，手里拿着一个和你纸条上相似的地址。',
    responses: [
      {
        role: 'guide',
        modelId: 'mock-1',
        modelName: 'Claude',
        text: '目标出现。是否跟踪取决于你的任务优先级——是收集信息，还是抵达目的地。',
        tone: '中立',
      },
      {
        role: 'partner',
        modelId: 'mock-2',
        modelName: 'GPT-4',
        text: '红衣人...纸条上说不要相信穿红衣服的！我们得小心！',
        tone: '警惕',
      },
      {
        role: 'variable',
        modelId: 'mock-3',
        modelName: 'Gemini',
        text: "也许...他也在找同一个地方。或者，他就是写纸条的人。",
        tone: '挑逗',
      },
    ],
    choices: [
      {
        id: 'follow-him',
        label: '跟踪红衣人',
        targetRole: 'variable',
        risk: 'dangerous',
        hint: '高风险高回报',
      },
      {
        id: 'ignore-continue',
        label: '无视，继续去地址',
        targetRole: 'guide',
        risk: 'safe',
        hint: '避免正面接触',
      },
      {
        id: 'protect-partner',
        label: '带伙伴离开这里',
        targetRole: 'partner',
        risk: 'safe',
        hint: '保护优先',
      },
    ],
  },
  // === 结局场景 ===
  'ending-good': {
    id: 'ending-good',
    chapter: '终章',
    title: '真相大白',
    premise: '你成功解开了谜团。原来这一切是一个谜题游戏的入口，纸条是邀请函。恭喜你完成了挑战！',
    responses: [],
    choices: [],
    ending: {
      kind: 'good',
      title: '完美通关',
      summary: '你凭借智慧和勇气找到了真相，获得了进入下一关的资格。',
      epilogue: '但这只是开始... 更大的谜团在等着你。',
    },
  },
  'ending-normal': {
    id: 'ending-normal',
    chapter: '终章',
    title: '平凡的一天',
    premise: '你安全度过了这一天，但没有发现什么特别的东西。纸条上的地址指向一个废弃的房子，里面什么都没有。',
    responses: [],
    choices: [],
    ending: {
      kind: 'normal',
      title: '无功无过',
      summary: '平安无事，但你总觉得错过了什么重要的东西。',
    },
  },
  'ending-bad': {
    id: 'ending-bad',
    chapter: '终章',
    title: '陷阱',
    premise: '你发现自己掉进了一个陷阱。那个穿红衣服的人微笑着看着你："欢迎来到游戏"。',
    responses: [],
    choices: [],
    ending: {
      kind: 'bad',
      title: 'GAME OVER',
      summary: '你成为了别人游戏的一部分。也许应该更谨慎一点的。',
    },
  },
  'ending-mystery': {
    id: 'ending-mystery',
    chapter: '终章',
    title: '未解之谜',
    premise: '故事结束了，但你仍然有很多疑问。纸条是谁给的？红衣人是谁？这一切意味着什么？',
    responses: [],
    choices: [],
    ending: {
      kind: 'mystery',
      title: '悬念待续',
      summary: '有些问题注定没有答案... 或者说，答案还没到揭晓的时候。',
      epilogue: '也许在某个平行时空，你会做出不同的选择。',
    },
  },
}

/** 简单的分支映射表 */
export const STORY_LITE_V2_BRANCHES: Record<string, Record<string, string>> = {
  start: {
    'check-paper': 'check-paper',
    'follow-address': 'follow-address',
    'look-around': 'look-around',
  },
  'check-paper': {
    'find-bank': 'ending-good',
    'ask-variable': 'ending-mystery',
    'calm-partner': 'ending-normal',
  },
  'follow-address': {
    'knock-door': 'ending-good',
    'sneak-in': 'ending-bad',
    'reassure-partner': 'ending-normal',
  },
  'look-around': {
    'follow-him': 'ending-mystery',
    'ignore-continue': 'ending-normal',
    'protect-partner': 'ending-good',
  },
}
