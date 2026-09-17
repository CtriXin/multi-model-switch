import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  suggestBotName,
  looksLikeStandingInstruction,
  parsePreset,
  buildPreset,
  runWizard,
  getPresetSummary,
  WIZARD_POOL,
  SKIPPED_WIZARD_PROMPT,
  getFocusOptions,
  getFocusBranchMap,
  getBranchOptionsForFocus,
  withCurrentValue,
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

test("parsePreset and buildPreset support new footer order and maintain backward compatibility", () => {
  const legacyOldOrderPrompt = [
    "这是创建时确认的工作预设，请持续遵守：",
    "- 主要帮我处理：工作与项目",
    "- 回报方式：只说结论",
    "- 执行方式：能直接做就直接做",
    "补充约定：",
    "- 第一条自定义约定",
    "- 结果优先，过程保持安静；遇到无法安全判断的关键分歧时再询问。",
  ].join("\n");

  const newOrderPrompt = [
    "这是创建时确认的工作预设，请持续遵守：",
    "- 主要帮我处理：工作与项目",
    "- 回报方式：只说结论",
    "- 执行方式：能直接做就直接做",
    "- 结果优先，过程保持安静；遇到无法安全判断的关键分歧时再询问。",
    "补充约定：",
    "- 第一条自定义约定",
  ].join("\n");

  const parsedOld = parsePreset(legacyOldOrderPrompt);
  const parsedNew = parsePreset(newOrderPrompt);

  assert.deepEqual(parsedOld.answers, parsedNew.answers);
  assert.deepEqual(parsedOld.rules, ["第一条自定义约定"]);
  assert.deepEqual(parsedNew.rules, ["第一条自定义约定"]);
  assert.equal(parsedOld.other, "");
  assert.equal(parsedNew.other, "");

  const built = buildPreset(parsedOld);
  assert.equal(built, newOrderPrompt);
  // 确认尾句排在补充约定之前
  const footerIdx = built.indexOf("- 结果优先，过程保持安静");
  const rulesIdx = built.indexOf("补充约定：");
  assert.ok(footerIdx > 0 && rulesIdx > 0);
  assert.ok(footerIdx < rulesIdx, "固定尾句必须排在向导答案之后、补充约定之前");
});


