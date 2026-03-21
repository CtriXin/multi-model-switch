import type { MultiLifeCase } from '../types'

export const ENDLESS_AUTUMN_CASE: MultiLifeCase = {
  id: 'endless-autumn',
  title: '漫长的季节 · 改变',
  premise:
    '1998年秋天的钢厂宿舍区，高中生王阳被发现死在废弃的炼钢炉旁。警方判定为自杀，但父亲王响坚信另有隐情。十八年后，一起套牌车肇事案让当年的真相重新浮出水面。三个关键人物被重新问询：当年死者的女友沈墨、钢厂保卫科长的儿子龚彪、以及当年的刑警队长马德胜。',
  truth:
    '凶手是沈墨的变态养父沈栋梁。沈墨长期遭受养父性侵，王阳发现后计划带她私奔。沈栋梁发现他们的计划后，在炼钢炉旁将王阳推下致死，并伪造自杀现场。沈墨为了保护龚彪（当时也在现场但被吓傻了）而沉默多年。马德胜当年查案时发现了蛛丝马迹，但因为证据不足和上级压力未能破案。',
  totalRounds: 7,
  challengeBudget: 4,
  roles: [
    {
      id: 'a',
      name: '沈墨',
      archetype: 'witness',
      reliability: 0.4,
      hiddenKnowledge: 0.95,
      lyingPattern: 'selective',
      personality:
        '沈墨三十六岁，当年是钢厂医院的护士，现在是一家诊所的医生。她长期承受心理创伤，为了保护他人而隐瞒真相。她的证词半真半假，关键信息被刻意模糊。',
    },
    {
      id: 'b',
      name: '龚彪',
      archetype: 'suspect',
      reliability: 0.5,
      hiddenKnowledge: 0.7,
      lyingPattern: 'selective',
      personality:
        '龚彪三十七岁，当年是王阳的好友，现在是出租车司机。他当年确实在现场附近，但因为害怕而没有出面作证。他一直被愧疚折磨，但又不敢说出全部真相。',
    },
    {
      id: 'c',
      name: '马德胜',
      archetype: 'analyst',
      reliability: 0.8,
      hiddenKnowledge: 0.6,
      lyingPattern: 'never',
      personality:
        '马德胜六十五岁，退休刑警队长，当年负责此案。他一直对当年的结论有怀疑，但受制于当时的环境没能深挖。现在退休了，终于可以说出当年的发现。',
    },
  ],
  rounds: [
    // Round 1
    {
      roundNumber: 1,
      scene: '2016年，旧案重提。王响坚持要重新调查儿子的死因。',
      roleDirectives: {
        a: {
          directive: '你是沈墨。你表现得很痛苦，说"那件事我花了十八年想忘记\"。你承认你当时是王阳的女友，但说他"太年轻，太冲动\"。你暗示王阳可能有自杀倾向。',
          lying: true,
        },
        b: {
          directive: '你是龚彪。你说那天晚上你和王阳约好了见面，但你迟到了。你到的时候只看到警车和围观人群。你表现得很懊悔，说"如果我当时准时到，也许能阻止\"。',
          lying: false,
        },
        c: {
          directive: '你是马德胜。你回顾当年的案情：王阳死在炼钢炉底部，现场没有打斗痕迹，死者身上没有外伤，只有坠落伤。你承认当年结案太快，因为有"其他压力\"。',
          lying: false,
        },
      },
    },
    // Round 2
    {
      roundNumber: 2,
      scene: '调查深入。马德胜翻出了当年的案卷，发现了一些被忽略的细节。',
      roleDirectives: {
        a: {
          directive: '你是沈墨。当被问及王阳死前的心理状态时，你说他"最近很焦虑\"，\"说要带我离开这里\"。你透露王阳发现了你的一些"家庭问题\"。',
          lying: false,
        },
        b: {
          directive: '你是龚彪。你补充说王阳死前一周确实提过"要离开桦林\"，还说要"带她走\"。你当时以为只是年轻人的冲动话，没在意。',
          lying: false,
        },
        c: {
          directive: '你是马德胜。你指出一个关键疑点：王阳的遗书笔迹鉴定有争议，当年认为是本人写的，但现在看有些笔画过于工整，像是模仿。而且遗书内容太"理智\"了。',
          lying: false,
        },
      },
    },
    // Round 3: 第一次矛盾
    {
      roundNumber: 3,
      scene: '有目击者称看到沈墨的养父沈栋梁当晚在炼钢厂附近出现。',
      contradictions: [
        {
          betweenRoles: ['a', 'c'],
          topic: '养父的行踪',
          keywords: ['在家', '钢厂', '没出门', '出现', '目击'],
          description: '沈墨说养父当晚在家，但有目击者看到沈栋梁在钢厂附近。',
        },
      ],
      roleDirectives: {
        a: {
          directive: '你是沈墨。你坚持说养父当晚在家，说"他身体不好，很少出门\"。但你说话时眼神躲闪，你补充说"就算他出去，也是去散步\"。',
          lying: true,
        },
        b: {
          directive: '你是龚彪。你突然想起来：那天晚上你去钢厂的路上，确实看到一个男人站在厂门口，背影像沈墨的养父。你当时没在意，现在觉得很可疑。',
          lying: false,
        },
        c: {
          directive: '你是马德胜。你出示新的证人证词：当年钢厂夜班工人看到沈栋梁晚上九点多在厂区徘徊，但他当年否认去过那里。这是重大疑点。',
          lying: false,
        },
      },
    },
    // Round 4
    {
      roundNumber: 4,
      scene: '调查沈栋梁的背景。马德胜发现沈墨长期遭受养父虐待。',
      roleDirectives: {
        a: {
          directive: '你是沈墨。在压力下你崩溃大哭，承认养父"确实对我不好\"，\"经常打骂\"。但你否认他杀人，说"他虽然坏，但不至于杀人\"。你内心在保护某人。',
          lying: false,
        },
        b: {
          directive: '你是龚彪。你透露一个秘密：你当年其实知道沈墨被养父虐待的事，王阳也发现了，他们计划私奔。你劝过王阳"别惹那个疯子\"。',
          lying: false,
        },
        c: {
          directive: '你是马德胜。你从专业角度分析：沈栋梁有强烈的控制欲和占有欲，沈墨要私奔等于"背叛\"。这种人面对"夺女之恨\"时，杀人动机非常充分。',
          lying: false,
        },
      },
    },
    // Round 5: 第二次矛盾
    {
      roundNumber: 5,
      scene: '龚彪的证词出现重大变化。',
      contradictions: [
        {
          betweenRoles: ['a', 'b'],
          topic: '龚彪当晚是否在现场',
          keywords: ['迟到', '在场', '看到', '躲起来', '害怕'],
          description: '龚彪说迟到了没看到，但沈墨暗示龚彪其实更早到了现场。',
        },
      ],
      roleDirectives: {
        a: {
          directive: '你是沈墨。在警方压力下你说出部分真相：龚彪其实当晚确实到了钢厂，他躲在暗处看到了一切，但因为害怕没有出来。你这些年保密是为了保护他。',
          lying: false,
        },
        b: {
          directive: '你是龚彪。你的谎言被戳穿。你承认你当晚确实准时到了，你看到了沈栋梁推王阳下去的那一幕，但你吓傻了，躲在废料堆后面不敢出声。你忏悔了十八年。',
          lying: false,
        },
        c: {
          directive: '你是马德胜。你质问龚彪：如果你当年站出来作证，沈栋梁早就伏法了，沈墨也不用承受十八年的痛苦。你的沉默也是另一种伤害。',
          lying: false,
        },
      },
    },
    // Round 6
    {
      roundNumber: 6,
      scene: '找到新的物证。当年炼钢炉旁的一枚纽扣，上面有沈栋梁的DNA。',
      roleDirectives: {
        a: {
          directive: '你是沈墨。你看到这个证据后彻底崩溃，你说"够了，我说出全部\"。你承认你这些年一直知道真相，但为了不让龚彪背负"见死不救\"的罪名而沉默。',
          lying: false,
        },
        b: {
          directive: '你是龚彪。你请求沈墨的原谅，说"我不该让你一个人承担\"。你愿意出庭作证，说出当年看到的一切，哪怕自己也要承担"包庇\"的责任。',
          lying: false,
        },
        c: {
          directive: '你是马德胜。你总结证据链：沈栋梁有动机（占有欲）、有现场（DNA）、有证人（龚彪）、有前科（虐待）。建议立即申请逮捕令。',
          lying: false,
        },
      },
    },
    // Round 7
    {
      roundNumber: 7,
      scene: '最终轮。沈栋梁被捕，真相大白。',
      contradictions: [
        {
          betweenRoles: ['a', 'b'],
          topic: '如果当时选择不同',
          keywords: ['私奔', '报警', '告诉'],
          description: '沈墨和龚彪反思如果当年做出不同选择，悲剧是否可以避免。',
        },
      ],
      roleDirectives: {
        a: {
          directive: '你是沈墨。你反思：如果当年王阳提议私奔时我选择报警而不是逃跑，如果我没有隐瞒养父的虐待，如果龚彪勇敢站出来...太多如果。但时间无法倒流。',
          lying: false,
        },
        b: {
          directive: '你是龚彪。你痛苦地说：如果当时我冲出去阻止，哪怕只是大喊一声，王阳可能不会死。我花了十八年问自己"为什么我不敢\"。',
          lying: false,
        },
        c: {
          directive: '你是马德胜。你总结：这是一个关于勇气和沉默的教训。沈栋梁是凶手，但每个人的沉默都让这个悲剧延续了十八年。真相虽迟但到。',
          lying: false,
        },
      },
    },
  ],
}
