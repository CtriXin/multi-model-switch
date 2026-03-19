// 96 seed tensions — 每个 category 16 个母题张力
// AI 会基于这些 seed + 用户历史改写成具体话题

import type { DailyCategory } from './types'

export interface SeedTension {
  id: string
  category: DailyCategory
  tensionA: string
  tensionB: string
  tags: string[]
}

export const TOPIC_SEEDS: SeedTension[] = [
  // ── tech (16) ──
  { id: 't01', category: 'tech', tensionA: '效率', tensionB: '深度', tags: ['productivity'] },
  { id: 't02', category: 'tech', tensionA: '开源', tensionB: '闭源', tags: ['ecosystem'] },
  { id: 't03', category: 'tech', tensionA: '自动化', tensionB: '人工把控', tags: ['ai'] },
  { id: 't04', category: 'tech', tensionA: '快速迭代', tensionB: '稳定可靠', tags: ['engineering'] },
  { id: 't05', category: 'tech', tensionA: '隐私保护', tensionB: '数据驱动', tags: ['privacy'] },
  { id: 't06', category: 'tech', tensionA: '通用能力', tensionB: '专精能力', tags: ['ai'] },
  { id: 't07', category: 'tech', tensionA: '本地优先', tensionB: '云端优先', tags: ['architecture'] },
  { id: 't08', category: 'tech', tensionA: '简洁设计', tensionB: '功能丰富', tags: ['product'] },
  { id: 't09', category: 'tech', tensionA: '向后兼容', tensionB: '大胆重构', tags: ['engineering'] },
  { id: 't10', category: 'tech', tensionA: '用户体验', tensionB: '技术优雅', tags: ['design'] },
  { id: 't11', category: 'tech', tensionA: 'AI 辅助决策', tensionB: '人类最终决策', tags: ['ai'] },
  { id: 't12', category: 'tech', tensionA: '全栈工程师', tensionB: '专业分工', tags: ['career'] },
  { id: 't13', category: 'tech', tensionA: '先发优势', tensionB: '后发制人', tags: ['strategy'] },
  { id: 't14', category: 'tech', tensionA: '免费增长', tensionB: '付费质量', tags: ['business'] },
  { id: 't15', category: 'tech', tensionA: '算力暴力', tensionB: '算法精巧', tags: ['ai'] },
  { id: 't16', category: 'tech', tensionA: '平台生态', tensionB: '独立工具', tags: ['product'] },

  // ── society (16) ──
  { id: 's01', category: 'society', tensionA: '个人自由', tensionB: '集体秩序', tags: ['governance'] },
  { id: 's02', category: 'society', tensionA: '公平优先', tensionB: '效率优先', tags: ['policy'] },
  { id: 's03', category: 'society', tensionA: '传统价值', tensionB: '现代观念', tags: ['culture'] },
  { id: 's04', category: 'society', tensionA: '本地化', tensionB: '全球化', tags: ['economy'] },
  { id: 's05', category: 'society', tensionA: '言论自由', tensionB: '信息规范', tags: ['media'] },
  { id: 's06', category: 'society', tensionA: '精英引导', tensionB: '大众参与', tags: ['governance'] },
  { id: 's07', category: 'society', tensionA: '竞争驱动', tensionB: '合作共赢', tags: ['culture'] },
  { id: 's08', category: 'society', tensionA: '经验传承', tensionB: '创新突破', tags: ['education'] },
  { id: 's09', category: 'society', tensionA: '结果正义', tensionB: '程序正义', tags: ['law'] },
  { id: 's10', category: 'society', tensionA: '短期利益', tensionB: '长期主义', tags: ['strategy'] },
  { id: 's11', category: 'society', tensionA: '透明公开', tensionB: '适度保留', tags: ['governance'] },
  { id: 's12', category: 'society', tensionA: '物质追求', tensionB: '精神充实', tags: ['life'] },
  { id: 's13', category: 'society', tensionA: '多数决定', tensionB: '少数权利', tags: ['policy'] },
  { id: 's14', category: 'society', tensionA: '标准化', tensionB: '多元化', tags: ['culture'] },
  { id: 's15', category: 'society', tensionA: '预防原则', tensionB: '创新原则', tags: ['policy'] },
  { id: 's16', category: 'society', tensionA: '代际责任', tensionB: '当下权利', tags: ['ethics'] },

  // ── career (16) ──
  { id: 'c01', category: 'career', tensionA: '稳定收入', tensionB: '创业冒险', tags: ['choice'] },
  { id: 'c02', category: 'career', tensionA: '深耕专业', tensionB: '跨界探索', tags: ['growth'] },
  { id: 'c03', category: 'career', tensionA: '大公司', tensionB: '小团队', tags: ['environment'] },
  { id: 'c04', category: 'career', tensionA: '高薪但无趣', tensionB: '低薪但热爱', tags: ['values'] },
  { id: 'c05', category: 'career', tensionA: '管理路线', tensionB: '技术路线', tags: ['path'] },
  { id: 'c06', category: 'career', tensionA: '远程办公', tensionB: '面对面协作', tags: ['work'] },
  { id: 'c07', category: 'career', tensionA: '学历优先', tensionB: '能力优先', tags: ['hiring'] },
  { id: 'c08', category: 'career', tensionA: '快速晋升', tensionB: '扎实积累', tags: ['growth'] },
  { id: 'c09', category: 'career', tensionA: '工作生活平衡', tensionB: '全力以赴', tags: ['lifestyle'] },
  { id: 'c10', category: 'career', tensionA: '人脉优先', tensionB: '实力优先', tags: ['strategy'] },
  { id: 'c11', category: 'career', tensionA: '跟随趋势', tensionB: '逆势而为', tags: ['strategy'] },
  { id: 'c12', category: 'career', tensionA: '忠诚留守', tensionB: '频繁跳槽', tags: ['choice'] },
  { id: 'c13', category: 'career', tensionA: '完美主义', tensionB: '足够好就行', tags: ['mindset'] },
  { id: 'c14', category: 'career', tensionA: '独自承担', tensionB: '团队分担', tags: ['work'] },
  { id: 'c15', category: 'career', tensionA: '向上管理', tensionB: '专注执行', tags: ['work'] },
  { id: 'c16', category: 'career', tensionA: '副业探索', tensionB: '主业聚焦', tags: ['choice'] },

  // ── philosophy (16) ──
  { id: 'p01', category: 'philosophy', tensionA: '自由意志', tensionB: '决定论', tags: ['metaphysics'] },
  { id: 'p02', category: 'philosophy', tensionA: '理性', tensionB: '感性', tags: ['epistemology'] },
  { id: 'p03', category: 'philosophy', tensionA: '过程重要', tensionB: '结果重要', tags: ['ethics'] },
  { id: 'p04', category: 'philosophy', tensionA: '利己', tensionB: '利他', tags: ['ethics'] },
  { id: 'p05', category: 'philosophy', tensionA: '绝对真理', tensionB: '相对真理', tags: ['epistemology'] },
  { id: 'p06', category: 'philosophy', tensionA: '天赋决定', tensionB: '努力决定', tags: ['debate'] },
  { id: 'p07', category: 'philosophy', tensionA: '活在当下', tensionB: '规划未来', tags: ['life'] },
  { id: 'p08', category: 'philosophy', tensionA: '简单生活', tensionB: '丰富体验', tags: ['values'] },
  { id: 'p09', category: 'philosophy', tensionA: '遵守规则', tensionB: '打破常规', tags: ['ethics'] },
  { id: 'p10', category: 'philosophy', tensionA: '知识价值', tensionB: '行动价值', tags: ['epistemology'] },
  { id: 'p11', category: 'philosophy', tensionA: '乐观偏向', tensionB: '现实主义', tags: ['mindset'] },
  { id: 'p12', category: 'philosophy', tensionA: '宽容包容', tensionB: '坚守底线', tags: ['ethics'] },
  { id: 'p13', category: 'philosophy', tensionA: '顺其自然', tensionB: '主动掌控', tags: ['life'] },
  { id: 'p14', category: 'philosophy', tensionA: '经验主义', tensionB: '理论先行', tags: ['method'] },
  { id: 'p15', category: 'philosophy', tensionA: '内在驱动', tensionB: '外在激励', tags: ['motivation'] },
  { id: 'p16', category: 'philosophy', tensionA: '接受不完美', tensionB: '追求完美', tags: ['mindset'] },

  // ── life (16) ──
  { id: 'l01', category: 'life', tensionA: '独处充电', tensionB: '社交滋养', tags: ['energy'] },
  { id: 'l02', category: 'life', tensionA: '计划旅行', tensionB: '随性出发', tags: ['travel'] },
  { id: 'l03', category: 'life', tensionA: '极简生活', tensionB: '物质丰富', tags: ['lifestyle'] },
  { id: 'l04', category: 'life', tensionA: '早起高效', tensionB: '夜猫创意', tags: ['routine'] },
  { id: 'l05', category: 'life', tensionA: '健康自律', tensionB: '享受放纵', tags: ['health'] },
  { id: 'l06', category: 'life', tensionA: '深度阅读', tensionB: '碎片获取', tags: ['learning'] },
  { id: 'l07', category: 'life', tensionA: '存钱安全', tensionB: '花钱体验', tags: ['money'] },
  { id: 'l08', category: 'life', tensionA: '大城市机会', tensionB: '小城市舒适', tags: ['living'] },
  { id: 'l09', category: 'life', tensionA: '维持旧友', tensionB: '结交新人', tags: ['social'] },
  { id: 'l10', category: 'life', tensionA: '数字记录', tensionB: '活在当下', tags: ['tech'] },
  { id: 'l11', category: 'life', tensionA: '养宠物', tensionB: '自由无牵挂', tags: ['lifestyle'] },
  { id: 'l12', category: 'life', tensionA: '做饭享受', tensionB: '外卖效率', tags: ['daily'] },
  { id: 'l13', category: 'life', tensionA: '断舍离', tensionB: '收藏回忆', tags: ['lifestyle'] },
  { id: 'l14', category: 'life', tensionA: '主动表达', tensionB: '沉默观察', tags: ['social'] },
  { id: 'l15', category: 'life', tensionA: '尝试新事物', tensionB: '坚持老习惯', tags: ['growth'] },
  { id: 'l16', category: 'life', tensionA: '追求效率', tensionB: '享受过程', tags: ['mindset'] },

  // ── economy (16) ──
  { id: 'e01', category: 'economy', tensionA: '消费驱动', tensionB: '储蓄驱动', tags: ['macro'] },
  { id: 'e02', category: 'economy', tensionA: '市场自由', tensionB: '政府调控', tags: ['policy'] },
  { id: 'e03', category: 'economy', tensionA: '增长优先', tensionB: '可持续优先', tags: ['strategy'] },
  { id: 'e04', category: 'economy', tensionA: '创新破坏', tensionB: '渐进改良', tags: ['innovation'] },
  { id: 'e05', category: 'economy', tensionA: '实体经济', tensionB: '虚拟经济', tags: ['structure'] },
  { id: 'e06', category: 'economy', tensionA: '全球供应链', tensionB: '本地自给', tags: ['trade'] },
  { id: 'e07', category: 'economy', tensionA: '规模效应', tensionB: '小而美', tags: ['business'] },
  { id: 'e08', category: 'economy', tensionA: '股东利益', tensionB: '社会责任', tags: ['corporate'] },
  { id: 'e09', category: 'economy', tensionA: '低价竞争', tensionB: '品质溢价', tags: ['strategy'] },
  { id: 'e10', category: 'economy', tensionA: '先盈利', tensionB: '先占市场', tags: ['startup'] },
  { id: 'e11', category: 'economy', tensionA: '通胀刺激', tensionB: '紧缩稳定', tags: ['monetary'] },
  { id: 'e12', category: 'economy', tensionA: '人力密集', tensionB: '技术替代', tags: ['labor'] },
  { id: 'e13', category: 'economy', tensionA: '租房灵活', tensionB: '买房稳定', tags: ['personal'] },
  { id: 'e14', category: 'economy', tensionA: '分散投资', tensionB: '集中押注', tags: ['investment'] },
  { id: 'e15', category: 'economy', tensionA: '订阅经济', tensionB: '一次买断', tags: ['model'] },
  { id: 'e16', category: 'economy', tensionA: '平台垄断', tensionB: '公平竞争', tags: ['regulation'] },
]
