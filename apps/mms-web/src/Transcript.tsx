import { useCallback, useEffect, useState, type ComponentProps } from "react";
import { ChevronDown, ChevronRight, ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { EventView } from "./components";
import { ToolGroup } from "./ToolEvent";
import type { SessionEvent } from "./types";

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

function Turn({events, completed, forced, report, ...props}: Props & {
  events: SessionEvent[]; completed: boolean; forced: {collapsed: boolean; revision: number} | null;
  report: (id: string, collapsed: boolean) => void;
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
    {answer && <EventView {...props} event={{...answer, thinking: undefined}} />}
    {after.map(event => <EventView key={event.id} {...props} event={event} />)}
    {answer && !!process.length && !collapsed && <div className="turn-process-footer">{controls}</div>}
  </section>;
}

export function Transcript(props: Props) {
  const [forced, setForced] = useState<{collapsed: boolean; revision: number} | null>(null);
  const [turnStates, setTurnStates] = useState<Record<string, boolean>>({});
  const report = useCallback((id: string, collapsed: boolean) => {
    setTurnStates(old => old[id] === collapsed ? old : {...old, [id]: collapsed});
  }, []);
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
  return <>
    {turns.map((turn, index) => <Turn key={turn[0].id} {...props} events={turn} report={report}
      forced={forced} completed={index < turns.length - 1 || !active} />)}
    {!!pending.length && <section className="pending-messages" aria-label="未执行的消息">
      {pending.map(event => <div key={event.id}><small>{event.status === "queued" ? "排队中，尚未执行" : event.status === "cancelled" ? "已取消，未执行" : "发送失败，未执行"}</small><EventView {...props} event={event} /></div>)}
    </section>}
    {events.some(e => e.kind === "tool" || e.thinking) && (() => {
      const shown = turns.map(turn => turnStates[turn[0].id]).filter(v => v !== undefined);
      // Anything still open means the useful action is to close it.
      const collapseNext = shown.some(collapsed => !collapsed);
      return <div className="transcript-process-actions" aria-label="过程显示">
        <button
          aria-expanded={collapseNext}
          onClick={() => setForced({collapsed: collapseNext, revision: (forced?.revision || 0) + 1})}
        >
          {collapseNext ? <ChevronsDownUp size={14} /> : <ChevronsUpDown size={14} />}
          {collapseNext ? "收起全部过程" : "展开全部过程"}
        </button>
      </div>;
    })()}
  </>;
}
