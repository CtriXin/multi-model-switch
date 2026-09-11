import { useEffect, useState, type ComponentProps } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { EventView } from "./components";
import { ToolGroup } from "./ToolEvent";
import type { SessionEvent } from "./types";
import { deliveryLabel, steerBadge, steerLinks } from "./message-control";

type Props = Omit<ComponentProps<typeof EventView>, "event" | "continuation" | "intermediate"> & {autoCollapseProcess: boolean};

function ProcessEvents({events, ...props}: Props & {events: SessionEvent[]}) {
  const blocks: {event: SessionEvent; tools?: SessionEvent[]}[] = [];
  for (const event of events) {
    const previous = blocks.at(-1);
    if (event.kind === "tool" && previous?.tools) previous.tools.push(event);
    else blocks.push({event, tools: event.kind === "tool" ? [event] : undefined});
  }
  return <>{blocks.map(({event, tools}) => tools
    ? <ToolGroup key={event.id} events={tools} detail={props.detail} disconnected={!!props.disconnected} />
    : <EventView key={event.id} {...props} event={event} continuation intermediate />)}</>;
}

function Turn({events, completed, forced, report, steered, ...props}: Props & {
  events: SessionEvent[]; completed: boolean; forced: {collapsed: boolean; revision: number} | null;
  report: (id: string, collapsed: boolean) => void;
  steered: Map<string, string>;
}) {
  const [choice, setChoice] = useState<{collapsed: boolean; revision: number} | null>(null);
  const revision = forced?.revision || 0;
  const user = events[0]?.kind === "user" ? events[0] : null;
  const answer = completed ? [...events].reverse().find(e => e.kind === "assistant" && !!e.text.trim()) : undefined;
  const collapsed = choice?.revision === revision ? choice.collapsed
    : forced ? forced.collapsed : props.autoCollapseProcess && completed && !!answer;
  const answerIndex = answer ? events.indexOf(answer) : events.length;
  const process = events.slice(0, answerIndex).filter(e => e !== user);
  if (answer?.thinking) process.push({...answer, id: answer.id + "-thinking", text: "", attachments: [], skills: [], references: []});
  const after = answer ? events.slice(answerIndex + 1) : [];
  const pinned = process.filter(e => e.kind === "notice" || e.kind === "approval" || e.status === "error");
  const count = process.filter(e => e.kind === "tool").length;
  const failures = process.filter(e => e.status === "error").length;
  const toggle = () => setChoice({collapsed: !collapsed, revision});
  // The transcript-wide button names the action, so it needs to know whether
  // anything is still open, including turns opened one at a time.
  const turnId = events[0]?.id || "";
  const hasProcess = !!process.length;
  useEffect(() => {
    if (hasProcess) report(turnId, collapsed);
  }, [report, turnId, collapsed, hasProcess]);
  const controls = <button type="button" className="turn-process-toggle" aria-expanded={!collapsed} onClick={toggle}>
    {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
    {collapsed ? "展开过程" : "收起过程"}
    <span>{count ? `${count} 次工具调用` : "思考与执行记录"}</span>
    {!!failures && <span className="process-failure">{failures} 项失败</span>}
  </button>;
  return <section className="conversation-turn">
    {user && <EventView {...props} event={user} />}
    {!!process.length && <div className="turn-process">
      {controls}
      <ProcessEvents {...props} events={collapsed ? pinned : process} />
    </div>}
    {answer && <EventView {...props} event={{...answer, thinking: undefined}} turnStartedAt={user?.createdAt} />}
    {(() => {
      // The steer may have landed in an intermediate answer that the collapsed
      // process hides, so the note belongs to the turn the reader is looking at.
      const note = events.map(event => steered.get(event.id)).find(Boolean);
      return note ? <p className="steer-note" role="note">{note}</p> : null;
    })()}
    {after.map(event => <EventView key={event.id} {...props} event={event} />)}
    {answer && !!process.length && !collapsed && <div className="turn-process-footer">{controls}</div>}
  </section>;
}

export function Transcript({forced, report, ...props}: Props & {
  forced: {collapsed: boolean; revision: number} | null;
  report: (id: string, collapsed: boolean) => void;
}) {
  const events = props.detail.events.filter(e => e.id !== "n-web-mode" &&
    !(e.kind === "notice" && e.text === "会话已通过 MMS 启动路径创建") &&
    !(e.kind === "assistant" && !e.text.trim() && !e.thinking?.trim()));
  const pending = events.filter(e => e.kind === "user" && ["queued", "cancelled", "error"].includes(e.status || ""));
  const turns: SessionEvent[][] = [];
  for (const event of events.filter(e => !pending.includes(e))) {
    if (!turns.length || event.kind === "user") turns.push([]);
    turns[turns.length - 1].push(event);
  }
  const active = ["running", "waiting"].includes(props.detail.session.state);
  const steered = new Map(steerLinks(events).flatMap(link => {
    const badge = steerBadge(link);
    return badge ? [[link.assistantId, badge] as const] : [];
  }));
  return <>
    {turns.map((turn, index) => <Turn key={turn[0].id} {...props} events={turn} report={report}
      steered={steered} forced={forced} completed={index < turns.length - 1 || !active} />)}
    {!!pending.length && <section className="pending-messages" aria-label="未执行的消息">
      {pending.map(event => <div key={event.id}><small>{deliveryLabel(event)}</small><EventView {...props} event={event} /></div>)}
    </section>}
  </>;
}
