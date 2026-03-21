import {
  STORY_LITE_V2_ROLES,
  type StoryLiteV2Choice,
  type StoryLiteV2Response,
  type StoryLiteV2Role,
  type StoryLiteV2Scene,
} from './types'

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

function normalizeSeedLabel(seedLabel: string) {
  const trimmed = seedLabel.trim().replace(/\s+/g, ' ')
  const withoutTrailingDots = trimmed.replace(/[.。!！?？~～…]+$/gu, '')
  return withoutTrailingDots || '你突然被抛进一场高压两难'
}

function formatSeedHook(seedLabel: string) {
  const normalized = normalizeSeedLabel(seedLabel)
  if (/^(假如|如果|当|设想)/.test(normalized)) return normalized
  return `假如${normalized}`
}

function buildSeededResponses(
  entries: Array<{ role: StoryLiteV2Role; modelName: string; text: string; tone: string }>,
): StoryLiteV2Response[] {
  return entries.map((entry, index) => ({
    ...entry,
    modelId: `mock-${index + 1}`,
  }))
}

function buildSeededChoices(sceneId: string): StoryLiteV2Choice[] {
  if (sceneId === 'start') {
    return [
      {
        id: 'secure-shield',
        label: '先稳住主线，别让局面继续失控',
        targetRole: 'guide',
        risk: 'safe',
        hint: '先止损，但你得接受关系代价会被继续拖欠',
      },
      {
        id: 'save-mother',
        label: '先保住最重要的人或关系',
        targetRole: 'partner',
        risk: 'risky',
        hint: '你先接住人心，但主线窗口会因此继续缩短',
      },
      {
        id: 'trace-signal',
        label: '先追查题面里最不合理的异常',
        targetRole: 'variable',
        risk: 'dangerous',
        hint: '也许能撕开第三条路，也可能两边一起加速恶化',
      },
    ]
  }

  if (sceneId === 'secure-shield') {
    return [
      {
        id: 'reroute-shield',
        label: '继续把主线推进到底，先把盘面彻底稳住',
        targetRole: 'guide',
        risk: 'safe',
        hint: '大局最先被保住，但你可能亲手放大关系裂痕',
      },
      {
        id: 'call-mother',
        label: '抽身处理关系代价，别让最重要的人先掉队',
        targetRole: 'partner',
        risk: 'risky',
        hint: '你会补回人的那一边，但主线代价会马上来讨债',
      },
      {
        id: 'open-maintenance-path',
        label: '掉头追异常点，赌题面之外还有出口',
        targetRole: 'variable',
        risk: 'dangerous',
        hint: '有机会改写二选一，也可能让局面彻底失控',
      },
    ]
  }

  if (sceneId === 'save-mother') {
    return [
      {
        id: 'borrow-substation',
        label: '回头补主线，争取把失去的时间抢回来',
        targetRole: 'guide',
        risk: 'risky',
        hint: '你会重新接盘，但眼前的人和关系又得被暂时放下',
      },
      {
        id: 'extract-now',
        label: '继续把关系放在第一位，不再追加代价',
        targetRole: 'partner',
        risk: 'safe',
        hint: '你守住最重要的人，但系统层面的损耗会被坐实',
      },
      {
        id: 'follow-red-led',
        label: '顺着异常继续往下查，看看谁在设计这一切',
        targetRole: 'variable',
        risk: 'risky',
        hint: '也许能看见幕后规则，也可能把现在仅有的安全感一起掀翻',
      },
    ]
  }

  if (sceneId === 'trace-signal') {
    return [
      {
        id: 'decode-route',
        label: '继续深挖异常，赌第三条路真的存在',
        targetRole: 'variable',
        risk: 'dangerous',
        hint: '最接近跳出题面，但也最可能一脚踩空',
      },
      {
        id: 'return-mainline',
        label: '带着新线索回主线，把局面重新接住',
        targetRole: 'guide',
        risk: 'safe',
        hint: '你回到可控路径，但已经被异常拖走了不少时间',
      },
      {
        id: 'keep-mother-awake',
        label: '先确认最重要的人或关系还来不来得及守住',
        targetRole: 'partner',
        risk: 'risky',
        hint: '你会先照顾人的那一边，也可能因此错过唯一出口',
      },
    ]
  }

  return []
}

