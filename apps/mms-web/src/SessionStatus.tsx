import type { Session } from "./types";
import {
  Check,
  CircleAlert,
  Pause,
  CircleHelp,
  WifiOff,
  LoaderCircle,
  Wrench,
} from "lucide-react";

export function sessionStatus(session: Session, disconnected = false) {
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
          (session.state === "idle" ? "completed" : session.state);
  const labels: Record<string, string> = {
    idle: "准备就绪",
    running: "执行中",
    thinking: "思考中",
    responding: "正在输出",
    tool: "执行工具",
    waiting: session.activity?.method === "confirm" ? "等待确认" : "等待你回答",
    compacting: "压缩上下文",
    retrying: "正在重试",
    completed: "本轮已完成",
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

export function Status({
  session,
  compact = false,
  disconnected = false,
}: {
  session: Session;
  compact?: boolean;
  disconnected?: boolean;
}) {
  const { phase, detail } = sessionStatus(session, disconnected);
  const Icon =
    (
      {
        completed: Check,
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

export function CurrentActivity({
  session,
  disconnected,
}: {
  session: Session;
  disconnected: boolean;
}) {
  const { phase } = sessionStatus(session, disconnected);
  const hints: Record<string, string> = {
    idle: "随时发送消息，继续这项工作",
    running: "正在等待模型或执行流程返回",
    thinking: "收到模型的思考内容",
    responding: "回复正在逐步生成",
    tool: "可以展开上方工具记录查看输出",
    waiting: "请在上方问题卡片中回答",
    compacting: "正在整理会话上下文",
    retrying: "执行工具正在自动重试",
    completed: "可以继续提问，或查看本轮成果",
    closed: "可从历史继续这项工作",
    stopped: "本轮已停止",
    error: "查看上方错误详情后再继续",
    disconnected: "连接恢复后更新；保留最近内容",
  };
  return (
    <div
      className={`current-activity ${phase}`}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <Status session={session} disconnected={disconnected} />
      <span className="activity-hint">{hints[phase]}</span>
    </div>
  );
}
