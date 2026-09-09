import type { SessionEvent } from "./types";

export interface UsageItem {
  kind: "skill" | "attachment" | "reference" | "selection" | "material";
  name?: string; title?: string; path?: string; filePath?: string; source?: string;
  sha256?: string; revision?: number; updatedAt?: string; referenceOnly?: boolean;
  sourceRoot?: string; overrides?: string[];
}
export interface ContextRecord { state: "prepared" | "submitted" | "failed" | "uncertain"; cwd?: string; items: UsageItem[] }

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
      {(item.filePath || (item.path && (item.title || item.name))) && <p>{item.filePath || item.path}</p>}
      {item.sourceRoot && <p>来源目录 · {item.sourceRoot}</p>}
      {!!item.overrides?.length && <p>同名入口已由此版本覆盖：{item.overrides.join("；")}</p>}
      <small>{item.kind === "material" ? "手动保存" : item.source}{item.revision !== undefined ? ` · ${item.revision ? `v${item.revision}` : "当前文件"}` : ""}{item.sha256 ? ` · ${item.sha256.slice(0, 12)}` : ""}{item.updatedAt ? ` · ${new Date(item.updatedAt).toLocaleString()}` : ""}</small>
    </div>)}
    <p className="section-note">仅记录这条消息明确附带的内容；文件引用不代表模型已读取。</p>
  </details>;
}
