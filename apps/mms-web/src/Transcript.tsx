import { useState, type ComponentProps } from "react";
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

function Turn({events, completed, forced, ...props}: Props & {
  events: SessionEvent[]; completed: boolean; forced: {collapsed: boolean; revision: number} | null;
}) {
  const [choice, setChoice] = useState<{collapsed: boolean; revision: number} | null>(null);
  const revision = forced?.revision || 0;
  const collapsed = choice?.revision === revision ? choice.collapsed
    : forced ? forced.collapsed : props.autoCollapseProcess && completed;
  const user = events[0]?.kind === "user" ? events[0] : null;
  const answer = completed ? [...events].reverse().find(e => e.kind === "assistant" && !!e.text.trim()) : undefined;
  const process = events.filter(e => e !== user && e !== answer && e.kind !== "notice" && e.kind !== "approval");
  if (answer?.thinking) process.push({...answer, id: answer.id + "-thinking", text: "", attachments: [], skills: [], references: []});
  const notices = events.filter(e => e.kind === "notice" || e.kind === "approval");
  const count = process.filter(e => e.kind === "tool").length;
  const toggle = () => setChoice({collapsed: !collapsed, revision});
  const controls = <button type="button" className="turn-process-toggle" aria-expanded={!collapsed} onClick={toggle}>
    {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
    {collapsed ? "展开过程" : "收起过程"}
    <span>{count ? `${count} 次工具调用` : "思考与执行记录"}</span>
  </button>;
  return <section className="conversation-turn">
    {user && <EventView {...props} event={user} />}
    {!!process.length && <div className="turn-process">
      {controls}
      {!collapsed && <ProcessEvents {...props} events={process} />}
    </div>}
    {notices.map(event => <EventView key={event.id} {...props} event={event} />)}
    {answer && <EventView {...props} event={{...answer, thinking: undefined}} />}
    {answer && !!process.length && !collapsed && <div className="turn-process-footer">{controls}</div>}
  </section>;
}

export function Transcript(props: Props) {
  const [forced, setForced] = useState<{collapsed: boolean; revision: number} | null>(null);
  const events = props.detail.events.filter(e => e.id !== "n-web-mode" &&
    !(e.kind === "notice" && e.text === "会话已通过 MMS 启动路径创建") &&
    !(e.kind === "assistant" && !e.text.trim() && !e.thinking?.trim()));
  const turns: SessionEvent[][] = [];
  for (const event of events) {
    if (!turns.length || event.kind === "user") turns.push([]);
    turns[turns.length - 1].push(event);
  }
  const active = ["running", "waiting"].includes(props.detail.session.state);
  return <>
    {turns.map((turn, index) => <Turn key={turn[0].id} {...props} events={turn}
      forced={forced} completed={index < turns.length - 1 || !active} />)}
    {events.some(e => e.kind === "tool" || e.thinking) && <div className="transcript-process-actions" aria-label="过程显示">
      <button onClick={() => setForced({collapsed: true, revision: (forced?.revision || 0) + 1})}><ChevronsDownUp size={14} />收起全部过程</button>
      <button onClick={() => setForced({collapsed: false, revision: (forced?.revision || 0) + 1})}><ChevronsUpDown size={14} />展开全部过程</button>
    </div>}
  </>;
}
