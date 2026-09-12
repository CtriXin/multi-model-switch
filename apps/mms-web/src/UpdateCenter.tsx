import { useEffect, useRef, useState } from "react";
import { Download, RefreshCw, X } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { isPreview, request } from "./api";
import { copyText } from "./clipboard";
import "./updates.css";

type UpdateStatus = {
  currentVersion: string;
  latest: { tag?: string; notes?: string; url?: string; upgradeNotice?: string };
  updateAvailable: boolean; enabled: boolean; checking: boolean; checkedAt: number;
  error: string; canUpgrade: boolean; port?: number;
  upgradeGuidance?: { required: boolean; title: string; reason: string; command: string; steps: string[] };
  /** Whether this update also replaces the `mms` command line, and why not. */
  installation?: { updatesCli?: boolean; root?: string; reason?: string };
  operation: { phase: string; message?: string; target?: string; cancellable?: boolean };
};

const activePhases = new Set(["preparing", "waiting", "backing-up", "restarting"]);
export function UpdateCenter({ ready, open, setOpen, onStatus }: {
  ready: boolean;
  open: boolean;
  setOpen: (open: boolean) => void;
  /** Lets the shell badge its own controls without owning the polling. */
  onStatus?: (status: { available: boolean; active: boolean }) => void;
}) {
  const [data, setData] = useState<UpdateStatus>();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [allowIdleRestart, setAllowIdleRestart] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [copiedCommand, setCopiedCommand] = useState(false);
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
        if (stopped) return;
        if (initialVersion.current && result.currentVersion !== initialVersion.current) {
          // The service is back on the same port running the new code. Drafts
          // are stored, so reloading costs nothing and is the only way this
          // page stops running the version it was served with.
          location.reload();
          return;
        }
        initialVersion.current ||= result.currentVersion; setData(result); setError("");
      } catch (e) {
        if (!stopped && open) setError(e instanceof Error ? e.message : "暂时无法读取更新状态。");
      } finally {
        if (!stopped) timer = setTimeout(poll, open || activePhases.has(phase) ? 2000 : 60000);
      }
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [ready, open, phase]);
  const available = !!data?.updateAvailable;
  const active = activePhases.has(phase);
  useEffect(() => { onStatus?.({ available, active }); }, [available, active, onStatus]);
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
  // At rest there is nothing to act on, so the top bar shows nothing. The
  // version label in settings is the way in; this control appears only when
  // an update is waiting or one is running, which is when it earns the space.
  return <>
    {(available || active) && <button ref={trigger} type="button" className={`update-trigger ${available ? "available" : ""}`} aria-label={available ? "有新版，查看更新" : "查看更新进度"} title="版本与更新" onClick={() => setOpen(true)}>
      <Download size={16} /><span>{phase === "waiting" ? "等待更新" : active ? "更新中" : "有新版"}</span>
    </button>}
    {open && <dialog ref={dialog} className="update-center" aria-labelledby="update-title" onCancel={e => { e.preventDefault(); setOpen(false); }} onClick={e => { if (e.target === dialog.current) setOpen(false); }}>
      <header><div><h2 id="update-title">版本与更新</h2><p>当前版本 {data ? `v${data.currentVersion}` : "读取中…"}</p></div><button type="button" className="icon-button" aria-label="关闭更新" onClick={() => setOpen(false)}><X size={19} /></button></header>
      <div className="update-body">
        <div className="update-check-row"><span>{data?.checking ? "正在检查…" : data?.updateAvailable ? `发现新版 ${data.latest.tag}` : data?.checkedAt && !data.error ? "已是最新稳定版" : "检查 Pilot 的最新版本"}</span><button type="button" className="text-button" disabled={busy || isPreview || !data} onClick={() => void act("check")}><RefreshCw size={14} />检查更新</button></div>
        {data?.checkedAt ? <p className="update-muted">上次检查：{new Date(data.checkedAt * 1000).toLocaleString()}</p> : null}
        <label className="update-preference"><span>自动检查更新<small>每 6 小时检查一次；发现新版后由你决定是否更新。</small></span><input type="checkbox" role="switch" aria-label="自动检查更新" checked={data?.enabled ?? false} disabled={pending || isPreview || !data} onChange={e => void act("preferences", { enabled: e.target.checked })} /></label>
        {data?.latest.notes && <section className="update-notes" aria-label="更新内容"><h3>{data.latest.tag} 更新内容</h3>{/* Release notes are Markdown. Rendering them into a paragraph showed
            the asterisks, the list dashes and the code fence as literal text. */}
        <div className="update-notes-body"><Markdown remarkPlugins={[remarkGfm]} skipHtml>{data.latest.notes}</Markdown></div>{data.latest.url && <a href={data.latest.url} target="_blank" rel="noreferrer">查看完整发布说明</a>}</section>}
        {data?.upgradeGuidance?.required && <section className="update-migration-warning" role="alert" aria-label="需要手动升级">
          <h3>{data.upgradeGuidance.title}</h3>
          <p>{data.upgradeGuidance.reason}</p>
          <ol>{data.upgradeGuidance.steps.map(step => <li key={step}>{step}</li>)}</ol>
          <div className="update-command"><pre><code>{data.upgradeGuidance.command}</code></pre><button type="button" className="text-button" onClick={() => { void copyText(data.upgradeGuidance!.command).then(done => { setCopiedCommand(done); if (done) setTimeout(() => setCopiedCommand(false), 1600); }); }}>{copiedCommand ? "已复制" : "复制命令"}</button></div>
          <p className="update-muted">这次不会清空会话或运行记录；安装器会保留旧目录，确认无误后再手动备份或清理。</p>
        </section>}
        {data?.operation.message && <p className="update-progress" role="status">{data.operation.message}</p>}
        {(error || data?.error) && <p className="update-error" role="alert">{error || data?.error}</p>}
        {isPreview && <p className="update-muted">预览模式不检查或安装更新。</p>}
        {confirming && data?.canUpgrade && !activePhases.has(phase) && <section className="update-confirm" aria-label={`确认更新到 ${data.latest.tag}`}>
          <h3>确认更新到 {data.latest.tag}</h3>
          {data.latest.upgradeNotice && <div className="update-warning"><h4>升级须知</h4><div className="update-notes-body"><Markdown remarkPlugins={[remarkGfm]} skipHtml>{data.latest.upgradeNotice}</Markdown></div></div>}
          <ul className="update-facts">
            <li>地址不变，仍然是 <code>http://127.0.0.1:{data.port || 8765}</code>；更新完成后这个页面会自动刷新到新版本。</li>
            <li>{data.installation?.updatesCli
              ? <>命令行会一起更新：<code>{data.installation.root}</code> 里的 <code>mms</code>、<code>mmf</code> 也会变成 {data.latest.tag}，之后两边版本一致。</>
              : <>只更新网页服务，命令行保持当前版本。{data.installation?.reason}</>}</li>
            <li>{allowIdleRestart ? "空闲会话会重启，历史和文件保留，续聊时恢复 Pi。" : "不重启任何会话；执行中、待确认或有排队消息的会话都会等它们结束。"}</li>
          </ul>
          <label className="update-preference"><span>允许重启空闲会话<small>历史和文件保留，续聊时恢复 Pi。关掉时保留所有活跃进程。执行中、待确认或有排队消息的会话仍会等待。</small></span><input type="checkbox" role="switch" aria-label="允许重启空闲会话" checked={allowIdleRestart} disabled={pending} onChange={e => setAllowIdleRestart(e.target.checked)} /></label>
        </section>}
      </div>
      <footer>
        <p>更新前检查会话并备份记录。有任务执行、等待确认或排队消息时，会等待完成后再更新。</p>
        <div>{data?.operation.cancellable && <button type="button" className="button" disabled={pending} onClick={() => void act("cancel")}>取消本次更新</button>}{data?.canUpgrade && !activePhases.has(phase) && (confirming
          ? <><button type="button" className="button" onClick={() => setConfirming(false)}>返回</button><button type="button" className="button primary" disabled={busy} onClick={() => { setConfirming(false); void act("start", { target: data.latest.tag, allowIdleRestart }); }}>确认更新</button></>
          : <button type="button" className="button primary" disabled={busy} onClick={() => setConfirming(true)}>更新到 {data.latest.tag}</button>)}<button type="button" className="button" onClick={() => setOpen(false)}>关闭</button></div>
      </footer>
    </dialog>}
  </>;
}
