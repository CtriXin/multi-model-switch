export interface WizardOption {
  key: string;
  label: string;
  hint?: string;
  value?: string;
}

export interface WizardQuestion {
  id: string;
  shortLabel: string;
  ask: string;
  options: WizardOption[];
  next?: (answerKey: string | "free") => string | null;
  writes: "focus" | "style" | "autonomy" | "extra";
}

export interface OnboardingAnswers {
  focus?: string;
  style?: string;
  autonomy?: string;
  extra?: Record<string, string>;
}

export interface ParsedPreset {
  answers: OnboardingAnswers;
  rules: string[];
  other: string;
}

export const WIZARD_POOL: Record<string, WizardQuestion> = {
  q_start: {
    id: "q_start",
    shortLabel: "主要工作",
    ask: "你最希望我主要帮你做什么？",
    writes: "focus",
    options: [
      { key: "A", label: "日常事务与提醒", hint: "日程规划、定时提醒、备忘与习惯跟进", value: "日常事务与提醒" },
      { key: "B", label: "工作与项目", hint: "写代码、推进需求、跟进工程与排期", value: "工作与项目" },
      { key: "C", label: "查询与研究", hint: "技术调研、资料检索、竞品分析与对比", value: "查询与研究" },
      { key: "D", label: "写作与沟通", hint: "起草文档、润色邮件、整理会议纪要", value: "写作与沟通" },
      { key: "E", label: "先聊聊再说", hint: "稍后在实际对话中逐步了解" },
    ],
    next: (key) => {
      if (key === "E") return null;
      if (key === "A") return "q_daily_remind";
      if (key === "B") return "q_work_report";
      if (key === "C") return "q_research_cite";
      if (key === "D") return "q_write_tone";
      return "q_work_report";
    },
  },
  q_work_report: {
    id: "q_work_report",
    shortLabel: "汇报方式",
    ask: "这类事你一般希望我怎么汇报？",
    writes: "style",
    options: [
      { key: "A", label: "只说结论", hint: "简明扼要，先给结果，不堆砌执行过程", value: "只说结论" },
      { key: "B", label: "结论加关键依据", hint: "先给结果，附带核心数据与推导原因", value: "结论加关键依据" },
      { key: "C", label: "详细进展流", hint: "保留每步尝试与验证细节，便于追溯排查", value: "详细进展流" },
      { key: "D", label: "阶段批量汇总", hint: "里程碑或阶段完成时统一交割，减少打扰", value: "阶段批量汇总" },
      { key: "E", label: "先聊聊再说", hint: "按事情的重要程度灵活处理" },
    ],
    next: (key) => (key === "E" ? null : "q_work_autonomy"),
  },
  q_work_autonomy: {
    id: "q_work_autonomy",
    shortLabel: "推进方式",
    ask: "要是我拿不准，是先做还是先问你？",
    writes: "autonomy",
    options: [
      { key: "A", label: "直接做", hint: "按最佳实践自主推进，遇到阻碍再停下", value: "直接做" },
      { key: "B", label: "先给方案", hint: "先梳理步骤或备选方案，确认后再动手", value: "先给方案" },
      { key: "C", label: "分步确认", hint: "每完成一个关键节点前停下来等你确认", value: "分步确认" },
      { key: "D", label: "安全优先", hint: "任何关键修改或外部操作一律先征求许可", value: "安全优先" },
      { key: "E", label: "先聊聊再说", hint: "由我根据风险高低自行拿捏" },
    ],
    next: (key) => (key === "E" ? null : "q_work_rhythm"),
  },
  q_work_rhythm: {
    id: "q_work_rhythm",
    shortLabel: "推进节奏",
    ask: "推进工程任务时，你更倾向哪种验证与执行节奏？",
    writes: "extra",
    options: [
      { key: "A", label: "小步快跑验证", hint: "每做完一步立刻运行测试与语法门禁", value: "小步快跑验证" },
      { key: "B", label: "整体验证交付", hint: "先写完完整变更再统一部署与验收", value: "整体验证交付" },
      { key: "C", label: "自动化优先", hint: "优先补充门禁脚本与自动化回归用例", value: "自动化优先" },
      { key: "D", label: "探索式推进", hint: "灵活尝试新方案与轻量原型", value: "探索式推进" },
      { key: "E", label: "先聊聊再说", hint: "视具体需求复杂度而定" },
    ],
    next: () => null,
  },
  q_daily_remind: {
    id: "q_daily_remind",
    shortLabel: "提醒方式",
    ask: "需要提醒你时，我以什么方式通知最顺手？",
    writes: "style",
    options: [
      { key: "A", label: "直奔主题", hint: "一句话说清该做什么，附带快捷操作", value: "直奔主题" },
      { key: "B", label: "温和提醒", hint: "语气轻松，适当预留准备与缓冲时间", value: "温和提醒" },
      { key: "C", label: "清单汇总", hint: "按优先级梳理成清晰易读的待办清单", value: "清单汇总" },
      { key: "D", label: "多轮跟进", hint: "重要事项未反馈时适度追加提醒", value: "多轮跟进" },
      { key: "E", label: "先聊聊再说", hint: "按实际需要直接发消息" },
    ],
    next: (key) => (key === "E" ? null : "q_daily_habit"),
  },
  q_daily_habit: {
    id: "q_daily_habit",
    shortLabel: "时间习惯",
    ask: "你平时倾向在什么时间段处理这类事务？",
    writes: "extra",
    options: [
      { key: "A", label: "早晨规划", hint: "每天开始工作前把事情理顺", value: "早晨规划" },
      { key: "B", label: "碎片时间", hint: "随时抽空处理，不要大块占用时间", value: "碎片时间" },
      { key: "C", label: "傍晚复盘", hint: "工作日结束时统一整理完成情况", value: "傍晚复盘" },
      { key: "D", label: "固定整点", hint: "在预设的固定时刻集中提醒", value: "固定整点" },
      { key: "E", label: "先聊聊再说", hint: "根据当天节奏随机安排" },
    ],
    next: (key) => (key === "E" ? null : "q_daily_autonomy"),
  },
  q_daily_autonomy: {
    id: "q_daily_autonomy",
    shortLabel: "处理权限",
    ask: "遇到日程冲突或待办逾期，我可以直接帮你调整还是先问你？",
    writes: "autonomy",
    options: [
      { key: "A", label: "直接顺延", hint: "按规则自动调优时间安排，直接排开", value: "直接顺延" },
      { key: "B", label: "先给建议", hint: "列出冲突与顺延备选方案供我确认", value: "先给建议" },
      { key: "C", label: "仅红字标出", hint: "保持现状，仅高亮提示冲突与逾期风险", value: "仅红字标出" },
      { key: "D", label: "灵活决策", hint: "视优先级高低自行拿捏", value: "灵活决策" },
      { key: "E", label: "先聊聊再说", hint: "按情况临时沟通" },
    ],
    next: () => null,
  },
  q_research_cite: {
    id: "q_research_cite",
    shortLabel: "证据要求",
    ask: "调研分析的结果，你希望我附带多深的数据和依据？",
    writes: "style",
    options: [
      { key: "A", label: "只要结论", hint: "快速决断，不需要过多理论论证", value: "只要结论" },
      { key: "B", label: "结论加核心依据", hint: "附带最关键的 2-3 个论据与出处", value: "结论加核心依据" },
      { key: "C", label: "完整报告", hint: "背景、论证过程、原文引用与对比表格", value: "完整报告" },
      { key: "D", label: "多方观点对比", hint: "分别列出主流不同流派或竞品优劣", value: "多方观点对比" },
      { key: "E", label: "先聊聊再说", hint: "根据课题深度灵活掌握" },
    ],
    next: (key) => (key === "E" ? null : "q_research_format"),
  },
  q_research_format: {
    id: "q_research_format",
    shortLabel: "排版习惯",
    ask: "你更习惯哪种信息呈现结构？",
    writes: "extra",
    options: [
      { key: "A", label: "要点列表", hint: "结构清晰的 Bullet points，容易扫读", value: "要点列表" },
      { key: "B", label: "对比表格", hint: "二维表格清晰比较维度与参数", value: "对比表格" },
      { key: "C", label: "通顺短文", hint: "段落流畅、上下文完整的连贯叙述", value: "通顺短文" },
      { key: "D", label: "问答结构", hint: "把复杂问题拆成几个自问自答", value: "问答结构" },
      { key: "E", label: "先聊聊再说", hint: "按内容特点选择适宜格式" },
    ],
    next: (key) => (key === "E" ? null : "q_research_depth"),
  },
  q_research_depth: {
    id: "q_research_depth",
    shortLabel: "考证原则",
    ask: "面对未经验证的信息源，我是深入交叉考证还是先给你参考？",
    writes: "autonomy",
    options: [
      { key: "A", label: "必须交叉验证", hint: "未确认真实性的内容不直接采信", value: "必须交叉验证" },
      { key: "B", label: "先给线索再深入", hint: "快速汇总多方线索，由你决定深挖方向", value: "先给线索再深入" },
      { key: "C", label: "快速初筛", hint: "优先速度，标注可疑点供后续复核", value: "快速初筛" },
      { key: "D", label: "仅限权威源", hint: "只采纳官方文档或权威论文", value: "仅限权威源" },
      { key: "E", label: "先聊聊再说", hint: "视研究课题而定" },
    ],
    next: () => null,
  },
  q_write_tone: {
    id: "q_write_tone",
    shortLabel: "语气偏好",
    ask: "起草和润色文案时，你偏好什么样的语调？",
    writes: "style",
    options: [
      { key: "A", label: "专业精炼", hint: "克制严谨、职业干练、不带多余情绪", value: "专业精炼" },
      { key: "B", label: "亲和自然", hint: "口吻温和谦逊，易于沟通与理解", value: "亲和自然" },
      { key: "C", label: "观点鲜明", hint: "节奏紧凑、态度明确、强调行动导向", value: "观点鲜明" },
      { key: "D", label: "生动活泼", hint: "轻松有趣、富于表现力与互动感", value: "生动活泼" },
      { key: "E", label: "先聊聊再说", hint: "视文案读者和场景而定" },
    ],
    next: (key) => (key === "E" ? null : "q_write_review"),
  },
  q_write_review: {
    id: "q_write_review",
    shortLabel: "修改幅度",
    ask: "帮我对文字润色时，我可以直接大改还是微调？",
    writes: "autonomy",
    options: [
      { key: "A", label: "大胆重构", hint: "为了表达效果可以调整段落和逻辑结构", value: "大胆重构" },
      { key: "B", label: "局部微调", hint: "只修饰语病、错别字与行文连贯性", value: "局部微调" },
      { key: "C", label: "提供多版", hint: "给出 2-3 种不同风格的改写方案供选", value: "提供多版" },
      { key: "D", label: "批注建议", hint: "不直接改原文，给出修改建议和侧边批注", value: "批注建议" },
      { key: "E", label: "先聊聊再说", hint: "视文稿成熟度而定" },
    ],
    next: () => null,
  },
};

