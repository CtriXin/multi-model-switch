import type { Session, SessionEvent } from "./types";
import {
  Check,
  Circle,
  CircleAlert,
  Pause,
  CircleHelp,
  WifiOff,
  LoaderCircle,
  Wrench,
} from "lucide-react";

export function sessionStatus(
  session: Session,
  disconnected = false,
  unread = false,
) {
  const terminal = ["completed", "stopped", "error"].includes(session.state);
  const phase = disconnected
    ? "disconnected"
    : terminal
      ? session.state === "completed"
        ? "closed"
        : session.state
      : session.state === "waiting"
        ? "waiting"
        : session.activity?.phase ||
          (session.state === "idle"
            ? unread
              ? "completed"
              : "pending"
            : session.state);
  const labels: Record<string, string> = {
    idle: "准备就绪",
    pending: "待命",
    running: "执行中",
    thinking: "思考中",
    responding: "正在输出",
    tool: "执行工具",
    waiting: session.activity?.method === "confirm" ? "等待确认" : "等待你回答",
    compacting: "压缩上下文",
    retrying: "正在重试",
    completed: "已完成",
    closed: "进程已结束",
    stopped: "已停止",
    error: "执行出错",
    disconnected: "状态未同步",
  };
  const label = labels[phase] || labels.running;
  const detail =
    phase === "tool" && session.activity?.toolName
      ? `${label} · ${session.activity.toolName}`
      : label;
  return { phase, label, detail };
}

export const BUSY_PHASES = new Set([
  "running",
  "thinking",
  "responding",
  "tool",
  "waiting",
  "compacting",
  "retrying",
]);

export function sessionIsBusy(session: Session, _disconnected = false): boolean {
  const { phase } = sessionStatus(session, false);
  return BUSY_PHASES.has(phase);
}

export function isTurnInterrupted(
  events: SessionEvent[],
  session?: Session,
  isLatestTurn = false,
  isSteered = false,
): boolean {
  const hasAnswer = events.some(e => e.kind === "assistant" && !!e.text.trim());
  if (hasAnswer) return false;
  if (isSteered) return false;

  // STRICT REQUIREMENT: Only the latest turn can be considered interrupted.
  // Historical turns where execution ended without an answer (e.g. user stopped during bash sleep)
  // are completed history and must never display the interrupted notice banner or resend prompt.
  if (!isLatestTurn) {
    return false;
  }

  const hasForceEndedTool = events.some(
    e => e.kind === "tool" && (e.status === "error" || e.status === "cancelled") &&
      typeof e.text === "string" && e.text.includes("本轮已结束，未收到此工具的完成回报。")
  );
  if (hasForceEndedTool) return true;

  if (session) {
    const isAbnormalTerminal = ["stopped", "error", "closed"].includes(session.state);
    if (isAbnormalTerminal && !sessionIsBusy(session)) {
      return true;
    }
  }

  const hasResumeNotice = events.some(
    e => e.kind === "notice" && typeof e.text === "string" && e.text.includes("已恢复上次的上下文，可以继续工作。")
  );
  if (hasResumeNotice) return true;

  return false;
}

export function turnInterruptedNotice(_events?: SessionEvent[]): string {
  return "本轮执行被中断，未产生回复。发送新消息可继续对话。";
}

export function Status({
  session,
  compact = false,
  disconnected = false,
  unread = false,
}: {
  session: Session;
  compact?: boolean;
  disconnected?: boolean;
  unread?: boolean;
}) {
  const { phase, detail } = sessionStatus(session, disconnected, unread);
  const Icon =
    (
      {
        completed: Check,
        pending: Circle,
        closed: Pause,
        stopped: Pause,
        error: CircleAlert,
        waiting: CircleHelp,
        disconnected: WifiOff,
        tool: Wrench,
      } as Record<string, typeof Check>
    )[phase] || LoaderCircle;
  return (
    <span
      className={`status ${phase}${compact ? " compact" : ""}`}
      title={detail}
      aria-label={compact ? detail : undefined}
      data-phase={phase}
    >
      <span className="status-symbol" aria-hidden="true">
        {["thinking", "responding"].includes(phase) ? (
          <span className="activity-bars">
            <i />
            <i />
            <i />
          </span>
        ) : (
          <Icon size={14} strokeWidth={2} />
        )}
      </span>
      {!compact && <span className="status-label">{detail}</span>}
    </span>
  );
}

export const activityHints: Record<string, string> = {
  idle: "就绪 · 随时发送消息",
  pending: "就绪 · 随时发送消息",
  running: "正在规划与执行…",
  thinking: "正在思考…",
  responding: "正在输出回复…",
  tool: "正在执行终端工具…",
  waiting: "等待你的回答",
  compacting: "正在整理上下文…",
  retrying: "正在自动重试…",
  completed: "本轮执行完成",
  closed: "进程已结束",
  stopped: "已停止",
  error: "查看上方错误详情后再继续",
  disconnected: "连接恢复后更新；保留最近内容",
};

export function turnWorkingHint(
  session: Session,
  disconnected = false,
  unread = false,
): string {
  if (disconnected) return "状态未同步，等待重新连接…";
  const { phase } = sessionStatus(session, disconnected, unread);
  if (phase === "tool" && session.activity?.toolName) {
    return `正在执行工具 · ${session.activity.toolName}`;
  }
  if (phase === "waiting") {
    return session.activity?.method === "confirm" ? "等待确认工具操作" : "等待你的回答";
  }
  return activityHints[phase] || "正在处理中…";
}

export function CurrentActivity({
  session,
  disconnected,
  unread = false,
}: {
  session: Session;
  disconnected: boolean;
  unread?: boolean;
}) {
  const { phase } = sessionStatus(session, disconnected, unread);
  const closedHint = session.capabilities.send
    ? "发送消息可继续本次对话"
    : "仍可查看历史记录";
  const hintText =
    phase === "closed" ? closedHint : activityHints[phase];
  const route = [session.modelName, session.providerName || session.channel]
    .filter(Boolean)
    .join(" · ");
  return (
    <div
      className={`current-activity ${phase}`}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <Status session={session} disconnected={disconnected} unread={unread} />
      {route && <span className="activity-route">{route}</span>}
      {!["completed", "pending", "stopped", "waiting"].includes(phase) &&
        hintText && <span className="activity-hint">{hintText}</span>}
    </div>
  );
}
