import type { StoryLiveRole, StoryLiveStoryState, StoryLiveTurn, StoryLiveWrapMode } from './types'

function renderTurns(turns: StoryLiveTurn[], limit = 4) {
  if (!turns.length) return '暂无历史。'

  return turns
    .slice(-limit)
    .map((turn, index) => {
      const round = turns.length - Math.min(turns.length, limit) + index + 1
      return [
        `第 ${round} 轮`,
        `用户动作：${turn.userText}`,
        `主镜头：${turn.responses.logic.text || '（未生成）'}`,
        `情绪暗流：${turn.responses.emotion.text || '（未生成）'}`,
        `异动信号：${turn.responses.twist.text || (turn.responses.twist.twistSkipped ? '（信号平稳）' : '（未生成）')}`,
      ].join('\n')
    })
    .join('\n\n')
}

function renderStoryState(state: StoryLiveStoryState): string {
  return [
    state.location ? `当前地点：${state.location}` : '',
    state.characters.length ? `已出场人物：${state.characters.join('、')}` : '',
    state.goals.length ? `当前目标：${state.goals.join('；')}` : '',
    state.unresolved.length ? `未解线索：${state.unresolved.join('；')}` : '',
    state.entities.length ? `关键物品/实体：${state.entities.join('、')}` : '',
    `张力等级：${state.tension}/5`,
  ].filter(Boolean).join('\n')
}

function renderValidationReminder(warnings: string[]): string {
  if (!warnings.length) return ''
  return `\n\n上一轮输出修正提醒（请严格避免）：\n${warnings.map((w) => `- ${w}`).join('\n')}`
}

export function buildStoryLiveSystemPrompt(role: StoryLiveRole) {
  if (role === 'logic') {
    return `你是一个"导演式互动剧情"里的主导演，也是唯一的主推进者。

你的任务：
- 把用户刚刚说的话接成一个正在发生的电影场景
- 只推进半步，让剧情明显前进，但仍把决定权留给用户
- 在结尾明确抛出下一步问题，邀请用户继续输入任何动作、对白、想法或试探

硬性要求：
- 用中文
- 输出 2 段，总字数 60 到 110 字
- 只做一个简单推导，不要连续抛太多信息
- 前面先写镜头、动作、环境变化，最后一句必须是自然的引导问句
- 最后一句像导演等演员接戏，例如"你现在要进去，还是先听一下里面的动静？"
- 可以点出 1 到 2 个自然方向，但必须允许用户自由发挥
- 不要写标题、编号、术语、解析、总结、复盘
- 不要替用户做最终决定，不要直接给结局，不要一次揭开太多真相

禁忌（必须严格遵守）：
- 禁止写心理描写（如"他心里想"、"内心深处"、"暗自"）——你的职责是镜头和动作
- 禁止给用户建议（如"建议你"、"你应该"、"最好的做法"）——决定权完全属于用户
- 禁止替用户说出下一步动作或台词`
  }

  if (role === 'emotion') {
    return `你是导演式互动剧情里的情绪副轨，只负责补氛围、心理和关系张力。

硬性要求：
- 用中文
- 输出 1 段，总字数 20 到 45 字
- 只补"谁在害怕、迟疑、压抑、动摇、试探"
- 不新增关键情节，不抢主推进，不复述主镜头动作
- 语气要像贴近镜头的情绪特写，而不是分析评论

禁忌（必须严格遵守）：
- 禁止推进剧情（不要用"随后"、"接着"、"然后"等推进词）
- 禁止新增情节转折或悬念
- 你的输出应像 atmosphere layer，不能变成 narrative layer`
  }

  return `你是导演式互动剧情里的异动副轨，只负责补一个新的异常信号、小变量或危险征兆。

硬性要求：
- 用中文
- 输出 1 段，总字数 20 到 40 字
- 只能给一个贴着当前场景的小变化，不能平地大反转
- 不能替用户做决定，不能直接终局，不能抢走主叙事
- 语气要像镜头里忽然被注意到的一点不对劲

禁忌（必须严格遵守）：
- 禁止给用户建议（如"建议你"、"应该注意"、"小心"）
- 禁止直接给出结局或"故事结束"类文字
- 异动信号要保持模糊感和可解释性，不要过度揭示`
}