export interface FocusBranchOptions {
  styleOptions: string[];
  autonomyOptions: string[];
}

/** 题目里可选的取值：跳过「先聊聊再说」，取 value，回退 label。 */
function questionOptionValues(q: WizardQuestion): string[] {
  const values: string[] = [];
  for (const opt of q.options) {
    if (opt.key === "E" || opt.label === "先聊聊再说") continue;
    const val = opt.value || opt.label;
    if (val && !values.includes(val)) values.push(val);
  }
  return values;
}

/** 沿 next 链往下走时使用的按键：第一个非 E 的选项。 */
function traversalKey(q: WizardQuestion): string {
  const opt = q.options.find((o) => o.key !== "E");
  return opt ? opt.key : "A";
}

/**
 * 从 q_start 的某个分支出发，沿 next() 链收集这条链上
 * 第一个 writes === "style" 与第一个 writes === "autonomy" 的问题选项。
 * 用 visited 防止题库出现环时无限循环。
 */
function collectBranchOptions(startQuestionId: string | null): FocusBranchOptions {
  const branch: FocusBranchOptions = { styleOptions: [], autonomyOptions: [] };
  const visited = new Set<string>();
  let currentId: string | null = startQuestionId;

  while (currentId && !visited.has(currentId)) {
    visited.add(currentId);
    const q: WizardQuestion | undefined = WIZARD_POOL[currentId];
    if (!q) break;
    if (q.writes === "style" && branch.styleOptions.length === 0) {
      branch.styleOptions = questionOptionValues(q);
    } else if (q.writes === "autonomy" && branch.autonomyOptions.length === 0) {
      branch.autonomyOptions = questionOptionValues(q);
    }
    currentId = q.next ? q.next(traversalKey(q)) : null;
  }

  return branch;
}

