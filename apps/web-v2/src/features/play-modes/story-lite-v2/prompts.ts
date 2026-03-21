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
    ? `上一轮用户选择站在${lastChoice.role}这一边，采取了动作："${lastChoice.label}"。\n`
    : ''

  return `当前剧情设定：${seedLabel}
${context}
当前情境：${premise}

现在是第${round}轮。
请严格根据你的角色定位，只输出一段简短判断。

三种角色分工是：
- 引路人：推进主线，给出最直接的任务方向
- 伙伴：指出情感与关系代价
- 变量：揭示异常细节、隐藏规则或第三种可能

要求：
- 中文输出，保持短促有张力
- 不要复述题面
- 不要替用户做决定
- 不要和其他角色说同一种话`
}

/**
 * Mock 数据 - 多 AI 版本
 */
export const STORY_LITE_V2_MOCK_SCENES: Record<string, import('./types').StoryLiteV2Scene> = {
  start: {
    id: 'start',
    chapter: '第 1 幕',
    title: '双重求救',
    premise: '你刚得到一枚可以稳定整座城市防御网的密钥。倒计时 40 分钟后，主城区护盾会崩溃。与此同时，母亲打来电话，说她被困在旧城区的地铁站。监控画面里还闪过一道不该出现的第三信号，像是有人故意把你逼进这场二选一。',
    responses: [
      {
        role: 'guide',
        modelId: 'mock-1',
        modelName: 'Claude',
        text: '先去主控塔。护盾一旦失守，整座城的生命线都会断掉，这才是主线。',
        tone: '决断',
      },
      {
        role: 'partner',
        modelId: 'mock-2',
        modelName: 'GPT-4',
        text: '可电话那头是你母亲。就算你救下整座城，失去她以后，你真的还能继续站着吗？',
        tone: '拉扯',
      },
      {
        role: 'variable',
        modelId: 'mock-3',
        modelName: 'Gemini',
        text: '第三信号比求救电话早出现了七码。有人提前知道你会被迫二选一。',
        tone: '诡异',
      },
    ],
    choices: [
      {
        id: 'secure-shield',
        label: '先去主控塔，稳住城市护盾',
        targetRole: 'guide',
        risk: 'safe',
        hint: '主线止损最快，但你要接受情感代价',
      },
      {
        id: 'save-mother',
        label: '先去旧城区，把母亲带出来',
        targetRole: 'partner',
        risk: 'risky',
        hint: '守住最重要的人，但全城窗口会继续缩短',
      },
      {
        id: 'trace-signal',
        label: '先追查那道第三信号',
        targetRole: 'variable',
        risk: 'dangerous',
        hint: '也许能打破二选一，也可能两边都来不及',
      },
    ],
  },
  'secure-shield': {
    id: 'secure-shield',
    chapter: '第 2 幕',
    title: '护盾核心',
    premise: '主控塔内电弧乱跳，备用护盾最多还能撑 12 分钟。母亲的电话已经断成杂音，但日志里出现了一条隐藏的维护通道，终点恰好通往旧城区地铁枢纽。',
    responses: [
      {
        role: 'guide',
        modelId: 'mock-1',
        modelName: 'Claude',
        text: '先切换备用护盾，把城市保住。主线必须先稳定，不然任何救援都会失去意义。',
        tone: '稳控',
      },
      {
        role: 'partner',
        modelId: 'mock-2',
        modelName: 'GPT-4',
        text: '如果你现在肯花十秒重新拨回去，也许还能听见她最后一次回应。',
        tone: '牵挂',
      },
      {
        role: 'variable',
        modelId: 'mock-3',
        modelName: 'Gemini',
        text: '隐藏通道不是给维修工留的，更像是给“知道真相的人”准备的捷径。',
        tone: '诱导',
      },
    ],
    choices: [
      {
        id: 'reroute-shield',
        label: '立刻切换备用护盾，先把城市稳住',
        targetRole: 'guide',
        risk: 'safe',
        hint: '你会守住大局，但可能错过最重要的人',
      },
      {
        id: 'call-mother',
        label: '先接通母亲线路，赌那条维护通道能同时救两边',
        targetRole: 'partner',
        risk: 'risky',
        hint: '关系优先，但你必须在极短时间内重新规划主线',
      },
      {
        id: 'open-maintenance-path',
        label: '沿隐藏维护通道追下去，找出谁在布这个局',
        targetRole: 'variable',
        risk: 'dangerous',
        hint: '可能发现第三条路，也可能直接掉进局里',
      },
    ],
  },
  'save-mother': {
    id: 'save-mother',
    chapter: '第 2 幕',
    title: '旧城区地铁',
    premise: '你赶到旧城区地铁口，母亲被困在半坍塌的站台里。远处已经能看见城市护盾闪烁失真，附近一座废弃变电站却还亮着异常的应急灯。',
    responses: [
      {
        role: 'guide',
        modelId: 'mock-1',
        modelName: 'Claude',
        text: '那座废弃变电站也许能给主网续命。只要抢到几分钟，你就不用真的牺牲一边。',
        tone: '拆解',
      },
      {
        role: 'partner',
        modelId: 'mock-2',
        modelName: 'GPT-4',
        text: '先把她带出去。你不是一台机器，你没资格把母亲变成可接受的损耗。',
        tone: '坚持',
      },
      {
        role: 'variable',
        modelId: 'mock-3',
        modelName: 'Gemini',
        text: '应急灯不是地铁系统的颜色。有人比你更早到了这里，而且在等你往里走。',
        tone: '警告',
      },
    ],
    choices: [
      {
        id: 'borrow-substation',
        label: '先接管废弃变电站，抢出同时救两边的时间',
        targetRole: 'guide',
        risk: 'risky',
        hint: '这是主线补救方案，但你必须把母亲暂时留在原地',
      },
      {
        id: 'extract-now',
        label: '立刻带母亲撤离，不再赌城市系统还撑得住',
        targetRole: 'partner',
        risk: 'safe',
        hint: '能立刻保住她，但城市会为你的选择付出代价',
      },
      {
        id: 'follow-red-led',
        label: '顺着异常灯源深入站台，看看谁在故意把你引来',
        targetRole: 'variable',
        risk: 'risky',
        hint: '也许能看见幕后黑手，也可能让你和母亲一起困死在里面',
      },
    ],
  },
  'trace-signal': {
    id: 'trace-signal',
    chapter: '第 2 幕',
    title: '第三条路',
    premise: '你顺着第三信号追到一间废弃调度室，屏幕上同时挂着主控塔和旧城区地铁的实时画面。桌上留着一条手写字条：\"如果你还在二选一，说明你来晚了。\"',
    responses: [
      {
        role: 'guide',
        modelId: 'mock-1',
        modelName: 'Claude',
        text: '先解码调度台，把第三路径找出来。只要路线是真的，主线就能被重写。',
        tone: '锁定',
      },
      {
        role: 'partner',
        modelId: 'mock-2',
        modelName: 'GPT-4',
        text: '别让谜题把你变得麻木。你追真相的每一分钟，你母亲都还被困在那边。',
        tone: '催逼',
      },
      {
        role: 'variable',
        modelId: 'mock-3',
        modelName: 'Gemini',
        text: '这字迹和你的笔记一模一样。也许布这个局的人，从来就不是别人。',
        tone: '悖论',
      },
    ],
    choices: [
      {
        id: 'decode-route',
        label: '解开调度台，赌这里藏着同时救两边的第三方案',
        targetRole: 'variable',
        risk: 'dangerous',
        hint: '这是最高风险的一步，但也最可能打破题面',
      },
      {
        id: 'return-mainline',
        label: '放弃追查，带着现有信息回主控塔执行主线',
        targetRole: 'guide',
        risk: 'safe',
        hint: '重新拥抱主线，但你已经消耗掉了宝贵时间',
      },
      {
        id: 'keep-mother-awake',
        label: '先接通母亲，确认她那边是否也出现了第三信号',
        targetRole: 'partner',
        risk: 'risky',
        hint: '情感优先，也可能让你听见一段不该存在的真相',
      },
    ],
  },
  'ending-good': {
    id: 'ending-good',
    chapter: '终章',
    title: '第三答案',
    premise: '你没有接受题面给你的二选一。通过隐藏通道与应急路由，你既稳住了护盾，也把母亲从旧城区带了出来。只是最后离开时，你在调度室门口看见一行尚未干透的字：\"这次你终于学会怀疑题目本身。\"',
    responses: [],
    choices: [],
    ending: {
      kind: 'good',
      title: '第三答案',
      summary: '你没有在主线、亲情和异常之间被迫割舍，而是硬生生找出了第三条路。',
      epilogue: '真正的强大，不是选得更狠，而是敢怀疑别人给你的选项。',
    },
  },
  'ending-normal': {
    id: 'ending-normal',
    chapter: '终章',
    title: '代价成立',
    premise: '你守住了一边，却亲手放掉了另一边。城市没有完全崩溃，母亲也没有真的死去，但你很清楚，从这一刻开始，有些裂痕永远不会自己愈合。',
    responses: [],
    choices: [],
    ending: {
      kind: 'normal',
      title: '代价成立',
      summary: '你做出了能自圆其说的选择，却也接受了它必然留下的损耗。',
    },
  },
  'ending-bad': {
    id: 'ending-bad',
    chapter: '终章',
    title: '两边皆失',
    premise: '你踩进了别人布好的陷阱。旧城区塌方，主控塔也在同一时间失守。最后的广播里只剩下一句平静的通知：\"感谢配合完成本轮价值压测。\"',
    responses: [],
    choices: [],
    ending: {
      kind: 'bad',
      title: '两边皆失',
      summary: '你试图赌一个更大的答案，却被题面背后的操盘者吞掉了全部筹码。',
    },
  },
  'ending-mystery': {
    id: 'ending-mystery',
    chapter: '终章',
    title: '题面之外',
    premise: '你摸到了布题者留下的边缘，却还没抓住全貌。调度室里留下的数据、字迹和你的过往记录全都对得上，却没有一处能完整解释这一切。有人在测试你，或者说，有什么东西一直在等你学会不按题面作答。',
    responses: [],
    choices: [],
    ending: {
      kind: 'mystery',
      title: '题面之外',
      summary: '你看见了这场两难背后的手，却还没来得及看清它的脸。',
      epilogue: '最危险的变量，不是选择本身，而是谁给了你这些选择。',
    },
  },
}

/** 简单的分支映射表 */
export const STORY_LITE_V2_BRANCHES: Record<string, Record<string, string>> = {
  start: {
    'secure-shield': 'secure-shield',
    'save-mother': 'save-mother',
    'trace-signal': 'trace-signal',
  },
  'secure-shield': {
    'reroute-shield': 'ending-normal',
    'call-mother': 'ending-good',
    'open-maintenance-path': 'ending-mystery',
  },
  'save-mother': {
    'borrow-substation': 'ending-good',
    'extract-now': 'ending-normal',
    'follow-red-led': 'ending-bad',
  },
  'trace-signal': {
    'decode-route': 'ending-good',
    'return-mainline': 'ending-bad',
    'keep-mother-awake': 'ending-mystery',
  },
}
