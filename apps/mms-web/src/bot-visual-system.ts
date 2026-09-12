export type BotStatus = "idle" | "busy" | "paused" | "error";
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
