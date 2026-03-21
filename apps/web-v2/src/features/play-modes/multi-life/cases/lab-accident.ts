import type { MultiLifeCase } from '../types'

export const LAB_ACCIDENT_CASE: MultiLifeCase = {
  id: 'lab-accident',
  title: '实验室禁区',
  premise:
    '某高校生物实验室发生"意外"，研究生导师郑教授死于实验事故。现场显示是毒气泄漏，但警方怀疑是他杀。三位相关人员被问询：死者的博士生（兼项目合作者）、实验室管理员、以及郑教授的竞争对手（另一位教授）。',
  truth:
    '凶手是博士生小杨。郑教授长期霸占他的研究成果，将他的论文署名为第一作者，并威胁如果不听话就让他无法毕业。小杨发现郑教授还挪用了项目经费，决定铤而走险。他利用实验室的毒气系统，在郑教授独自加班时远程触发泄漏，伪装成设备故障。实验室管理员发现设备记录有异常但没敢说，竞争对手教授知道郑教授的学术不端行为但乐见其成。',
  totalRounds: 7,
  challengeBudget: 4,
  roles: [
    {
      id: 'a',
      name: '博士生 小杨',
      archetype: 'suspect',
      reliability: 0.3,
      hiddenKnowledge: 0.95,
      lyingPattern: 'consistent',
      personality:
        '小杨二十八岁，聪明但压抑，长期被导师压榨。他对实验室设备极其熟悉，精心策划了这场"意外"。他表面看起来老实，内心充满怨恨。',
    },
    {
      id: 'b',
      name: '实验室管理员 周师傅',
      archetype: 'witness',
      reliability: 0.6,
      hiddenKnowledge: 0.7,
      lyingPattern: 'selective',
      personality:
        '周师傅五十五岁，在实验室工作二十年，老实但怕事。他知道一些内幕但不敢说，因为担心丢掉工作。他的证词部分真实，但关于设备记录的部分有所隐瞒。',
    },
    {
      id: 'c',
      name: '竞争对手 李教授',
      archetype: 'analyst',
      reliability: 0.7,
      hiddenKnowledge: 0.6,
      lyingPattern: 'selective',
      personality:
        '李教授五十岁，和郑教授有学术竞争关系，知道郑教授学术不端但没有证据。他对郑教授的死感到幸灾乐祸，但同时也担心影响学校声誉。',
    },
  ],
  rounds: [
    // Round 1
    {
      roundNumber: 1,
      scene: '实验室外，警方正在封锁现场。实验室门口贴着"危险：有毒气体"的警示牌。',
      roleDirectives: {
        a: {
          directive: '你是小杨。你表现得悲伤和震惊，说郑教授是你的导师，"我一直很尊敬他\"。你暗示可能是设备老化导致的意外。你要表现得像个悲痛的学生。',
          lying: true,
        },
        b: {
          directive: '你是周师傅。你如实说你发现毒气报警时已经是晚上十点，郑教授倒在实验台前。你立即疏散人员并报警。你说设备是五年前购买的。',
          lying: false,
        },
        c: {
          directive: '你是李教授。你从专业角度分析：郑教授研究的病毒样本需要严格的生物安全防护，如果操作失误确实可能导致泄漏。你暗示可能是操作失误。',
          lying: false,
        },
      },
    },
    // Round 2
    {
      roundNumber: 2,
      scene: '初步调查发现，毒气泄漏的触发方式存在疑点。',
      roleDirectives: {
        a: {
          directive: '你是小杨。你透露郑教授最近压力很大，说他"经常工作到深夜\"，\"可能是太累了操作失误\"。你在暗示的同时显得关心老师。',
          lying: false,
        },
        b: {
          directive: '你是周师傅。你补充设备维护记录：上个月刚做过全面检查，所有设备都正常。你开始怀疑这可能不是意外，但你不敢明说。',
          lying: false,
        },
        c: {
          directive: '你是李教授。你透露学术圈的内幕：郑教授最近因为论文署名问题和几个学生闹得不愉快，有人威胁要举报他。你暗示可能有学生怀恨在心。',
          lying: false,
        },
      },
    },
    // Round 3: 第一次矛盾
    {
      roundNumber: 3,
      scene: '监控显示小杨在案发前两小时曾进入实验室，待了四十分钟。',
      contradictions: [
        {
          betweenRoles: ['a', 'b'],
          topic: '进入实验室的时间',
          keywords: ['十分钟', '四十分钟', '拿东西', '调试', '很快', '很久'],
          description: '小杨说只进去\"十分钟拿资料\"，但监控显示待了四十分钟，且一直在操作设备。',
        },
      ],
      roleDirectives: {
        a: {
          directive: '你是小杨。你改口说你进去是\"调试设备\"，因为你发现有个参数异常。你辩解说你担心设备出问题，所以多检查了一会儿。',
          lying: true,
        },
        b: {
          directive: '你是周师傅。你说监控显示小杨一直在操作气体控制系统，还打开了平时不开的维护面板。你当时以为他是在做正常维护，现在想想很奇怪。',
          lying: false,
        },
        c: {
          directive: '你是李教授。你指出从专业角度：只有非常熟悉设备的人才能绕过安全联锁触发泄漏，普通操作失误不会导致这种结果。',
          lying: false,
        },
      },
    },
    // Round 4
    {
      roundNumber: 4,
      scene: '警方查到小杨和郑教授的论文署名纠纷记录。',
      roleDirectives: {
        a: {
          directive: '你是小杨。你承认有过分歧，但说\"那是学术讨论\"，\"最后都解决了\"。你表现得委屈，说\"我怎么会害自己的导师\"。',
          lying: false,
        },
        b: {
          directive: '你是周师傅。你透露你 overheard 过他们的争吵，郑教授威胁小杨\"不听话就让你毕不了业\"。你当时觉得很过分。',
          lying: false,
        },
        c: {
          directive: '你是李教授。你补充说郑教授在学术圈风评不好，\"霸占学生成果\"是出了名的。你暗示如果小杨是凶手，也是\"被逼急了\"。',
          lying: false,
        },
      },
    },
    // Round 5: 第二次矛盾
    {
      roundNumber: 5,
      scene: '实验室的远程访问日志显示，案发时有人通过局域网远程操作了毒气系统。',
      contradictions: [
        {
          betweenRoles: ['a', 'c'],
          topic: '谁能远程操作',
          keywords: ['权限', '远程', '只有他能', '管理员', '密码'],
          description: '小杨说只有郑教授有权限，但日志显示操作来源是小杨的电脑。',
        },
      ],
      roleDirectives: {
        a: {
          directive: '你是小杨。你辩解说你确实能远程监控设备，但\"我只是监控，没有操作\"。你开始紧张，说话结巴。',
          lying: true,
        },
        b: {
          directive: '你是周师傅。你确认小杨确实有助教的系统权限，因为郑教授让他帮忙管理设备。你说这个权限可以远程控制气体阀门。',
          lying: false,
        },
        c: {
          directive: '你是李教授。你从技术上分析：远程操作需要高级权限和系统密码，普通学生不可能做到，除非是被授权的管理员。',
          lying: false,
        },
      },
    },
    // Round 6
    {
      roundNumber: 6,
      scene: '警方在小杨的电脑里发现了删除的系统操作记录备份。',
      roleDirectives: {
        a: {
          directive: '你是小杨。你面对铁证开始崩溃，你承认你远程操作了系统，但辩解说是\"误操作\"，\"我没想杀他，只是想吓吓他\"。',
          lying: true,
        },
        b: {
          directive: '你是周师傅。你透露案发前一周，小杨曾问你\"如果毒气泄漏会发生什么\"，你当时以为是正常询问，现在想想很可疑。',
          lying: false,
        },
        c: {
          directive: '你是李教授。你总结：这不是误操作，而是精心策划的谋杀。远程触发、删除记录、伪装意外，步步为营。',
          lying: false,
        },
      },
    },
    // Round 7
    {
      roundNumber: 7,
      scene: '最终轮。警方查到郑教授挪用项目经费的证据，以及小杨毕业延期三次的记录。',
      contradictions: [
        {
          betweenRoles: ['a', 'c'],
          topic: '动机强度',
          keywords: ['忍无可忍', '一般矛盾', '被逼急', '普通纠纷'],
          description: '小杨试图淡化动机，但证据显示他已被逼到绝境。',
        },
      ],
      roleDirectives: {
        a: {
          directive: '你是小杨。你彻底崩溃，你承认所有罪行。你说\"他毁了我的人生，我只是想保护自己\"。你哭诉延期三年、成果被抢、无法毕业的痛苦。',
          lying: false,
        },
        b: {
          directive: '你是周师傅。你唏嘘感慨，说\"都是这个制度逼的\"。你为小杨求情，说郑教授确实做得过分，但这是两条人命啊。',
          lying: false,
        },
        c: {
          directive: '你是李教授。你总结：这是学术压迫导致的悲剧。小杨是凶手，但郑教授也不是无辜的。你建议调查学术腐败问题，防止悲剧重演。',
          lying: false,
        },
      },
    },
  ],
}
