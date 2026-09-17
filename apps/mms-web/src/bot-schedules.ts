/** Schedule rule helpers and run-state labels for the Bot 定时 UI. */

export const MIN_INTERVAL_SECONDS = 300;
export const MAX_SCHEDULES_PER_BOT = 20;
export const MAX_PROMPT_CHARS = 32000;
export const WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"] as const;
export const INTERVAL_HOUR_PRESETS = [1, 3, 6, 12] as const;

export type ScheduleKind = "once" | "interval" | "daily" | "weekly";
export type OverlapPolicy = "skip" | "queue";
export type SkipReason = "paused" | "busy" | "missed" | "error" | "invalid";

export type ScheduleRule =
  | { kind: "once"; at: string }
  | { kind: "interval"; everySeconds: number }
  | { kind: "daily"; atLocalTime: string }
  | { kind: "weekly"; weekday: number; atLocalTime: string };

export interface ScheduleLastSkip {
  at?: string;
  reason: SkipReason | string;
  skipped?: number;
}

export interface BotSchedule {
  id: string;
  botId: string;
  prompt: string;
  rule: ScheduleRule;
  timezone: string;
  enabled: boolean;
  overlapPolicy: OverlapPolicy | string;
  nextRunAt: string | null;
  lastRunAt: string | null;
  lastTaskId: string | null;
  recentTaskIds?: string[];
  lastSkip: ScheduleLastSkip | null;
  createdBy?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ComposerScheduleForm {
  kind: ScheduleKind;
  onceDate: string;
  onceTime: string;
  atLocalTime: string;
  weekday: number;
  intervalHours: number;
}

export type ScheduleRunKind =
  | "upcoming"
  | "held"
  | "completed"
  | "invalid"
  | "error"
  | "disabled"
  | "gated"
  | "unknown";

export interface ScheduleRunState {
  kind: ScheduleRunKind;
  holdReason?: "paused" | "busy";
  label: string;
  detail: string;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function defaultComposerForm(now: Date = new Date()): ComposerScheduleForm {
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  return {
    kind: "once",
    onceDate: `${tomorrow.getFullYear()}-${pad(tomorrow.getMonth() + 1)}-${pad(tomorrow.getDate())}`,
    onceTime: "09:00",
    atLocalTime: "09:00",
    weekday: 0,
    intervalHours: 3,
  };
}

export function intervalSecondsFromHours(hours: number): number {
  return Math.round(Number(hours) * 3600);
}

export function localTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function padTime(value: string): string {
  const match = String(value || "").trim().match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return "";
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) return "";
  return `${pad(hours)}:${pad(minutes)}`;
}

export function onceLocalToIso(date: string, time: string): string {
  const clock = padTime(time) || "09:00";
  const local = new Date(`${date}T${clock}:00`);
  if (Number.isNaN(local.valueOf())) {
    throw new Error("时间无效");
  }
  return local.toISOString();
}

export function composerRuleFromForm(form: ComposerScheduleForm): ScheduleRule {
  if (form.kind === "once") {
    return { kind: "once", at: onceLocalToIso(form.onceDate, form.onceTime) };
  }
  if (form.kind === "daily") {
    const atLocalTime = padTime(form.atLocalTime);
    if (!atLocalTime) throw new Error("时间无效");
    return { kind: "daily", atLocalTime };
  }
  if (form.kind === "weekly") {
    const atLocalTime = padTime(form.atLocalTime);
    if (!atLocalTime) throw new Error("时间无效");
    const weekday = Number(form.weekday);
    if (!Number.isInteger(weekday) || weekday < 0 || weekday > 6) {
      throw new Error("星期无效");
    }
    return { kind: "weekly", weekday, atLocalTime };
  }
  return {
    kind: "interval",
    everySeconds: intervalSecondsFromHours(form.intervalHours),
  };
}

export function validateComposerForm(form: ComposerScheduleForm): string | null {
  if (form.kind === "interval") {
    const seconds = intervalSecondsFromHours(form.intervalHours);
    if (!Number.isFinite(seconds) || seconds <= 0) return "请填写间隔小时数";
    if (seconds < MIN_INTERVAL_SECONDS) {
      return "定时间隔最短 5 分钟。太频繁会持续消耗模型额度。";
    }
    return null;
  }
  if (form.kind === "once") {
    if (!form.onceDate) return "请选择日期";
    if (!padTime(form.onceTime)) return "请填写 HH:MM 时间";
    try {
      onceLocalToIso(form.onceDate, form.onceTime);
    } catch {
      return "时间无效";
    }
    return null;
  }
  if (!padTime(form.atLocalTime)) return "请填写 HH:MM 时间";
  if (form.kind === "weekly") {
    const weekday = Number(form.weekday);
    if (!Number.isInteger(weekday) || weekday < 0 || weekday > 6) return "请选择星期";
  }
  return null;
}

export function describeInterval(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "周期间隔";
  if (seconds % 3600 === 0) {
    const hours = seconds / 3600;
    return `每 ${hours} 小时`;
  }
  if (seconds % 60 === 0) {
    const minutes = seconds / 60;
    return `每 ${minutes} 分钟`;
  }
  return `每 ${seconds} 秒`;
}

export function describeRule(rule?: ScheduleRule | null): string {
  if (!rule) return "";
  if (rule.kind === "once") {
    const date = new Date(rule.at);
    if (Number.isNaN(date.valueOf())) return "一次";
    return `一次 ${date.getMonth() + 1}月${date.getDate()}日 ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }
  if (rule.kind === "daily") return `每天 ${rule.atLocalTime}`;
  if (rule.kind === "weekly") {
    const label = WEEKDAY_LABELS[rule.weekday] || `周${rule.weekday}`;
    return `每周${label} ${rule.atLocalTime}`;
  }
  if (rule.kind === "interval") return describeInterval(rule.everySeconds);
  return "";
}

export function formFromRule(rule: ScheduleRule, now: Date = new Date()): ComposerScheduleForm {
  const form = defaultComposerForm(now);
  form.kind = rule.kind;
  if (rule.kind === "once") {
    const date = new Date(rule.at);
    if (!Number.isNaN(date.valueOf())) {
      form.onceDate = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
      form.onceTime = `${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }
    return form;
  }
  if (rule.kind === "daily") {
    form.atLocalTime = rule.atLocalTime;
    return form;
  }
  if (rule.kind === "weekly") {
    form.weekday = rule.weekday;
    form.atLocalTime = rule.atLocalTime;
    return form;
  }
  form.intervalHours = rule.everySeconds / 3600;
  return form;
}

export function describeComposerChip(form: ComposerScheduleForm): string {
  if (form.kind === "once") {
    if (!form.onceDate || !padTime(form.onceTime)) return "";
    return `${form.onceDate} ${padTime(form.onceTime)}`;
  }
  try {
    return describeRule(composerRuleFromForm(form));
  } catch {
    return "";
  }
}

function holdDetail(reason: string | undefined): string {
  return reason === "busy"
    ? "到点时上一轮还在跑，恢复后会补跑。"
    : "到点时被暂停或总闸拦住，恢复后会补跑。";
}

export function scheduleRunState(
  schedule: BotSchedule,
  now: Date = new Date(),
  options: { wakeEnabled?: boolean } = {},
): ScheduleRunState {
  const skip = schedule.lastSkip;
  const next = schedule.nextRunAt;
  const nextMs = next ? Date.parse(next) : Number.NaN;
  const hasNext = Number.isFinite(nextMs);
  const past = hasNext && nextMs <= now.getTime();
  const future = hasNext && nextMs > now.getTime();
  const holdSkip = skip?.reason === "paused" || skip?.reason === "busy";

  if (next == null && schedule.enabled === false && skip?.reason === "invalid") {
    return {
      kind: "invalid",
      label: "记录损坏",
      detail: "这条定时读不出来，改规则或时区后再启用。",
    };
  }
  if (next == null && schedule.lastRunAt) {
    return {
      kind: "completed",
      label: "已执行完",
      detail: "这一次已经跑过，不会再触发。",
    };
  }
  // Repeating rules keep a future nextRunAt while paused. That must not read as 待触发.
  if (!schedule.enabled) {
    if (holdSkip && schedule.lastRunAt == null) {
      return {
        kind: "disabled",
        holdReason: skip?.reason as "paused" | "busy",
        label: "已暂停",
        detail: holdDetail(skip?.reason),
      };
    }
    return {
      kind: "disabled",
      label: "已暂停",
      detail: "这条定时不会触发；恢复后按下次时间跑。",
    };
  }
  if (past && holdSkip && schedule.lastRunAt == null) {
    return {
      kind: "held",
      holdReason: skip?.reason as "paused" | "busy",
      label: "已到点但被挂起",
      detail: holdDetail(skip?.reason),
    };
  }
  if (skip?.reason === "error") {
    return {
      kind: "error",
      label: "上次没能建出任务",
      detail: "到点会再试，不是已经执行完。",
    };
  }
  if (options.wakeEnabled === false) {
    return {
      kind: "gated",
      label: "被总闸拦住",
      detail: "被自动唤醒总闸拦住",
    };
  }
  if (future) {
    return { kind: "upcoming", label: "待触发", detail: "" };
  }
  if (past) {
    return {
      kind: "upcoming",
      label: "待触发",
      detail: "已到点，正在等下一轮调度，不是卡住。",
    };
  }
  return { kind: "unknown", label: "", detail: "" };
}

export function skipNote(schedule: BotSchedule, now: Date = new Date()): string {
  const skip = schedule.lastSkip;
  if (!skip) return "";
  if (skip.reason === "missed") {
    const skipped = Number(skip.skipped) || 0;
    return skipped > 0
      ? `错过 ${skipped} 次（进程没开着，不补跑）`
      : "错过了周期（不补跑）";
  }
  if (skip.reason === "busy") {
    const nextMs = schedule.nextRunAt ? Date.parse(schedule.nextRunAt) : Number.NaN;
    if (Number.isFinite(nextMs) && nextMs > now.getTime()) {
      return "上一轮还在跑，已跳到下一次";
    }
  }
  return "";
}

export function overlapPolicyLabel(policy?: string): string {
  return policy === "queue" ? "排队执行" : "上一轮在跑就跳过";
}

export function remainingScheduleQuota(count: number): string {
  const total = Math.max(0, count);
  const left = Math.max(0, MAX_SCHEDULES_PER_BOT - total);
  if (total >= MAX_SCHEDULES_PER_BOT) {
    return `一个 Bot 最多 20 条定时，先删掉不用的再加（当前 ${total}/20）`;
  }
  if (total >= 19) {
    return `还能再加 ${left} 条（${total}/20）`;
  }
  return "";
}

export function apiErrorCode(cause: unknown): string | undefined {
  if (cause && typeof cause === "object" && "code" in cause) {
    const code = (cause as { code?: unknown }).code;
    return typeof code === "string" ? code : undefined;
  }
  return undefined;
}

export function scheduleErrorMessage(
  code: string | undefined,
  fallback: string,
  count?: number,
): string {
  if (code === "SCHEDULE_LIMIT") {
    return remainingScheduleQuota(count ?? MAX_SCHEDULES_PER_BOT);
  }
  if (code === "SCHEDULE_INTERVAL_TOO_SHORT") {
    return "定时间隔最短 5 分钟。太频繁会持续消耗模型额度。";
  }
  return fallback;
}

export function nextEnabledSchedule(schedules: BotSchedule[]): BotSchedule | null {
  const enabled = schedules.filter((item) => item.enabled && item.nextRunAt);
  if (!enabled.length) return null;
  return enabled
    .slice()
    .sort((left, right) => String(left.nextRunAt).localeCompare(String(right.nextRunAt)))[0];
}

export function isScheduleCreateResult(value: unknown): value is BotSchedule & { kind?: string } {
  if (!value || typeof value !== "object") return false;
  const row = value as { kind?: unknown; id?: unknown };
  if (row.kind === "schedule") return true;
  return typeof row.id === "string" && row.id.startsWith("sch_");
}

export function createdScheduleNotice(
  schedule: BotSchedule,
  formatNext: (value?: string | null) => string,
  now: Date = new Date(),
): string {
  const next = schedule.nextRunAt;
  const nextMs = next ? Date.parse(next) : Number.NaN;
  if (schedule.rule?.kind === "once" && Number.isFinite(nextMs) && nextMs <= now.getTime()) {
    return "已设定，时间已过，Pilot 开着时会马上补跑一次。";
  }
  const when = formatNext(next);
  return when ? `已设定，下次 ${when}` : "已设定定时。";
}

export function nextEvening(now: Date): { date: Date; label: string } {
  const date = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 20, 0, 0, 0);
  const tomorrow = date.getTime() <= now.getTime();
  if (tomorrow) date.setDate(date.getDate() + 1);
  return { date, label: `${tomorrow ? "明晚" : "今晚"} 20:00` };
}
