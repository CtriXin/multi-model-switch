import { useEffect, useRef, useState } from "react";
import { MessageSquare } from "lucide-react";
import { isPreview, request } from "./api";
import "./feedback.css";

type Status = {
  enabled: boolean;
  eligible: boolean;
  idle: boolean;
  phase: string;
  formUrl: string;
};

export function useFeedback({ ready, allowed }: { ready: boolean; allowed: boolean }) {
  const [status, setStatus] = useState<Status>();
  const [invited, setInvited] = useState(false);
  const lastInput = useRef(Date.now());
  const claimPending = useRef(false);
  const current = useRef({ allowed });
  current.current = { allowed };
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
        if (["opened", "dismissed", "submitted"].includes(next.phase)) setInvited(false);
        const active = document.activeElement;
        const editing = active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement
          ? Boolean(active.value.trim())
          : active?.matches("select, [contenteditable=true]");
        const hasDraft = Array.from(document.querySelectorAll<HTMLTextAreaElement>("textarea"))
          .some(input => input.getClientRects().length > 0 && input.value.trim());
        if (!next.eligible || !current.current.allowed || editing ||
            hasDraft ||
            document.querySelector("dialog[open], [popover]:popover-open") ||
            Date.now() - lastInput.current < 30000 || claimPending.current) return;
        claimPending.current = true;
        try {
          const claim = await request<{ claimed: boolean }>("/feedback/invitation", { action: "claim" });
          if (!cancelled && claim.claimed && current.current.allowed && Date.now() - lastInput.current >= 30000) setInvited(true);
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

  function openForm() {
    // The anchor opens synchronously on the click. Preference persistence must
    // never block navigation, and opening must never imply a received answer.
    setInvited(false);
    void request<Status>("/feedback/invitation", { action: "open" })
      .then(setStatus).catch(() => {});
  }
  async function dismiss(action: "later" | "dismiss") {
    setInvited(false);
    try { setStatus(await request<Status>("/feedback/invitation", { action })); }
    catch { /* Claim was already persisted; a failed dismiss cannot cause re-prompting. */ }
  }
  const formLink = status?.enabled && status.formUrl ? status.formUrl : undefined;
  return {
    trigger: formLink ? <a className="icon-button feedback-link" href={formLink} target="_blank" rel="noopener noreferrer" title="反馈使用体验（飞书表单，无需登录）" aria-label="反馈使用体验（飞书表单，新标签页）" onClick={openForm}><MessageSquare size={18} /></a> : null,
    invitation: invited && allowed && formLink && status?.idle ? <aside className="feedback-invitation" aria-label="使用体验邀请">
      <span>用了几天，MMS 有没有帮你把事情做成？</span>
      <div><a className="button feedback-link" href={formLink} target="_blank" rel="noopener noreferrer" onClick={openForm}>反馈一下</a><button className="text-button" onClick={() => void dismiss("later")}>以后再说</button><button className="text-button" onClick={() => void dismiss("dismiss")}>不再提醒</button></div>
    </aside> : null,
  };
}
