import type { MultiLifeCase } from '../types'

export const HIDDEN_CORNER_CASE: MultiLifeCase = {
  id: 'hidden-corner',
  title: '隐秘的角落 · 真相',
  premise:
    '六峰山景区，少年朱朝阳和伙伴们在山顶意外拍下了一起谋杀：数学老师张东升将岳父母推下悬崖。三个孩子的命运因此改变。现在，案发三个月后，警方重新调查此案，三个关键人物被问询：拍下视频的朱朝阳、朱朝阳的继母王瑶、以及张东升的妻子徐静。',
  truth:
    '张东升是杀害岳父母的凶手，但朱朝阳利用视频证据勒索张东升的同时，也借机除掉了自己的妹妹朱晶晶（并非张东升直接杀害）。王瑶一直怀疑朱朝阳与女儿朱晶晶的死有关，但缺乏证据。徐静在父亲母亲死后发现丈夫的真面目，却在准备报警前被张东升毒杀。',
  totalRounds: 7,
  challengeBudget: 4,
  roles: [
    {
      id: 'a',
      name: '朱朝阳',
      archetype: 'witness',
      reliability: 0.3,
      hiddenKnowledge: 0.95,
      lyingPattern: 'selective',
      personality:
        '朱朝阳十四岁，天才少年，内心深沉。他拍下了谋杀视频，却选择勒索而非报警。他善于伪装成无辜的孩子，实际上心思缜密，借刀杀人除掉了妹妹。',
    },
    {
      id: 'b',
      name: '继母 王瑶',
      archetype: 'analyst',
      reliability: 0.6,
      hiddenKnowledge: 0.5,
      lyingPattern: 'selective',
      personality:
        '王瑶四十岁，朱晶晶的母亲，直觉敏锐但偏执。她失去女儿后精神受创，一心想证明朱朝阳是凶手，却忽视了张东升这个真正的威胁。',
    },
    {
      id: 'c',
      name: '徐静',
      archetype: 'suspect',
      reliability: 0.4,
      hiddenKnowledge: 0.7,
      lyingPattern: 'selective',
      personality:
        '徐静三十八岁，张东升的妻子。她在父母死后开始怀疑丈夫，掌握了部分证据却不敢面对真相。她处于极度恐惧中，不知道是否该相信任何人。',
    },
  ],
  rounds: [
    {
      roundNumber: 1,
      scene: '案发三个月后的问询室。',
      roleDirectives: {
        a: { directive: '你是朱朝阳。你表现得像个受惊的孩子，说你只是"无意中拍到了视频"，你很害怕张东升。你暗示王瑶一直"针对你"。', lying: false },
        b: { directive: '你是王瑶。你坚持认为朱朝阳不是无辜的，说他"心机太深"。你把焦点引向朱晶晶的死，说"他恨我女儿"。', lying: false },
        c: { directive: '你是徐静。你透露你开始怀疑张东升，说父母死后他"表现得太冷静"。你承认你发现了一些药物。', lying: false },
      },
    },
    {
      roundNumber: 2,
      scene: '调查张东升的背景。',
      roleDirectives: {
        a: { directive: '你是朱朝阳。你透露张东升曾威胁你，说"他知道我家地址"。你暗示你之所以没报警是因为害怕报复。', lying: true },
        b: { directive: '你是王瑶。你从母亲直觉出发，说朱朝阳说话"太有条理，不像个孩子"。你质疑他为什么第一时间想到勒索而不是告诉家长。', lying: false },
        c: { directive: '你是徐静。你承认张东升提出过签署受益人变更协议，把岳父母的遗产转给他。你当时觉得不对劲。', lying: false },
      },
    },
    {
      roundNumber: 3,
      scene: '矛盾点：朱晶晶坠楼案。',
      contradictions: [{ betweenRoles: ['a', 'b'], topic: '朱晶晶坠楼时朱朝阳是否在场', keywords: ['在场', '不在', '五楼', '少年宫'], description: '朱朝阳说他不在场，但王瑶有目击证据。' }],
      roleDirectives: {
        a: { directive: '你是朱朝阳。你坚持说你那天在少年宫补课，不在现场。但你的说法开始出现漏洞，你补充说"就算我在，我也不会推她"。', lying: true },
        b: { directive: '你是王瑶。你出示证据：有人看到朱朝阳在少年宫五楼和朱晶晶争吵，晶晶坠楼前喊了一声"哥哥"。你质问朱朝阳。', lying: false },
        c: { directive: '你是徐静。你从旁观者角度分析：两个孩子之间的事很难理清，但张东升的威胁是真实存在的。你试图让调查回到张东升身上。', lying: false },
      },
    },
    {
      roundNumber: 4,
      scene: '朱朝阳的心理评估。',
      roleDirectives: {
        a: { directive: '你是朱朝阳。你在压力下承认你去过五楼，但说晶晶是"自己失足"。你暗示是意外，与你无关。你眼中有泪，但冷静得不像孩子。', lying: true },
        b: { directive: '你是王瑶。你不接受"失足"的说法，说晶晶"最胆小，不会靠近栏杆"。你坚信朱朝阳做了什么，可能是推，可能是吓。', lying: false },
        c: { directive: '你是徐静。你透露张东升知道你妹妹的事，他曾说"那孩子很聪明，懂得利用机会"。你怀疑张东升和朱朝阳之间有什么交易。', lying: false },
      },
    },
    {
      roundNumber: 5,
      scene: '关键证据：一段新的录音。',
      contradictions: [{ betweenRoles: ['a', 'c'], topic: '勒索视频的交易', keywords: ['三十万', '删视频', '交易', '合作'], description: '徐静发现张东升给朱朝阳转账，朱朝阳说是借的。' }],
      roleDirectives: {
        a: { directive: '你是朱朝阳。你承认拿了张东升的钱，但辩解说是"借的学费"。你的谎言越来越难以自圆，你开始沉默。', lying: true },
        b: { directive: '你是王瑶。你质问朱朝阳：如果真是借的，为什么转账备注是"封口费"？你指出张东升在花钱收买他。', lying: false },
        c: { directive: '你是徐静。你出示银行记录，显示张东升多次给朱朝阳转账，总额超过三十万。你意识到这场交易比你想象的更深。', lying: false },
      },
    },
    {
      roundNumber: 6,
      scene: '徐静准备说出全部真相。',
      roleDirectives: {
        a: { directive: '你是朱朝阳。你看到证据确凿，开始崩溃。你承认你利用张东升除掉了妹妹，因为"她抢走了爸爸"。但你否认推她，说是"她自己掉下去的"。', lying: false },
        b: { directive: '你是王瑶。你听完真相后痛苦万分，你质问朱朝阳："她才十岁！"你意识到这场悲剧源于成人的忽视和孩子的扭曲。', lying: false },
        c: { directive: '你是徐静。你总结：张东升杀了你的父母，朱朝阳间接导致妹妹死亡，而你自己也活在一个杀人犯的阴影下。你决定报警。', lying: false },
      },
    },
    {
      roundNumber: 7,
      scene: '最终轮：如果一切可以重来。',
      contradictions: [{ betweenRoles: ['a', 'b'], topic: '谁该为朱晶晶的死负责', keywords: ['我', '他', '意外', '谋杀'], description: '朱朝阳认为是意外，王瑶认为是谋杀。' }],
      roleDirectives: {
        a: { directive: '你是朱朝阳。你反思：如果那天我没有带她去五楼，如果我没有吓唬她，如果...但她已经不在了。我会带着这个秘密活下去。', lying: false },
        b: { directive: '你是王瑶。你痛苦地说：如果我对你好一点，如果我没有偏心晶晶，如果你感受到被爱...悲剧是不是就不会发生？', lying: false },
        c: { directive: '你是徐静。你总结：这个案件没有赢家。张东升是凶手，朱朝阳是帮凶，而我们这些成年人都是失职的旁观者。', lying: false },
      },
    },
  ],
}
