import { useState } from "react";
import { loadLabel } from "./ContextUsage";
import type { SessionDetail } from "./types";

export function ContextEvidence({ detail }: { detail: SessionDetail }) {
  const turns = detail.events.filter(e => e.kind === "user");
  const [selected, select] = useState("");
  const event = turns.find(e => e.id === selected) || [...turns].reverse().find(e => e.contextUsage?.consumed) || turns.at(-1);
  const usage = event?.contextUsage;
  const native = usage?.native;
  const chosen = usage?.items.filter(item => item.kind === "skill") || [];
  return <section className="context-evidence" aria-label="上下文与 Skills 来源">
    <h3>上下文与 Skills 来源</h3>
    {!!turns.length && <label>查看哪条消息<select aria-label="查看消息的上下文" value={event?.id || ""} onChange={e => select(e.target.value)}>
      {turns.map((e, i) => <option key={e.id} value={e.id}>{i + 1}. {e.text.slice(0, 45)}</option>)}
    </select></label>}
    <p className="section-note">{usage?.consumed ? "Pi 已接收本条输入。" : "尚未取得本条消息的加载确认。"} 以下为当时的记录，刷新和续聊会保留。</p>
    {chosen.map((s, i) => <details key={i}><summary>已选 Skill · {s.name}<small>{loadLabel(s, true)}</small></summary><p>{s.filePath}</p><p>来源 · {s.sourceRoot || s.source}</p>{s.sha256 && <small>版本指纹 · {s.sha256.slice(0, 12)}</small>}</details>)}
    {!native?.available ? <p className="section-note">该轮没有 Pi 的自动加载证据；旧会话或旧版 Pi 不会补造记录。</p> : <>
      <details><summary>自动加载的规则 · {native.rules.length}</summary>
        {native.rules.map((s, i) => <div className="context-source" key={i}><strong>已加载 · {s.path.split("/").at(-1)}</strong><p>{s.path}</p><small>{s.source} · {s.sha256?.slice(0, 12)}</small></div>)}
        {!native.rules.length && <p>Pi 没有报告自动载入规则文件。</p>}
      </details>
      <details><summary>Pi 可用 Skills · {native.skills.length}</summary>
        {native.skills.map((s, i) => <div className="context-source" key={i}><strong>{s.name}</strong><p>{s.invoked ? loadLabel(s) : s.listed ? "可用 · 仅介绍进入目录，正文未确认加载" : "可用 · 未加入自动选择目录"}</p><p>{s.path}</p><small>{s.source}{s.toolEventId ? ` · 工具记录 ${s.toolEventId}` : ""}</small></div>)}
        {!native.skills.length && <p>Pi 没有报告可用的原生 Skills。</p>}
      </details>
      {native.truncated && <p role="status">来源过多，当前各展示前 200 项，记录不完整。</p>}
      <p className="section-note">加载不代表模型遵循了内容。调用只记录明确的 Skill 命令与 read 工具；通过脚本或其他工具间接读取的内容暂不能可靠归因。</p>
    </>}
  </section>;
}
