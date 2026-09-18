import { useEffect, useState } from "react";
import type { Bootstrap, SessionDetail } from "./types";
import { request } from "./api";
import { copyText } from "./clipboard";
import { Dialog } from "./components";
import { ModelPicker } from "./LaunchOptions";
import "./session-recovery.css";

export interface RecoveryPacket {
  sourceSessionId: string;
  title: string;
  workspaceId: string;
  cwd: string;
  prompt: string;
  nativeHistoryAvailable: boolean;
}
export interface RecoveryDraft extends RecoveryPacket {
  key: string;
  presetId: string;
}

export function SessionRecovery({ detail, data, favorites, toggleFavorite, busy, action, prepare }: {
  detail: SessionDetail;
  data: Bootstrap;
  favorites: string[];
  toggleFavorite: (id: string) => void;
  busy: boolean;
  action: (path: string, payload: Record<string, unknown>) => Promise<boolean>;
  prepare: (draft: Omit<RecoveryDraft, "key">) => void;
}) {
  const [open, setOpen] = useState(false);
  const blocked = detail.recovery?.suggested || detail.session.state === "error";
  return <>
    <div className={"session-recovery-entry" + (blocked ? " suggested" : "")}>
      {blocked && <p role="status">{detail.recovery?.retryExhausted
        ? "模型自动重试已用尽。" : detail.recovery?.suggested
        ? "模型已连续多次失败。" : "这条会话执行失败了。"} 可以换模型，或把已有资料带到新会话。</p>}
      <button type="button" onClick={() => setOpen(true)}>接续工作</button>
    </div>
    {open && <RecoveryDialog key={detail.session.id} {...{ detail, data, favorites, toggleFavorite, busy, action, prepare }} close={() => setOpen(false)} />}
  </>;
}

export function RecoveryDialog({ detail, data, favorites, toggleFavorite, busy, action, prepare, close }: {
  detail: SessionDetail; data: Bootstrap; favorites: string[]; toggleFavorite: (id: string) => void;
  busy: boolean; action: (path: string, payload: Record<string, unknown>) => Promise<boolean>;
  prepare: (draft: Omit<RecoveryDraft, "key">) => void; close: () => void;
}) {
  const [packet, setPacket] = useState<RecoveryPacket | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [pending, setPending] = useState(false);
  const [reload, setReload] = useState(0);
  const folders = data.workspaces.filter(w => !w.unregistered);
  const [workspaceId, setWorkspaceId] = useState(folders.find(w => w.id === detail.session.workspaceId || w.path === detail.session.cwd)?.id || "");
  const [presetId, setPresetId] = useState(detail.session.presetId || "");
  const running = ["running", "waiting"].includes(detail.session.state);
  const selected = data.presets.find(p => p.id === presetId && p.harness === "pi" && p.available);
  const workspace = folders.find(w => w.id === workspaceId);
  useEffect(() => {
    let current = true;
    setError(""); setPacket(null);
    request<RecoveryPacket>(`/sessions/${encodeURIComponent(detail.session.id)}/recovery`)
      .then(value => { if (current) { setPacket(value); setText(value.prompt); } })
      .catch(cause => { if (current) setError(cause instanceof Error ? cause.message : "接续资料暂时无法读取。"); });
    return () => { current = false; };
  }, [detail.session.id, reload]);
  return <Dialog title="接续工作" close={close} dismissible={!pending} size="wide">
    <div className="session-recovery-body">
      <p>保留原会话。换模型可继续使用旧上下文；新会话只带入你确认的接续资料。</p>
      <p className="muted">资料由本地记录生成，无需旧模型响应。新会话会先打开草稿，发送后才开始执行。</p>
      {error && <p className="inline-alert" role="alert">{error}</p>}
      {!packet ? <div aria-live="polite">{error ? <button type="button" onClick={() => setReload(n => n + 1)}>重新读取资料</button> : "正在读取本地记录…"}</div> : <>
        <label className="recovery-preview">接续资料（可编辑）
          <textarea data-autofocus value={text} rows={10} onChange={e => { setText(e.target.value); setCopied(false); }} />
        </label>
        {!packet.nativeHistoryAvailable && <p role="status">原生日志不可用，已保留可读取的历史摘录。</p>}
        <button type="button" onClick={async () => {
          try { await copyText(text); setCopied(true); setError(""); }
          catch { setError("复制失败，请选中上方资料手动复制。"); }
        }}>{copied ? "已复制接续信息" : "复制接续信息"}</button>
      </>}
      <div className="recovery-options">
        <label>新会话工作文件夹
          <select value={workspaceId} onChange={e => setWorkspaceId(e.target.value)}>
            <option value="">请选择工作文件夹</option>
            {folders.map(w => <option value={w.id} key={w.id}>{w.name}</option>)}
          </select>
        </label>
        <div><span>接续使用的模型</span><ModelPicker presets={data.presets.filter(p => p.harness === "pi")} models={data.models} workspaceId={workspaceId || detail.session.workspaceId}
          value={presetId} change={setPresetId} favorites={favorites} toggleFavorite={toggleFavorite} disabled={pending} /></div>
      </div>
      <p className="recovery-path">原工作目录：{detail.session.cwd || "未记录"}</p>
      {workspace && detail.session.cwd && workspace.path !== detail.session.cwd && <p role="status">新会话将在 {workspace.path} 开始，请先确认它能访问原工作文件。</p>}
      {!folders.length && <p role="status">请先在主页添加工作文件夹，或复制资料到其他会话接续。</p>}
      {running && <p role="status">当前会话仍在执行或等待操作。请先停止或等它结束；现在可以复制资料。</p>}
      {detail.session.owner === "cli" && <p className="muted">终端会话的运行状态无法在这里确认。发送新草稿前，请确认旧终端已停止。</p>}
      <div className="recovery-actions">
        {detail.session.owner === "web" && detail.session.capabilities.send && <button type="button" disabled={busy || pending || running || !selected} onClick={async () => {
          setPending(true); setError("");
          try {
            if (await action(`/sessions/${encodeURIComponent(detail.session.id)}/model`, { presetId })) close();
            else setError("切换未完成，接续资料仍保留在这里。");
          } catch (cause) { setError(cause instanceof Error ? cause.message : "切换未完成，请重试。"); }
          finally { setPending(false); }
        }}>在原会话切换模型</button>}
        <button type="button" className="button primary" disabled={busy || pending || running || !packet || !text.trim() || !workspace || !selected || !data.capabilities.launch}
          onClick={() => { if (packet && workspace && selected && !running) { prepare({ ...packet, prompt: text, workspaceId, presetId }); close(); } }}>在新会话中准备接续</button>
      </div>
      <p className="muted">切换模型不会自动重发消息。504 等错误也可能来自上游服务，换新会话不保证能解决连接问题。</p>
    </div>
  </Dialog>;
}