export function buildStoryLiteV2SeededScene(seedLabel: string, sceneId: string): StoryLiteV2Scene {
  const hook = formatSeedHook(seedLabel)

  if (sceneId === 'secure-shield') {
    return {
      id: 'secure-shield',
      chapter: '第 2 幕',
      title: '主线加压',
      premise: `你决定先沿主线推进「${hook}」。表面局势暂时被按住了，但你最在乎的人或关系开始掉队，而那个异常点也没有消失，反而像是在提醒你：题面根本不是完整的。`,
      responses: buildSeededResponses([
        { role: 'guide', modelName: 'Claude', text: '别松手。你既然先押主线，就要把最直接的失控点彻底压住。', tone: '推进' },
        { role: 'partner', modelName: 'GPT-4', text: '你现在稳住的是盘面，不是人心。真正会在事后留下裂痕的部分，已经开始发生了。', tone: '提醒' },
        { role: 'variable', modelName: 'Gemini', text: '最奇怪的是，异常点并没有因为你押主线就退场，它像是在故意等你回头看它。', tone: '逼近' },
      ]),
      choices: buildSeededChoices(sceneId),
    }
  }

  if (sceneId === 'save-mother') {
    return {
      id: 'save-mother',
      chapter: '第 2 幕',
      title: '关系优先',
      premise: `你先选择守住关系线「${hook}」。你在乎的人、承诺或底线暂时被接住了，但主线压力迅速上涨，那个异常细节也越来越像有人故意把你引到这里。`,
      responses: buildSeededResponses([
        { role: 'guide', modelName: 'Claude', text: '你先救了人的这一边，现在得立刻想办法把主线损耗追回来。', tone: '补救' },
        { role: 'partner', modelName: 'GPT-4', text: '至少这一刻，你没有把最重要的人丢给“等事情忙完再说”。这不是小事。', tone: '撑住' },
        { role: 'variable', modelName: 'Gemini', text: '异常像是专门配合你的选择被点亮的。它不是背景噪音，更像有人在引导你站队。', tone: '引导' },
      ]),
      choices: buildSeededChoices(sceneId),
    }
  }

  if (sceneId === 'trace-signal') {
    return {
      id: 'trace-signal',
      chapter: '第 2 幕',
      title: '题面裂开',
      premise: `你先追向异常线「${hook}」。表面的二选一被你撕开了一道口子，但主线窗口还在收缩，关系代价也没有因为你看见更多真相就自动消失。`,
      responses: buildSeededResponses([
        { role: 'guide', modelName: 'Claude', text: '真相重要，但它不能代替止损。你必须尽快决定这些新线索该服务哪条主线。', tone: '收束' },
        { role: 'partner', modelName: 'GPT-4', text: '你在追真相的时候，别忘了真正会疼的人和关系还留在现实那一边。', tone: '牵引' },
        { role: 'variable', modelName: 'Gemini', text: '异常线已经回应你了。问题不是“有没有第三条路”，而是你敢不敢继续赌。', tone: '诱发' },
      ]),
      choices: buildSeededChoices(sceneId),
    }
  }

  if (sceneId === 'ending-good') {
    return {
      id: 'ending-good',
      chapter: '终章',
      title: '第三答案',
      premise: `在「${hook}」这道设定里，你没有完全接受别人递给你的二选一，而是硬生生拧出了第三个答案。真正被你保住的，不只是结果，还有你拒绝被题面牵着走的那部分自己。`,
      responses: [],
      choices: [],
      ending: {
        kind: 'good',
        title: '第三答案',
        summary: '你没有只在主线、关系和异常之间站队，而是逼出了原本不存在的出口。',
        epilogue: '最难的从来不是选得更狠，而是敢怀疑题目本身。',
      },
    }
  }

  if (sceneId === 'ending-bad') {
    return {
      id: 'ending-bad',
      chapter: '终章',
      title: '两边皆失',
      premise: `在「${hook}」这道设定里，你试图抓住更多，却同时把两边都拖进了坠落。真正可怕的不是输掉，而是你直到最后一刻都知道，自己差一点就能改写题面。`,
      responses: [],
      choices: [],
      ending: {
        kind: 'bad',
        title: '两边皆失',
        summary: '你想赌一个更大的答案，却被失控的时间差吞掉了全部筹码。',
      },
    }
  }

  if (sceneId === 'ending-mystery') {
    return {
      id: 'ending-mystery',
      chapter: '终章',
      title: '题面之外',
      premise: `在「${hook}」这道设定里，你终于摸到了题面外缘。你看见了那只安排分叉的手，却还没来得及真正抓住它。你离答案已经很近，只是还没近到能把它说完整。`,
      responses: [],
      choices: [],
      ending: {
        kind: 'mystery',
        title: '题面之外',
        summary: '你看见了分叉背后的规则影子，但还没来得及看清操盘者的脸。',
        epilogue: '最危险的异常，不是你看到的那一个，而是你还没学会怎么命名它。',
      },
    }
  }

  if (sceneId === 'ending-normal') {
    return {
      id: 'ending-normal',
      chapter: '终章',
      title: '代价成立',
      premise: `在「${hook}」这道设定里，你保住了一边，也承认了另一边的损耗。局面没有彻底崩坏，但你很清楚，这不是“皆大欢喜”，而是一种需要你长期背着走的清醒。`,
      responses: [],
      choices: [],
      ending: {
        kind: 'normal',
        title: '代价成立',
        summary: '你做出了能自圆其说的选择，也接受了它必然留下的裂痕。',
      },
    }
  }

  return {
    id: 'start',
    chapter: '第 1 幕',
    title: '命题落下',
    premise: `设定成立：${hook}。局面刚一展开，你就发现自己被同时拉向三边：一条是最直接的主线，一条牵动你最重要的人与关系，另一条则指向一个明显不合理的异常。现在还没有标准答案，只有你准备先相信哪一种判断。`,
    responses: buildSeededResponses([
      { role: 'guide', modelName: 'Claude', text: '先处理最会立刻失控的那条主线。越晚止损，后面的每一步都会更贵。', tone: '决断' },
      { role: 'partner', modelName: 'GPT-4', text: '别把你最在乎的人或关系放到“等忙完再说”的位置，那通常就是来不及。', tone: '拉扯' },
      { role: 'variable', modelName: 'Gemini', text: '题面被设计得太像二选一了。真正该看的，是那个不该这么整齐出现的异常。', tone: '诡异' },
    ]),
    choices: buildSeededChoices('start'),
  }
}

/**
 * Mock 数据 - 多 AI 版本
 */
export const STORY_LITE_V2_MOCK_SCENES: Record<string, StoryLiteV2Scene> = {
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
