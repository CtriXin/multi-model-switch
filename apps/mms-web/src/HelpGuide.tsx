import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Search, X } from "lucide-react";
import { guideTopics, matchingTopics, starterPrompt } from "./guide-content";
import type { GuideAction } from "./guide-content";
import type { Bootstrap } from "./types";
import "./guide.css";

const seenKey = "mms-web-guide-seen-v1";
const steps = [
  { title: "连接一个模型服务", body: "MMS 把你自己的模型服务接到这个页面。在设置中填入服务地址、API Key 和模型，检查后保存。已经有可用模型时，可以直接继续。", action: "settings", label: "去连接模型服务" },
  { title: "选好工作的文件夹", body: "选择这次任务所在的项目目录。模型读取和修改文件时会使用这个工作路径。已有会话保留原路径；换项目时新建一个任务，再选择目录。", action: "workspace", label: "去选择工作文件夹" },
  { title: "选模型，调整思考强度", body: "点击输入框底部的模型名称，选择模型与通道，再按任务调整 effort。简单问答可用较低档，复杂分析可提高；更高通常需要更多时间和用量。这里只提供当前模型支持的档位。", action: "model", label: "找到模型与 effort" },
  { title: "从一条简单对话开始", body: "把目标、已有材料和希望得到的结果说清楚。下面是一条入门示例：填入草稿后可以修改，确认模型和目录，再由你点击发送。", action: "compose", label: "找到输入框" },
] as const;

export function HelpGuide({ ready, open, setOpen, data, hasSession, navigate, example }: {
  ready: boolean; open: boolean; setOpen: (open: boolean) => void; data: Bootstrap;
  hasSession: boolean; navigate: (action: GuideAction) => void; example: (text: string) => void;
}) {
  const [section, setSection] = useState("start");
  const [step, setStep] = useState(0);
  const [query, setQuery] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const content = useRef<HTMLElement>(null);
  const attempted = useRef(false);
  const returnFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!ready || attempted.current) return;
    attempted.current = true;
    try { if (localStorage.getItem(seenKey)) return; } catch { /* Help remains usable without storage. */ }
    setOpen(true);
  }, [ready, setOpen]);
  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement as HTMLElement;
    dialog.current?.showModal();
    try { localStorage.setItem(seenKey, "1"); } catch { /* One attempt per page load. */ }
    return () => {
      dialog.current?.close();
      if (returnFocus.current?.isConnected) returnFocus.current.focus();
    };
  }, [open]);
  useEffect(() => { content.current?.scrollTo(0, 0); }, [section, step]);
  const close = () => setOpen(false);
  const go = (action: GuideAction) => { close(); navigate(action); };
  const topics = matchingTopics(query);
  const topic = guideTopics.find(t => t.id === section);
  const current = steps[step];
  const modelReady = data.presets.some(p => p.available);
  return <>
    <button id="mms-help-button" type="button" className="icon-button help-trigger" title="使用引导与功能说明" aria-label="使用引导与功能说明" onClick={() => setOpen(true)}>?</button>
    {open && <dialog ref={dialog} className="help-guide" aria-labelledby="help-guide-title" onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === dialog.current) close(); }}>
      <header className="guide-header">
        <div><h2 id="help-guide-title">MMS 使用引导</h2><p>从第一条对话开始，需要时再了解更多。</p></div>
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
            <div className="guide-progress" aria-label={`入门第 ${step + 1} 步，共 ${steps.length} 步`}>
              {steps.map((item, index) => <button type="button" key={item.title} className={index === step ? "active" : ""} aria-label={`第 ${index + 1} 步：${item.title}`} aria-current={index === step ? "step" : undefined} onClick={() => setStep(index)}>{index + 1}</button>)}
              <span>{step + 1} / {steps.length}</span>
            </div>
            <h3>{current.title}</h3><p className="guide-lead">{current.body}</p>
            {step === 0 && <p className="guide-status">{modelReady ? <><Check size={16} /> 当前已发现可用模型，可以继续。</> : "尚未发现可用模型。可以先了解操作，再到设置中连接服务。"}</p>}
            {step === 1 && <p className="guide-status">{data.workspaces.length ? "已添加的工作文件夹可在新建任务顶部选择，也能添加其他路径。" : "先添加一个你准备使用的工作文件夹。"}</p>}
            {step === 2 && <dl className="guide-definitions"><div><dt>模型</dt><dd>负责理解任务和生成回答。</dd></div><div><dt>通道</dt><dd>提供这个模型的连接服务。</dd></div><div><dt>effort</dt><dd>当前模型的思考投入，按需要调整。</dd></div></dl>}
            {step === 3 && <div className="guide-example"><p>{starterPrompt}</p><button type="button" className="button" onClick={() => { close(); example(starterPrompt); }}>填入新任务草稿 <ArrowRight size={15} /></button><small>已有草稿会保留，示例追加在后面。这里不会发送消息。</small></div>}
            <button type="button" className="guide-location-link" onClick={() => go(current.action)}>{current.label}<ArrowRight size={15} /></button>
            <div className="guide-step-footer">
              <button type="button" className="text-button" disabled={step === 0} onClick={() => setStep(step - 1)}><ArrowLeft size={15} /> 上一步</button>
              {step < steps.length - 1 ? <button type="button" className="button" onClick={() => setStep(step + 1)}>下一步 <ArrowRight size={15} /></button> : <button type="button" className="text-button" onClick={() => setSection("messages")}>继续了解功能 <ArrowRight size={15} /></button>}
            </div>
          </> : topic && <>
            <h3>{topic.title}</h3><p className="guide-lead">{topic.summary}</p>
            <div className="guide-article">{topic.sections.map(item => <section key={item.title}><h4>{item.title}</h4><p>{item.body}</p></section>)}</div>
            <button type="button" className="button" disabled={topic.needsSession && !hasSession} onClick={() => go(topic.action)}>{topic.actionLabel}<ArrowRight size={15} /></button>
            {topic.needsSession && !hasSession && <p className="guide-footnote">先打开或开始一条会话，再查看这里的实际内容。</p>}
          </>}
        </section>
      </div>
      <footer className="guide-footer"><span>随时点击右上角 ? 重新打开。</span><button type="button" className="text-button" onClick={close}>先自己试试</button></footer>
    </dialog>}
  </>;
}

export interface GuideDestination { target: string; text: string; nonce: string }
export function GuideNudge({ destination, close, reopen }: { destination: GuideDestination | null; close: () => void; reopen: () => void }) {
  useEffect(() => {
    if (!destination) return;
    let target: HTMLElement | null = null;
    const frame = requestAnimationFrame(() => {
      target = document.querySelector<HTMLElement>(destination.target);
      if (!target) return;
      target.setAttribute("data-guide-highlight", "true");
      target.scrollIntoView({ block: "nearest" });
      target.focus({ preventScroll: true });
    });
    return () => { cancelAnimationFrame(frame); target?.removeAttribute("data-guide-highlight"); };
  }, [destination]);
  if (!destination) return null;
  return <aside className="guide-nudge" aria-label="操作引导"><p role="status">{destination.text}</p><button type="button" className="text-button" onClick={reopen}>返回引导</button><button type="button" className="icon-button" aria-label="结束操作引导" onClick={close}><X size={16} /></button></aside>;
}
