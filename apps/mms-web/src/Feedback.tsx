import { useEffect, useRef, useState } from "react";
import { MessageSquare, X } from "lucide-react";
import { Dialog } from "./components";
import { isPreview, request } from "./api";
import { newRequestId } from "./request-id";
import "./feedback.css";

type Status = {
  enabled: boolean;
  eligible: boolean;
  idle: boolean;
  usedBot: boolean;
  phase: string;
  metadata: { version: string; system: string };
  destination: string;
};

function FeedbackForm({ status, surface, close, submitted }: {
  status: Status; surface: "pilot" | "bot";
  close: () => void; submitted: () => void;
}) {
  const [job, setJob] = useState("");
  const [outcome, setOutcome] = useState("");
  const [detail, setDetail] = useState("");
  const [recurring, setRecurring] = useState("");
  const [contact, setContact] = useState("");
  const [entry, setEntry] = useState<string>(surface);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState("");
  const attempt = useRef<{ key: string; requestId: string } | undefined>(undefined);
  async function send() {
    const answers = { surface: entry, job: job.trim(), outcome, detail: detail.trim(), recurring: recurring.trim(), contact: contact.trim() };
    const key = JSON.stringify(answers);
    if (attempt.current?.key !== key) attempt.current = { key, requestId: newRequestId() };
    setBusy(true); setError("");
    try {
      const result = await request<{ received: boolean; receiptId: string }>("/feedback/submit", { ...answers, requestId: attempt.current.requestId });
      if (!result.received || result.receiptId !== attempt.current.requestId) throw new Error("尚未确认收到，请稍后重试。");
      setReceipt(result.receiptId); submitted();
    } catch (e) { setError(e instanceof Error ? e.message : "发送未成功，请稍后重试。"); }
    finally { setBusy(false); }
  }
  return <Dialog title={receipt ? "反馈已收到" : "告诉我们实际用得怎样"} close={close} dismissible={!busy}>
    {receipt ? <div className="feedback-success" role="status">
      <p>谢谢，你的反馈已送到 MMS 维护者的收件箱。</p>
      <p>此轮体验邀请不会再出现。你仍可随时从「反馈」入口补充。</p>
      <small>回执：{receipt}</small>
      <button className="button primary" onClick={close}>完成</button>
    </div> : <form className="feedback-form" onSubmit={e => { e.preventDefault(); void send(); }}>
      <p className="feedback-intro">约 30 秒，无需登录。好用的地方和没做成的事情，我们都想知道。</p>
      <label>这次反馈的是
        <select value={entry} onChange={e => setEntry(e.target.value)} disabled={busy}>
          <option value="pilot">Pilot 对话</option><option value="bot">Bot</option><option value="both">两者都有</option>
        </select>
      </label>
      <label>你最近用它做什么？
        <input required maxLength={500} value={job} onChange={e => setJob(e.target.value)} disabled={busy} placeholder="例如：给一个网站修问题" />
      </label>
      <fieldset disabled={busy}><legend>事情做成了吗？</legend>
        <div className="feedback-outcomes">
          {[["done", "做成了"], ["partial", "部分完成"], ["failed", "没做成"], ["exploring", "还在尝试"]].map(([value, label]) =>
            <label key={value}><input required type="radio" name="feedback-outcome" value={value} checked={outcome === value} onChange={() => setOutcome(value)} />{label}</label>)}
        </div>
      </fieldset>
      <label>哪里需要你自己接手，或哪一点值得保留？<span>选填</span>
        <textarea rows={3} maxLength={2000} value={detail} onChange={e => setDetail(e.target.value)} disabled={busy} placeholder="描述一次具体经历就好" />
      </label>
      {(status.usedBot || entry !== "pilot") && <details className="feedback-contact"><summary>想让 Bot 长期负责什么？（选填）</summary>
        <label>哪件反复发生的事，你希望一直交给它？
          <textarea rows={2} maxLength={1000} value={recurring} onChange={e => setRecurring(e.target.value)} disabled={busy} />
        </label>
      </details>}
      <details className="feedback-contact"><summary>愿意接受追问？留下联系方式（选填）</summary>
        <label>邮箱或其他联系方式<input maxLength={200} value={contact} onChange={e => setContact(e.target.value)} disabled={busy} /></label>
        <p>不填写也能提交；填写后仅用于跟进这条反馈。</p>
      </details>
      <p className="feedback-disclosure">发送到{status.destination}。附带：MMS {status.metadata.version} · {status.metadata.system} · 所选入口。不会附带聊天、代码、文件路径或 Key，请勿在回答中填写这些私密内容。</p>
      {error && <p className="feedback-error" role="alert">{error}</p>}
      <footer><button type="button" className="button" disabled={busy} onClick={close}>取消</button>
        <button className="button primary" disabled={busy || !status.enabled || !job.trim() || !outcome}>{busy ? "正在发送…" : "发送反馈"}</button></footer>
    </form>}
  </Dialog>;
}