test("the preset editor lets the rename input keep Escape to itself", () => {
  const source = readFileSync(new URL("../src/BotPresetPanel.tsx", import.meta.url), "utf8");
  const start = source.indexOf("const handleKeyDown");
  assert.ok(start > 0);
  const handler = source.slice(start, source.indexOf('document.addEventListener', start));
  assert.ok(handler.includes("bot-chat-title-input"));
  assert.ok(handler.indexOf("bot-chat-title-input") < handler.indexOf("handleClose()"));
  assert.match(handler, /!hasTopLayer\(\)/, "nested native layers own their Escape");
  const parent = readFileSync(new URL("../src/Bot.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(parent, /if \(!onboardingEditing\) return;/, "no second listener may bypass the guard");
});

test("runWizard covers branches for work, daily, research, and write", () => {
  // 1. Initial state
  const initial = runWizard([]);
  assert.equal(initial.nextQuestion?.id, "q_start");

  // 2. Daily branch: q_start (A: 日常事务与提醒) -> q_daily_remind -> q_daily_habit -> complete
  const daily1 = runWizard([{ questionId: "q_start", optionKey: "A" }]);
  assert.equal(daily1.nextQuestion?.id, "q_daily_remind");
  assert.equal(daily1.preset.answers.focus, "日常事务与提醒");

  const daily2 = runWizard([
    { questionId: "q_start", optionKey: "A" },
    { questionId: "q_daily_remind", optionKey: "A" },
  ]);
  assert.equal(daily2.nextQuestion?.id, "q_daily_habit");

  const daily3 = runWizard([
    { questionId: "q_start", optionKey: "A" },
    { questionId: "q_daily_remind", optionKey: "A" },
    { questionId: "q_daily_habit", optionKey: "A" },
  ]);
  assert.equal(daily3.nextQuestion, null, "3 步后必须完成向导");
  assert.equal(daily3.preset.answers.extra?.["q_daily_habit"], "早晨规划");

  // 3. Work branch: q_start (B: 工作与项目) -> q_work_report -> q_work_autonomy -> complete
  const work1 = runWizard([{ questionId: "q_start", optionKey: "B" }]);
  assert.equal(work1.nextQuestion?.id, "q_work_report");
  assert.equal(work1.preset.answers.focus, "工作与项目");

  const work2 = runWizard([
    { questionId: "q_start", optionKey: "B" },
    { questionId: "q_work_report", optionKey: "A" },
  ]);
  assert.equal(work2.nextQuestion?.id, "q_work_autonomy");
  assert.equal(work2.preset.answers.style, "只说结论");

  const work3 = runWizard([
    { questionId: "q_start", optionKey: "B" },
    { questionId: "q_work_report", optionKey: "A" },
    { questionId: "q_work_autonomy", optionKey: "A" },
  ]);
  assert.equal(work3.nextQuestion, null, "3 步后必须完成向导");
  assert.equal(work3.preset.answers.autonomy, "直接做");

  // 4. Research branch: q_start (C: 查询与研究) -> q_research_cite -> q_research_format
  const res1 = runWizard([{ questionId: "q_start", optionKey: "C" }]);
  assert.equal(res1.nextQuestion?.id, "q_research_cite");
  assert.equal(res1.preset.answers.focus, "查询与研究");

  // 5. Write branch: q_start (D: 写作与沟通) -> q_write_tone -> q_write_review
  const write1 = runWizard([{ questionId: "q_start", optionKey: "D" }]);
  assert.equal(write1.nextQuestion?.id, "q_write_tone");
  assert.equal(write1.preset.answers.focus, "写作与沟通");
});

test("runWizard option E terminates wizard immediately without further questions", () => {
  // Option E on start question
  const quitOnStart = runWizard([{ questionId: "q_start", optionKey: "E" }]);
  assert.equal(quitOnStart.nextQuestion, null);
  assert.equal(quitOnStart.preset.answers.focus, undefined);

  // Option E on second question
  const quitOnSecond = runWizard([
    { questionId: "q_start", optionKey: "B" },
    { questionId: "q_work_report", optionKey: "E" },
  ]);
  assert.equal(quitOnSecond.nextQuestion, null);
  assert.equal(quitOnSecond.preset.answers.focus, "工作与项目");
  assert.equal(quitOnSecond.preset.answers.style, undefined);
});

test("runWizard supports free text input and populates answers.extra without duplicate focus/style/autonomy", () => {
  const freeWork = runWizard([
    { questionId: "q_start", text: "做一些自动化数据同步" },
    { questionId: "q_work_report", text: "每天下班前发微信" },
    { questionId: "q_work_autonomy", text: "只要不花钱就直接执行" },
  ]);
  assert.equal(freeWork.nextQuestion, null);
  // 自由回答只进 extra，不污染 focus/style/autonomy
  assert.equal(freeWork.preset.answers.focus, undefined);
  assert.equal(freeWork.preset.answers.style, undefined);
  assert.equal(freeWork.preset.answers.autonomy, undefined);
  assert.ok(freeWork.preset.answers.extra);
  assert.equal(freeWork.preset.answers.extra["q_start"], "做一些自动化数据同步");
  assert.equal(freeWork.preset.answers.extra["q_work_report"], "每天下班前发微信");
  assert.equal(freeWork.preset.answers.extra["q_work_autonomy"], "只要不花钱就直接执行");
  // 确保没有为同一题写重复的 shortLabel 键
  assert.equal(freeWork.preset.answers.extra["主要工作"], undefined);
  assert.equal(freeWork.preset.answers.extra["汇报方式"], undefined);
});

test("getPresetSummary formats correctly and excludes extra fields", () => {
  assert.equal(getPresetSummary(null), null);
  assert.equal(getPresetSummary({}), null);

  const full = {
    focus: "工作与项目",
    style: "只说结论",
    autonomy: "直接做",
    extra: { "补充习惯": "每天早晨打招呼" },
  };
  assert.equal(getPresetSummary(full), "工作与项目 · 只说结论 · 直接做");

  const partial = {
    focus: "工作与项目",
    autonomy: "直接做",
  };
  assert.equal(getPresetSummary(partial), "工作与项目 · 直接做");
});

test("parsePreset and buildPreset round-trip extra preferences with single key and allow deletion", () => {
  const promptWithExtra = [
    "这是创建时确认的工作预设，请持续遵守：",
    "- 主要帮我处理：工作与项目",
    "- 回报方式：只说结论",
    "- 执行方式：能直接做就直接做",
    "- 结果优先，过程保持安静；遇到无法安全判断的关键分歧时再询问。",
    "了解到的偏好：",
    "- 时间习惯：早晨规划",
    "- 特殊说明：尽量用 Python 实现",
    "补充约定：",
    "- 所有接口入参必须有校验",
  ].join("\n");

  const parsed = parsePreset(promptWithExtra);
  assert.equal(parsed.answers.focus, "工作与项目");
  assert.equal(parsed.answers.style, "只说结论");
  assert.equal(parsed.answers.autonomy, "能直接做就直接做");
  // 题库中的题目解析为 q_<id>，非题库自定义项使用原 label
  assert.equal(parsed.answers.extra?.["q_daily_habit"], "早晨规划");
  assert.equal(parsed.answers.extra?.["特殊说明"], "尽量用 Python 实现");
  // 确保只有一个键，绝无重复键
  assert.equal(parsed.answers.extra?.["时间习惯"], undefined);
  assert.equal(Object.keys(parsed.answers.extra || {}).length, 2);
  assert.deepEqual(parsed.rules, ["所有接口入参必须有校验"]);

  // 往回构建后格式完全一致
  const rebuilt = buildPreset({
    answers: parsed.answers,
    rules: parsed.rules,
  });
  assert.equal(rebuilt, promptWithExtra);

  // 必修 1 重点门禁：删除偏好项后保存，再读回必须彻底没有，绝不复活
  delete parsed.answers.extra?.["q_daily_habit"];
  const afterDelete = buildPreset({
    answers: parsed.answers,
    rules: parsed.rules,
  });
  assert.ok(!afterDelete.includes("时间习惯"), "buildPreset 中不应再包含已删除的时间习惯");
  assert.ok(!afterDelete.includes("早晨规划"), "buildPreset 中不应再包含已删除的内容");

  const reParsed = parsePreset(afterDelete);
  assert.equal(reParsed.answers.extra?.["q_daily_habit"], undefined);
  assert.equal(reParsed.answers.extra?.["时间习惯"], undefined);
  assert.equal(reParsed.answers.extra?.["特殊说明"], "尽量用 Python 实现");
  assert.equal(Object.keys(reParsed.answers.extra || {}).length, 1);
});

test("SKIPPED_WIZARD_PROMPT is a real default rule: kept in other, round-trips, no summary", () => {
  assert.ok(SKIPPED_WIZARD_PROMPT.trim(), "跳过向导写入的必须是非空真实约定");
  const parsed = parsePreset(SKIPPED_WIZARD_PROMPT);
  assert.equal(parsed.answers.focus, undefined);
  assert.equal(parsed.answers.style, undefined);
  assert.equal(parsed.answers.autonomy, undefined);
  assert.deepEqual(parsed.rules, []);
  assert.equal(parsed.other, SKIPPED_WIZARD_PROMPT);
  // 打开预设面板不改直接保存：buildPreset 往返不丢，向导不会复活
  assert.equal(buildPreset(parsed), SKIPPED_WIZARD_PROMPT);
  assert.equal(buildPreset({ answers: parsed.answers, rules: parsed.rules, other: parsed.other }), SKIPPED_WIZARD_PROMPT);
  // 侧栏不把默认约定当摘要
  assert.equal(getPresetSummary(parsed.answers), null);
});


test("focus branch options are derived from the wizard chain, not a hardcoded map", () => {
  // 工作重点仍然只来自 q_start 的 4 个取值
  assert.deepEqual(
    getFocusOptions(),
    WIZARD_POOL["q_start"].options
    .filter((o) => o.key !== "E")
    .map((o) => o.value || o.label),
  );
  assert.equal(getFocusOptions().length, 4);

  const map = getFocusBranchMap();

  // 「工作与项目」这条链：q_work_report(style) -> q_work_autonomy(autonomy)
  assert.deepEqual(
    map["工作与项目"].styleOptions,
    WIZARD_POOL["q_work_report"].options
    .filter((o) => o.key !== "E")
    .map((o) => o.value || o.label),
  );
  assert.deepEqual(
    map["工作与项目"].autonomyOptions,
    WIZARD_POOL["q_work_autonomy"].options
    .filter((o) => o.key !== "E")
    .map((o) => o.value || o.label),
  );
  assert.equal(map["工作与项目"].styleOptions.length, 4);
  assert.equal(map["工作与项目"].autonomyOptions.length, 4);

  // 「日常事务与提醒」这条链：q_daily_remind(style) -> q_daily_habit(extra) -> q_daily_autonomy(autonomy)
  assert.deepEqual(
    map["日常事务与提醒"].styleOptions,
    WIZARD_POOL["q_daily_remind"].options
    .filter((o) => o.key !== "E")
    .map((o) => o.value || o.label),
  );
  assert.deepEqual(
    map["日常事务与提醒"].autonomyOptions,
    WIZARD_POOL["q_daily_autonomy"].options
    .filter((o) => o.key !== "E")
    .map((o) => o.value || o.label),
  );

  // 分支之间不串味
  assert.ok(!map["日常事务与提醒"].styleOptions.includes("只说结论"));
  assert.ok(!map["工作与项目"].styleOptions.includes("直奔主题"));
});

test("unknown focus falls back to the default branch and the saved value is kept as a chip", () => {
  const fallback = getBranchOptionsForFocus(undefined);
  assert.deepEqual(fallback, getFocusBranchMap()["工作与项目"]);
  assert.deepEqual(getBranchOptionsForFocus("我自己写的工作重点"), fallback);
  assert.deepEqual(getBranchOptionsForFocus("查询与研究"), getFocusBranchMap()["查询与研究"]);

  // 当前值不在收窄后的选项里时追加到末尾，仍然是一个选中的芯片
  const style = withCurrentValue(getBranchOptionsForFocus("工作与项目").styleOptions, "直奔主题");
  assert.equal(style.length, 5);
  assert.equal(style[style.length - 1], "直奔主题");
  // 已在选项里则不重复追加
  assert.deepEqual(
    withCurrentValue(style, "只说结论"),
    style,
  );
  assert.deepEqual(withCurrentValue(style, ""), style);
  assert.deepEqual(withCurrentValue(style, undefined), style);
});
