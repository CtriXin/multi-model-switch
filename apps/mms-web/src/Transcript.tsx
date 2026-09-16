import { useEffect, useState, type ComponentProps } from "react";
import { ChevronDown, ChevronRight, CircleAlert, RotateCcw } from "lucide-react";
import { EventView, Logo, harnessNames } from "./components";
import { ToolGroup } from "./ToolEvent";
import type { Session, SessionDetail, SessionEvent } from "./types";
import { deliveryLabel, steerBadge, steerLinks } from "./message-control";
import { sessionIsBusy, turnWorkingHint, turnInterruptedNotice, isTurnInterrupted } from "./SessionStatus";

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

function findActiveAnswer(events: SessionEvent[]): SessionEvent | undefined {
  const lastAssistant = [...events].reverse().find(e => e.kind === "assistant" && !!e.text.trim());
  if (!lastAssistant) return undefined;
  const assistantIndex = events.indexOf(lastAssistant);
  const subsequentTools = events.slice(assistantIndex + 1).some(e => e.kind === "tool");
  if (subsequentTools) return undefined;
  return lastAssistant;
}

function TurnWorkingStatus({
  detail,
  disconnected = false,
}: {
  detail: SessionDetail;
  disconnected?: boolean;
}) {
  const session = detail.session;
  const author = harnessNames[session.harness] || "AI";
  const model = session.modelName;
  const statusText = turnWorkingHint(session, disconnected);

  return (
    <article
      className="message assistant turn-working-message"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <div className="message-avatar">
        <Logo small />
      </div>
      <div className="message-body">
        <div className="message-author">
          {author}
          {model && <span>{model}</span>}
        </div>
        <div className="turn-working-indicator">
          <span className="activity-bars" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span className="turn-working-label">{statusText}</span>
        </div>
      </div>
    </article>
  );
}

export function evaluateTurnReplySlot({
  events,
  completed,
  isLatestTurn,
  isSteered,
  session,
}: {
  events: SessionEvent[];
  completed: boolean;
  isLatestTurn: boolean;
  isSteered: boolean;
  session: Session;
}): {
  slot: "answer" | "working" | "interrupted" | "empty";
  answer?: SessionEvent;
  notice?: string;
} {
  const completedAnswer = completed ? [...events].reverse().find(e => e.kind === "assistant" && !!e.text.trim()) : undefined;
  const streamingAnswer = !completed ? findActiveAnswer(events) : undefined;
  const answer = completedAnswer || streamingAnswer;
  if (answer) {
    return { slot: "answer", answer };
  }
  if (!completed) {
    return { slot: "working" };
  }
  const interrupted = isTurnInterrupted(events, session, isLatestTurn, isSteered);
  if (interrupted) {
    return { slot: "interrupted", notice: turnInterruptedNotice(events) };
  }
  return { slot: "empty" };
}

