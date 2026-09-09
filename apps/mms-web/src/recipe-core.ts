export interface Recipe {
  format: "mms-work-recipe-v2";
  title: string;
  prompt: string;
  preferredModel: string;
  planning: boolean;
  examples: { input: string; output: string };
  requiredSkills: string[];
  modelRequirements: { image: boolean; reasoning: boolean };
  variables: string[];
}
export const RECIPE_BYTES = 128000;
const token = /\{\{([^{}]*)\}\}/g;
const namePattern = /^[a-zA-Z][a-zA-Z0-9_]{0,39}$/;
const reserved = new Set(["constructor", "prototype", "__proto__"]);
const bytes = (value: string) => new TextEncoder().encode(value).length;
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("模板字段必须是对象。");
  return value as Record<string, unknown>;
}
function text(value: unknown, field: string, limit: number, fallback = ""): string {
  if (value === undefined) return fallback;
  if (typeof value !== "string" || value.length > limit) throw new Error(`${field}格式不正确或过长。`);
  return value;
}
function flag(value: unknown, field: string): boolean {
  if (value === undefined) return false;
  if (typeof value !== "boolean") throw new Error(`${field}必须是开关值。`);
  return value;
}
function names(value: unknown, field: string, limit: number, valid: (s: string) => boolean): string[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length > limit || value.some(n => typeof n !== "string" || !valid(n))) throw new Error(`${field}格式不正确或数量过多。`);
  if (new Set(value).size !== value.length) throw new Error(`${field}不能重复。`);
  return value;
}
export function variableNames(...parts: string[]): string[] {
  const found = new Set<string>();
  for (const part of parts) for (const match of part.matchAll(token)) {
    if (!namePattern.test(match[1]) || reserved.has(match[1])) throw new Error("变量名须以英文字母开头，只含字母、数字和下划线，最多 40 字符。");
    found.add(match[1]);
  }
  if (found.size > 20) throw new Error("每份模板最多 20 个变量。");
  return [...found];
}
export function parseRecipe(raw: string): Recipe {
  if (bytes(raw) > RECIPE_BYTES) throw new Error("任务模板应小于 128 KB。");
  let value: Record<string, unknown>;
  try { value = object(JSON.parse(raw)); } catch { throw new Error("这个文件不是有效的任务模板对象。"); }
  if (!["mms-work-recipe-v1", "mms-work-recipe-v2"].includes(String(value.format))) throw new Error("不支持这个任务模板版本。");
  const legacy = value.format === "mms-work-recipe-v1";
  const examples = legacy ? {} : object(value.examples ?? {});
  const requirements = legacy ? {} : object(value.modelRequirements ?? {});
  const recipe: Recipe = {
    format: "mms-work-recipe-v2",
    title: text(value.title, "标题", 100, "导入的任务模板"),
    prompt: text(value.prompt, "目标", 50000),
    preferredModel: text(value.preferredModel, "模型偏好", 200),
    planning: flag(value.planning, "规划模式"),
    examples: { input: text(examples.input, "示例输入", 12000), output: text(examples.output, "预期成果", 12000) },
    requiredSkills: legacy ? [] : names(value.requiredSkills, "Skills", 20, s => /^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,99}$/.test(s)),
    modelRequirements: { image: flag(requirements.image, "图片输入要求"), reasoning: flag(requirements.reasoning, "推理能力要求") },
    variables: legacy ? [] : names(value.variables, "变量", 20, s => namePattern.test(s) && !reserved.has(s)),
  };
  if (!recipe.prompt.trim()) throw new Error("模板目标不能为空。");
  if (!legacy) {
    const used = variableNames(recipe.prompt, recipe.examples.input, recipe.examples.output);
    if (used.some(n => !recipe.variables.includes(n)) || recipe.variables.some(n => !used.includes(n))) throw new Error("变量声明与正文中的 {{name}} 不一致。");
  }
  return recipe;
}
export function renderRecipe(recipe: Recipe, values: Record<string, string>): string {
  for (const name of recipe.variables) if (!Object.hasOwn(values, name) || typeof values[name] !== "string" || !values[name].trim()) throw new Error(`请填写变量 ${name}。`);
  const replace = (s: string) => recipe.variables.length ? s.replace(token, (whole, name) => recipe.variables.includes(name) ? values[name] : whole) : s;
  const parts = [replace(recipe.prompt)];
  if (recipe.examples.input) parts.push("示例输入（供参考）：\n" + replace(recipe.examples.input));
  if (recipe.examples.output) parts.push("预期成果示例（供参考，并非已完成的结果）：\n" + replace(recipe.examples.output));
  const result = parts.join("\n\n");
  if (result.length > 50000 || bytes(result) > RECIPE_BYTES) throw new Error("填写后的任务说明过长，请缩短变量或示例。");
  return result;
}

