import type { Recipe } from "./recipe-core";

const base = { format: "mms-work-recipe-v2" as const, preferredModel: "MiniMax-M3", planning: false,
  modelRequirements: { image: false, reasoning: false } };
export const recipeExamples: { description: string; recipe: Recipe }[] = [
  { description: "给一份资料，整理目标、需求和待确认问题。", recipe: { ...base,
    title: "整理产品需求", prompt: "请阅读 {{file}}，围绕 {{goal}} 整理需求。不要编造缺失信息，把待确认事项单独列出。完成后保存为需求整理.md。",
    requiredSkills: ["plan-task"], variables: ["file", "goal"],
    examples: { input: "产品想法、访谈记录或需求笔记。", output: "Markdown：目标、用户场景、需求清单、验收条件、待确认问题。" } } },
  { description: "检查当前项目改动，指出有证据的问题。", recipe: { ...base, planning: true,
    title: "检查项目改动", prompt: "请检查当前工作文件夹中尚未提交的改动，重点关注 {{focus}}。先读项目规则，再给出具体问题及文件位置、影响与建议；没有发现问题时也要说明检查范围。",
    requiredSkills: ["review-changes"], variables: ["focus"],
    examples: { input: "本次项目改动，关注正确性、交互或兼容性。", output: "按严重程度排列的审查意见，每项含证据与建议；不自动修改文件。" } } },
  { description: "读取 CSV，解释数据并生成可复核的结论。", recipe: { ...base,
    title: "分析一份数据", prompt: "请分析 {{file}}，回答 {{question}}。先确认列名、单位和缺失值，说明计算方法与限制。保存分析报告.md，并将关键汇总保存为分析汇总.csv。不要覆盖原始数据。",
    requiredSkills: [], variables: ["file", "question"],
    examples: { input: "带列名的 CSV 文件。", output: "Markdown 结论、方法与限制，以及一份汇总 CSV。" } } },
];