export function useFeedback({ ready, allowed, surface }: { ready: boolean; allowed: boolean; surface: "pilot" | "bot" }) {
  const [status, setStatus] = useState<Status>();
  const [invited, setInvited] = useState(false);
  const [open, setOpen] = useState(false);
  const [opening, setOpening] = useState(false);
  const [notice, setNotice] = useState("");
  const lastInput = useRef(Date.now());
  const claimPending = useRef(false);
  const current = useRef({ allowed, open });
  current.current = { allowed, open };
  useEffect(() => {
    if (!ready || isPreview) return;
    let cancelled = false;
    const activity = () => { lastInput.current = Date.now(); };
    document.addEventListener("keydown", activity, true);
    document.addEventListener("pointerdown", activity, true);
    document.addEventListener("visibilitychange", activity);
    async function refresh() {
      if (document.visibilityState !== "visible") return;
      try {
        const next = await request<Status>("/feedback");
        if (cancelled) return;
        setStatus(next);
        if (["dismissed", "submitted"].includes(next.phase)) setInvited(false);
        const active = document.activeElement;
        const editing = active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement
          ? Boolean(active.value.trim())
          : active?.matches("select, [contenteditable=true]");
        const hasDraft = Array.from(document.querySelectorAll<HTMLTextAreaElement>("textarea"))
          .some(input => input.getClientRects().length > 0 && input.value.trim());
        if (!next.eligible || !current.current.allowed || current.current.open || editing ||
            hasDraft ||
            document.querySelector("dialog[open], [popover]:popover-open") ||
            Date.now() - lastInput.current < 30000 || claimPending.current) return;
        claimPending.current = true;
        try {
          const claim = await request<{ claimed: boolean }>("/feedback/invitation", { action: "claim" });
          if (!cancelled && claim.claimed && current.current.allowed && !current.current.open && Date.now() - lastInput.current >= 30000) setInvited(true);
        } finally { claimPending.current = false; }
      } catch { /* Feedback must never interrupt work or display background errors. */ }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30000);
    return () => {
      cancelled = true; window.clearInterval(timer);
      document.removeEventListener("keydown", activity, true);
      document.removeEventListener("pointerdown", activity, true);
      document.removeEventListener("visibilitychange", activity);
    };
  }, [ready]);

  async function showForm() {
    setOpening(true); setNotice("");
    try {
      if (isPreview) throw new Error("界面预览不会发送反馈，请在实际使用的 MMS 中打开。");
      const next = await request<Status>("/feedback"); setStatus(next);
      if (!next.enabled) throw new Error("反馈接收暂未开放，请稍后再试。");
      await request("/feedback/invitation", { action: "open" });
      setInvited(false); setOpen(true);
    } catch (e) { setNotice(e instanceof Error ? e.message : "暂时无法打开反馈。"); }
    finally { setOpening(false); }
  }
  async function dismiss(action: "later" | "dismiss") {
    setInvited(false);
    try { setStatus(await request<Status>("/feedback/invitation", { action })); }
    catch { /* Claim was already persisted; a failed dismiss cannot cause re-prompting. */ }
  }
  return {
    trigger: status?.enabled ? <button className="icon-button" title="反馈使用体验" aria-label="反馈使用体验" disabled={opening} onClick={() => void showForm()}><MessageSquare size={18} /></button> : null,
    invitation: <>
      {notice && <div className="feedback-invitation" role="status"><span>{notice}</span><button className="icon-button" aria-label="关闭反馈提示" onClick={() => setNotice("")}><X size={15} /></button></div>}
      {invited && allowed && status?.enabled && status.idle && <aside className="feedback-invitation" aria-label="使用体验邀请">
        <span>用了几天，MMS 有没有帮你把事情做成？</span>
        <div><button className="button" onClick={() => void showForm()}>反馈一下</button><button className="text-button" onClick={() => void dismiss("later")}>以后再说</button><button className="text-button" onClick={() => void dismiss("dismiss")}>不再提醒</button></div>
      </aside>}
    </>,
    dialog: open && status ? <FeedbackForm status={status} surface={surface} close={() => setOpen(false)} submitted={() => { setInvited(false); setStatus({ ...status, phase: "submitted", eligible: false }); }} /> : null,
  };
}
