import { useEffect, useRef, useState } from "react";
import { Download, RefreshCw, X } from "lucide-react";
import { isPreview, request } from "./api";
import "./updates.css";

type UpdateStatus = {
  currentVersion: string; latest: { tag?: string; notes?: string; url?: string };
  updateAvailable: boolean; enabled: boolean; checking: boolean; checkedAt: number;
  error: string; canUpgrade: boolean;
  operation: { phase: string; message?: string; target?: string; cancellable?: boolean };
};

const activePhases = new Set(["preparing", "waiting", "backing-up", "restarting"]);
export function UpdateCenter({ ready }: { ready: boolean }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<UpdateStatus>();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const initialVersion = useRef<string | undefined>(undefined);
  const phase = data?.operation.phase || "idle";
  useEffect(() => {
    if (!ready || isPreview) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await request<UpdateStatus>("/update");
        if (!stopped) { initialVersion.current ||= result.currentVersion; setData(result); setError(""); }
      } catch (e) {
        if (!stopped && open) setError(e instanceof Error ? e.message : "暂时无法读取更新状态。");
      } finally {
        if (!stopped) timer = setTimeout(poll, open || activePhases.has(phase) ? 2000 : 60000);
      }
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [ready, open, phase]);
  useEffect(() => {
    if (!open) return;
    dialog.current?.showModal();
    return () => { dialog.current?.close(); trigger.current?.focus(); };
  }, [open]);
  async function act(action: string, payload: Record<string, unknown> = {}) {
    setPending(true); setError("");
    try { setData(await request<UpdateStatus>(`/update/${action}`, payload)); }
    catch (e) { setError(e instanceof Error ? e.message : "操作未完成，请重试。"); }
    finally { setPending(false); }
  }
  const busy = pending || data?.checking;
  return <>
    <button ref={trigger} type="button" className={`update-trigger ${data?.updateAvailable ? "available" : ""}`} aria-label={data?.updateAvailable ? "有新版，查看更新" : "检查更新"} title="版本与更新" onClick={() => setOpen(true)}>
      <Download size={16} /><span>{phase === "waiting" ? "等待更新" : activePhases.has(phase) ? "更新中" : data?.updateAvailable ? "有新版" : "更新"}</span>
    </button>
    {open && <dialog ref={dialog} className="update-center" aria-labelledby="update-title" onCancel={e => { e.preventDefault(); setOpen(false); }} onClick={e => { if (e.target === dialog.current) setOpen(false); }}>
      <header><div><h2 id="update-title">版本与更新</h2><p>当前版本 {data ? `v${data.currentVersion}` : "读取中…"}</p></div><button type="button" className="icon-button" aria-label="关闭更新" onClick={() => setOpen(false)}><X size={19} /></button></header>
      <div className="update-body">
        <div className="update-check-row"><span>{data?.checking ? "正在检查…" : data?.updateAvailable ? `发现新版 ${data.latest.tag}` : data?.checkedAt && !data.error ? "已是最新稳定版" : "检查 Pilot 的最新版本"}</span><button type="button" className="text-button" disabled={busy || isPreview || !data} onClick={() => void act("check")}><RefreshCw size={14} />检查更新</button></div>
        {data?.checkedAt ? <p className="update-muted">上次检查：{new Date(data.checkedAt * 1000).toLocaleString()}</p> : null}
        <label className="update-preference"><input type="checkbox" checked={data?.enabled ?? false} disabled={pending || isPreview || !data} onChange={e => void act("preferences", { enabled: e.target.checked })} /><span>自动检查更新<small>每 6 小时检查一次；发现新版后由你决定是否更新。</small></span></label>
        {data?.latest.notes && <section className="update-notes" aria-label="更新内容"><h3>{data.latest.tag} 更新内容</h3><p>{data.latest.notes}</p>{data.latest.url && <a href={data.latest.url} target="_blank" rel="noreferrer">查看完整发布说明</a>}</section>}
        {data?.operation.message && <p className="update-progress" role="status">{data.operation.message}</p>}
        {(error || data?.error) && <p className="update-error" role="alert">{error || data?.error}</p>}
        {isPreview && <p className="update-muted">预览模式不检查或安装更新。</p>}
      </div>
      <footer>
        <p>更新前检查会话并备份记录。有任务执行、等待确认或排队消息时，会等待完成后再更新。</p>
        <div>{data && initialVersion.current && data.currentVersion !== initialVersion.current && <button type="button" className="button primary" onClick={() => location.reload()}>刷新使用新版本</button>}{data?.operation.cancellable && <button type="button" className="button" disabled={pending} onClick={() => void act("cancel")}>取消本次更新</button>}{data?.canUpgrade && !activePhases.has(phase) && <button type="button" className="button primary" disabled={busy} onClick={() => void act("start", { target: data.latest.tag })}>更新到 {data.latest.tag}</button>}<button type="button" className="button" onClick={() => setOpen(false)}>关闭</button></div>
      </footer>
    </dialog>}
  </>;
}
