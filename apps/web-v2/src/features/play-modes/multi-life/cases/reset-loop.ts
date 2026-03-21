import type { MultiLifeCase } from '../types'

export const RESET_LOOP_CASE: MultiLifeCase = {
  id: 'reset-loop',
  title: '开端 · 循环',
  premise:
    '45路公交车即将爆炸，女程序员李诗情和游戏架构师肖鹤云陷入时间循环。每次爆炸后他们都会回到爆炸前几分钟。为了拯救全车人，他们必须找出携带炸弹的人。三个关键人物被怀疑：提着红色塑料袋的大妈、戴着耳机一直沉默的青年、以及经常看表的司机。',
  truth:
    '凶手是提着红色塑料袋的大妈陶映红，她的丈夫是司机王兴德。他们的女儿五年前在这条线路上出车祸死亡，他们要为女儿"讨回公道"。炸弹藏在红色塑料袋的高压锅里，定时装置由司机控制。大妈负责带炸弹上车，司机在特定时间引爆炸弹。',
  totalRounds: 7,
  challengeBudget: 4,
  roles: [
    {
      id: 'a',
      name: '李诗情',
      archetype: 'witness',
      reliability: 0.8,
      hiddenKnowledge: 0.7,
      lyingPattern: 'never',
      personality:
        '李诗情二十五岁，程序员，善良但理性。她经历了多次循环，知道爆炸即将发生，但每次循环的记忆只有她和肖鹤云保留。她必须说服别人相信"预言"。',
    },
    {
      id: 'b',
      name: '肖鹤云',
      archetype: 'analyst',
      reliability: 0.75,
      hiddenKnowledge: 0.6,
      lyingPattern: 'selective',
      personality:
        '肖鹤云二十七岁，游戏架构师，逻辑性强但有点自私。他最初想自己下车不管别人，后来被李诗情感化。他擅长观察细节，是找出炸弹位置的关键。',
    },
    {
      id: 'c',
      name: '司机 王兴德',
      archetype: 'suspect',
      reliability: 0.2,
      hiddenKnowledge: 0.9,
      lyingPattern: 'consistent',
      personality:
        '王兴德五十二岁，公交车司机，沉默寡言。他配合妻子的复仇计划，内心痛苦但坚定。他在等一个特定的时机——当年女儿出事的时间和地点。',
    },
  ],
  rounds: [
    {
      roundNumber: 1,
      scene: '第N次循环，公交车正在行驶中，距离爆炸还有15分钟。',
      roleDirectives: {
        a: { directive: '你是李诗情。你大喊"这辆车会爆炸"，试图让司机停车。你说你已经经历过很多次了，"请相信我"。你描述上次爆炸的细节来证明。', lying: false },
        b: { directive: '你是肖鹤云。你拉住李诗情，说"冷静点，我们需要先找出炸弹在哪"。你观察车内乘客，注意到司机的表情有些异常。', lying: false },
        c: { directive: '你是司机。你保持沉默，但内心紧张。你说"不要扰乱公共秩序"，坚持要在下一站才停车。你暗示时间还没到。', lying: true },
      },
    },
    {
      roundNumber: 2,
      scene: '排查嫌疑人，重点观察提着红色塑料袋的大妈。',
      roleDirectives: {
        a: { directive: '你是李诗情。你注意到大妈很紧张，双手一直护着袋子。你试图和她搭话，但她不理你。你怀疑炸弹就在那个袋子里。', lying: false },
        b: { directive: '你是肖鹤云。你从游戏设计角度分析：如果我是凶手，我会把炸弹藏在最不起眼的地方。那个红色塑料袋太显眼了，反而是掩护。', lying: false },
        c: { directive: '你是司机。你从后视镜观察李诗情和肖鹤云，意识到他们真的知道什么。你加速开车，试图在他们阻止之前到达目标地点。', lying: true },
      },
    },
    {
      roundNumber: 3,
      scene: '矛盾点：司机为什么拒绝停车？',
      contradictions: [{ betweenRoles: ['a', 'c'], topic: '司机的行为', keywords: ['正常', '可疑', '加速', '拒绝', '下一站'], description: '李诗情说司机故意加速，但司机说是正常行驶。' }],
      roleDirectives: {
        a: { directive: '你是李诗情。你指出司机在故意加速，绕过了平时会停的站点。你说"他在拖延时间，等炸弹爆炸"。', lying: false },
        b: { directive: '你是肖鹤云。你注意到司机看表的频率越来越高，而且他的手放在某个按钮附近。你怀疑司机和炸弹有关。', lying: false },
        c: { directive: '你是司机。你辩解说是"交通状况不好"，但你确实跳过了几个站点。你说"我要按时完成线路"，但你的借口很牵强。', lying: true },
      },
    },
    {
      roundNumber: 4,
      scene: '发现真相：大妈和司机是夫妻，他们的女儿五年前在这条路上出车祸。',
      roleDirectives: {
        a: { directive: '你是李诗情。你了解到司机女儿的故事后感到震惊和同情，但你说"复仇不能伤害无辜的人"。你试图劝说司机停车。', lying: false },
        b: { directive: '你是肖鹤云。你从逻辑角度分析：司机在等特定的时间和地点，那个地点就是他女儿出事的地方。这是一场"仪式性"的复仇。', lying: false },
        c: { directive: '你是司机。你听到他们提起女儿，眼眶红了。你小声说"你们不懂失去孩子的痛苦"。你内心动摇，但还在坚持。', lying: false },
      },
    },
    {
      roundNumber: 5,
      scene: '关键时刻：距离爆炸还有3分钟，接近目的地。',
      contradictions: [{ betweenRoles: ['b', 'c'], topic: '炸弹触发方式', keywords: ['定时', '遥控', '按钮', '自动'], description: '肖鹤云认为是定时触发，但司机暗示他可以手动控制。' }],
      roleDirectives: {
        a: { directive: '你是李诗情。你冲上前试图抢夺方向盘让车停下，但司机死死抓住。你大喊"车上还有孩子，你不能这样做"。', lying: false },
        b: { directive: '你是肖鹤云。你发现仪表盘下有个隐藏的按钮，你意识到司机可以手动触发爆炸。你试图阻止司机按下去。', lying: false },
        c: { directive: '你是司机。你的手放在隐藏按钮上，犹豫要不要按下去。大妈在喊"老王，为我们的女儿报仇"。你内心在挣扎。', lying: true },
      },
    },
    {
      roundNumber: 6,
      scene: '循环再次重置，但这次他们带着更多记忆。',
      roleDirectives: {
        a: { directive: '你是李诗情。这次你决定提前报警，并在上车时就暗示司机你知道他的计划。你说"我知道你女儿的事，但这不是她想要的"。', lying: false },
        b: { directive: '你是肖鹤云。你设计了分散注意力的方案：让其他乘客同时行动，制造混乱阻止司机按按钮。你意识到必须改变策略。', lying: false },
        c: { directive: '你是司机。你注意到李诗情和肖鹤云这次行动更有针对性，你怀疑他们真的经历过这一切。你开始怀疑自己的决定是否正确。', lying: false },
      },
    },
    {
      roundNumber: 7,
      scene: '最终循环：改变命运的时刻。',
      contradictions: [{ betweenRoles: ['a', 'c'], topic: '复仇的意义', keywords: ['解脱', '伤害', '无辜', '正义'], description: '李诗情认为复仇不会带来解脱，司机认为只有这样才能引起重视。' }],
      roleDirectives: {
        a: { directive: '你是李诗情。你说"如果你按下按钮，你就变成了和女儿出车祸一样的人——夺走无辜生命的人"。你的话触动了司机。', lying: false },
        b: { directive: '你是肖鹤云。你趁机制服了大妈，夺下了高压锅。你打开袋子确认里面是炸弹，你成功阻止了爆炸。', lying: false },
        c: { directive: '你是司机。你的手停在按钮上，最终没有按下去。你哭了，说"对不起，女儿，爸爸做不到"。你放下了复仇的念头。', lying: false },
      },
    },
  ],
}