/** q_start 的 focus 取值，工作预设面板「工作重点」的选项来源。 */
export function getFocusOptions(): string[] {
  const start = WIZARD_POOL.q_start;
  return start ? questionOptionValues(start) : [];
}

/**
 * focus 取值 -> 该分支的汇报方式 / 推进方式选项。
 * 不硬编码 focus 到题目 id 的映射：逐个走 q_start 的选项，用该选项的 key 调 q_start.next(key)。
 */
export function getFocusBranchMap(): Record<string, FocusBranchOptions> {
  const map: Record<string, FocusBranchOptions> = {};
  const start = WIZARD_POOL.q_start;
  if (!start || !start.next) return map;
  for (const opt of start.options) {
    if (opt.key === "E" || opt.label === "先聊聊再说") continue;
    const focusValue = opt.value || opt.label;
    if (!focusValue) continue;
    map[focusValue] = collectBranchOptions(start.next(opt.key));
  }
  return map;
}

/** 默认分支：q_start 走 next("B")，即工作与项目那条链。 */
function getDefaultBranchOptions(): FocusBranchOptions {
  const start = WIZARD_POOL.q_start;
  if (!start || !start.next) return { styleOptions: [], autonomyOptions: [] };
  return collectBranchOptions(start.next("B"));
}

