import type { MultiLifeCase } from '../types'

export const ANTIQUE_DEALER_CASE: MultiLifeCase = {
  id: 'antique-dealer',
  title: '古董迷局',
  premise:
    '著名古董商马先生在拍卖会预展期间死于VIP室，死因是被人用青铜爵击打头部。即将拍卖的镇馆之宝——一尊明代青花瓷瓶也不翼而飞。三位在场人员被问询：马先生的合伙人、负责鉴定的专家、以及一位神秘买家。',
  truth:
    '凶手是鉴定专家老徐。他长期为马先生做伪证，将赝品鉴定为真品高价出售。这次拍卖的青花瓷瓶是他做的最高明的一件赝品，但马先生临时反悔不想拍卖，威胁要揭发老徐。老徐用现场的青铜爵击中马先生后，慌乱中打碎瓷瓶发现是赝品，于是带着碎片逃离，伪造成盗窃案。',
  totalRounds: 7,
  challengeBudget: 4,
  roles: [
    {
      id: 'a',
      name: '合伙人 刘总',
      archetype: 'witness',
      reliability: 0.65,
      hiddenKnowledge: 0.5,
      lyingPattern: 'selective',
      personality:
        '刘总四十五岁，马先生的多年合伙人，知道很多内幕但不敢说。他怀疑公司有造假行为，但没有证据。他的证词有保留，因为他自己也从造假中获利。',
    },
    {
      id: 'b',
      name: '鉴定专家 老徐',
      archetype: 'suspect',
      reliability: 0.2,
      hiddenKnowledge: 0.95,
      lyingPattern: 'consistent',
      personality:
        '老徐六十岁，业内权威的鉴定专家，实际上是个高超的造假者。他善于用专业术语迷惑他人，心理素质极好，但一旦专业领域被质疑就会露出破绽。',
    },
    {
      id: 'c',
      name: '神秘买家 方先生',
      archetype: 'analyst',
      reliability: 0.7,
      hiddenKnowledge: 0.6,
      lyingPattern: 'selective',
      personality:
        '方先生身份神秘，实际上是另一家拍卖行的卧底调查员。他发现这件瓷瓶有问题，本想揭露真相，却遇上命案。他有所隐瞒（关于自己的身份），但不是凶手。',
    },
  ],
  rounds: [
    // Round 1
    {
      roundNumber: 1,
      scene: '拍卖会VIP室，警方正在勘察现场。青铜爵倒在血泊中，展柜破碎。',
      roleDirectives: {
        a: {
          directive: '你是刘总。你发现尸体时非常震惊，说你和马先生半小时前还在讨论拍卖细节。你注意到青花瓷瓶不见了，怀疑是抢劫杀人。你表现得既悲痛又紧张。',
          lying: false,
        },
        b: {
          directive: '你是老徐。你表现得很专业，说瓷瓶是\"无可争议的真品\"，估价五千万。你暗示是专业盗贼所为，因为一般人看不出瓷瓶的价值。你用专业术语包装谎言。',
          lying: true,
        },
        c: {
          directive: '你是方先生。你说你来参加拍卖是因为\"对这件藏品感兴趣\"。你注意到瓷瓶的釉色有些异常，但还没确认就被打断了。你说话谨慎，避免暴露身份。',
          lying: false,
        },
      },
    },
    // Round 2
    {
      roundNumber: 2,
      scene: '警方发现马先生死前正在打电话，通话内容是关于取消拍卖。',
      roleDirectives: {
        a: {
          directive: '你是刘总。你承认知道取消拍卖的事，但说马先生没告诉你原因。你猜测可能是瓷瓶有问题，但不敢确定。你透露马先生最近压力很大。',
          lying: false,
        },
        b: {
          directive: '你是老徐。你否认知道取消拍卖的事，表现得很惊讶。你说瓷瓶绝对没问题，\"我以四十年声誉担保\"。你开始紧张，语速加快。',
          lying: true,
        },
        c: {
          directive: '你是方先生。你从专业角度指出：瓷瓶的底款刻工虽然精细，但釉料成分和明代标准配方有微小差异。你质疑这件瓷瓶可能是\"高仿\"。',
          lying: false,
        },
      },
    },
    // Round 3: 第一次矛盾
    {
      roundNumber: 3,
      scene: '监控显示老徐在案发前进入VIP室和马先生独处了十五分钟。',
      contradictions: [
        {
          betweenRoles: ['a', 'b'],
          topic: '独处时间和内容',
          keywords: ['五分钟', '十五分钟', '鉴定', '争论', '讨论'],
          description: '老徐说只待了五分钟\"例行检查\"，但监控显示待了十五分钟，且两人有激烈争论。',
        },
      ],
      roleDirectives: {
        a: {
          directive: '你是刘总。你说你从监控室看到老徐和马先生争吵，马先生情绪激动地指着瓷瓶，老徐则在辩解什么。大约十五分钟后老徐匆忙离开。',
          lying: false,
        },
        b: {
          directive: '你是老徐。你改口说可能是\"记错了时间\"，但坚持只是\"例行鉴定\"。你说马先生对瓷瓶有疑问，你只是在解释。你的解释开始前后矛盾。',
          lying: true,
        },
        c: {
          directive: '你是方先生。你从专业角度说明：如果是对真品有信心，鉴定专家不会\"匆忙\"离开。老徐的异常行为说明他知道瓷瓶有问题。',
          lying: false,
        },
      },
    },
    // Round 4
    {
      roundNumber: 4,
      scene: '警方在老徐的工作室发现了大量高仿瓷器的原料和工具。',
      roleDirectives: {
        a: {
          directive: '你是刘总。你看到这些证据后很震惊，你开始怀疑老徐长期造假。你承认公司最近几年的\"大拍品\"都是老徐鉴定的，如果都是假的，公司将破产。',
          lying: false,
        },
        b: {
          directive: '你是老徐。你辩解说你只是\"研究古代工艺\"，\"每个专家都有实验材料\"。你的借口很牵强，你开始出汗，手在颤抖。',
          lying: true,
        },
        c: {
          directive: '你是方先生。你指出你追踪老徐已经半年了，他制作的赝品至少有三件已流入市场。你暗示你的真实身份是调查员。',
          lying: false,
        },
      },
    },
    // Round 5: 第二次矛盾
    {
      roundNumber: 5,
      scene: '现场勘查发现瓷瓶碎片的数量不对，似乎少了一部分。',
      contradictions: [
        {
          betweenRoles: ['b', 'c'],
          topic: '瓷瓶去向',
          keywords: ['偷走', '打碎', '完整', '拿走', '消失'],
          description: '老徐说瓷瓶是\"完整的被偷走\"，但现场勘查显示瓷瓶是在现场被打碎的。',
        },
      ],
      roleDirectives: {
        a: {
          directive: '你是刘总。你说展柜的玻璃是从内部被打碎的，说明有人从里面拿东西时打碎的。这不符合\"盗窃\"的特征，更像是\"慌乱中打碎\"。',
          lying: false,
        },
        b: {
          directive: '你是老徐。你坚持说瓷瓶是\"被偷走的\"，但当你被问到现场碎片时，你改口说\"可能盗贼打碎了\"。你的谎言越来越乱。',
          lying: true,
        },
        c: {
          directive: '你是方先生。你从碎片分析：瓷片的断面显示是\"新痕\"，而且碎片的分布集中在门口方向，说明凶手是带着碎片离开的。',
          lying: false,
        },
      },
    },
    // Round 6
    {
      roundNumber: 6,
      scene: '警方在老徐的车里发现了藏有瓷瓶碎片的包裹。',
      roleDirectives: {
        a: {
          directive: '你是刘总。你得知真相后既愤怒又绝望，你质问老徐为什么要毁掉公司。你透露出马先生可能发现了老徐的秘密，正在准备揭发。',
          lying: false,
        },
        b: {
          directive: '你是老徐。你面对铁证开始崩溃，你承认瓷瓶是假的，但还在狡辩说\"我没想杀人，是他逼我的\"。你的心理防线开始瓦解。',
          lying: true,
        },
        c: {
          directive: '你是方先生。你总结：老徐为了掩盖长期造假的事实，在马先生准备揭发时杀人灭口，并试图伪装成盗窃案。证据链已经完整。',
          lying: false,
        },
      },
    },
    // Round 7
    {
      roundNumber: 7,
      scene: '最终轮。老徐的银行账户显示他通过卖假古董获利数千万。',
      contradictions: [
        {
          betweenRoles: ['a', 'b'],
          topic: '知情程度',
          keywords: ['不知道', '知道', '怀疑', '知情不报', '同谋'],
          description: '老徐暗示刘总也知情，但刘总坚称自己只是\"怀疑\"没有证据。',
        },
      ],
      roleDirectives: {
        a: {
          directive: '你是刘总。你承认你怀疑过，但说\"我没有证据\"，\"我不敢相信\"。你否认参与造假，但承认你\"选择性忽视了迹象\"。',
          lying: false,
        },
        b: {
          directive: '你是老徐。你绝望中试图拉人下水，说\"刘总早就知道\"，\"我们都从中获利\"。这是你的最后挣扎。用第一人称，50-80字。',
          lying: true,
        },
        c: {
          directive: '你是方先生。你总结：老徐是主犯，犯有谋杀和长期诈骗罪；刘总可能涉及知情不报。你建议立即逮捕老徐，并深入调查刘总。',
          lying: false,
        },
      },
    },
  ],
}
