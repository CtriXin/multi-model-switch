export interface OnboardingAnswers {
  focus?: string;
  style?: string;
  autonomy?: string;
}

export interface ParsedPreset {
  answers: OnboardingAnswers;
  rules: string[];
  other: string;
}

/**
 * A · 2: 建议名由 suggestBotName(answers, existingNames) 生成，只看 focus：
 * 工作与项目 → "项目助手"
 * 资料整理与写作 → "写作助手"
 * 生活安排 → "生活管家"
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
  } else if (focus === "资料整理与写作") {
    baseName = "写作助手";
  } else if (focus === "生活安排") {
    baseName = "生活管家";
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
const RULES_HEADER = "补充约定：";
const DEFAULT_FOOTER = "- 结果优先，过程保持安静；遇到无法安全判断的关键分歧时再询问。";

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
  let inRulesSection = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed === ONBOARDING_HEADER) {
      inOnboardingSection = true;
      inRulesSection = false;
      continue;
    }

    if (trimmed === RULES_HEADER) {
      inRulesSection = true;
      inOnboardingSection = false;
      continue;
    }

    // Check for footer line of onboarding
    if (inOnboardingSection || inRulesSection) {
      if (
        trimmed === DEFAULT_FOOTER ||
        trimmed.startsWith("- 结果优先，过程保持安静") ||
        trimmed.startsWith("收到指令后直接执行，结果优先")
      ) {
        // This is a known footer line, do not treat as an unknown other line
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
      // If it starts with another dash or non-empty line before rules header
      if (trimmed.startsWith("- ") && !inRulesSection) {
        otherLines.push(line);
        continue;
      }
    }

    if (inRulesSection) {
      if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        const ruleText = trimmed.slice(2).trim();
        if (ruleText && !rules.includes(ruleText) && rules.length < 12) {
          rules.push(ruleText.slice(0, 200));
        }
        continue;
      }
      // Blank line inside rules section is tolerated
      if (!trimmed) {
        continue;
      }
    }

    // Any line not recognized as onboarding or rules belongs to "other"
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

  // Deduplicate and cap rules to 12 items
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
