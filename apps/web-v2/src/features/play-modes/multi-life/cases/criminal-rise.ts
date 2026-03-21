import type { MultiLifeCase } from '../types'

export const CRIMINAL_RISE_CASE: MultiLifeCase = {
  id: 'criminal-rise',
  title: '狂飙 · 抉择',
  premise:
    '京海市，强盛集团涉黑案关键证人突然死亡，案件陷入僵局。三名核心人物被秘密问询：安欣（执着的刑警，二十年追查此案）、高启强（从鱼贩到黑老大的传奇人物）、以及孟钰（记者，安欣的前女友，也是政法委书记的女儿）。他们各自掌握着案件的不同侧面。',
  truth:
    '强盛集团的保护伞是政法委书记赵立冬，而高启强只是他的"白手套"。关键证人是被赵立冬派人灭口的。高启强想摆脱赵立冬的控制，暗中收集了证据准备反水。安欣二十年来收集的证据都指向高启强，却忽略了更高层的腐败。孟钰作为记者知道一些内幕，但因为父亲的职位而左右为难。',
  totalRounds: 7,
  challengeBudget: 4,
  roles: [
    {
      id: 'a',
      name: '刑警 安欣',
      archetype: 'analyst',
      reliability: 0.85,
      hiddenKnowledge: 0.6,
      lyingPattern: 'never',
      personality:
        '安欣四十五岁，满头白发的刑警，二十年来执着追查高启强。他因为过于正直而被边缘化，但从未放弃。他手里有大量证据，但都只触及中层。',
    },
    {
      id: 'b',
      name: '高启强',
      archetype: 'suspect',
      reliability: 0.3,
      hiddenKnowledge: 0.95,
      lyingPattern: 'selective',
      personality:
        '高启强五十三岁，从菜市场鱼贩崛起的黑老大，城府极深。他现在想洗白脱身，但知道太多秘密。他的证词真假参半，目的是保护自己同时扳倒赵立冬。',
    },
    {
      id: 'c',
      name: '记者 孟钰',
      archetype: 'witness',
      reliability: 0.5,
      hiddenKnowledge: 0.7,
      lyingPattern: 'selective',
      personality:
        '孟钰四十三岁，资深调查记者，安欣的前女友。她知道父亲赵立冬和高启强的关系，内心在正义和亲情之间挣扎。她的证词有保留。',
    },
  ],
  rounds: [
    {
      roundNumber: 1,
      scene: '秘密问询室，证人死亡案让三人再次聚首。',
      roleDirectives: {
        a: { directive: '你是安欣。你质问高启强："证人都死了，你是不是又要逍遥法外？"你表现出二十年的疲惫和愤怒，但眼神依然执着。', lying: false },
        b: { directive: '你是高启强。你表现得很平静，说"安警官，你还是这么执着"。你暗示证人的死不是强盛集团干的，但你没有明说。', lying: false },
        c: { directive: '你是孟钰。你看到安欣和高启强对峙，内心复杂。你说"二十年了，你们俩还在斗"。你暗示你知道一些内幕但不敢说。', lying: false },
      },
    },
    {
      roundNumber: 2,
      scene: '调查证人死因，发现是职业杀手所为。',
      roleDirectives: {
        a: { directive: '你是安欣。你从专业角度分析：杀人手法干净利落，是职业杀手。但强盛集团一般不用这种方式，你怀疑有更专业的幕后黑手。', lying: false },
        b: { directive: '你是高启强。你透露你确实想杀那个证人灭口，但"有人抢先了一步"。你暗示有更高层的人不想让证人开口。', lying: false },
        c: { directive: '你是孟钰。你听到父亲打电话时提到过"处理干净"，你开始怀疑父亲和案件有关。你内心在挣扎是否要告诉安欣。', lying: false },
      },
    },
    {
      roundNumber: 3,
      scene: '矛盾点：高启强的证词前后矛盾。',
      contradictions: [{ betweenRoles: ['a', 'b'], topic: '强盛集团和赵立冬的关系', keywords: ['合作', '控制', '利用', '保护伞'], description: '高启强说赵立冬控制他，但安欣认为是合作关系。' }],
      roleDirectives: {
        a: { directive: '你是安欣。你质问高启强："你以为供出赵立冬就能减刑？你手上也沾满了血。"你警告他不要耍花样。', lying: false },
        b: { directive: '你是高启强。你反驳说"我只是个手套，手是别人的"。你暗示赵立冬才是真正的幕后黑手，你只是被迫合作。', lying: true },
        c: { directive: '你是孟钰。你听到他们提到你父亲的名字，你崩溃了，说"够了，我知道我父亲不干净，但请给我留点尊严"。', lying: false },
      },
    },
    {
      roundNumber: 4,
      scene: '孟钰掌握了一份关键录音，是她父亲和赵立冬的对话。',
      roleDirectives: {
        a: { directive: '你是安欣。你劝说孟钰交出录音："这是扳倒赵立冬的唯一机会，也是你父亲自首的机会。"你试图打动她的正义感。', lying: false },
        b: { directive: '你是高启强。你也劝孟钰："我手上也有证据，如果我们合作，可以把赵立冬拉下马。这是我洗白的机会。"', lying: false },
        c: { directive: '你是孟钰。你内心挣扎：交出录音意味着父亲入狱，不交意味着让坏人逍遥法外。你说"给我时间考虑"。', lying: false },
      },
    },
    {
      roundNumber: 5,
      scene: '关键证据：高启强出示了他多年来保存的秘密账本。',
      contradictions: [{ betweenRoles: ['b', 'c'], topic: '账本的完整性', keywords: ['完整', '删减', '备份', '隐藏'], description: '高启强说账本是完整的，但孟钰发现缺失了关于她父亲的部分。' }],
      roleDirectives: {
        a: { directive: '你是安欣。你检查账本后发现确实缺失了关键部分，你质问高启强："你还在保护谁？"你意识到水比想象的深。', lying: false },
        b: { directive: '你是高启强。你承认账本有删减，说"有些证据我要留着保命"。你暗示如果你把所有证据都交出，你会被灭口。', lying: false },
        c: { directive: '你是孟钰。你意识到高启强在利用证据要挟各方，包括你父亲。你决定不再犹豫，把录音交给了安欣。', lying: false },
      },
    },
    {
      roundNumber: 6,
      scene: '赵立冬准备反击，试图销毁所有证据。',
      roleDirectives: {
        a: { directive: '你是安欣。你得知赵立冬准备出逃，你必须立即行动。你说"二十年了，终于等到这一天"。你准备申请逮捕令。', lying: false },
        b: { directive: '你是高启强。你意识到赵立冬要对你灭口，你决定抢先一步，把所有证据都交给安欣，换取证人保护。你说"我不想死"。', lying: false },
        c: { directive: '你是孟钰。你面对父亲，说服他自首："爸，趁还来得及，别一错再错了。"你父亲最终同意了。', lying: false },
      },
    },
    {
      roundNumber: 7,
      scene: '最终轮：正义迟到但到。',
      contradictions: [{ betweenRoles: ['a', 'b'], topic: '高启强是否值得同情', keywords: ['可恨', '可悲', '活该', '无奈'], description: '安欣认为高启强罪有应得，高启强说自己也是受害者。' }],
      roleDirectives: {
        a: { directive: '你是安欣。你总结：高启强确实可悲，但他的每一步选择都是他自己做的。二十年的追查终于结束，但代价太大了。', lying: false },
        b: { directive: '你是高启强。你反思：如果当年我没有走上这条路，如果我没有认识赵立冬...但人生没有如果。我接受审判。', lying: false },
        c: { directive: '你是孟钰。你说这场斗争没有赢家，安欣失去了青春，你失去了父亲，高启强失去了一切。但至少真相大白了。', lying: false },
      },
    },
  ],
}
