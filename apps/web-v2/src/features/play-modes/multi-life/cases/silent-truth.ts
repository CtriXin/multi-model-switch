import type { MultiLifeCase } from '../types'

export const SILENT_TRUTH_CASE: MultiLifeCase = {
  id: 'silent-truth',
  title: '沉默的真相 · 长夜',
  premise:
    '知名检察官江阳离奇死亡，尸体被发现在行李箱中。现场证据显示是自杀，但他的旧案卷宗里藏着惊天秘密——十年前，他调查的一起支教老师死亡案牵扯出地方黑恶势力保护伞。三个关键人物被问询：江阳的前女友（现法医）、当年支教案的目击者（现已精神失常）、以及江阳的律师朋友（唯一知道他计划的人）。',
  truth:
    '江阳是自杀，但他是用死亡换取关注。十年前，支教老师侯贵平发现学生被性侵并向上举报，却被黑恶势力灭口，伪装成"强奸后自杀"。江阳花了十年追查真相，却被陷害入狱、身败名裂。最终他决定用自己的死制造轰动效应，让社会关注这个被压制的案件。他的律师朋友协助他完成了这个"殉道"计划。',
  totalRounds: 7,
  challengeBudget: 4,
  roles: [
    {
      id: 'a',
      name: '前女友 吴爱可',
      archetype: 'analyst',
      reliability: 0.6,
      hiddenKnowledge: 0.5,
      lyingPattern: 'selective',
      personality:
        '吴爱可三十五岁，现任法医，江阳的前女友。她当年因为懦弱离开了江阳，一直心怀愧疚。她的证词有保留，因为她知道一些江阳的计划但没有参与。',
    },
    {
      id: 'b',
      name: '目击者 李雪',
      archetype: 'witness',
      reliability: 0.4,
      hiddenKnowledge: 0.9,
      lyingPattern: 'selective',
      personality:
        '李雪三十岁，当年是侯贵平的学生，性侵案的幸存者之一。她因为创伤而精神不稳定，但掌握着最关键的证词。她的证词断断续续，但信息量巨大。',
    },
    {
      id: 'c',
      name: '律师 张超',
      archetype: 'suspect',
      reliability: 0.5,
      hiddenKnowledge: 0.95,
      lyingPattern: 'consistent',
      personality:
        '张超四十五岁，江阳的大学同学，知名刑辩律师。他协助江阳完成了自杀计划，包括抛尸和制造舆论。他是这个"殉道计划"的执行者。',
    },
  ],
  rounds: [
    {
      roundNumber: 1,
      scene: '江阳死亡案发现场，一个行李箱被丢弃在地铁站。',
      roleDirectives: {
        a: { directive: '你是吴爱可。你作为法医检查尸体，发现是机械性窒息死亡，表面看是自杀。你注意到江阳身上有旧伤，是当年在狱中被打的。你内心痛苦但保持专业。', lying: false },
        b: { directive: '你是李雪。你听到江阳死了，情绪激动，说"他答应过要帮侯老师报仇的"。你开始说胡话，提到"照片"和"名单"，但语无伦次。', lying: false },
        c: { directive: '你是张超。你作为嫌疑人被拘留，因为是你抛的尸。你 initially 承认杀人，但说"真相需要被看见"。你在引导警方去查十年前的旧案。', lying: true },
      },
    },
    {
      roundNumber: 2,
      scene: '调查江阳的过去，发现他曾因"受贿罪"入狱三年。',
      roleDirectives: {
        a: { directive: '你是吴爱可。你承认江阳是被陷害的，那些罪名都是假的。你说他为了查侯贵平案，得罪了太多人。你后悔当年没有陪他走下去。', lying: false },
        b: { directive: '你是李雪。你提到侯贵平老师，说他"是好人，他救了我们"。你开始回忆当年的事，提到有"大人物"来村里，然后侯老师就死了。', lying: false },
        c: { directive: '你是张超。你透露江阳入狱期间遭受了非人待遇，他说"就算死，我也要死得有价值"。你开始暗示他的死不是简单的自杀。', lying: false },
      },
    },
    {
      roundNumber: 3,
      scene: '矛盾点：江阳死前给张超打了最后一通电话。',
      contradictions: [{ betweenRoles: ['a', 'c'], topic: '江阳死前状态', keywords: ['绝望', '平静', '计划', '遗言'], description: '吴爱可认为江阳死前很绝望，但张超说他很"平静"。' }],
      roleDirectives: {
        a: { directive: '你是吴爱可。你说江阳最后一次见你的时候很颓废，说"我输了，输得一败涂地"。你以为他要放弃，没想到他会选择死亡。', lying: false },
        b: { directive: '你是李雪。你突然清醒了一会儿，说出关键信息："侯老师有张照片，上面有很多大人物，还有女学生"。这是十年来第一次有人明确提到证据。', lying: false },
        c: { directive: '你是张超。你承认江阳死前给你打了电话，说"帮我完成最后一件事"。你承认你帮他完成了自杀装置，但你坚持说这是他的选择。', lying: false },
      },
    },
    {
      roundNumber: 4,
      scene: '调查侯贵平案，发现当年定性为"强奸后自杀"存在大量疑点。',
      roleDirectives: {
        a: { directive: '你是吴爱可。你从法医角度分析：侯贵平的尸体显示死后被投水，不是自杀。而且体内有镇静剂成分，说明是被迷晕后杀害的。你意识到这是一起谋杀。', lying: false },
        b: { directive: '你是李雪。你回忆起更多细节：那天晚上你看到一些车来村里，然后侯老师被带走，再也没回来。你当时躲起来了，因为你也在那些"名单"上。', lying: false },
        c: { directive: '你是张超。你出示江阳收集的证据：一张名单，上面有当地政商要人的名字，还有被性侵的女学生名字。这就是侯贵平被害的原因。', lying: false },
      },
    },
    {
      roundNumber: 5,
      scene: '关键证据：侯贵平当年寄出的举报信被发现。',
      contradictions: [{ betweenRoles: ['b', 'c'], topic: '举报信的内容', keywords: ['性侵', '名单', '照片', '证据'], description: '李雪说举报信里有照片，但张超说只有名单。实际上江阳手里有完整的证据链。' }],
      roleDirectives: {
        a: { directive: '你是吴爱可。你意识到江阳手里有完整的证据，但他选择了最极端的方式曝光——用死亡制造舆论。你说"他本可以用其他方式"。', lying: false },
        b: { directive: '你是李雪。你确认侯老师当年拍了照片，"是那些人和我们在一起的画面"。你说江阳死前见过你，拿走了照片的复印件。', lying: false },
        c: { directive: '你是张超。你承认江阳的计划：先用死亡引起关注，然后你作为"凶手"被捕，在法庭上公开所有证据。这是一个精心设计的局。', lying: false },
      },
    },
    {
      roundNumber: 6,
      scene: '张超在法庭上准备公开真相。',
      roleDirectives: {
        a: { directive: '你是吴爱可。你作为证人出庭，说出你知道的一切。你说江阳不是殉道者，他是被逼死的，是被这个沉默的系统杀死的。', lying: false },
        b: { directive: '你是李雪。你克服了心理障碍，在法庭上指证当年的施害者。你说"侯老师和江检察官都是为了保护我们而死，我不能再沉默"。', lying: false },
        c: { directive: '你是张超。你在法庭上完成了江阳的遗愿，公开了所有证据，包括名单、照片、录音。你说你准备好承担"协助自杀"的罪名了。', lying: false },
      },
    },
    {
      roundNumber: 7,
      scene: '最终轮：长夜终明。',
      contradictions: [{ betweenRoles: ['a', 'c'], topic: '江阳的选择是否值得', keywords: ['值得', '悲哀', '无奈', '正义'], description: '吴爱可认为江阳的选择是悲哀的，张超认为这是值得的牺牲。' }],
      roleDirectives: {
        a: { directive: '你是吴爱可。你反思：如果当年我没有离开他，如果社会能更早关注，如果那些人不那么有权有势...江阳是不是就不用死？', lying: false },
        b: { directive: '你是李雪。你说江阳和侯老师改变了你的命运，你终于可以堂堂正正地活着。你说"他们的死不是结束，是开始"。', lying: false },
        c: { directive: '你是张超。你说江阳用生命撕开了一道口子，让光照进了黑暗。虽然代价巨大，但长夜终明。你准备好了去陪他。', lying: false },
      },
    },
  ],
}