/** 取当前 focus 对应分支的选项；focus 为空或不认识时回退默认分支。 */
export function getBranchOptionsForFocus(focus?: string | null): FocusBranchOptions {
  const key = focus ? focus.trim() : "";
  const map = getFocusBranchMap();
  if (key && map[key]) return map[key];
  return getDefaultBranchOptions();
}

/**
 * 当前已保存的值若不在收窄后的选项里，追加到末尾（去重），
 * 这样它仍然渲染成一个选中的芯片，而不是掉进「自定义」输入框。
 */
export function withCurrentValue(options: string[], value?: string | null): string[] {
  const val = value ? value.trim() : "";
  if (!val || options.includes(val)) return options;
  return [...options, val];
}

export interface WizardAnswerEntry {
  questionId: string;
  optionKey?: string;
  text?: string;
}

export function runWizard(answersList: WizardAnswerEntry[] = []): {
  nextQuestion: WizardQuestion | null;
  preset: ParsedPreset;
} {
  const answers: OnboardingAnswers = { extra: {} };
  let currentQuestionId: string | null = "q_start";

  for (const entry of answersList) {
    if (!currentQuestionId) break;
    const q: WizardQuestion | undefined = WIZARD_POOL[currentQuestionId];
    if (!q) break;

    // "E" ends the wizard
    if (entry.optionKey === "E") {
      currentQuestionId = null;
      break;
    }

    const chosenOption = q.options.find((opt) => opt.key === entry.optionKey);
    const value = chosenOption?.value || chosenOption?.label || entry.text || "";

    if (entry.text && !entry.optionKey) {
      // 自由回答：只写进 extra，且只使用一个 key (q.id)！不写 focus/style/autonomy 避免重复
      if (!answers.extra) answers.extra = {};
      answers.extra[q.id] = entry.text.trim();
    } else {
      if (q.writes === "focus") {
        answers.focus = value;
      } else if (q.writes === "style") {
        answers.style = value;
      } else if (q.writes === "autonomy") {
        answers.autonomy = value;
      } else {
        // extra 字段同样只以 q.id 为唯一 key
        if (!answers.extra) answers.extra = {};
        answers.extra[q.id] = value;
      }
    }

    if (q.next) {
      const nextKey = entry.optionKey ? entry.optionKey : "free";
      currentQuestionId = q.next(nextKey);
    } else {
      currentQuestionId = null;
    }
  }

  if (answersList.length >= 3) {
    currentQuestionId = null;
  }

  const nextQuestion = currentQuestionId ? (WIZARD_POOL[currentQuestionId] || null) : null;
  const preset: ParsedPreset = {
    answers,
    rules: [],
    other: "",
  };

  return { nextQuestion, preset };
}