// Only known text patterns are scrubbed. This is not a claim that business data is public.
export function scrubSharedText(input: string): { text: string; removed: number } {
  let removed = 0;
  const replace = (pattern: RegExp, replacement: string | ((...args: string[]) => string)) => {
    input = input.replace(pattern, (...args: string[]) => { removed++; return typeof replacement === "string" ? replacement : replacement(...args); });
  };
  replace(/-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----/g, "[已移除私钥]");
  replace(/\b(?:sk|rk|ghp|github_pat|xoxb|xoxp)[-_][A-Za-z0-9_-]{16,}\b/g, "[已移除凭据]");
  replace(/\bBearer\s+[A-Za-z0-9._~+\/-]+=*/gi, "Bearer [已移除凭据]");
  replace(/(^|\n)[ \t]*(?:export[ \t]+)?[A-Z][A-Z0-9_]*[ \t]*=[^\n]*/g, (_, prefix) => prefix + "[已移除环境变量赋值]");
  replace(/\b(?:api[_ -]?key|access[_ -]?token|secret|password|credential)\s*[:=]\s*(?:"[^"\n]*"|'[^'\n]*'|[^\s,;&]+)/gi, "[已移除凭据赋值]");
  replace(/https?:\/\/[^\s/]+@[^\s)"'<>]+/gi, "[已移除带凭据的地址]");
  replace(/([?&])(?:key|token|api_key|access_token|secret|password)=[^&#\s)"'<>]+/gi, (_, prefix) => prefix + "removed=REDACTED");
  replace(/(["'`])(?:file:\/\/|~?\/|[A-Za-z]:[\\/]|\\\\)[^\r\n]*?\1/g, (_, quote) => quote + "[本地路径已移除]" + quote);
  replace(/file:\/\/[^\s"'<>]+/gi, "[本地路径已移除]");
  replace(/(^|[\s("'`=])(?:[A-Za-z]:[\\/]|\\\\)[^\s"'<>]+/g, (_, prefix) => prefix + "[本地路径已移除]");
  replace(/(^|[\s("'`=])(?:~\/|\/(?!\/))[^\s"'`<>),;]+/g, (_, prefix) => prefix + "[本地路径已移除]");
  return { text: input, removed };
}
export function prepareExport(value: Recipe): { recipe: Recipe; json: string; filename: string; removed: number } {
  let removed = 0;
  const clean = (s: string) => { const result = scrubSharedText(s); removed += result.removed; return result.text; };
  const prompt = clean(value.prompt), input = clean(value.examples.input), output = clean(value.examples.output);
  const safe = {
    format: "mms-work-recipe-v2", title: clean(value.title), prompt,
    preferredModel: clean(value.preferredModel), planning: value.planning,
    examples: { input, output }, requiredSkills: [...value.requiredSkills],
    modelRequirements: { image: value.modelRequirements.image, reasoning: value.modelRequirements.reasoning },
    variables: variableNames(prompt, input, output),
  };
  for (const name of [...safe.requiredSkills, ...safe.variables]) {
    if (scrubSharedText(name).removed) throw new Error("Skills 或变量名称含有疑似凭据，请修改后再导出。");
  }
  const recipe = parseRecipe(JSON.stringify(safe));
  const filename = (clean(recipe.title).replace(/[\\/:*?"<>|]/g, "-").slice(0, 60) || "task-template") + ".mms-recipe.json";
  return { recipe, json: JSON.stringify(recipe, null, 2), filename, removed };
}
export function modelRequirementIssues(recipe: Recipe, model?: { input?: string[]; reasoning?: boolean }): string[] {
  if (!model) return ["正在核对所选模型能力。"];
  const issues: string[] = [];
  if (recipe.modelRequirements.image && !model.input?.includes("image")) issues.push(model.input ? "所选模型不支持模板要求的图片输入。" : "尚未确认所选模型的图片输入能力。");
  if (recipe.modelRequirements.reasoning && model.reasoning !== true) issues.push(model.reasoning === false ? "所选模型不支持模板要求的推理能力。" : "尚未确认所选模型的推理能力。");
  return issues;
}
export function requiredSkillMatches(required: string[], skills: { id: string; name: string }[], selected?: string[]) {
  const ids: string[] = [], issues: string[] = [];
  for (const name of required) {
    const matches = skills.filter(s => s.name === name);
    if (matches.length !== 1) issues.push(matches.length ? `Skill ${name} 有多个同名入口，请先解决来源冲突。` : `当前项目缺少 Skill ${name}。`);
    else if (selected && !selected.includes(matches[0].id)) issues.push(`请选中模板要求的 Skill ${name}。`);
    else ids.push(matches[0].id);
  }
  return { ids, issues };
}
