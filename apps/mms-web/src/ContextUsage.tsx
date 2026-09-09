import type { SessionEvent } from "./types";

export interface UsageItem {
  kind: "skill" | "attachment" | "reference" | "selection" | "material";
  name?: string; title?: string; path?: string; filePath?: string; source?: string;
  sha256?: string; revision?: number; updatedAt?: string; referenceOnly?: boolean;
  sourceRoot?: string; overrides?: string[];
  loadState?: "referenced" | "loaded" | "loading" | "failed";
  invoked?: boolean; proof?: string; toolEventId?: string; partial?: boolean;
}
export interface NativeSource { sourcePath?: string; name?: string; path: string; source?: string; sha256?: string; state?: string; listed?: boolean; invoked?: boolean; loadState?: string; proof?: string; toolEventId?: string; partial?: boolean }
export interface NativeEvidence { version: number; available: boolean; truncated: boolean; rules: NativeSource[]; skills: NativeSource[]; systemPromptSha256?: string }
export interface ContextRecord { state: "prepared" | "submitted" | "failed" | "uncertain"; cwd?: string; items: UsageItem[]; consumed?: boolean; native?: NativeEvidence }
export function loadLabel(item: { loadState?: string; invoked?: boolean; partial?: boolean }, selected = false) {
  if (item.loadState === "failed") return "调用失败";
  if (item.loadState === "loading") return "正在调用读取";
  if (item.invoked) return item.partial ? "已调用 · 读取完成（可能为选段）" : "已调用 · 正文已加载";
  if (item.loadState === "loaded") return "已加载到本轮输入";
  return selected ? "已选中 · 等待加载确认" : "仅引用 · 未观察到读取";
}

export function ContextUsage({ event }: { event: SessionEvent }) {
  const usage = event.contextUsage;
  if (!usage) return null;
  const label = usage.state === "uncertain" ? "发送结果待确认" : event.status === "cancelled" ? "已取消" : event.status === "queued" ? "等待处理" :
    ({ prepared: "已准备", submitted: "已提交", failed: "发送失败", uncertain: "发送结果待确认" })[usage.state];
  const submitted = usage.state === "submitted" && event.status !== "queued" && event.status !== "cancelled";
  if (!usage.items.length) {
    return submitted ? null : <p className="context-delivery-status" role="status">{label}</p>;
  }
  return <details className="context-usage">
    <summary>附带资料<span>{usage.items.length} 项{submitted ? "" : ` · ${label}`}</span></summary>
    <p className="context-workspace">工作文件夹 · {usage.cwd}</p>
    {usage.items.map((item, index) => <div className="context-source" key={index}>
      <strong>{({ skill: "Skill", attachment: item.referenceOnly ? "本地原文件" : "附件", reference: "工作文件引用", selection: "成果选段", material: "项目资料" })[item.kind]} · {item.title || item.name || item.path}</strong>
      <p className="context-source-state">{loadLabel(item, item.kind === "skill")}</p>
      {(item.filePath || (item.path && (item.title || item.name))) && <p>{item.filePath || item.path}</p>}
      {item.sourceRoot && <p>来源目录 · {item.sourceRoot}</p>}
      {!!item.overrides?.length && <p>同名入口已由此版本覆盖：{item.overrides.join("；")}</p>}
      <small>{item.kind === "material" ? "手动保存" : item.source}{item.revision !== undefined ? ` · ${item.revision ? `v${item.revision}` : "当前文件"}` : ""}{item.sha256 ? ` · ${item.sha256.slice(0, 12)}` : ""}{item.updatedAt ? ` · ${new Date(item.updatedAt).toLocaleString()}` : ""}</small>
    </div>)}
    <p className="section-note">加载表示内容进入本轮输入，调用来自实际 Skill 命令或 read 工具记录；不代表模型遵循了指引。自动载入的规则和 Skills 可在运行详情查看。</p>
  </details>;
}