export function getPresetSummary(answers?: OnboardingAnswers | null): string | null {
  if (!answers) return null;
  const parts = [answers.focus, answers.style, answers.autonomy].filter(Boolean);
  if (!parts.length) return null;
  return parts.join(" · ");
}

/**
 * A · 2: 建议名由 suggestBotName(answers, existingNames) 生成，只看 focus：
 * 工作与项目 → "项目助手"
 * 资料整理与写作 / 写作与沟通 → "写作助手"
 * 生活安排 / 日常事务与提醒 → "生活管家"
 * 查询与研究 → "研究助手"
 * 其它 / 空 → "通用助手"
 * 同名已存在时加序号："项目助手 2"
 * 纯函数，输入 answers 和现有名字列表
 */
export function suggestBotName(
  answers?: OnboardingAnswers | null,
  existingNames: string[] = [],
): string {
  let baseName = "通用助手";
  const focus = answers?.focus?.trim();
  if (focus === "工作与项目") {
    baseName = "项目助手";
  } else if (focus === "资料整理与写作" || focus === "写作与沟通") {
    baseName = "写作助手";
  } else if (focus === "生活安排" || focus === "日常事务与提醒") {
    baseName = "生活管家";
  } else if (focus === "查询与研究") {
    baseName = "研究助手";
  }

  const nameSet = new Set(existingNames.map((n) => n.trim()));
  if (!nameSet.has(baseName)) {
    return baseName;
  }
  let index = 2;
  while (nameSet.has(`${baseName} ${index}`)) {
    index++;
  }
  return `${baseName} ${index}`;
}

/**
 * C · 4: 自动提议匹配规则：
 * 匹配 "以后 / 今后 / 从现在起 / 每次 / 默认 / 都要 / 总是 / 别再 / 不要再" 且长度 ≤ 200 字
 */
const STANDING_INSTRUCTION_TRIGGER = /(?:以后|今后|从现在起|每次|默认|都要|总是|别再|不要再)/;

export function looksLikeStandingInstruction(text: string): boolean {
  if (!text) return false;
  const trimmed = text.trim();
  if (trimmed.length === 0 || trimmed.length > 200) return false;
  return STANDING_INSTRUCTION_TRIGGER.test(trimmed);
}

const ONBOARDING_HEADER = "这是创建时确认的工作预设，请持续遵守：";
const EXTRA_HEADER = "了解到的偏好：";
const RULES_HEADER = "补充约定：";
const DEFAULT_FOOTER = "- 结果优先，过程保持安静；遇到无法安全判断的关键分歧时再询问。";
/**
 * 跳过向导（点 × 或选 E）时写入的真实默认约定。
 * 任意非空 prompt 即视为 onboardingDone；parsePreset 把它落到 other，buildPreset 往返保留，
 * getPresetSummary 对它返回 null（侧栏不把默认约定当摘要）。
 */
export const SKIPPED_WIZARD_PROMPT = DEFAULT_FOOTER;

/**
 * C · 1 & 2: 解析现有 systemPrompt 为向导选项、补充约定列表与用户手写的其它行。
 * 对旧格式的 systemPrompt 完全兼容。
 */
