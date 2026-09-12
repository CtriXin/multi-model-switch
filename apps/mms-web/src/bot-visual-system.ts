export type BotStatus = "idle" | "busy" | "paused" | "failed" | "error";
export type TaskStatus =
  | "queued"
  | "scheduled"
  | "starting"
  | "running"
  | "waiting"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";

export const taskStatusLabels: Record<TaskStatus, string> = {
  queued: "排队中",
  scheduled: "已安排",
  starting: "正在启动",
  running: "执行中",
  waiting: "等待输入",
  completed: "已完成",
  failed: "执行失败",
  cancelled: "已取消",
  interrupted: "已中断",
};

export function waitReasonLabel(reason?: string | null) {
  if (!reason) return "";
  const normalized = reason.toLowerCase();
  if (normalized.includes("approval") || normalized.includes("confirm")) {
    return "等待你在会话中确认";
  }
  if (normalized.includes("connection") || normalized.includes("connect")) {
    return "等待模型服务恢复连接";
  }
  if (normalized.includes("stopping") || normalized.includes("stop")) {
    return "正在停止，稍后刷新状态";
  }
  if (normalized.includes("schedule") || normalized.includes("runat")) {
    return "已安排在指定时间运行";
  }
  if (normalized.includes("input") || normalized.includes("user")) {
    return "等待你补充信息";
  }
  if (normalized === "manual") {
    return "等待你手动唤醒";
  }
  return reason;
}

export function getStatusBadgeText(status: BotStatus | TaskStatus): string {
  if (status === "busy" || status === "running") return "执行中";
  if (status === "starting") return "正在启动";
  if (status === "idle") return "待命";
  if (status === "paused") return "已暂停";
  if (status === "waiting") return "等待你";
  if (status === "queued" || status === "scheduled") return "已排队";
  return taskStatusLabels[status as TaskStatus] || status;
}

export function resolveAvatarColor(avatarColor?: string): string {
  if (!avatarColor) return "var(--bot-avatar-1)";
  const colorMap: Record<string, string> = {
    "#b9a5ff": "var(--bot-avatar-1)",
    "#ff9f91": "var(--bot-avatar-2)",
    "#73dfc7": "var(--bot-avatar-3)",
    "#ffd77d": "var(--bot-avatar-4)",
    "#8bb8ff": "var(--bot-avatar-5)",
    "#f18bd5": "var(--bot-avatar-6)",
  };
  return colorMap[avatarColor] || avatarColor;
}

export function formatScheduledTaskTime(value?: string | null, referenceNow?: Date): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  const pad = (part: number) => String(part).padStart(2, "0");
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());
  const timeStr = `${hours}:${minutes}`;

  const now = referenceNow || new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const targetDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round((targetDay.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return `今天 ${timeStr}`;
  }
  if (diffDays === 1) {
    return `明天 ${timeStr}`;
  }
  if (diffDays === 2) {
    return `后天 ${timeStr}`;
  }
  return `${date.getMonth() + 1}月${date.getDate()}日 ${timeStr}`;
}

export interface BotSummaryTask {
  id?: string;
  botId: string;
  prompt: string;
  status?: TaskStatus | string;
  waitReason?: string | null;
  runAt?: string | null;
  updatedAt?: string;
  createdAt?: string;
  outcome?: { summary?: string | null } | null;
  result?: string | null;
}

export interface BotSummaryBot {
  id: string;
  status: BotStatus;
  description?: string;
}

export function getBotSecondLine(
  bot: BotSummaryBot,
  task?: BotSummaryTask,
  allTasks?: BotSummaryTask[],
  referenceNow?: Date,
): string | null {
  const botTasks = allTasks?.filter((t) => t.botId === bot.id) || (task ? [task] : []);

  // 1. 活跃运行任务一句话
  const runningTask = botTasks.find((t) => t.status === "running" || t.status === "starting")
    || (task && (task.status === "running" || task.status === "starting") ? task : undefined);
  if (runningTask?.prompt?.trim()) {
    return runningTask.prompt.trim();
  }

  // 2. waitReason
  const waitingTask = botTasks.find((t) => Boolean(t.waitReason) || t.status === "waiting")
    || (task && (Boolean(task.waitReason) || task.status === "waiting") ? task : undefined);
  if (waitingTask?.waitReason?.trim()) {
    return waitReasonLabel(waitingTask.waitReason) || waitingTask.waitReason.trim();
  }

  // 3. 下次定时（"明天 09:00 · 任务前 12 字"）
  const scheduledTask = botTasks.find((t) => t.status === "scheduled" || Boolean(t.runAt))
    || (task && (task.status === "scheduled" || Boolean(task.runAt)) ? task : undefined);
  if (scheduledTask?.runAt) {
    const timeLabel = formatScheduledTaskTime(scheduledTask.runAt, referenceNow);
    const snippet = (scheduledTask.prompt || "").trim().slice(0, 12);
    return snippet ? `${timeLabel} · ${snippet}` : timeLabel;
  }

  // 4. 上次 outcome.summary
  const finishedTasks = botTasks
    .filter((t) => Boolean(t.outcome?.summary?.trim()))
    .sort((a, b) => (b.updatedAt || b.createdAt || "").localeCompare(a.updatedAt || a.createdAt || ""));
  if (finishedTasks.length > 0 && finishedTasks[0].outcome?.summary?.trim()) {
    return finishedTasks[0].outcome.summary.trim();
  }
  if (task?.outcome?.summary?.trim()) {
    return task.outcome.summary.trim();
  }

  // 5. description
  if (bot.description?.trim()) {
    return bot.description.trim();
  }

  // 6. 如果没有则不渲染第二行，单行垂直居中。禁止 "MMS Bot" 占位。
  return null;
}

export function getIndicatorStatus(
  bot: BotSummaryBot,
  task?: BotSummaryTask,
  allTasks?: BotSummaryTask[],
): "running" | "waiting" | "failed" | "idle" {
  const botTasks = allTasks?.filter((t) => t.botId === bot.id) || (task ? [task] : []);
  const runningTask = botTasks.find((t) => t.status === "running" || t.status === "starting")
    || (task && (task.status === "running" || task.status === "starting") ? task : undefined);
  if (bot.status === "busy" || runningTask) {
    return "running";
  }

  const waitingTask = botTasks.find((t) => Boolean(t.waitReason) || t.status === "waiting")
    || (task && (Boolean(task.waitReason) || task.status === "waiting") ? task : undefined);
  if (bot.status === "paused" || waitingTask) {
    return "waiting";
  }

  const failedTask = botTasks.find((t) => t.status === "failed") || (task?.status === "failed" ? task : undefined);
  if (bot.status === "failed" || failedTask) {
    return "failed";
  }

  return "idle";
}

