import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, X } from "lucide-react";

export type SetupStep = "connection" | "credentials" | "models" | "preview" | "saved";
const steps: Record<SetupStep, { title: string; body: string; target: string }> = {
  connection: { title: "先粘贴模型服务的地址", body: "在亮起的输入框填写服务商给你的 API 地址。保留 /v1 等路径，填好后点击下一步。", target: "address" },
  credentials: { title: "再填入你的 API Key", body: "从服务商的密钥管理页面复制 Key，粘贴到亮起的输入框。下一步读取模型列表，不发送付费对话。", target: "key" },
  models: { title: "选一个模型开始", body: "勾选你想使用的模型；服务不提供列表时，可以手动填写模型名称。以后还能添加或更换。", target: "models" },
  preview: { title: "检查后，保存这条通道", body: "确认亮起区域的地址和模型。点击保存后，Pilot 会载入 MMS 的思考强度、上下文和识图预设，无需逐项填写。", target: "review" },
  saved: { title: "预设就绪后，开始第一条对话", body: "在这里选首次使用的模型。预设载入成功后，下一步会带你选项目、调整模型和发送消息。", target: "ready" },
};

/** Uses the real form and its validation; the coach never owns credentials. */
export function ConnectionGuide({ step, close, back, busy, manual }: {
  step: SetupStep; close: () => void; back: () => void; busy: boolean; manual: boolean;
}) {
  const layer = useRef<HTMLDivElement>(null);
  const card = useRef<HTMLElement>(null);
  const [layout, setLayout] = useState({ x: 0, y: 0, w: 0, h: 0, left: 12, top: 12, blocked: true, docked: false });
  const item = steps[step];
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let targetBefore: Element | null = null;
    const host = layer.current?.closest<HTMLElement>(".connection-flow");
    const update = () => {
      if (!host || !layer.current || !host.closest("dialog[open]")) { timer = setTimeout(update, 100); return; }
      if (!layer.current.matches(":popover-open")) layer.current.showPopover();
      const target = host.querySelector<HTMLElement>(`[data-setup="${item.target}"]`);
      const next = host.querySelector<HTMLButtonElement>('[data-setup-next]');
      const viewport = window.visualViewport;
      const width = viewport?.width || window.innerWidth, height = viewport?.height || window.innerHeight;
      const offset = viewport?.offsetTop || 0;
      const cw = Math.min(320, width - 24), ch = card.current?.offsetHeight || 220;
      const dialog = host.closest("dialog")?.getBoundingClientRect();
      const docked = !dialog || (width - dialog.right < cw + 24 && dialog.left < cw + 24);
      host.style.setProperty("--setup-coach-space", docked ? `${ch + 28}px` : "0px");
      if (target && target !== targetBefore) {
        target.scrollIntoView({ block: "nearest", behavior: "instant" });
        targetBefore = target;
      }
      let r = target?.getBoundingClientRect();
      const top = docked ? Math.max(offset + 8, offset + height - ch - 12) : Math.max(offset + 12, Math.min(r?.top || 80, offset + height - ch - 12));
      if (r && docked && r.bottom > top - 12) {
        // Reserve room inside the real scroll container so the card never
        // covers the field, even with the mobile keyboard or large text.
        const body = host.closest<HTMLElement>("dialog");
        if (body) body.scrollTop += r.bottom - top + 20;
        r = target?.getBoundingClientRect();
      }
      const left = docked ? (width - cw) / 2 : width - dialog!.right >= cw + 24 ? dialog!.right + 16 : Math.max(12, dialog!.left - cw - 16);
      const value = { x: Math.max(4, (r?.left || 4) - 4), y: Math.max(offset + 4, (r?.top || offset + 4) - 4),
        w: Math.min((r?.width || 0) + 8, width - 8), h: Math.max(0, Math.min((r?.bottom || 0) + 4, docked ? top - 12 : offset + height - 4) - Math.max(offset + 4, (r?.top || offset + 4) - 4)),
        left, top, blocked: !next || next.disabled, docked };
      setLayout(old => JSON.stringify(old) === JSON.stringify(value) ? old : value);
      timer = setTimeout(update, 100);
    };
    timer = setTimeout(update, 0);
    return () => { clearTimeout(timer); host?.style.removeProperty("--setup-coach-space"); layer.current?.hidePopover(); };
  }, [item]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault(); event.stopPropagation(); close();
    };
    document.addEventListener("keydown", escape, true);
    return () => document.removeEventListener("keydown", escape, true);
  }, [close]);
  function next() { layer.current?.closest(".connection-flow")?.querySelector<HTMLButtonElement>('[data-setup-next]')?.click(); }
  return <div ref={layer} popover="manual" className="tour-layer setup-tour-layer" aria-label="悬浮连接引导"
    onKeyDown={e => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); } }}>
    {layout.w > 8 && layout.h > 0 && <div className="tour-spotlight" style={{ left: layout.x, top: layout.y, width: layout.w, height: layout.h }} />}
    <section ref={card} className="tour-card setup-tour-card" role="region" aria-label={item.title}
      style={{ left: layout.left, top: layout.top, width: "min(320px, calc(100vw - 24px))" }}>
      <header><span>连接 AI · {Object.keys(steps).indexOf(step) + 1} / 5</span><button type="button" className="icon-button" aria-label="收起连接引导" onClick={close}><X size={16} /></button></header>
      <h2>{item.title}</h2>
      <p>{step === "credentials" && manual ? "把服务商提供的 API Key 粘贴到亮起的输入框，下一步填写模型名称。密钥不会存到浏览器。" : item.body}</p>
      <footer>{step !== "connection" && step !== "saved" ? <button type="button" className="text-button" disabled={busy} onClick={back}><ArrowLeft size={14} />上一步</button> : <button type="button" className="text-button" onClick={close}>自己填写</button>}
        <button type="button" className="button primary" disabled={busy || layout.blocked} onClick={next}>{busy ? "处理中…" : step === "preview" ? "保存通道" : step === "saved" ? "开始对话引导" : "下一步"}<ArrowRight size={14} /></button></footer>
    </section>
  </div>;
}
