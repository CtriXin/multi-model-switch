import { useEffect, useRef, useState } from "react";
import { Upload } from "lucide-react";
import type { SessionDetail } from "./types";
import { Dialog } from "./components";
import { parseRecipe, prepareExport, renderRecipe, scrubSharedText, variableNames, RECIPE_BYTES } from "./recipe-core";
import type { Recipe } from "./recipe-core";
import { recipeExamples } from "./recipe-examples";
export type { Recipe } from "./recipe-core";
export interface RecipeDraft { recipe: Recipe; draftPrompt: string; key: string; savedAt: number }
const draftStorage = "mms-web-template-draft-v2";
export function readRecipeDraft(): RecipeDraft | null {
  try {
    const raw = sessionStorage.getItem(draftStorage);
    if (!raw || raw.length > RECIPE_BYTES * 2) return null;
    const value = JSON.parse(raw);
    if (typeof value.key !== "string" || !/^[a-z0-9-]{1,60}$/.test(value.key) ||
        typeof value.draftPrompt !== "string" || value.draftPrompt.length > 50000 ||
        typeof value.savedAt !== "number" || Date.now() - value.savedAt > 7 * 86400000) return null;
    return { ...value, recipe: parseRecipe(JSON.stringify(value.recipe)) };
  } catch { return null; }
}
export function saveRecipeDraft(value: RecipeDraft | null) {
  try { if (value) sessionStorage.setItem(draftStorage, JSON.stringify(value)); else sessionStorage.removeItem(draftStorage); } catch { /* current tab remains usable */ }
}
function Requirements({ recipe }: { recipe: Recipe }) {
  return <div className="recipe-requirements">
    <span>模型偏好：{recipe.preferredModel || "未指定"}</span>
    <span>Skills：{recipe.requiredSkills.join("、") || "无必需项"}</span>
    <span>能力要求：{[recipe.modelRequirements.image && "图片输入", recipe.modelRequirements.reasoning && "推理"].filter(Boolean).join("、") || "无额外要求"}</span>
  </div>;
}
const fillingStorage = "mms-web-template-filling-v2";
function readFilling(): { recipe?: Recipe; values: Record<string, string> } {
  try {
    const raw = sessionStorage.getItem(fillingStorage);
    if (!raw || raw.length > RECIPE_BYTES * 2) return { values: {} };
    const value = JSON.parse(raw), recipe = parseRecipe(JSON.stringify(value.recipe));
    if (Date.now() - value.savedAt > 7 * 86400000 || typeof value.savedAt !== "number") return { values: {} };
    const values = Object.fromEntries(recipe.variables.filter(n => typeof value.values?.[n] === "string" && value.values[n].length <= 50000).map(n => [n, value.values[n]]));
    return {recipe, values};
  } catch { return {values:{}}; }
}
export function RecipeImport({ loaded }: { loaded: (draft: RecipeDraft) => void }) {
  const picker = useRef<HTMLInputElement>(null);
  const generation = useRef(0);
  const [error, setError] = useState("");
  const [initial] = useState(readFilling);
  const [recipe, setRecipe] = useState<Recipe | undefined>(initial.recipe);
  const [values, setValues] = useState<Record<string, string>>(initial.values);
  const [examples, showExamples] = useState(false);
  useEffect(() => {
    try {
      if (recipe) sessionStorage.setItem(fillingStorage, JSON.stringify({recipe, values, savedAt: Date.now()}));
      else sessionStorage.removeItem(fillingStorage);
    } catch { /* Private browsing may disable storage. */ }
  }, [recipe, values]);
  const [showPrompt, setShowPrompt] = useState(false);
  let prompt = "", variableError = "";
  if (recipe) try { prompt = renderRecipe(recipe, values); } catch (e) { variableError = (e as Error).message; }
  async function read(file?: File) {
    const current = ++generation.current;
    if (!file) return;
    setError("");
    try {
      if (file.size > RECIPE_BYTES) throw new Error("任务模板应小于 128 KB。");
      const content = await file.text();
      if (generation.current !== current) return;
      const parsed = parseRecipe(content);
      setRecipe(parsed); setValues({}); setShowPrompt(false);
    } catch (e) { if (generation.current === current) setError((e as Error).message); }
    finally { if (generation.current === current && picker.current) picker.current.value = ""; }
  }
  return <div className="recipe-import">
    <button className="text-button" title="填写模板变量，检查草稿后再发送。" onClick={() => picker.current?.click()}><Upload size={14} />导入任务模板</button>
    <button className="text-button" onClick={() => showExamples(true)}>试用任务模板</button>
    {examples && <Dialog title="从一份任务模板开始" close={() => showExamples(false)}>
      <p className="dialog-intro">选择想做的事，填自己的资料，再确认模型和项目。所有模板都可以编辑。</p>
      <div className="recipe-examples">{recipeExamples.map(item => <button key={item.recipe.title} onClick={() => { setRecipe(item.recipe); setValues({}); setShowPrompt(false); showExamples(false); }}><strong>{item.recipe.title}</strong><small>{item.description}</small></button>)}</div>
    </Dialog>}
    <input hidden ref={picker} type="file" accept=".json" aria-label="导入任务模板文件" onChange={e => void read(e.target.files?.[0])} />
    {error && <small role="alert">{error}</small>}
    {recipe && <Dialog title={`导入「${recipe.title}」`} close={() => { generation.current++; setRecipe(undefined); }}>
      <div className="recipe-dialog">
        <p className="section-note">填写后载入可编辑草稿，再核对当前项目的 Skills 和模型。发送任务时才开始执行。</p>
        <Requirements recipe={recipe} />
        {!!recipe.variables.length && <div className="recipe-variables">{recipe.variables.map(name => <label key={name}>{name}<input aria-label={`变量 ${name}`} value={values[name] || ""} onChange={e => { setValues({ ...values, [name]: e.target.value }); setShowPrompt(false); }} maxLength={50000} placeholder={name === "file" ? "文件名或路径，例如 data.csv" : "填写本次使用的值"} /></label>)}</div>}
        {variableError && <p className="section-note">{variableError}</p>}
        <details open={showPrompt} onToggle={e => setShowPrompt(e.currentTarget.open)}><summary>查看将载入的任务说明</summary><pre className="recipe-preview">{prompt || recipe.prompt}</pre></details>
        <p className="section-note">载入会替换当前模板草稿。模板不会安装 Skills、读取变量中的文件或导入连接凭据。</p>
        <button className="button primary" type="button" disabled={!!variableError} onClick={() => {
          loaded({ recipe, draftPrompt: prompt, key: crypto.randomUUID(), savedAt: Date.now() });
          setRecipe(undefined);
        }}>载入草稿</button>
      </div>
    </Dialog>}
  </div>;
}
export function RecipeExport({ detail, close }: { detail: SessionDetail; close: () => void }) {
  const [recipe, setRecipe] = useState<Recipe>(() => {
    const first = detail.events.find(e => e.kind === "user");
    return {
      format: "mms-work-recipe-v2", title: scrubSharedText(detail.session.title).text,
      prompt: scrubSharedText(first?.text || "").text, preferredModel: scrubSharedText(detail.session.modelName).text,
      planning: !!detail.runtime?.planning, examples: { input: "", output: "" },
      requiredSkills: first?.skills?.map(s => s.name) || [], modelRequirements: { image: false, reasoning: false }, variables: [],
    };
  });
  const [skillsText, setSkillsText] = useState(recipe.requiredSkills.join(", "));
  const [preview, setPreview] = useState<ReturnType<typeof prepareExport>>();
  const [error, setError] = useState("");
  function edit(value: Partial<Recipe>) { setRecipe({ ...recipe, ...value }); setPreview(undefined); setError(""); }
  function check() { try { setPreview(prepareExport({ ...recipe, requiredSkills: skillsText.split(/[,，]/).map(s => s.trim()).filter(Boolean) })); setError(""); } catch (e) { setError((e as Error).message); } }
  function download() {
    if (!preview) return;
    try {
      const checked = prepareExport(preview.recipe);
      if (checked.json !== preview.json || checked.filename !== preview.filename) throw new Error("导出内容已经变化，请重新检查。");
      const url = URL.createObjectURL(new Blob([checked.json], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = checked.filename; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000); close();
    } catch (e) { setError((e as Error).message); }
  }
  let variables: string[] = [];
  try { variables = variableNames(recipe.prompt, recipe.examples.input, recipe.examples.output); } catch { /* check button reports invalid tokens */ }
  return <Dialog title="保存为任务模板" close={close}>
    <div className="recipe-dialog">
      <p className="section-note">以首条任务为起点，核对可复用的目标和需求。仅导出下方字段，示例由你填写；不会附带后续对话、文件、项目资料正文或账号配置。</p>
      <label>模板标题<input aria-label="模板标题" value={recipe.title} maxLength={100} onChange={e => edit({ title: e.target.value })} /></label>
      <label>任务目标<textarea aria-label="模板目标" value={recipe.prompt} maxLength={50000} onChange={e => edit({ prompt: e.target.value })} /></label>
      <p className="section-note">把每次不同的内容写成 {'{{file}}'}、{'{{topic}}'} 等变量，导入时填写。当前变量：{variables.join("、") || "无"}。</p>
      <div className="recipe-fields"><label>示例输入<textarea aria-label="模板示例输入" value={recipe.examples.input} maxLength={12000} onChange={e => edit({ examples: { ...recipe.examples, input: e.target.value } })} /></label>
      <label>预期成果示例<textarea aria-label="模板预期成果" value={recipe.examples.output} maxLength={12000} onChange={e => edit({ examples: { ...recipe.examples, output: e.target.value } })} /></label></div>
      <label>必需 Skills 名称<input aria-label="模板 Skills" value={skillsText} onChange={e => { setSkillsText(e.target.value); setPreview(undefined); setError(""); }} placeholder="用逗号分隔；对方需要自行准备" /></label>
      <label>模型偏好<input aria-label="模板模型偏好" maxLength={200} value={recipe.preferredModel} onChange={e => edit({ preferredModel: e.target.value })} /></label>
      <div className="recipe-flags">
        <label><input type="checkbox" checked={recipe.modelRequirements.image} onChange={e => edit({ modelRequirements: { ...recipe.modelRequirements, image: e.target.checked } })} />需要图片输入</label>
        <label><input type="checkbox" checked={recipe.modelRequirements.reasoning} onChange={e => edit({ modelRequirements: { ...recipe.modelRequirements, reasoning: e.target.checked } })} />需要推理能力</label>
        <label><input type="checkbox" checked={recipe.planning} onChange={e => edit({ planning: e.target.checked })} />默认只读规划</label>
      </div>
      <p className="section-note">检查会移除识别到的凭据、环境赋值和绝对路径。仍请检查剩余业务内容，避免分享私密信息。</p>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <button type="button" onClick={check}>检查导出内容</button>
      {preview && <section className="recipe-reviewed"><p role="status">已检查，移除 {preview.removed} 处识别到的内容。以下是最终文件：</p><pre className="recipe-preview">{preview.json}</pre><button className="button primary" type="button" onClick={download}>确认并下载模板</button></section>}
    </div>
  </Dialog>;
}
