import test from "node:test";
import assert from "node:assert/strict";
import {
  suggestBotName,
  looksLikeStandingInstruction,
  parsePreset,
  buildPreset,
} from "../src/bot-presets.ts";

test("suggestBotName covers all four focus branches and duplicate index incrementing", () => {
  // 1. Four focus branches
  assert.equal(suggestBotName({ focus: "工作与项目" }), "项目助手");
  assert.equal(suggestBotName({ focus: "资料整理与写作" }), "写作助手");
  assert.equal(suggestBotName({ focus: "生活安排" }), "生活管家");
  assert.equal(suggestBotName({ focus: "都可以，按事情判断" }), "通用助手");
  assert.equal(suggestBotName(null), "通用助手");
  assert.equal(suggestBotName({}), "通用助手");

  // 2. Duplicate index incrementing
  assert.equal(suggestBotName({ focus: "工作与项目" }, ["项目助手"]), "项目助手 2");
  assert.equal(
    suggestBotName({ focus: "工作与项目" }, ["项目助手", "项目助手 2"]),
    "项目助手 3",
  );
  assert.equal(
    suggestBotName({ focus: "资料整理与写作" }, ["写作助手", "其他 Bot"]),
    "写作助手 2",
  );
  assert.equal(suggestBotName({ focus: "生活安排" }, ["项目助手"]), "生活管家");
});

test("looksLikeStandingInstruction correctly matches positive and negative examples", () => {
  // Positive examples (>= 3)
  assert.equal(looksLikeStandingInstruction("以后回复短一点"), true);
  assert.equal(looksLikeStandingInstruction("每次提交前都要跑测试"), true);
  assert.equal(looksLikeStandingInstruction("从现在起不要再解释过程"), true);
  assert.equal(looksLikeStandingInstruction("今后默认采用英文命名"), true);
  assert.equal(looksLikeStandingInstruction("总是先给我结论"), true);
  assert.equal(looksLikeStandingInstruction("别再使用过时的接口"), true);

  // Negative examples (>= 3)
  assert.equal(looksLikeStandingInstruction("帮我写个 Python 脚本"), false);
  assert.equal(looksLikeStandingInstruction("你好，今天天气不错"), false);
  assert.equal(looksLikeStandingInstruction(""), false);
  // Exceeds 200 chars
  const longText = "以后 " + "文字".repeat(120);
  assert.equal(looksLikeStandingInstruction(longText), false);
});

test("parsePreset and buildPreset round-trip and maintain compatibility with legacy prompts", () => {
  const legacyPrompt = [
    "这是创建时确认的工作预设，请持续遵守：",
    "- 主要帮我处理：工作与项目",
    "- 回报方式：只说结论",
    "- 执行方式：能直接做就直接做",
    "- 结果优先，过程保持安静；遇到无法安全判断的关键分歧时再询问。",
  ].join("\n");

  const parsed = parsePreset(legacyPrompt);
  assert.equal(parsed.answers.focus, "工作与项目");
  assert.equal(parsed.answers.style, "只说结论");
  assert.equal(parsed.answers.autonomy, "能直接做就直接做");
  assert.deepEqual(parsed.rules, []);
  assert.equal(parsed.other, "");

  const rebuilt = buildPreset({ answers: parsed.answers, rules: parsed.rules, other: parsed.other });
  assert.equal(rebuilt, legacyPrompt);
});

test("parsePreset and buildPreset preserve user-written custom lines (other)", () => {
  const customPrompt = [
    "这是创建时确认的工作预设，请持续遵守：",
    "- 主要帮我处理：资料整理与写作",
    "- 回报方式：结论加关键依据",
    "- 执行方式：涉及外部操作先问我",
    "补充约定：",
    "- 默认用 Markdown 列表",
    "- 结果优先，过程保持安静；遇到无法安全判断的关键分歧时再询问。",
    "自定义段落：所有输出保持学术风格，禁止口语化。",
  ].join("\n");

  const parsed = parsePreset(customPrompt);
  assert.equal(parsed.answers.focus, "资料整理与写作");
  assert.deepEqual(parsed.rules, ["默认用 Markdown 列表"]);
  assert.equal(parsed.other, "自定义段落：所有输出保持学术风格，禁止口语化。");

  const rebuilt = buildPreset(parsed);
  assert.ok(rebuilt.includes("自定义段落：所有输出保持学术风格，禁止口语化。"));
  assert.ok(rebuilt.includes("补充约定：\n- 默认用 Markdown 列表"));
});

test("buildPreset enforces 12 rules limit, length <= 200, and deduplication", () => {
  const rawRules = [
    "第一条规则",
    "第一条规则", // duplicate
    "第二条规则",
    "a".repeat(250), // exceeds 200
  ];
  for (let i = 3; i <= 20; i++) {
    rawRules.push(`第 ${i} 条规则`);
  }

  const prompt = buildPreset({
    answers: { focus: "工作与项目" },
    rules: rawRules,
  });

  const parsed = parsePreset(prompt);
  // Maximum 12 unique rules
  assert.equal(parsed.rules.length, 12);
  assert.equal(parsed.rules[0], "第一条规则");
  assert.equal(parsed.rules[1], "第二条规则");
  assert.equal(parsed.rules[2].length, 200); // capped at 200
  // "第一条规则" only appears once
  assert.equal(parsed.rules.filter((r) => r === "第一条规则").length, 1);
});
