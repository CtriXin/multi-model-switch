import { useEffect, useRef, useState } from "react";
import { ArrowRight, Search, X } from "lucide-react";
import { guideTopics, matchingTopics } from "./guide-content";
import type { GuideAction } from "./guide-content";
import "./guide.css";
import { request } from "./api";

const seenKey = "mms-web-tour-seen-v1";
function markSeen(persist: boolean) {
  try { localStorage.setItem(seenKey, "1"); } catch { /* One attempt per page load. */ }
  if (persist) void request("/ui-preferences", { tourSeen: true }).catch(() => { /* browser cache still prevents a replay on this origin */ });
}
export function HelpGuide({ ready, modelReady, open, setOpen, hasSession, navigate, startTour, startConnection }: {
  ready: boolean; modelReady: boolean; open: boolean; setOpen: (open: boolean) => void;
  hasSession: boolean; navigate: (action: GuideAction) => void; startTour: () => void;
  startConnection?: () => void;
}) {
  const [section, setSection] = useState("start");
  const [query, setQuery] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const content = useRef<HTMLElement>(null);
  const attempted = useRef(false);
  const returnFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!ready || attempted.current) return;
    attempted.current = true;
    let cancelled = false;
    // The install-level flag lives in the Pilot state root, so a new port or
    // browser does not replay the first-run tour; localStorage is only a cache.
    void (async () => {
      let seenOnServer: boolean | null = null;
      try { seenOnServer = (await request<{ tourSeen: boolean }>("/ui-preferences")).tourSeen; } catch { /* fall back to the browser cache */ }
      if (cancelled) return;
      let seenLocally = false;
      try { seenLocally = !!localStorage.getItem(seenKey); } catch { /* Help remains usable without storage. */ }
      if (seenOnServer) { markSeen(false); return; }
      markSeen(true);
      if (seenLocally) return;
      startTour();
    })();
    return () => { cancelled = true; };
  }, [ready, startTour]);
  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement as HTMLElement;
    dialog.current?.showModal();
    if (modelReady) markSeen(true);
    return () => {
      dialog.current?.close();
      if (returnFocus.current?.isConnected) returnFocus.current.focus();
    };
  }, [open]);
  useEffect(() => { content.current?.scrollTo(0, 0); }, [section]);
  const close = () => setOpen(false);
  const go = (action: GuideAction) => { close(); navigate(action); };
  const topics = matchingTopics(query);
  const topic = guideTopics.find(t => t.id === section);
  return <>
    <button id="mms-help-button" type="button" className="icon-button help-trigger" title="使用引导与功能说明" aria-label="使用引导与功能说明" onClick={() => setOpen(true)}>?</button>
    {open && <dialog ref={dialog} className="help-guide" aria-labelledby="help-guide-title" onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === dialog.current) close(); }}>
      <header className="guide-header">
        <div><h2 id="help-guide-title">MMS 使用引导</h2><p>悬浮引导带你操作，功能说明随时查阅。</p></div>
        <button type="button" className="icon-button" aria-label="关闭使用引导" onClick={close}><X size={19} /></button>
      </header>
      <div className="guide-layout">
        <nav className="guide-index" aria-label="使用引导目录">
          <label className="guide-search"><Search size={16} /><input type="search" aria-label="搜索功能说明" placeholder="搜索功能，如 effort" value={query} onChange={event => setQuery(event.target.value)} /></label>
          {!query.trim() && <button type="button" aria-current={section === "start" ? "page" : undefined} onClick={() => setSection("start")}>第一次使用<span>连接、选择、开始对话</span></button>}
          {topics.map(item => <button type="button" key={item.id} aria-current={section === item.id ? "page" : undefined} onClick={() => setSection(item.id)}>{item.title}</button>)}
          {!topics.length && <p className="guide-empty" role="status">没有匹配的功能。试试“模型”“路径”或“成果”。</p>}
        </nav>
        <section className="guide-content" ref={content} aria-label="功能说明">
          {section === "start" ? <>
            <h3>让我们一起开始第一条对话</h3>
            <p className="guide-lead">不用先读完说明书。悬浮引导会圈亮真实按钮和输入框，一步步带你选择文件夹、模型与思考强度，再写下并发送第一条消息。</p>
            <button type="button" className="button primary" onClick={() => { close(); startTour(); }}>{modelReady ? "带我一步步操作" : "先配置模型服务"} <ArrowRight size={15} /></button>
            {modelReady && startConnection && <button type="button" className="text-button guide-connection-entry" onClick={() => { close(); startConnection(); }}>引导我连接新通道<ArrowRight size={15} /></button>}
            <p className="guide-footnote">可以直接操作亮起的功能，随时跳过。已有草稿和会话会保留；引导不会替你发送消息。</p>
            <div className="guide-article"><section><h4>暂时没有模型服务？</h4><p>你需要服务商提供的 API 地址和 API Key（连接密钥）。我们会先带你填写连接信息并读取模型预设，成功后再介绍聊天功能。没有服务信息也可以稍后配置。</p></section><section><h4>只想了解某个功能？</h4><p>从目录选择，或搜索「effort」「路径」「成果」。每篇说明都可以带你找到实际入口。</p></section></div>
          </> : topic && <>
            <h3>{topic.title}</h3><p className="guide-lead">{topic.summary}</p>
            <div className="guide-article">{topic.sections.map(item => <section key={item.title}><h4>{item.title}</h4><p>{item.body}</p></section>)}</div>
            <button type="button" className="button" disabled={topic.needsSession && !hasSession} onClick={() => go(topic.action)}>{topic.actionLabel}<ArrowRight size={15} /></button>
            {topic.needsSession && !hasSession && <p className="guide-footnote">先打开或开始一条会话，再查看这里的实际内容。</p>}
          </>}
        </section>
      </div>
      <footer className="guide-footer"><button type="button" className="text-button" onClick={() => { close(); startTour(); }}>{modelReady ? "重新开始悬浮引导" : "开始配置模型服务"}</button><button type="button" className="text-button" onClick={close}>先自己试试</button></footer>
    </dialog>}
  </>;
}
