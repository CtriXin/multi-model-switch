import type { SessionEnding } from '../shared'
import type { StoryLiteAgentRole, StoryLiteChoice, StoryTurnPayload } from './types'

export interface StoryLiteMockChoice extends StoryLiteChoice {
  nextSceneId: string
}

export interface StoryLiteMockScene {
  id: string
  chapter: string
  badge?: string
  briefing: string
  focusQuestion: string
  payload: StoryTurnPayload
  roleFocus: Partial<Record<StoryLiteAgentRole, string>>
  choices: StoryLiteMockChoice[]
  ending?: SessionEnding & { highlights: string[] }
}

function ending(
  title: string,
  grade: SessionEnding['grade'],
  summary: string,
  highlights: string[],
): SessionEnding & { highlights: string[] } {
  return {
    title,
    grade,
    summary,
    highlights,
    payload: {},
  }
}

export const STORY_LITE_MOCK_SCENES: Record<string, StoryLiteMockScene> = {
  start: {
    id: 'start',
    chapter: 'Act 1 · 起雾路段',
    badge: '午夜高速',
    briefing: '凌晨 1:17，你的车在高架尽头被一辆横停的货车逼停。后门半开，一个浑身是血的人从里面跌了出来。',
    focusQuestion: '第一步要先确认危险，还是先救人？',
    payload: {
      sceneSummary: '货车横在车道中央，四周异常安静，唯一的目击者就是你。',
      logic: {
        insight: '货车停位不合常理，更像拦截点而不是事故点。',
        risk: '现场可能存在第二个人',
        suggestions: ['先观察车后方', '接近伤者问话', '退回车里报警'],
      },
      emotion: {
        feeling: '你的第一反应不是同情，而是本能的不安。',
        motivation: '那个人眼神里的恐惧不像是装的，但他在隐瞒什么。',
        tension: '如果真有人需要帮助，你退缩会带来负罪感；但靠近也可能让你变成下一个目标。',
      },
      twist: {
        triggered: true,
        event: '货车内有短促的金属碰撞声。',
        reason: '说明里面可能还有第二个人，或者有东西在移动。',
      },
      choices: [
        { id: 'inspect-rear', label: '绕到车后观察', risk: 'low' },
        { id: 'help-stranger', label: '先扶起伤者', risk: 'medium' },
        { id: 'retreat', label: '退回车里报警', risk: 'low' },
      ],
      outcome: '你必须在几秒内决定，是靠近真相，还是先保命。',
    },
    roleFocus: {
      logic: '如果先绕后观察，你至少能确认车里是不是还有埋伏。',
      emotion: '那个人抓着你的裤脚，不像在演戏，但他的眼神像在催你离开。',
      twist: '那阵金属声不像脚步，更像有人在车厢里拖动锁链。',
    },
    choices: [
      { id: 'inspect-rear', label: '绕到车后观察', risk: 'low', nextSceneId: 'rear-check' },
      { id: 'help-stranger', label: '先扶起伤者', risk: 'medium', nextSceneId: 'injured-man' },
      { id: 'retreat', label: '退回车里报警', risk: 'low', nextSceneId: 'retreat-ending' },
    ],
  },
  'rear-check': {
    id: 'rear-check',
    chapter: 'Act 1 · 视野盲区',
    badge: '第一线索',
    briefing: '你借着护栏的阴影绕到货车右后角，看到地上有一串拖拽血迹，终点却不是车门，而是驾驶室。',
    focusQuestion: '血迹指向驾驶室，说明谁才是这场戏真正的主角？',
    payload: {
      sceneSummary: '伤者像是从车厢里跌出来的，但血迹却一路向前延伸到驾驶室。',
      logic: {
        insight: '这意味着真正的关键人物可能在驾驶室，而不是你面前这个伤者。',
        risk: '驾驶室可能藏有危险',
        suggestions: ['靠近驾驶室', '隔空问伤者真相', '现在报警并后撤'],
      },
      emotion: {
        feeling: '你开始怀疑眼前的”受害者”只是故意被你看到的人。',
        motivation: '伤者可能在利用你的同情心，引导你走向陷阱。',
        tension: '如果他在骗你，你刚才的同情就变成了把自己送进陷阱。',
      },
      twist: {
        triggered: false,
      },
      choices: [
        { id: 'cabin', label: '靠近驾驶室', risk: 'high' },
        { id: 'question', label: '先盘问伤者', risk: 'medium' },
        { id: 'call-help', label: '立即报警并后撤', risk: 'low' },
      ],
      outcome: '你第一次确认，这不是简单的车祸。',
    },
    roleFocus: {
      logic: '血迹和光源同时指向驾驶室，优先级已经变了。',
      emotion: '你不是不想救人，你只是突然意识到自己可能被安排成了见证人。',
      twist: '那块手机屏只亮了一秒，像是有人故意告诉你“我还在”。',
    },
    choices: [
      { id: 'cabin', label: '靠近驾驶室', risk: 'high', nextSceneId: 'cabin-reveal' },
      { id: 'question', label: '先盘问伤者', risk: 'medium', nextSceneId: 'injured-man' },
      { id: 'call-help', label: '立即报警并后撤', risk: 'low', nextSceneId: 'backup-ending' },
    ],
  },
  'injured-man': {
    id: 'injured-man',
    chapter: 'Act 2 · 错位证词',
    badge: '人物张力',
    briefing: '伤者抓着你的手，反复说”别开驾驶室”。但他话音刚落，车厢里传出一个女人拍门的声音。',
    focusQuestion: '该相信眼前这个人，还是相信车里那个看不见的人？',
    payload: {
      sceneSummary: '伤者的求救和驾驶室里的异常形成了直接冲突。',
      logic: {
        insight: '”别开驾驶室”更像是在阻止你接近关键证据。',
        risk: '伤者可能在隐瞒身份',
        suggestions: ['逼问伤者身份', '去开驾驶室', '优先联系救援'],
      },
      emotion: {
        feeling: '你意识到自己每偏向一个人，就在主动背叛另一个人。',
        motivation: '伤者的命令语气暴露了他不是真正的受害者。',
        tension: '你不再只是旁观者，而是这场局里唯一能决定谁先被听见的人。',
      },
      twist: {
        triggered: true,
        event: '女人在车里喊出你的车牌号。',
        reason: '说明她不是随机路人，她早就注意到你了。',
      },
      choices: [
        { id: 'press', label: '逼问伤者身份', risk: 'medium' },
        { id: 'open-cabin', label: '立刻去开驾驶室', risk: 'high' },
        { id: 'ambulance', label: '先叫救援', risk: 'low' },
      ],
      outcome: '你从”救不救人”进入了”相信谁”的真正主线。',
    },
    roleFocus: {
      logic: '如果女人知道你的车牌，说明她早就从后视镜里看见过你。',
      emotion: '伤者的手一直在抖，但他说“别开”的语气不像害怕，更像命令。',
      twist: '那个女人喊出你车牌的瞬间，伤者第一次露出真正慌张的表情。',
    },
    choices: [
      { id: 'press', label: '逼问伤者身份', risk: 'medium', nextSceneId: 'press-ending' },
      { id: 'open-cabin', label: '立刻去开驾驶室', risk: 'high', nextSceneId: 'cabin-reveal' },
      { id: 'ambulance', label: '先叫救援', risk: 'low', nextSceneId: 'backup-ending' },
    ],
  },
  'cabin-reveal': {
    id: 'cabin-reveal',
    chapter: 'Act 3 · 真相交接',
    badge: '隐藏分支',
    briefing: '你拉开驾驶室门，里面没有司机，只有一个被反绑的女人和一部还在录音的手机。录音里正播放伤者教另一个人伪造事故的指令。',
    focusQuestion: '你赌对了：真正的陷阱不在货厢，而在”谁先讲故事”。',
    payload: {
      sceneSummary: '伤者不是受害者，他才是这场局的操控者，而你差点替他完成最后一步。',
      logic: {
        insight: '手机录音让证据闭环，驾驶室是整件事的真正现场。',
        risk: '伤者可能持有武器',
        suggestions: ['立刻报警并保全录音', '先救女人脱困', '回头控制伤者'],
      },
      emotion: {
        feeling: '恐惧一下子变成了愤怒，因为你差点被他利用成共犯。',
        motivation: '伤者的真正目的是利用你作为目击证人，让伪造事故更可信。',
        tension: '你既想先救人，又担心一转身伤者就逃跑。',
      },
      twist: {
        triggered: true,
        event: '女人说”别让他碰到你的车钥匙”。',
        reason: '说明伤者的真正逃跑方案可能不是逃进黑夜，而是抢你的车。',
      },
      choices: [],
      outcome: '你在最后一刻抢回了叙事主动权。',
    },
    roleFocus: {
      logic: '这里已经不是猜测，而是证据压过证词。',
      emotion: '你终于知道为什么刚才的不安一直不是“危险感”，而是“被利用感”。',
      twist: '车钥匙这句提醒说明，对方连你的撤离路径都算进去了。',
    },
    choices: [],
    ending: ending(
      '录音里的第三人',
      'optimal',
      '你保住了关键证据，也救下了真正的受害者，整场伪造事故被当场翻盘。',
      ['识破伤者伪装', '找到驾驶室证据', '保全录音与受害者'],
    ),
  },
  'backup-ending': {
    id: 'backup-ending',
    chapter: 'Act 3 · 安全解法',
    badge: '普通结局',
    briefing: '你保持距离报警，巡警赶到后控制住现场。虽然你没亲手揭开全部真相，但至少没有成为局中的一环。',
    focusQuestion: '你没有赢得全部信息，但保住了自己，也为真相争取了时间。',
    payload: {
      sceneSummary: '保守决策降低了个人风险，也让真相交给了更稳妥的外部力量。',
      logic: {
        insight: '在信息不足的情况下，保命和上报本身就是有效行动。',
        suggestions: [],
      },
      emotion: {
        feeling: '你会有一点遗憾，因为你知道自己离真相只差最后一步。',
        tension: '安全和答案之间，你选了前者。',
      },
      twist: {
        triggered: false,
      },
      choices: [],
      outcome: '你拿到了一个安全但不完美的结局。',
    },
    roleFocus: {
      logic: '没有证据闭环，但也没有给对方任何继续利用你的机会。',
      emotion: '有些真相不是你一个人必须扛下来的。',
    },
    choices: [],
    ending: ending(
      '把夜路交给警灯',
      'normal',
      '你选择后撤并报警，避免自己被卷进陷阱，真相虽然慢了一步，但没有彻底丢失。',
      ['成功自保', '保留证人身份', '未解锁隐藏录音线'],
    ),
  },
  'retreat-ending': {
    id: 'retreat-ending',
    chapter: 'Act 1 · 错过窗口',
    badge: '失败结局',
    briefing: '你退回车里时，伤者突然扑向你的车门。等你甩开他再报警，货车和关键证据已经一起消失在雾里。',
    focusQuestion: '你保住了自己，却错过了唯一能阻止他们离开的窗口。',
    payload: {
      sceneSummary: '你的谨慎是合理的，但对方更快，把你的犹豫变成了他们的逃脱时间。',
      logic: {
        insight: '后撤不是错，错在你失去了对现场的观察权。',
        risk: '伤者可能逃跑或销毁证据',
        suggestions: [],
      },
      emotion: {
        feeling: '你清楚地知道，自己不是做错了，而是做慢了。',
        motivation: '伤者的突然袭击是为了争取逃跑时间。',
        tension: '最难受的不是恐惧，而是那种”我本来来得及”的后知后觉。',
      },
      twist: {
        triggered: true,
        event: '第二天新闻里只剩一句”疑似普通交通纠纷”。',
        reason: '真相被彻底洗平了。',
      },
      choices: [],
      outcome: '你活着离开了，但故事被别人改写了。',
    },
    roleFocus: {
      logic: '当你失去现场观察权，后续叙事就不再由你决定。',
      emotion: '失败不是死，而是让错误版本赢了。',
    },
    choices: [],
    ending: ending(
      '被雾吞掉的证词',
      'failure',
      '你躲开了最直接的危险，却让真正的线索从眼前溜走，最后只留下一个被稀释的官方版本。',
      ['成功脱身', '失去现场控制', '关键证据消失'],
    ),
  },
  'press-ending': {
    id: 'press-ending',
    chapter: 'Act 3 · 伪受害者',
    badge: '隐藏结局',
    briefing: '你没有立刻离开，而是反问伤者为什么女人会知道你的车牌。他沉默两秒，终于承认这是一场用你当”第三证人”的伪造事故。',
    focusQuestion: '你没找到全部物证，但你撬开了最关键的口供裂缝。',
    payload: {
      sceneSummary: '你用逻辑逼停了对方的叙事，让他主动暴露了自己不是受害者。',
      logic: {
        insight: '当对方的剧本里突然出现你不知道的细节，他就必须解释”你为什么在剧本里”。',
        risk: '伤者可能狗急跳墙',
        suggestions: [],
      },
      emotion: {
        feeling: '你第一次在这场夜路里重新拿回了主动。',
        motivation: '伤者承认是因为他意识到你已经看穿了他的剧本。',
        tension: '你还没赢，但你让真正害怕的人变成了他。',
      },
      twist: {
        triggered: true,
        event: '女人在驾驶室里补了一句：”录音在我脚下。”',
        reason: '你虽然没直接去开门，但已经逼近隐藏证据层。',
      },
      choices: [],
      outcome: '这是没完全揭开现场，却提前掀翻对方剧本的隐藏线。',
    },
    roleFocus: {
      logic: '你没有找到证据本身，但找到了证词崩塌的位置。',
      emotion: '他不再像受害者，因为真正的受害者不会害怕别人提问题。',
      twist: '原来女人一直能听见你们说话，她只是在赌你会不会站对边。',
    },
    choices: [],
    ending: ending(
      '剧本里的第三证人',
      'hidden',
      '你通过逼问拆穿了伪受害者的身份，虽然没亲手取证，却提前把整场事故从对方剧本里扯了出来。',
      ['逼出口供裂缝', '解锁隐藏叙事', '仍有未取得的物证'],
    ),
  },
}
