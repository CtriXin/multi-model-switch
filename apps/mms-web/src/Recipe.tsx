import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import type { SessionDetail } from "./types";

export interface Recipe {
  format: "mms-work-recipe-v1";
  title: string;
  prompt: string;
  preferredModel: string;
  planning: boolean;
}
export function shareRecipe(detail: SessionDetail) {
  const first = detail.events.find((e) => e.kind === "user");
  const recipe: Recipe = {
    format: "mms-work-recipe-v1",
    title: detail.session.title,
    prompt: first?.text || "",
    preferredModel: detail.session.modelName,
    planning: !!detail.runtime?.planning,
  };
  const blob = new Blob([JSON.stringify(recipe, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download =
    detail.session.title.replace(/[\\/:*?"<>|]/g, "-").slice(0, 60) +
    ".mms-recipe.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function RecipeImport({ loaded }: { loaded: (recipe: Recipe) => void }) {
  const picker = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  async function read(file?: File) {
    if (!file) return;
    setError("");
    try {
      if (file.size > 128000) throw new Error("任务模板应小于 128 KB。");
      const value = JSON.parse(await file.text());
      if (
        value?.format !== "mms-work-recipe-v1" ||
        typeof value.prompt !== "string" ||
        !value.prompt.trim() ||
        value.prompt.length > 50000
      )
        throw new Error("请选择 MMS 导出的任务模板文件。");
      loaded({
        format: value.format,
        prompt: value.prompt,
        title:
          typeof value.title === "string"
            ? value.title.slice(0, 100)
            : "导入的任务模板",
        preferredModel:
          typeof value.preferredModel === "string"
            ? value.preferredModel.slice(0, 200)
            : "",
        planning: value.planning === true,
      });
    } catch (e) {
      setError(
        e instanceof SyntaxError
          ? "这个文件不是有效的任务模板。"
          : (e as Error).message,
      );
    } finally {
      if (picker.current) picker.current.value = "";
    }
  }
  return (
    <div className="recipe-import">
      <button
        className="text-button"
        title="载入保存的任务说明，检查草稿后再发送。"
        onClick={() => picker.current?.click()}
      >
        <Upload size={14} />
        导入任务模板
      </button>
      <input
        hidden
        ref={picker}
        type="file"
        accept=".json"
        aria-label="导入任务模板文件"
        onChange={(e) => void read(e.target.files?.[0])}
      />
      {error && <small role="alert">{error}</small>}
    </div>
  );
}