export function parsePreset(systemPrompt: string): ParsedPreset {
  if (!systemPrompt || !systemPrompt.trim()) {
    return {
      answers: {},
      rules: [],
      other: "",
    };
  }

  const normalized = systemPrompt.replace(/\\n/g, "\n");
  const lines = normalized.split(/\r?\n/);

  const answers: OnboardingAnswers = {};
  const rules: string[] = [];
  const otherLines: string[] = [];

  let inOnboardingSection = false;
  let inExtraSection = false;
  let inRulesSection = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed === ONBOARDING_HEADER) {
      inOnboardingSection = true;
      inExtraSection = false;
      inRulesSection = false;
      continue;
    }

    if (trimmed === EXTRA_HEADER) {
      inExtraSection = true;
      inOnboardingSection = false;
      inRulesSection = false;
      if (!answers.extra) answers.extra = {};
      continue;
    }

    if (trimmed === RULES_HEADER) {
      inRulesSection = true;
      inOnboardingSection = false;
      inExtraSection = false;
      continue;
    }

    if (inOnboardingSection || inRulesSection) {
      if (
        trimmed === DEFAULT_FOOTER ||
        trimmed.startsWith("- 结果优先，过程保持安静") ||
        trimmed.startsWith("收到指令后直接执行，结果优先")
      ) {
        continue;
      }
    }

    if (inOnboardingSection) {
      if (trimmed.startsWith("- 主要帮我处理：")) {
        answers.focus = trimmed.slice("- 主要帮我处理：".length).trim();
        continue;
      }
      if (trimmed.startsWith("- 回报方式：")) {
        answers.style = trimmed.slice("- 回报方式：".length).trim();
        continue;
      }
      if (trimmed.startsWith("- 执行方式：")) {
        answers.autonomy = trimmed.slice("- 执行方式：".length).trim();
        continue;
      }
      if (trimmed.startsWith("- ") && !inRulesSection) {
        otherLines.push(line);
        continue;
      }
    }

    if (inExtraSection) {
      if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        const content = trimmed.slice(2).trim();
        const colonIdx = content.indexOf("：") !== -1 ? content.indexOf("：") : content.indexOf(":");
        if (colonIdx > 0) {
          const label = content.slice(0, colonIdx).trim();
          const val = content.slice(colonIdx + 1).trim();
          if (!answers.extra) answers.extra = {};
          // 用 q_<id> 做键（题库匹配），自定义则用 label 做键；只保留单一键，避免复活
          const matchedQ = Object.values(WIZARD_POOL).find((q) => q.shortLabel === label);
          const key = matchedQ ? matchedQ.id : label;
          answers.extra[key] = val;
        } else {
          if (!answers.extra) answers.extra = {};
          answers.extra[content] = content;
        }
        continue;
      }
      if (!trimmed) continue;
    }

    if (inRulesSection) {
      if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        const ruleText = trimmed.slice(2).trim();
        if (ruleText && !rules.includes(ruleText) && rules.length < 12) {
          rules.push(ruleText.slice(0, 200));
        }
        continue;
      }
      if (!trimmed) {
        continue;
      }
    }

    otherLines.push(line);
  }

  return {
    answers,
    rules,
    other: otherLines.join("\n").trim(),
  };
}

/**
 * C · 1 & 2: 构建 systemPrompt。
 * 最多 12 条补充约定，每条 ≤ 200 字，去重。
 * 用户手写的 other 行必须原样保留在相应位置。
 * T1e: 默认工作约定 footer 移至工作预设段落末尾。
 */
export function buildPreset({
  answers,
  rules = [],
  other = "",
}: {
  answers?: OnboardingAnswers | null;
  rules?: string[];
  other?: string;
}): string {
  const parts: string[] = [];

  const hasAnswers = Boolean(answers && (answers.focus || answers.style || answers.autonomy));

  if (hasAnswers) {
    parts.push(ONBOARDING_HEADER);
    if (answers?.focus) parts.push(`- 主要帮我处理：${answers.focus}`);
    if (answers?.style) parts.push(`- 回报方式：${answers.style}`);
    if (answers?.autonomy) parts.push(`- 执行方式：${answers.autonomy}`);
    parts.push(DEFAULT_FOOTER);
  }

  const extraObj = answers?.extra || {};
  const extraEntries = Object.entries(extraObj).filter(([_, v]) => v && v.trim());
  if (extraEntries.length > 0) {
    parts.push(EXTRA_HEADER);
    for (const [k, v] of extraEntries) {
      const q = WIZARD_POOL[k];
      const label = q ? q.shortLabel : k;
      parts.push(`- ${label}：${v.trim()}`);
    }
  }

  const cleanRules: string[] = [];
  for (const r of rules) {
    const trimmed = r.trim();
    if (trimmed && !cleanRules.includes(trimmed) && cleanRules.length < 12) {
      cleanRules.push(trimmed.slice(0, 200));
    }
  }

  if (cleanRules.length > 0) {
    parts.push(RULES_HEADER);
    for (const rule of cleanRules) {
      parts.push(`- ${rule}`);
    }
  }

  if (other && other.trim()) {
    parts.push(other.trim());
  }

  return parts.join("\n");
}