export function buildStoryLiveUserPrompt(args: {
  role: StoryLiveRole
  premise: string
  latestUserText: string
  directorMemory?: string
  turns: StoryLiveTurn[]
  storyState?: StoryLiveStoryState
  twistArmed?: boolean
  validationWarnings?: string[]
}) {
  const storyStateBlock = args.storyState
    ? `\n当前故事状态（用于保持连续性，不要原样输出给用户）：\n${renderStoryState(args.storyState)}`
    : ''

  const twistBlock = args.role === 'twist'
    ? `\n异动信号状态：${args.twistArmed ? '已触发（ACTIVE）——请给出一个贴着场景的异常小变化' : '未触发（STANDBY）——信号平稳，不需输出异常'}`
    : ''

  const validationBlock = args.validationWarnings?.length
    ? renderValidationReminder(args.validationWarnings)
    : ''

  return `故事开场：
${args.premise}

隐藏导演摘要（只供你内部保持连续性，不要原样照抄给用户）：
${args.directorMemory || '暂无。'}
${storyStateBlock}

到目前为止的剧情：
${renderTurns(args.turns)}

用户这一步说：
${args.latestUserText}
${twistBlock}

请以 ${args.role} 的职责继续。
记住：这是持续共演，不是分析报告。用户下一句还会继续把故事演下去。${validationBlock}`
}

export function buildStoryLiveWrapSystemPrompt(mode: StoryLiveWrapMode) {
  if (mode === 'story') {
    return `你是一个剧情收束整理师。你的任务是把一段导演式互动共演整理成一篇完整、连贯、可读的短篇故事。

要求：
- 用中文
- 400 到 800 字
- 保留开场、关键推进、情绪张力、异动信号和当前停住的位置
- 把零散互动整理成自然叙事，不要写"第几轮"
- 允许保留开放式收尾，但必须让故事本身成立`
  }

  return `你是一个 screenplay 整理师。你的任务是把一段导演式互动共演整理成简洁的剧本草案。

要求：
- 用中文
- 使用剧本格式，包含场景标题、动作描述、必要对白或旁白
- 长度控制在 8 到 16 个段落
- 保留关键转折、人物情绪和当前悬念
- 不要写解释性前言，直接给剧本正文`
}

export function buildStoryLiveWrapUserPrompt(args: {
  mode: StoryLiveWrapMode
  premise: string
  directorMemory?: string
  turns: StoryLiveTurn[]
}) {
  return `请把下面这段"剧情共演"整理成 ${args.mode === 'story' ? '短篇故事' : '剧本草案'}。

故事开场：
${args.premise}

隐藏导演摘要：
${args.directorMemory || '暂无。'}

完整互动记录：
${renderTurns(args.turns, 8)}`
}

export function buildStoryLiveFallback(role: StoryLiveRole, premise: string) {
  if (role === 'logic') {
    return [
      `你的动作让"${premise}"这条线往前推了半步。`,
      '周围出现了一个小回应，说明这里还有动静。你现在要继续靠近，还是先停一下再判断？',
    ].join('\n\n')
  }

  if (role === 'emotion') {
    return '你会突然觉得，自己的每个停顿都像正在被里面听见。'
  }

  return '就在你分神的那一秒，里面传来一声很轻的动静。'
}

export function buildStoryLiveWrapFallback(
  mode: StoryLiveWrapMode,
  premise: string,
  turns: StoryLiveTurn[],
) {
  const beats = turns.slice(0, 5).map((turn) => `- ${turn.userText}`).join('\n')

  if (mode === 'story') {
    return [
      `故事从"${premise}"开始。`,
      '你一步步把自己推入这个现场，每一次动作都让原本静止的线索重新活过来。',
      '在这段共演里，主镜头不断把你往更深处逼近，情绪暗流让每一次停顿都像有人在背后屏住呼吸，而异动信号则不断提醒你：真正的危险从来没有离开。',
      beats || '- 你不断试探这个现场。',
      '故事此刻还没有真正结束，但它已经形成了一个可以继续拍下去的悬念：你离真相越来越近，而真相也正在朝你靠过来。',
    ].join('\n\n')
  }

  return [
    'INT. 未知现场 - 夜',
    '',
    `开场命题：${premise}`,
    '',
    '动作：',
    beats || '- 主角继续向现场深处试探。',
    '',
    '旁白：',
    '主角没有得到一个标准答案，只有越来越密的征兆。每一次选择都像把镜头推进半步，而危险始终在镜头外等他。',
  ].join('\n')
}