export function Turn({events, completed, forced, report, steered, isLatestTurn, isSteered, onResend, ...props}: Props & {
  events: SessionEvent[]; completed: boolean; forced: {collapsed: boolean; revision: number} | null;
  report: (id: string, collapsed: boolean) => void;
  steered: Map<string, string>;
  isLatestTurn: boolean;
  isSteered: boolean;
  onResend?: (text: string) => void;
}) {
  const [choice, setChoice] = useState<{collapsed: boolean; revision: number} | null>(null);
  const revision = forced?.revision || 0;
  const user = events[0]?.kind === "user" ? events[0] : null;
  const replySlot = evaluateTurnReplySlot({
    events,
    completed,
    isLatestTurn,
    isSteered,
    session: props.detail.session,
  });
  const answer = replySlot.answer;
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
  const isRunning = !completed;
  useEffect(() => {
    if (hasProcess) report(turnId, collapsed);
  }, [report, turnId, collapsed, hasProcess]);
  const controls = <button type="button" className="turn-process-toggle" aria-expanded={!collapsed} onClick={toggle}>
    {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
    {collapsed ? "展开过程" : "收起过程"}
    <span>{count ? `${count} 次工具调用` : "思考与执行记录"}</span>
    {isRunning && collapsed && <span className="turn-process-live-dot" title="正在执行中" aria-label="正在执行中" />}
    {!!failures && <span className="process-failure">{failures} 项失败</span>}
  </button>;
  return <section className="conversation-turn">
    {user && <EventView {...props} event={user} />}
    {!!process.length && <div className="turn-process">
      {controls}
      <ProcessEvents {...props} events={collapsed ? pinned : process} />
    </div>}
    {replySlot.slot === "answer" && replySlot.answer ? (
      <EventView {...props} event={{...replySlot.answer, thinking: undefined}} turnStartedAt={user?.createdAt} />
    ) : replySlot.slot === "working" ? (
      <TurnWorkingStatus detail={props.detail} disconnected={props.disconnected} />
    ) : replySlot.slot === "interrupted" ? (
      <div className="turn-interrupted-notice" role="status">
        <span className="turn-interrupted-icon" aria-hidden="true">
          <CircleAlert size={14} />
        </span>
        <span className="turn-interrupted-text">
          {replySlot.notice || turnInterruptedNotice(events)}
        </span>
        {onResend && !!user?.text?.trim() && (
          <button
            type="button"
            className="pending-resend-button"
            onClick={() => onResend(user.text)}
          >
            <RotateCcw size={12} />
            重新发送
          </button>
        )}
      </div>
    ) : null}
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

export function isTurnCompleted(
  turnEvents: SessionEvent[],
  index: number,
  totalTurns: number,
  session: Session,
  disconnected = false,
): boolean {
  const busy = sessionIsBusy(session, disconnected);
  const hasRunningTool = turnEvents.some(e => e.kind === "tool" && e.status === "running");
  const hasActiveEvent = Boolean(
    session.activity?.eventId && turnEvents.some(e => e.id === session.activity?.eventId)
  );

  // If this turn has a tool currently running or is the target of current activity,
  // it is actively working and NOT completed, even if subsequent user messages exist.
  if (hasRunningTool || (hasActiveEvent && busy)) {
    return false;
  }

  // If it's the latest turn, completion directly depends on whether the session is busy.
  if (index === totalTurns - 1) {
    return !busy;
  }

  // Prior turns with no active tools or events are completed.
  return true;
}

export function Transcript({forced, report, onResend, ...props}: Props & {
  forced: {collapsed: boolean; revision: number} | null;
  report: (id: string, collapsed: boolean) => void;
  onResend?: (text: string) => void;
}) {
  const events = props.detail.events.filter(e => e.id !== "n-web-mode" &&
    !(e.kind === "notice" && e.text === "会话已通过 MMS 启动路径创建") &&
    !(e.kind === "assistant" && !e.text.trim() && !e.thinking?.trim()));
  const pending = events.filter(e => e.kind === "user" && ["queued", "cancelled", "error", "failed", "interrupted"].includes(e.status || ""));
  const turns: SessionEvent[][] = [];
  for (const event of events.filter(e => !pending.includes(e))) {
    if (!turns.length || event.kind === "user") turns.push([]);
    turns[turns.length - 1].push(event);
  }
  const steered = new Map(steerLinks(events).flatMap(link => {
    const badge = steerBadge(link);
    return badge ? [[link.assistantId, badge] as const] : [];
  }));
  return <>
    {turns.map((turn, index) => {
      const nextTurn = turns[index + 1];
      const isSteered = Boolean(
        (nextTurn && nextTurn[0]?.mode === "steer") ||
        (turn[0]?.id && steered.has(turn[0]?.id))
      );
      const isLatestTurn = index === turns.length - 1;
      return (
        <Turn
          key={turn[0].id}
          {...props}
          events={turn}
          report={report}
          steered={steered}
          forced={forced}
          isLatestTurn={isLatestTurn}
          isSteered={isSteered}
          completed={isTurnCompleted(turn, index, turns.length, props.detail.session, props.disconnected)}
          onResend={onResend}
        />
      );
    })}
    {!!pending.length && (
      <section className="pending-messages" aria-label="未执行的消息">
        {pending.map(event => {
          const canResend = ["cancelled", "interrupted", "error", "failed"].includes(event.status || "");
          return (
            <div key={event.id} className="pending-message-item">
              <div className="pending-message-header">
                <small>{deliveryLabel(event)}</small>
                {onResend && canResend && !!event.text?.trim() && (
                  <button
                    type="button"
                    className="pending-resend-button"
                    onClick={() => onResend(event.text)}
                  >
                    <RotateCcw size={12} />
                    重新发送
                  </button>
                )}
              </div>
              <EventView {...props} event={event} />
            </div>
          );
        })}
      </section>
    )}
  </>;
}
