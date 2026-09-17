import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, FormEvent, ReactNode } from "react";
import { RichText } from "./components";
import { formatDate, formatCompactTime, kindLabel } from "./BotCommunications";
import type { BotCommunication } from "./BotCommunications";
import { BotArtifactPreview } from "./BotArtifactPreview";
import {
  ArrowLeft,
  AlarmClockCheck,
  Bot as BotIcon,
  Brain,
  Camera,
  Check,
  ChevronDown,
  Calendar,
  CircleAlert,
  Clock3,
  FileText,
  LoaderCircle,
  MessageSquare,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Send,
  Settings2,
  Square,
  Timer,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { BotPlan } from "./BotPlan";
import { previewType } from "./bot-artifact-preview";
import type { BotChildResult, BotPendingQuestion, BotTaskPlan, Model, Preset } from "./types";
import { isPreview, mutate, request } from "./api";
import { BotPresetPanel } from "./BotPresetPanel";
import { BotSchedulePanel } from "./BotSchedulePanel";
import {
  INTERVAL_HOUR_PRESETS,
  MAX_SCHEDULES_PER_BOT,
  WEEKDAY_LABELS,
  apiErrorCode,
  composerRuleFromForm,
  createdScheduleNotice,
  defaultComposerForm,
  describeComposerChip,
  describeRule,
  intervalSecondsFromHours,
  localTimezone,
  onceLocalToIso,
  remainingScheduleQuota,
  scheduleErrorMessage,
  validateComposerForm,
  type BotSchedule,
  type ComposerScheduleForm,
} from "./bot-schedules";
import {
  suggestBotName,
  looksLikeStandingInstruction,
  parsePreset,
  buildPreset,
  runWizard,
  getPresetSummary,
  WIZARD_POOL,
  SKIPPED_WIZARD_PROMPT,
  parseMessageOptions,
} from "./bot-presets";
import type {
  OnboardingAnswers,
  ParsedPreset,
  WizardAnswerEntry,
  WizardQuestion,
} from "./bot-presets";
import "./bot.css";

export type BotStatus = "idle" | "busy" | "paused";
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
export interface BotDefinition {
  id: string;
  name: string;
  description: string;
  systemPrompt: string;
  presetId: string | null;
  workspaceId: string | null;
  status: BotStatus;
  wakeEnabled: boolean;
  sessionId?: string | null;
  modelName?: string;
  memoryEnabled?: boolean;
  memoryBudgetTokens?: number;
  autoCompact?: boolean;
  compactAtPercent?: number;
  avatarId?: string;
  avatarColor?: string;
  pendingQuestion?: BotPendingQuestion | null;
}
export interface BotTask {
  id: string;
  botId: string;
  prompt: string;
  status: TaskStatus;
  result?: string | null;
  error?: string | null;
  waitReason?: string | null;
  runAt?: string | null;
  sessionId?: string | null;
  parentTaskId?: string | null;
  priority?: number;
  queueReason?: string | null;
  coordinatorPlan?: BotTaskPlan | null;
  planExecutedAt?: string | null;
  planDecidedAt?: string | null;
  originMessageId?: string | null;
  senderBotId?: string | null;
  acceptedAt?: string | null;
  scheduleId?: string | null;
  createdAt: string;
  updatedAt: string;
  outcome?: BotOutcome | null;
  childResults?: BotChildResult[];
  waitQuestion?: string;
  waitOptions?: string[];
  waitSince?: string;
  waitDismissed?: boolean;
  waitAnsweredAt?: string;
}
export interface BotOutcome {
  summary: string;
  evidence?: string | null;
  changes?: string | null;
  pending?: string | null;
  next?: string | null;
  raw?: string;
}
export interface BotEvent {
  id: string;
  taskId?: string;
  senderBotId?: string | null;
  sourceKind?: "assistant" | "tool" | "notice" | "approval" | "error" | "wait" | string;
  type: "instruction" | "message" | "progress" | "approval" | "wait" | "result" | "error" | "handoff" | "system";
  content: string;
  createdAt: string;
  scheduleId?: string | null;
}
export interface BotArtifact {
  id: string;
  taskId?: string;
  name: string;
  kind: "screenshot" | "file";
  mimeType?: string | null;
  url: string;
  sha256?: string | null;
}
export interface BotDispatchPayload {
  botId: string;
  prompt: string;
  runAt?: string;
  wake: boolean;
  parentTaskId?: string;
}
export interface BotDispatchResult {
  task?: BotTask;
  schedule?: BotSchedule;
  kind?: "task" | "schedule";
  message?: string;
}
export type { BotSchedule };
export type BotAction = (
  payload: BotDispatchPayload,
) => Promise<BotDispatchResult | void> | BotDispatchResult | void;

export interface BotAvatarShapeDef {
  path: string;
  faceY: number;
  eyeDx?: number;
  eyeRadius?: number;
  blushDx?: number;
  mouth?: "default" | "cat";
  wink?: boolean;
  extra?: { d: string; fill: string };
}

export const ORGANIC_SMILE_AVATARS: Record<string, BotAvatarShapeDef> = {
  round: {
    path: "M 16 3 C 23.18 3 29 8.82 29 16 C 29 23.18 23.18 29 16 29 C 8.82 29 3 23.18 3 16 C 3 8.82 8.82 3 16 3 Z",
    faceY: 16.2,
    eyeDx: 5.2,
    eyeRadius: 1.25,
    blushDx: 8.0,
  },
  cat: {
    path: "M 16 5.5 C 18.5 5.5 20.2 4.2 21.8 3.2 C 23.2 2.3 24.8 2.5 25.5 4.0 C 26.2 5.5 25.8 7.5 25.2 9.5 C 27.8 11.8 29.0 14.5 29.0 17.5 C 29.0 23.8 23.2 29.0 16.0 29.0 C 8.8 29.0 3.0 23.8 3.0 17.5 C 3.0 14.5 4.2 11.8 6.8 9.5 C 6.2 7.5 5.8 5.5 6.5 4.0 C 7.2 2.5 8.8 2.3 10.2 3.2 C 11.8 4.2 13.5 5.5 16 5.5 Z",
    faceY: 17.8,
    eyeDx: 5.2,
    eyeRadius: 1.25,
    blushDx: 8.2,
    mouth: "cat",
  },
  cube: {
    path: "M 12 3.5 L 20 3.5 C 25.5 3.5 28.5 6.5 28.5 12 L 28.5 20 C 28.5 25.5 25.5 28.5 20 28.5 L 12 28.5 C 6.5 28.5 3.5 25.5 3.5 20 L 3.5 12 C 3.5 6.5 6.5 3.5 12 3.5 Z",
    faceY: 16.0,
    eyeDx: 5.2,
    eyeRadius: 1.25,
    blushDx: 8.0,
  },
  bean: {
    path: "M 11 8.5 L 21 8.5 C 25.5 8.5 29 11.8 29 16 C 29 20.2 25.5 23.5 21 23.5 L 11 23.5 C 6.5 23.5 3 20.2 3 16 C 3 11.8 6.5 8.5 11 8.5 Z",
    faceY: 16.0,
    eyeDx: 5.0,
    eyeRadius: 1.25,
    blushDx: 7.8,
  },
  rocket: {
    path: "M 16 3.8 C 18.2 3.8 19.8 5.2 21.0 7.4 L 26.8 19.8 C 28.2 22.8 26.8 27.5 23.5 27.5 L 8.5 27.5 C 5.2 27.5 3.8 22.8 5.2 19.8 L 11.0 7.4 C 12.2 5.2 13.8 3.8 16 3.8 Z",
    faceY: 18.2,
    eyeDx: 4.8,
    eyeRadius: 1.25,
    blushDx: 7.6,
    wink: true,
  },
  sprout: {
    path: "M 16 7.0 C 22.6 7.0 28.0 12.0 28.0 18.0 C 28.0 24.2 22.6 29.0 16 29.0 C 9.4 29.0 4.0 24.2 4.0 18.0 C 4.0 12.0 9.4 7.0 16 7.0 Z",
    faceY: 18.0,
    eyeDx: 5.0,
    eyeRadius: 1.25,
    blushDx: 7.8,
    extra: {
      d: "M 16 7.0 C 16 4.5 18.2 2.6 20.8 2.6 C 22.2 2.6 22.8 3.5 22.0 4.8 C 20.8 6.5 18.4 6.9 16 7.0 Z",
      fill: "#34d399",
    },
  },
  puff: {
    path: "M 8.5 26.5 C 4.5 26.5 2.0 23.5 2.0 19.5 C 2.0 16.0 4.5 13.2 8.0 12.6 C 8.5 7.2 12.8 3.0 18.0 3.0 C 23.0 3.0 27.0 6.8 27.8 11.5 C 29.8 12.2 31.5 14.2 31.5 16.8 C 31.5 19.5 29.8 21.8 27.5 22.5 C 28.0 23.5 28.0 24.8 27.2 25.6 C 26.2 26.5 24.5 26.5 22.5 26.5 Z",
    faceY: 17.5,
    eyeDx: 5.0,
    eyeRadius: 1.25,
    blushDx: 7.8,
  },
  leaf: {
    path: "M 16 3.0 C 17.0 3.0 18.2 4.8 19.3 7.0 L 26.0 17.5 C 27.8 20.2 28.2 22.0 28.2 23.5 C 28.2 27.0 22.8 29.0 16 29.0 C 9.2 29.0 3.8 27.0 3.8 23.5 C 3.8 22.0 4.2 20.2 6.0 17.5 L 12.7 7.0 C 13.8 4.8 15.0 3.0 16 3.0 Z",
    faceY: 18.2,
    eyeDx: 4.8,
    eyeRadius: 1.25,
    blushDx: 7.6,
  },
  star: {
    path: "M 16 3.5 C 17.5 3.5 19.2 8.5 21.0 10.5 C 23.2 11.0 28.5 12.0 28.5 14.2 C 28.5 16.5 24.8 19.2 23.8 21.2 C 24.5 23.5 25.5 28.5 23.5 28.5 C 21.8 28.5 18.2 25.2 16 25.2 C 13.8 25.2 10.2 28.5 8.5 28.5 C 6.5 28.5 7.5 23.5 8.2 21.2 C 7.2 19.2 3.5 16.5 3.5 14.2 C 3.5 12.0 8.8 11.0 11.0 10.5 C 12.8 8.5 14.5 3.5 16 3.5 Z",
    faceY: 16.2,
    eyeDx: 4.8,
    eyeRadius: 1.25,
    blushDx: 7.6,
  },
  ghost: {
    path: "M 16 3.5 C 22.8 3.5 27.5 8.5 27.5 15.5 L 27.5 24.5 C 27.5 26.8 25.0 27.8 23.2 26.2 C 21.2 24.5 19.5 24.5 17.5 26.2 C 15.5 27.8 13.5 27.8 11.5 26.2 C 9.5 24.5 7.8 24.5 5.8 26.2 C 4.0 27.8 1.5 26.8 1.5 24.5 L 1.5 15.5 C 1.5 8.5 6.2 3.5 16 3.5 Z",
    faceY: 15.8,
    eyeDx: 5.0,
    eyeRadius: 1.25,
    blushDx: 7.8,
  },
};

export const GROK_AVATAR_SHAPES = ORGANIC_SMILE_AVATARS;

const ORGANIC_AVATAR_ALIASES: Record<string, string> = {
  circle: "round",
  blob: "cat",
  squircle: "cube",
  capsule: "bean",
  triangle: "rocket",
  hexagon: "sprout",
  cloud: "puff",
  drop: "leaf",
  star: "star",
  ghost: "ghost",
};

export const PIXEL_AVATARS = [
  { id: "round", label: "圆圆", shape: "round" },
  { id: "cat", label: "萌猫", shape: "cat" },
  { id: "cube", label: "方糖", shape: "cube" },
  { id: "bean", label: "海豹", shape: "bean" },
  { id: "rocket", label: "饭团", shape: "rocket" },
  { id: "sprout", label: "芽宝", shape: "sprout" },
  { id: "puff", label: "朵云", shape: "puff" },
  { id: "leaf", label: "水滴", shape: "leaf" },
  { id: "star", label: "萌星", shape: "star" },
  { id: "ghost", label: "幽灵", shape: "ghost" },
] as const;

// Saved Bots from earlier builds can still refer to a removed preset. Keep
// those ids renderable, while keeping the picker focused on the softer core set.
const LEGACY_AVATAR_SHAPES: Record<string, string> = {
  round: "round",
  circle: "round",
  blob: "cat",
  cat: "cat",
  cube: "cube",
  squircle: "cube",
  bean: "bean",
  capsule: "bean",
  rocket: "rocket",
  triangle: "rocket",
  hex: "sprout",
  hexagon: "sprout",
  sprout: "sprout",
  bot: "cube",
  puff: "puff",
  cloud: "puff",
  leaf: "leaf",
  drop: "leaf",
  diamond: "cube",
  star: "star",
  ticket: "bean",
  wave: "leaf",
  shield: "sprout",
  gem: "leaf",
  orbit: "round",
  sun: "round",
  ghost: "ghost",
  oval: "bean",
};

export const PIXEL_AVATAR_COLORS = [
  "#b9a5ff",
  "#ff9f91",
  "#73dfc7",
  "#ffd77d",
  "#8bb8ff",
  "#f18bd5",
] as const;

import {
  resolveAvatarColor,
  getStatusBadgeText,
  waitReasonLabel,
  taskStatusLabels,
  formatScheduledTaskTime,
  getBotSecondLine,
  getIndicatorStatus,
} from "./bot-visual-system.ts";

export {
  resolveAvatarColor,
  getStatusBadgeText,
  waitReasonLabel,
  taskStatusLabels,
  formatScheduledTaskTime,
  getBotSecondLine,
  getIndicatorStatus,
};

export function PixelAvatar({
  avatarId,
  color,
  seed = "",
  className = "bot-avatar",
  active = false,
  selected = false,
}: {
  avatarId?: string;
  color?: string;
  seed?: string;
  className?: string;
  active?: boolean;
  selected?: boolean;
}) {
  const seedValue = [...seed].reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const selectedAvatar = PIXEL_AVATARS.find((item) => item.id === avatarId);
  const avatar = selectedAvatar || PIXEL_AVATARS[seedValue % PIXEL_AVATARS.length];
  const avatarColor = color || PIXEL_AVATAR_COLORS[seedValue % PIXEL_AVATAR_COLORS.length];
  const effectiveColor = resolveAvatarColor(avatarColor);
  const rawShape = avatar.shape || LEGACY_AVATAR_SHAPES[avatarId || ""] || "round";
  const shape = ORGANIC_AVATAR_ALIASES[rawShape] || rawShape;
  const shapeDef = ORGANIC_SMILE_AVATARS[shape] || ORGANIC_SMILE_AVATARS.round;
  const id = avatar.id;

  const fy = shapeDef.faceY;
  const edx = shapeDef.eyeDx ?? 5.0;
  const er = shapeDef.eyeRadius ?? 1.25;
  const bdx = shapeDef.blushDx ?? 7.8;
  const e1_x = 16.0 - edx;
  const e2_x = 16.0 + edx;
  const eye_y = fy - 1.2;
  const mouth_y = fy + 1.8;
  const b1_x = 16.0 - bdx;
  const b2_x = 16.0 + bdx;
  const blush_y = fy + 1.0;

  return (
    <span
      className={`${className} pixel-avatar avatar-id-${id} avatar-shape-${shape}${active ? " is-active" : ""}${selected ? " is-selected" : ""}`}
      style={{ "--pixel-color": effectiveColor } as CSSProperties}
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 32 32"
        className="bot-avatar-svg grok-avatar-svg"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d={shapeDef.path} fill="currentColor" />
        {shapeDef.extra && (
          <path d={shapeDef.extra.d} fill={shapeDef.extra.fill} />
        )}
        <circle cx={e1_x} cy={eye_y} r={er} fill="#ffffff" />
        {shapeDef.wink ? (
          <path
            d={`M ${e2_x - 1.3} ${eye_y} Q ${e2_x} ${eye_y - 1.2} ${e2_x + 1.3} ${eye_y}`}
            fill="none"
            stroke="#ffffff"
            strokeWidth="1.15"
            strokeLinecap="round"
          />
        ) : (
          <circle cx={e2_x} cy={eye_y} r={er} fill="#ffffff" />
        )}
        {shapeDef.mouth === "cat" ? (
          <path
            d={`M 13.9 ${mouth_y} Q 15.0 ${mouth_y + 1.2} 16.0 ${mouth_y} Q 17.0 ${mouth_y + 1.2} 18.1 ${mouth_y}`}
            fill="none"
            stroke="#ffffff"
            strokeWidth="1.1"
            strokeLinecap="round"
          />
        ) : (
          <path
            d={`M 14.7 ${mouth_y} Q 16.0 ${mouth_y + 1.4} 17.3 ${mouth_y}`}
            fill="none"
            stroke="#ffffff"
            strokeWidth="1.1"
            strokeLinecap="round"
          />
        )}
        <circle cx={b1_x} cy={blush_y} r={1.4} fill="rgba(255, 115, 140, 0.45)" />
        <circle cx={b2_x} cy={blush_y} r={1.4} fill="rgba(255, 115, 140, 0.45)" />
      </svg>
    </span>
  );
}

export function BotStatusBadge({
  status,
  compact = false,
  label: customLabel,
}: {
  status: BotStatus | TaskStatus;
  compact?: boolean;
  label?: string;
}) {
  const label = customLabel || getStatusBadgeText(status);
  return (
    <span
      className={`bot-state bot-state-${status}${compact ? " bot-state-compact" : ""}`}
      title={label}
    >
      <span className="bot-state-dot" aria-hidden="true" />
      {!compact && label}
    </span>
  );
}

export function getBotHeaderStatusText(
  bot: BotDefinition | null | undefined,
  tasks?: BotTask[],
): string {
  if (!bot) return "";
  if (bot.pendingQuestion) {
    return "等你回复";
  }
  const botTasks = tasks?.filter((t) => t.botId === bot.id) || [];
  const runningTask = botTasks.find(
    (t) => t.status === "running" || t.status === "starting",
  );
  if (bot.status === "busy" || runningTask) {
    return "执行中";
  }
  const waitingTask = botTasks.find(
    (t) => Boolean(t.waitReason) || t.status === "waiting",
  );
  if (bot.status === "paused" || waitingTask) {
    return "等待你";
  }
  const failedTask = botTasks.find((t) => t.status === "failed");
  if (failedTask) {
    return "执行失败";
  }
  return getStatusBadgeText(bot.status) || "待命";
}

function cleanTranscriptText(value: string) {
  return value
    .split(/\r?\n/)
    .filter((line) => !/(?:内部\s*`?(?:list|wait|status|dispatch|complete)`?|已调用内部|执行器诊断|原始 CLI|Request was aborted|待发送(?:消息|队列)|会话已通过 MMS 启动路径创建|^session$|^I'll complete thi|complete 只是流程记录|^边界：|^\*{0,2}边界\*{0,2}|^`?complete`?\s*只是流程记录|^复用原 Ego|未修改模型\/账号配置|与内部工具回执一致|^artifact id|Bot模型状态|现在有\s*\d+\s*个 bot|^已核对[:：]|^协作者[“\"]|^已向.+说|^没有产生任何文件改动|按.+要求已调用\s*wait)/i.test(line.trim()))
    .join("\n")
    .replace(/\s*（内部\s*`?(?:list|wait|status|dispatch)`?\s*实际返回）/gi, "")
    .replace(/\s*(?:复用原 Ego|artifact id)[^\n]*/gi, "")
    .replace(/\s*(?:未修改模型\/账号配置|与内部工具回执一致)[^\n]*/gi, "")
    .replace(/[^。\n]*(?:已向.+说|协作者.+打招呼)[^。\n]*(?:。|$)/gi, "")
    .trim();
}

export function BotCard({
  bot,
  selected = false,
  task,
  tasks = [],
  schedules = [],
  onSelect,
  onWake,
  onEdit,
  onDelete,
}: {
  bot: BotDefinition;
  selected?: boolean;
  task?: BotTask;
  tasks?: BotTask[];
  schedules?: BotSchedule[];
  onSelect?: (bot: BotDefinition) => void;
  onWake?: (botId: string) => void;
  onEdit?: (bot: BotDefinition) => void;
  onDelete?: (bot: BotDefinition) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function handlePointerDown(event: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }
    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  const indicatorStatus = bot.pendingQuestion
    ? "waiting"
    : getIndicatorStatus(bot, task, tasks);
  const secondLine = bot.pendingQuestion
    ? "等你回复"
    : getBotSecondLine(bot, task, tasks, undefined, schedules);

  return (
    <article className={`bot-card bot-card-${bot.status}${selected ? " is-selected" : ""}`}>
      <button
        className="bot-card-main"
        type="button"
        onClick={() => onSelect?.(bot)}
        aria-pressed={selected}
      >
        <span className="bot-card-avatar-wrap">
          <PixelAvatar avatarId={bot.avatarId} color={bot.avatarColor} seed={bot.id} />
          {indicatorStatus !== "idle" && (
            <span
              className={`bot-card-status-dot is-${indicatorStatus}`}
              aria-label={indicatorStatus}
            />
          )}
        </span>
        <span className="bot-card-copy">
          <span className="bot-card-title">
            {bot.name === "新 Bot" && !bot.systemPrompt ? (
              <strong className="bot-name-unnamed" title="未命名（去聊天区完成）">
                未命名
              </strong>
            ) : (
              <strong title={bot.name}>{bot.name}</strong>
            )}
          </span>
          {secondLine && (
            <span className="bot-card-description" title={secondLine}>
              {secondLine}
            </span>
          )}
        </span>
      </button>
      {bot.status === "paused" && onWake && (
        <button
          className="bot-icon-button"
          type="button"
          onClick={() => onWake(bot.id)}
          aria-label={`唤醒 ${bot.name}`}
          title="唤醒"
        >
          <Play size={14} />
        </button>
      )}
      {(onEdit || onDelete) && (
        <div className="bot-card-actions" ref={menuRef}>
          <button
            className="bot-card-more-button"
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              setMenuOpen((prev) => !prev);
            }}
            aria-label={`操作 ${bot.name}`}
            aria-expanded={menuOpen}
          >
            <MoreHorizontal size={15} />
          </button>
          {menuOpen && (
            <div className="bot-card-menu" role="menu">
              {onDelete && (
                <button
                  type="button"
                  className="bot-card-menu-item is-danger"
                  role="menuitem"
                  onClick={(event) => {
                    event.stopPropagation();
                    setMenuOpen(false);
                    onDelete(bot);
                  }}
                >
                  <Trash2 size={13} />
                  删除 Bot
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export function BotList({
  bots,
  tasks = [],
  schedulesByBot = {},
  selectedBotId,
  onSelect,
  onWake,
  onCreate,
  onEdit,
  onDelete,
}: {
  bots: BotDefinition[];
  tasks?: BotTask[];
  schedulesByBot?: Record<string, BotSchedule[]>;
  selectedBotId?: string;
  onSelect?: (bot: BotDefinition) => void;
  onWake?: (botId: string) => void;
  onCreate?: () => void;
  onEdit?: (bot: BotDefinition) => void;
  onDelete?: (bot: BotDefinition) => void;
}) {
  return (
    <section className="bot-list" aria-label="Bots">
      <div className="bot-section-heading">
        <h2>Bots</h2>
        {onCreate && (
          <button
            className="bot-secondary-button"
            type="button"
            onClick={onCreate}
            aria-label="创建 Bot"
            title="创建 Bot"
          >
            <Plus size={16} />
          </button>
        )}
      </div>
      <div className="bot-card-list">
        {bots.length ? (
          bots.map((bot) => (
            <BotCard
              key={bot.id}
              bot={bot}
              selected={bot.id === selectedBotId}
              task={tasks.find(
                (task) =>
                  task.botId === bot.id &&
                  [
                    "queued",
                    "scheduled",
                    "starting",
                    "running",
                    "waiting",
                  ].includes(task.status),
              )}
              tasks={tasks}
              schedules={schedulesByBot[bot.id] || []}
              onSelect={onSelect}
              onWake={onWake}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))
        ) : (
          <p className="bot-empty">
            还没有 Bot。创建一个后，就能把任务交给它在电脑上执行。
          </p>
        )}
      </div>
    </section>
  );
}

function toDateTimeValue(value?: string) {
  if (!value) return "";
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return value;
  return formatLocalDateTime(value).replace(" ", "T");
}

export function formatLocalDateTime(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function onceLocalToIsoSafe(form: ComposerScheduleForm): string {
  return onceLocalToIso(form.onceDate, form.onceTime);
}

function DispatchScheduleFields({
  form,
  onChange,
}: {
  form: ComposerScheduleForm;
  onChange: (form: ComposerScheduleForm) => void;
}) {
  const invalid = validateComposerForm(form);
  return (
    <div className="bot-dispatch-schedule-fields">
      <div className="bot-schedule-kind-tabs" role="tablist" aria-label="定时类型">
        {(
          [
            ["once", "一次"],
            ["daily", "每天"],
            ["weekly", "每周"],
            ["interval", "每 N 小时"],
          ] as const
        ).map(([kind, label]) => (
          <button
            key={kind}
            type="button"
            role="tab"
            aria-selected={form.kind === kind}
            className={`bot-schedule-kind-tab${form.kind === kind ? " is-selected" : ""}`}
            onClick={() => onChange({ ...form, kind })}
          >
            {label}
          </button>
        ))}
      </div>
      {form.kind === "once" && (
        <div className="bot-schedule-custom-row">
          <input
            type="date"
            className="bot-schedule-select"
            value={form.onceDate}
            onChange={(event) => onChange({ ...form, onceDate: event.target.value })}
            aria-label="日期"
          />
          <input
            type="text"
            className="bot-schedule-time-input"
            value={form.onceTime}
            maxLength={5}
            onChange={(event) => onChange({ ...form, onceTime: event.target.value })}
            aria-label="精确时间"
          />
        </div>
      )}
      {form.kind === "daily" && (
        <input
          type="text"
          className="bot-schedule-time-input"
          value={form.atLocalTime}
          maxLength={5}
          onChange={(event) => onChange({ ...form, atLocalTime: event.target.value })}
          aria-label="每天时间"
        />
      )}
      {form.kind === "weekly" && (
        <div className="bot-schedule-weekdays">
          {WEEKDAY_LABELS.map((label, weekday) => (
            <button
              key={label}
              type="button"
              className={`bot-schedule-kind-tab${form.weekday === weekday ? " is-selected" : ""}`}
              onClick={() => onChange({ ...form, weekday })}
            >
              {label}
            </button>
          ))}
          <input
            type="text"
            className="bot-schedule-time-input"
            value={form.atLocalTime}
            maxLength={5}
            onChange={(event) => onChange({ ...form, atLocalTime: event.target.value })}
            aria-label="每周时间"
          />
        </div>
      )}
      {form.kind === "interval" && (
        <div className="bot-schedule-interval-row">
          {INTERVAL_HOUR_PRESETS.map((hours) => (
            <button
              key={hours}
              type="button"
              className={`bot-schedule-kind-tab${form.intervalHours === hours ? " is-selected" : ""}`}
              onClick={() => onChange({ ...form, intervalHours: hours })}
            >
              {hours} 小时
            </button>
          ))}
          <input
            type="number"
            min={0.09}
            step="any"
            className="bot-schedule-select"
            value={form.intervalHours}
            onChange={(event) =>
              onChange({ ...form, intervalHours: Number(event.target.value) })
            }
            aria-label="自定义间隔小时"
          />
        </div>
      )}
      {invalid && (
        <p className="bot-schedule-hint" role="status">
          {invalid}
        </p>
      )}
    </div>
  );
}
export function DispatchForm({
  bots,
  defaultBotId,
  onDispatch,
  onAutoDispatch,
  disabled = false,
  parentTaskId,
  label = "派发任务",
}: {
  bots: BotDefinition[];
  defaultBotId?: string;
  onDispatch: BotAction;
  onAutoDispatch?: (content: string) => Promise<void>;
  disabled?: boolean;
  parentTaskId?: string;
  label?: string;
}) {
  const [botId, setBotId] = useState(defaultBotId || bots[0]?.id || "");
  const [prompt, setPrompt] = useState("");
  const [scheduleForm, setScheduleForm] = useState<ComposerScheduleForm>(() => defaultComposerForm());
  const [scheduleArmed, setScheduleArmed] = useState(false);
  const [wake, setWake] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const previousDefaultBotId = useRef(defaultBotId);
  useEffect(() => {
    const defaultChanged = previousDefaultBotId.current !== defaultBotId;
    previousDefaultBotId.current = defaultBotId;
    if (
      defaultChanged &&
      defaultBotId &&
      bots.some((bot) => bot.id === defaultBotId)
    ) {
      setBotId(defaultBotId);
    } else if (!botId || !bots.some((bot) => bot.id === botId)) {
      setBotId(bots[0]?.id || "");
    }
  }, [botId, bots, defaultBotId]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!prompt.trim() || !botId || busy || disabled) return;
    setBusy(true);
    setError("");
    try {
      if (scheduleArmed) {
        const invalid = validateComposerForm(scheduleForm);
        if (invalid) {
          setError(invalid);
          setBusy(false);
          return;
        }
        if (scheduleForm.kind === "once") {
          await onDispatch({
            botId,
            prompt: prompt.trim(),
            runAt: onceLocalToIsoSafe(scheduleForm),
            wake,
            parentTaskId,
          });
        } else {
          await mutate(`/bots/${encodeURIComponent(botId)}/schedules`, {
            prompt: prompt.trim(),
            rule: composerRuleFromForm(scheduleForm),
            timezone: localTimezone(),
            overlapPolicy: "skip",
          });
        }
      } else {
        await onDispatch({
          botId,
          prompt: prompt.trim(),
          wake,
          parentTaskId,
        });
      }
      setPrompt("");
      setScheduleArmed(false);
      setScheduleForm(defaultComposerForm());
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "任务未能派发，请稍后重试。",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="bot-dispatch" onSubmit={submit} aria-label={label}>
      <div className="bot-section-heading">
        <h2>{label}</h2>
        <Send size={17} className="bot-heading-icon" />
      </div>
      <label className="bot-field">
        <span>交给</span>
        <select
          value={botId}
          onChange={(event) => setBotId(event.target.value)}
          disabled={disabled || busy || !bots.length}
          aria-label="选择 Bot"
        >
          {bots.map((bot) => (
            <option key={bot.id} value={bot.id}>
              {bot.name}
              {bot.modelName ? ` · ${bot.modelName}` : ""}
            </option>
          ))}
        </select>
      </label>
      <label className="bot-field">
        <span>任务内容</span>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="描述目标，Bot 会执行并回传结果…"
          rows={4}
          disabled={disabled || busy}
          required
        />
      </label>
      <fieldset className="bot-field bot-dispatch-schedule" disabled={disabled || busy}>
        <legend>
          定时
          <small>{scheduleArmed ? describeComposerChip(scheduleForm) || "已选择" : "留空立即执行"}</small>
        </legend>
        <label className="bot-check">
          <input
            type="checkbox"
            checked={scheduleArmed}
            onChange={(event) => setScheduleArmed(event.target.checked)}
          />
          <span>按周期执行</span>
        </label>
        {scheduleArmed && (
          <DispatchScheduleFields form={scheduleForm} onChange={setScheduleForm} />
        )}
      </fieldset>
      <div className="bot-dispatch-footer">
        <label className="bot-check">
          <input
            type="checkbox"
            checked={wake}
            onChange={(event) => setWake(event.target.checked)}
            disabled={disabled || busy}
          />
          <span>
            <Zap size={13} />
            需要时自动唤醒
          </span>
        </label>
        <button
          className="bot-primary-button"
          type="submit"
          disabled={disabled || busy || !prompt.trim() || !botId}
        >
          {busy ? (
            <>
              <LoaderCircle className="bot-spin" size={15} />
              派发中…
            </>
          ) : (
            <>
              <Send size={15} />
              派发
            </>
          )}
        </button>
      </div>
      {error && (
        <p className="bot-inline-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

export function TaskList({
  tasks,
  bots,
  selectedTaskId,
  onRetry,
  onSelect,
}: {
  tasks: BotTask[];
  bots: BotDefinition[];
  selectedTaskId?: string;
  onRetry?: (task: BotTask) => void;
  onSelect?: (task: BotTask) => void;
}) {
  const sorted = [...tasks].sort((a, b) =>
    b.updatedAt.localeCompare(a.updatedAt),
  );
  return (
    <section className="bot-task-list" aria-label="任务状态">
      <div className="bot-section-heading">
        <h2>任务状态</h2>
        <span className="bot-count">{tasks.length}</span>
      </div>
      {sorted.length ? (
        <div className="bot-task-items">
          {sorted.map((task) => (
            <button
              type="button"
              className={`bot-task-row${task.id === selectedTaskId ? " is-selected" : ""}`}
              key={task.id}
              onClick={() => onSelect?.(task)}
            >
              <span className="bot-task-icon">
                <BotIcon size={16} />
              </span>
              <span className="bot-task-copy">
                <strong>{task.prompt}</strong>
                <small>
                  {bots.find((bot) => bot.id === task.botId)?.name ||
                    task.botId}
                  {task.scheduleId
                    ? " · 由定时触发"
                    : task.queueReason && task.status === "queued"
                      ? ` · ${task.queueReason}`
                      : ""}
                </small>
              </span>
              <span className="bot-task-actions">
                <BotStatusBadge status={task.status} />
                {(task.status === "failed" || task.status === "interrupted") &&
                  onRetry && (
                    <span
                      role="button"
                      tabIndex={0}
                      className="bot-retry"
                      onClick={(event) => {
                        event.stopPropagation();
                        onRetry(task);
                      }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.stopPropagation();
                          onRetry(task);
                        }
                      }}
                      title="用原任务重试"
                    >
                      <RotateCcw size={14} />
                    </span>
                  )}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="bot-empty">派发任务后，运行状态和结果会出现在这里。</p>
      )}
    </section>
  );
}

export function EventFeed({
  events,
  bots,
  limit = 8,
}: {
  events: BotEvent[];
  bots?: BotDefinition[];
  limit?: number;
}) {
  return (
    <section className="bot-event-feed" aria-label="执行反馈">
      <div className="bot-section-heading">
        <h2>执行反馈</h2>
        <span className="bot-feed-note">自动刷新</span>
      </div>
      {events.length ? (
        <div className="bot-events">
          {events
            .slice(-limit)
            .reverse()
            .map((event) => (
              <div
                className={`bot-event bot-event-${event.type}`}
                key={event.id}
              >
                <span className="bot-event-mark">
                  {event.type === "result" ? (
                    <Check size={13} />
                  ) : event.type === "error" ? (
                    <CircleAlert size={13} />
                  ) : event.type === "progress" ? (
                    <LoaderCircle size={13} />
                  ) : (
                    <MessageSquare size={13} />
                  )}
                </span>
                <div>
                  <div className="bot-event-meta">
                    <strong>
                      {bots?.find((bot) => bot.id === event.senderBotId)
                        ?.name || "Bot"}
                    </strong>
                    <time dateTime={event.createdAt}>
                      {new Date(event.createdAt).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </time>
                  </div>
                  {event.content.length > 520 ? (
                    <details className="bot-chat-event-details">
                      <summary>{event.content.slice(0, 180).replace(/\s+/g, " ")}… 查看执行详情</summary>
                      <p>{event.content}</p>
                    </details>
                  ) : (
                    <p>{event.content}</p>
                  )}
                </div>
              </div>
            ))}
        </div>
      ) : (
        <p className="bot-empty">
          Bot 开始工作后，工具调用、等待和结果会显示在这里。
        </p>
      )}
    </section>
  );
}

function isImageArtifact(artifact: BotArtifact) {
  return artifact.kind === "screenshot" || Boolean(artifact.mimeType?.startsWith("image/"));
}

function canPreviewArtifact(artifact: BotArtifact) {
  return previewType(artifact).kind !== "unsupported";
}

function parseBotSettingCommand(content: string, presets: Preset[]) {
  const name = content.match(/(?:把|将)?(?:我的)?(?:bot\s*)?(?:名字|名称)(?:改成|改为|叫|设为)\s*[“「\"]?(.+?)[”」\"]?$/i)
    || content.match(/^(?:你|bot)?(?:以后)?叫\s*[“「\"]?(.+?)[”」\"]?$/i);
  if (name?.[1]?.trim()) return { patch: { name: name[1].trim() }, message: `好，之后我就叫「${name[1].trim()}」。` };
  const model = content.match(/(?:把|将)?(?:默认)?模型(?:改成|改为|换成|用|设为)\s*[“「\"]?(.+?)[”」\"]?$/i)
    || content.match(/^(?:切换(?:到)?|换(?:成)?|用)\s*([a-z][a-z0-9._ -]*\d[a-z0-9._ -]*?)(?:吧|模型)?[。！!]?$/i);
  if (model?.[1]?.trim()) {
    const query = model[1].trim().replace(/[吧。！!]+$/, "").toLowerCase().replace(/[\s._:/-]+/g, "");
    const preset = presets.find((item) => item.harness === "pi" && item.available && [item.id, item.name, item.modelId, item.channel]
      .some((value) => value.toLowerCase().replace(/[\s._:/-]+/g, "").includes(query)));
    if (!preset) return { patch: null, message: `我没找到「${model[1].trim()}」这个可用模型，你可以说得更具体一点。` };
    return { patch: { presetId: preset.id }, message: `好，默认模型切换为 ${preset.name} · ${preset.channel}。` };
  }
  return null;
}

export function ArtifactGallery({ artifacts }: { artifacts: BotArtifact[] }) {
  const [previewArtifact, setPreviewArtifact] = useState<BotArtifact | null>(null);
  return (
    <>
      <section className="bot-artifacts" aria-label="成果与截图">
        <div className="bot-section-heading">
          <h2>成果与截图</h2>
          <span className="bot-count">{artifacts.length}</span>
        </div>
        {artifacts.length ? (
          <div className="bot-artifact-grid">
            {artifacts.map((artifact) =>
              isImageArtifact(artifact) ? (
                <button
                  className="bot-artifact bot-artifact-image bot-image-preview-trigger"
                  key={artifact.id}
                  type="button"
                  onClick={() => setPreviewArtifact(artifact)}
                  aria-label={`预览 ${artifact.name}`}
                >
                  <img src={artifact.url} alt={artifact.name} />
                  <span>
                    <Camera size={13} />
                    {artifact.name}
                  </span>
                </button>
              ) : canPreviewArtifact(artifact) ? (
                <button
                  className="bot-artifact bot-artifact-file bot-artifact-file-preview-trigger"
                  key={artifact.id}
                  type="button"
                  onClick={() => setPreviewArtifact(artifact)}
                  aria-label={`预览 ${artifact.name}`}
                >
                  <span className="bot-file-icon"><FileText size={18} /></span>
                  <span>
                    <strong>{artifact.name}</strong>
                    <small>点击预览</small>
                  </span>
                </button>
              ) : (
                <a
                  className="bot-artifact bot-artifact-file"
                  key={artifact.id}
                  href={artifact.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className="bot-file-icon"><FileText size={18} /></span>
                  <span>
                    <strong>{artifact.name}</strong>
                    <small>
                      {artifact.sha256
                        ? `SHA256 ${artifact.sha256.slice(0, 12)}`
                        : "Bot 返回的文件"}
                    </small>
                  </span>
                </a>
              ),
            )}
          </div>
        ) : (
          <p className="bot-empty">截图和文件成果会在任务完成后出现在这里。</p>
        )}
      </section>
      {previewArtifact && <BotArtifactPreview artifact={previewArtifact} onClose={() => setPreviewArtifact(null)} />}
    </>
  );
}

export function AutoWakeControl({
  enabled,
  onChange,
  disabled = false,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="bot-auto-wake-control">
      <input
        type="checkbox"
        role="switch"
        checked={enabled}
        onChange={(event) => onChange(event.target.checked)}
        disabled={disabled}
      />
      <span>
        <strong>自动唤醒</strong>
        <small>
          {enabled ? "这个 Bot 的定时到点后自动开始" : "定时不会触发，只在你手动唤醒时执行"}
        </small>
      </span>
    </label>
  );
}

export type { OnboardingAnswers, ParsedPreset };
export { suggestBotName, looksLikeStandingInstruction, parsePreset, buildPreset };

function readOnboardingAnswers(prompt: string): OnboardingAnswers {
  return parsePreset(prompt).answers;
}

function BotConversationalWizard({
  bot,
  existingNames = [],
  busy,
  disabled,
  error,
  onComplete,
  onSkip,
}: {
  bot: BotDefinition;
  existingNames?: string[];
  busy: boolean;
  disabled: boolean;
  error?: string;
  onComplete: (finalName: string, prompt: string, fact?: string | null) => Promise<void>;
  onSkip: () => void;
}) {
  const [answersList, setAnswersList] = useState<WizardAnswerEntry[]>([]);
  const [freeInput, setFreeInput] = useState("");
  const nameInputRef = useRef<HTMLInputElement>(null);

  const { nextQuestion, preset } = useMemo(() => runWizard(answersList), [answersList]);
  const isFinished = nextQuestion === null;

  const isNewBot = !bot.name || !bot.name.trim() || bot.name === "未命名" || (bot.name === "新 Bot" && !bot.systemPrompt);
  const suggestedName = useMemo(() => suggestBotName(preset.answers, existingNames), [preset.answers, existingNames]);
  const [nameInput, setNameInput] = useState(isNewBot ? "" : bot.name);

  useEffect(() => {
    if (isFinished) {
      if (isNewBot && !nameInput) {
        setNameInput(suggestedName);
      }
      const timer = setTimeout(() => {
        nameInputRef.current?.focus();
        nameInputRef.current?.select();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isFinished, isNewBot, suggestedName]);

  // 键盘快捷键监听 A-E
  useEffect(() => {
    if (isFinished || disabled || busy || !nextQuestion) return;

    function handleKeyDown(e: KeyboardEvent) {
      const active = document.activeElement;
      if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement) {
        return;
      }
      const key = e.key.toUpperCase();
      if (["A", "B", "C", "D", "E"].includes(key)) {
        const opt = nextQuestion?.options.find((o) => o.key === key);
        if (opt) {
          e.preventDefault();
          chooseOption(opt.key);
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isFinished, disabled, busy, nextQuestion]);

  const chooseOption = (key: string) => {
    if (!nextQuestion) return;
    setAnswersList((prev) => [...prev, { questionId: nextQuestion.id, optionKey: key }]);
    setFreeInput("");
  };

  const handleFreeSubmit = () => {
    const text = freeInput.trim();
    if (!text || !nextQuestion) return;
    setAnswersList((prev) => [...prev, { questionId: nextQuestion.id, text }]);
    setFreeInput("");
  };

  const handleFinish = async () => {
    const finalName = nameInput.trim() || (isNewBot ? suggestedName : bot.name);
    // 判断是否以 E 退出或无任何有效偏好
    const quitAtFirst = answersList.length === 1 && answersList[0].optionKey === "E";
    const hasPreferences = !quitAtFirst && Boolean(
      preset.answers.focus ||
      preset.answers.style ||
      preset.answers.autonomy ||
      (preset.answers.extra && Object.keys(preset.answers.extra).length > 0)
    );

    const prompt = hasPreferences ? buildPreset({ answers: preset.answers, rules: [], other: "" }) : SKIPPED_WIZARD_PROMPT;
    let fact: string | null = null;
    if (hasPreferences) {
      const parts: string[] = [];
      if (preset.answers.focus) parts.push(`主要偏好处理${preset.answers.focus}`);
      if (preset.answers.style) parts.push(`希望以“${preset.answers.style}”的方式汇报`);
      if (preset.answers.autonomy) parts.push(`推进方式偏好“${preset.answers.autonomy}”`);
      if (preset.answers.extra) {
        for (const [k, v] of Object.entries(preset.answers.extra)) {
          const q = WIZARD_POOL[k];
          const displayLabel = q ? q.shortLabel : k;
          if (v && !parts.some((p) => p.includes(v))) {
            parts.push(`${displayLabel}偏好“${v}”`);
          }
        }
      }
      if (parts.length > 0) {
        fact = `工作偏好：${parts.slice(0, 3).join("；")}。`;
      }
    }
    await onComplete(finalName, prompt, fact);
  };

  return (
    <div className="bot-conversational-wizard" aria-label="工作预设向导">
      {/* 初始问候语 */}
      <div className="bot-chat-message bot-chat-event bot-wizard-greeting">
        <PixelAvatar className="bot-chat-event-avatar" avatarId={bot.avatarId} color={bot.avatarColor} seed={bot.id} />
        <div className="bot-chat-bubble bot-chat-bubble-system">
          <p>你好，我是刚建好的助手。</p>
        </div>
      </div>

      {/* 已完成的问答轮次 */}
      {answersList.map((entry, idx) => {
        const q = WIZARD_POOL[entry.questionId];
        const chosenOpt = q?.options.find((o) => o.key === entry.optionKey);
        const userText = entry.text || chosenOpt?.label || entry.optionKey || "";
        return (
          <Fragment key={idx}>
            {q && (
              <div className="bot-chat-message bot-chat-event bot-wizard-history-question">
                <PixelAvatar className="bot-chat-event-avatar" avatarId={bot.avatarId} color={bot.avatarColor} seed={bot.id} />
                <div className="bot-chat-bubble bot-chat-bubble-system">
                  <p>{q.ask}</p>
                </div>
              </div>
            )}
            <div className="bot-chat-message bot-chat-user bot-wizard-history-answer">
              <div className="bot-chat-bubble bot-chat-bubble-user">
                <p>{userText}</p>
              </div>
            </div>
          </Fragment>
        );
      })}

      {/* 当前提问卡片 */}
      {!isFinished && nextQuestion && (
        <div className="bot-chat-message bot-chat-event bot-wizard-active-step">
          <PixelAvatar className="bot-chat-event-avatar" avatarId={bot.avatarId} color={bot.avatarColor} seed={bot.id} />
          <div className="bot-wizard-card">
            <div className="bot-wizard-card-header">
              <h3 className="bot-wizard-question-title">{nextQuestion.ask}</h3>
              <button
                type="button"
                className="bot-wizard-skip-btn"
                onClick={onSkip}
                title="跳过向导"
                aria-label="跳过向导"
              >
                <X size={15} />
              </button>
            </div>
            <div className="bot-wizard-options-list">
              {nextQuestion.options.map((opt) => (
                <button
                  key={opt.key}
                  type="button"
                  className="bot-wizard-option-row"
                  disabled={disabled || busy}
                  onClick={() => chooseOption(opt.key)}
                >
                  <span className="bot-wizard-option-badge">{opt.key}</span>
                  <div className="bot-wizard-option-text">
                    <span className="bot-wizard-option-label">{opt.label}</span>
                    {opt.hint && <span className="bot-wizard-option-hint">{opt.hint}</span>}
                  </div>
                </button>
              ))}
            </div>
            <div className="bot-wizard-free-input-row">
              <input
                type="text"
                className="bot-wizard-free-input"
                placeholder="输入你自己的回答…"
                value={freeInput}
                disabled={disabled || busy}
                onChange={(e) => setFreeInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleFreeSubmit();
                  }
                }}
              />
              <button
                type="button"
                className="bot-secondary-button bot-wizard-free-submit"
                disabled={disabled || busy || !freeInput.trim()}
                onClick={handleFreeSubmit}
              >
                发送
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 提问完成，起名阶段 */}
      {isFinished && (
        <>
          <div className="bot-chat-message bot-chat-event bot-wizard-memorized">
            <PixelAvatar className="bot-chat-event-avatar" avatarId={bot.avatarId} color={bot.avatarColor} seed={bot.id} />
            <div className="bot-chat-bubble bot-chat-bubble-system">
              <p>好，记住了。</p>
            </div>
          </div>
          <div className="bot-chat-message bot-chat-event bot-wizard-naming-step">
            <PixelAvatar className="bot-chat-event-avatar" avatarId={bot.avatarId} color={bot.avatarColor} seed={bot.id} />
            <div className="bot-wizard-card bot-onboarding-name-block">
              <span className="bot-onboarding-question-title">我叫什么？</span>
              <div className="bot-onboarding-name-row">
                <input
                  ref={nameInputRef}
                  type="text"
                  className="bot-onboarding-name-input"
                  value={nameInput}
                  placeholder={suggestedName}
                  disabled={disabled || busy}
                  onChange={(e) => setNameInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleFinish();
                    }
                  }}
                />
                <button
                  className="bot-primary-button"
                  type="button"
                  disabled={disabled || busy}
                  onClick={handleFinish}
                >
                  {busy ? "正在保存…" : "确认并开始对话"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {error && <p className="bot-inline-error" role="alert">{error}</p>}
    </div>
  );
}

function getChainedParentTaskId(
  task: BotTask,
  allTasks: BotTask[],
  allComms: BotCommunication[],
  visited: Set<string> = new Set(),
): string | null {
  if (!task.senderBotId) return null;
  // A reply chain can loop back on itself; stop instead of recursing forever.
  if (visited.has(task.id)) return null;
  visited.add(task.id);
  const related = allComms.filter((c) => c.deliveryTaskId === task.id || c.taskId === task.id);
  for (const c of related) {
    if (c.replyTo) {
      const parentComm = allComms.find((p) => p.id === c.replyTo);
      if (parentComm) {
        const candidateId = parentComm.taskId || parentComm.deliveryTaskId;
        if (candidateId && candidateId !== task.id) {
          const candTask = allTasks.find((t) => t.id === candidateId);
          if (candTask) {
            if (!candTask.senderBotId || candTask.senderBotId === candTask.botId) return candTask.id;
            const ancestor = getChainedParentTaskId(candTask, allTasks, allComms, visited);
            if (ancestor) return ancestor;
          }
        }
      }
    }
  }
  return null;
}

function BotMessageBody({
  content,
  onSelectOption,
  onOpenConfig,
  disabled,
}: {
  content: string;
  onSelectOption?: (option: string) => void;
  onOpenConfig?: () => void;
  disabled?: boolean;
}) {
  const { body, options, suggestsConfig } = useMemo(
    () => parseMessageOptions(content),
    [content],
  );

  return (
    <div className="bot-chat-event-body">
      <RichText text={body} repair />
      {options.length > 0 && onSelectOption && (
        <div className="bot-chat-quick-options" role="group" aria-label="快捷选项">
          {options.map((option, idx) => (
            <button
              key={idx}
              type="button"
              className="bot-chat-quick-option"
              disabled={disabled}
              onClick={() => onSelectOption(option)}
              title={`快捷回复：${option}`}
            >
              {option}
            </button>
          ))}
        </div>
      )}
      {suggestsConfig && onOpenConfig && (
        <div style={{ marginTop: 8 }}>
          <button
            type="button"
            className="bot-chat-quick-action"
            onClick={onOpenConfig}
            title="打开工作预设与配置面板"
          >
            <Settings2 size={12} />
            <span>打开工作预设与配置</span>
          </button>
        </div>
      )}
    </div>
  );
}

export function BotChat({
  bot,
  bots,
  tasks,
  task,
  events,
  artifacts,
  onSelectBot,
  onSelectTask,
  onDispatch,
  onAutoDispatch,
  onFollowUp,
  onWake,
  onCancel,
  onRetry,
  onOpenMemory,
  communications = [],
  onOpenCommunications,
  schedules = [],
  onSchedulesChange,
  presets = [],
  models = [],
  onUpdateBot,
  onExit,
  disabled = false,
  enterToSend = true,
}: {
  bot?: BotDefinition;
  bots: BotDefinition[];
  tasks: BotTask[];
  task?: BotTask;
  events: BotEvent[];
  artifacts: BotArtifact[];
  onSelectBot?: (bot: BotDefinition) => void;
  onSelectTask?: (task: BotTask) => void;
  onDispatch: BotAction;
  onAutoDispatch?: (content: string) => Promise<void>;
  onFollowUp?: (content: string) => Promise<void> | void;
  onWake?: () => void;
  onCancel?: () => void;
  onRetry?: (task: BotTask) => void;
  onOpenMemory?: () => void;
  communications?: BotCommunication[];
  onOpenCommunications?: (peerBotId?: string) => void;
  schedules?: BotSchedule[];
  onSchedulesChange?: () => void;
  presets?: Preset[];
  models?: Model[];
  onUpdateBot?: (
    botId: string,
    patch: Partial<
      Pick<
        BotDefinition,
        | "name"
        | "presetId"
        | "systemPrompt"
        | "description"
        | "avatarId"
        | "avatarColor"
        | "wakeEnabled"
      >
    >,
  ) => Promise<void>;
  onExit?: () => void;
  disabled?: boolean;
  enterToSend?: boolean;
}) {
  const [value, setValue] = useState("");
  const [scheduleForm, setScheduleForm] = useState<ComposerScheduleForm>(() => defaultComposerForm());
  const [scheduleArmed, setScheduleArmed] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const scheduleTriggerRef = useRef<HTMLButtonElement>(null);
  const [schedulePopoverOpen, setSchedulePopoverOpen] = useState(false);
  const [schedulePanelOpen, setSchedulePanelOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [previewArtifact, setPreviewArtifact] = useState<BotArtifact | null>(null);

  // 头部原地编辑名字
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [savingName, setSavingName] = useState(false);
  const nameEditInputRef = useRef<HTMLInputElement>(null);

  // 头部原地编辑描述
  const [editingDesc, setEditingDesc] = useState(false);
  const [descInput, setDescInput] = useState("");
  const [savingDesc, setSavingDesc] = useState(false);
  const descEditInputRef = useRef<HTMLInputElement>(null);

  // 头部内联错误
  const [headerError, setHeaderError] = useState("");

  // 长期约定反馈与自动提议忽略集合
  const [ruleFeedback, setRuleFeedback] = useState<Record<string, string>>({});
  const [dismissedSuggestions, setDismissedSuggestions] = useState<Set<string>>(new Set());

  // 等你回复（T3d-ui）
  const [dismissedPendingTaskIds, setDismissedPendingTaskIds] = useState<string[]>([]);
  const [highlightQuestionCard, setHighlightQuestionCard] = useState(false);
  const [legacyDismissedTaskIds, setLegacyDismissedTaskIds] = useState<string[]>([]);
  const [legacyDismissingTaskId, setLegacyDismissingTaskId] = useState<string | null>(null);
  const [legacyDismissError, setLegacyDismissError] = useState("");
  const questionCardRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const hasPendingQuestion = Boolean(
    bot?.pendingQuestion &&
    !dismissedPendingTaskIds.includes(bot.pendingQuestion.taskId)
  );

  const isTaskRunning = Boolean(
    task && ["queued", "starting", "running"].includes(task.status),
  );

  useEffect(() => {
    if (hasPendingQuestion) {
      setHighlightQuestionCard(true);
      textareaRef.current?.focus();
      questionCardRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      const timer = setTimeout(() => setHighlightQuestionCard(false), 1600);
      return () => clearTimeout(timer);
    }
  }, [bot?.id, bot?.pendingQuestion?.taskId, hasPendingQuestion]);

  async function handleAnswerWait(taskId: string, answerText: string) {
    if (!answerText.trim() || busy || disabled) return;
    setBusy(true);
    setError("");
    try {
      await request(`/tasks/${encodeURIComponent(taskId)}/wait`, {
        action: "answer",
        text: answerText.trim(),
      });
      setDismissedPendingTaskIds((prev) => [...prev, taskId]);
      setValue("");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "回答提问失败，请稍后重试。",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleDismissWait(taskId: string) {
    if (busy || disabled) return;
    setBusy(true);
    setError("");
    try {
      await request(`/tasks/${encodeURIComponent(taskId)}/wait`, {
        action: "dismiss",
      });
      setDismissedPendingTaskIds((prev) => [...prev, taskId]);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "结束等待失败，请稍后重试。",
      );
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (editingName) {
      nameEditInputRef.current?.focus();
      nameEditInputRef.current?.select();
    }
  }, [editingName]);

  useEffect(() => {
    if (editingDesc) {
      descEditInputRef.current?.focus();
      descEditInputRef.current?.select();
    }
  }, [editingDesc]);

  async function handleSaveName() {
    if (!bot || !onUpdateBot) return;
    const trimmed = nameInput.trim();
    if (!trimmed || trimmed === bot.name) {
      setEditingName(false);
      setNameInput(bot.name);
      return;
    }
    setSavingName(true);
    setHeaderError("");
    try {
      await onUpdateBot(bot.id, { name: trimmed });
      setEditingName(false);
    } catch (err) {
      setHeaderError(err instanceof Error ? err.message : "修改名字失败");
    } finally {
      setSavingName(false);
    }
  }

  async function handleSaveDesc() {
    if (!bot || !onUpdateBot) return;
    const trimmed = descInput.trim();
    const nextDesc = trimmed || "随时可以接活";
    if (nextDesc === (bot.description || "随时可以接活")) {
      setEditingDesc(false);
      return;
    }
    setSavingDesc(true);
    setHeaderError("");
    try {
      await onUpdateBot(bot.id, { description: nextDesc });
      setEditingDesc(false);
    } catch (err) {
      setHeaderError(err instanceof Error ? err.message : "修改描述失败");
    } finally {
      setSavingDesc(false);
    }
  }

  async function handleSaveAsRule(text: string, msgKey: string) {
    if (!bot || !onUpdateBot) return;
    const cleanText = text.trim().slice(0, 200);
    if (!cleanText) return;

    const parsed = parsePreset(bot.systemPrompt || "");
    if (parsed.rules.includes(cleanText)) {
      setRuleFeedback((prev) => ({ ...prev, [msgKey]: "已存在该约定" }));
      setTimeout(() => setRuleFeedback((prev) => ({ ...prev, [msgKey]: "" })), 3000);
      return;
    }
    if (parsed.rules.length >= 12) {
      setRuleFeedback((prev) => ({ ...prev, [msgKey]: "约定已满，先去预设里删几条" }));
      setTimeout(() => setRuleFeedback((prev) => ({ ...prev, [msgKey]: "" })), 4000);
      return;
    }

    const nextRules = [...parsed.rules, cleanText];
    const nextPrompt = buildPreset({
      answers: parsed.answers,
      rules: nextRules,
      other: parsed.other,
    });

    try {
      await onUpdateBot(bot.id, { systemPrompt: nextPrompt });
      setRuleFeedback((prev) => ({ ...prev, [msgKey]: "已记为长期约定" }));
      setTimeout(() => setRuleFeedback((prev) => ({ ...prev, [msgKey]: "" })), 3000);
    } catch (err) {
      setRuleFeedback((prev) => ({ ...prev, [msgKey]: "保存约定失败" }));
      setTimeout(() => setRuleFeedback((prev) => ({ ...prev, [msgKey]: "" })), 3000);
    }
  }

  function armOnce(date: string, time: string) {
    setScheduleForm((current) => ({ ...current, kind: "once", onceDate: date, onceTime: time }));
    setScheduleArmed(true);
    try {
      popoverRef.current?.hidePopover();
    } catch {
      // popover might not be open
    }
  }

  function selectSchedulePreset(preset: "1h" | "tonight" | "tomorrow") {
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    if (preset === "1h") {
      const d = new Date(now.getTime() + 60 * 60 * 1000);
      d.setSeconds(0, 0);
      armOnce(
        `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
        `${pad(d.getHours())}:${pad(d.getMinutes())}`,
      );
      return;
    }
    if (preset === "tonight") {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 20, 0, 0, 0);
      if (d.getTime() <= now.getTime()) d.setDate(d.getDate() + 1);
      armOnce(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`, "20:00");
      return;
    }
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 9, 0, 0, 0);
    armOnce(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`, "09:00");
  }

  function placeSchedulePopover() {
    const popover = popoverRef.current;
    const trigger = scheduleTriggerRef.current;
    if (!popover || !trigger) return;
    const rect = trigger.getBoundingClientRect();
    popover.style.position = "fixed";
    popover.style.margin = "0";
    popover.style.bottom = `${window.innerHeight - rect.top + 6}px`;
    popover.style.right = `${Math.max(16, window.innerWidth - rect.right)}px`;
    popover.style.top = "auto";
    popover.style.left = "auto";
    popover.style.maxHeight = "min(70vh, 420px)";
    popover.style.overflow = "auto";
  }

  function confirmComposerSchedule() {
    const invalid = validateComposerForm(scheduleForm);
    if (invalid) {
      setError(invalid);
      return;
    }
    if (scheduleForm.kind === "interval") {
      const everySeconds = intervalSecondsFromHours(scheduleForm.intervalHours);
      if (everySeconds < 300) {
        setError("定时间隔最短 5 分钟。太频繁会持续消耗模型额度。");
        return;
      }
    }
    setScheduleArmed(true);
    setError("");
    try {
      popoverRef.current?.hidePopover();
    } catch {
      // popover might not be open
    }
  }

  const scheduleDateOptions = (() => {
    const options = [];
    const pad = (n: number) => String(n).padStart(2, "0");
    const now = new Date();
    for (let i = 0; i < 7; i++) {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + i);
      const val = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
      const label =
        i === 0
          ? `今天 (${d.getMonth() + 1}月${d.getDate()}日)`
          : i === 1
            ? `明天 (${d.getMonth() + 1}月${d.getDate()}日)`
            : i === 2
              ? `后天 (${d.getMonth() + 1}月${d.getDate()}日)`
              : `${d.getMonth() + 1}月${d.getDate()}日`;
      options.push({ value: val, label });
    }
    return options;
  })();
  useEffect(() => {
    if (schedulePopoverOpen) placeSchedulePopover();
  }, [scheduleForm.kind, schedulePopoverOpen]);
  const composerScheduleInvalid = validateComposerForm(scheduleForm);
  const composerIntervalSeconds = intervalSecondsFromHours(scheduleForm.intervalHours);
  const scheduleQuotaText = remainingScheduleQuota(schedules.length);
  let composerChipLabel = "";
  if (scheduleArmed) {
    try {
      composerChipLabel =
        scheduleForm.kind === "once"
          ? formatScheduledTaskTime(onceLocalToIso(scheduleForm.onceDate, scheduleForm.onceTime))
          : describeRule(composerRuleFromForm(scheduleForm));
    } catch {
      composerChipLabel = describeComposerChip(scheduleForm);
    }
  }
  const [onboarding, setOnboarding] = useState<{ focus?: string; style?: string; autonomy?: string }>({});
  const [onboardingBusy, setOnboardingBusy] = useState(false);
  const [onboardingDone, setOnboardingDone] = useState(false);
  const [onboardingEditing, setOnboardingEditing] = useState(false);
  const [onboardingError, setOnboardingError] = useState("");
  const [settingNotice, setSettingNotice] = useState("");
  const streamRef = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);

  const currentPresetSummary = useMemo(() => {
    return bot?.systemPrompt ? getPresetSummary(parsePreset(bot.systemPrompt).answers) : null;
  }, [bot?.systemPrompt]);

  const displayedDescription = useMemo(() => {
    if (bot?.description && bot.description.trim() && bot.description !== "随时可以接活") {
      return bot.description.trim();
    }
    return currentPresetSummary || "";
  }, [bot?.description, currentPresetSummary]);

  useEffect(() => {
    followLatest.current = true;
    setOnboarding(bot?.systemPrompt ? readOnboardingAnswers(bot.systemPrompt) : {});
    const parsed = bot?.systemPrompt ? parsePreset(bot.systemPrompt) : null;
    const hasPreset = Boolean(
      parsed &&
      (parsed.answers.focus || parsed.answers.style || parsed.answers.autonomy || (parsed.answers.extra && Object.keys(parsed.answers.extra).length > 0))
    );
    const hasTasks = tasks.some((t) => t.botId === bot?.id);
    const hasCustomPrompt = Boolean(bot?.systemPrompt && bot.systemPrompt.trim());
    setOnboardingDone(hasPreset || hasTasks || hasCustomPrompt);
    setOnboardingEditing(false);
    setOnboardingError("");
    setSettingNotice("");
    setScheduleArmed(false);
    setScheduleForm(defaultComposerForm());
    setSchedulePanelOpen(false);
    setError("");
  }, [bot?.id]);
  useEffect(() => {
    if (!onboardingEditing) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      // Renaming owns Escape while its input has focus, so one press only
      // cancels the rename instead of also closing the preset editor.
      const active = document.activeElement;
      if (active instanceof HTMLElement && active.classList.contains("bot-chat-title-input")) return;
      setOnboardingEditing(false);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onboardingEditing]);
  useEffect(() => {
    const stream = streamRef.current;
    if (stream && followLatest.current) stream.scrollTop = stream.scrollHeight;
  }, [bot?.id, tasks, events, artifacts]);
  const activeTask =
    task &&
    ["queued", "scheduled", "starting", "running", "waiting"].includes(
      task.status,
    )
      ? task
      : undefined;
  const taskEvents = events.flatMap((event) => {
    const content = event.content.trim();
    if (!content) return [];
    if (event.type === "instruction") return [{ ...event, content }];
    if (event.sourceKind === "tool" || event.sourceKind === "notice") return [];
    if (!["message", "handoff", "result", "error"].includes(event.type)) return [];
    if (/(?:已核对|协作者|已向.+说)/i.test(content)) return [];
    if (event.type === "result" && task?.result) return [];
    if (/^(?:bash|exit=\d+|Pi 已接收任务。|已恢复上次的上下文)/.test(content)) return [];
    if (/^\{"(?:bots|ok|taskId)"/.test(content)) return [];
    if (/\|\s*Bot\s*\|\s*模型\s*\|\s*状态\s*\|/i.test(content)) return [];
    const readable = cleanTranscriptText(content);
    return readable ? [{ ...event, content: readable }] : [];
  });
  const conversationTasks = useMemo(() => {
    return tasks
      .filter((item) => item.botId === bot?.id)
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  }, [tasks, bot?.id]);

  const absorbedTasksByParent = useMemo(() => {
    const map = new Map<string, BotTask[]>();
    for (const t of conversationTasks) {
      const parentId = getChainedParentTaskId(t, conversationTasks, communications);
      if (parentId) {
        const list = map.get(parentId) || [];
        list.push(t);
        map.set(parentId, list);
      }
    }
    return map;
  }, [conversationTasks, communications]);

  const rootConversationTasks = useMemo(() => {
    const absorbedIds = new Set<string>();
    for (const list of absorbedTasksByParent.values()) {
      for (const t of list) absorbedIds.add(t.id);
    }
    return conversationTasks.filter((t) => !absorbedIds.has(t.id));
  }, [conversationTasks, absorbedTasksByParent]);

  async function sendMessage(textToSend: string) {
    const content = textToSend.trim();
    if (!content || busy || disabled || !bot) return;

    if (hasPendingQuestion && bot?.pendingQuestion) {
      await handleAnswerWait(bot.pendingQuestion.taskId, content);
      return;
    }

    setBusy(true);
    setError("");
    try {
      const setting = parseBotSettingCommand(content, presets);
      if (setting && onUpdateBot) {
        if (!setting.patch) {
          setSettingNotice(setting.message);
        } else {
          await onUpdateBot(bot.id, setting.patch);
          setSettingNotice(setting.message);
        }
        setValue("");
        return;
      }
      // 每条新消息默认开启独立任务，让互不相关的目标可以并发推进。
      // 针对已有任务的补充仍通过任务详情中的跟进入口完成。
      if (scheduleArmed) {
        const invalid = validateComposerForm(scheduleForm);
        if (invalid) {
          setError(invalid);
          return;
        }
        if (schedules.length >= MAX_SCHEDULES_PER_BOT) {
          setError(remainingScheduleQuota(schedules.length));
          return;
        }
        if (scheduleForm.kind === "once") {
          const result = await onDispatch({
            botId: bot.id,
            prompt: content,
            wake: true,
            runAt: onceLocalToIso(scheduleForm.onceDate, scheduleForm.onceTime),
          });
          const created = result?.schedule;
          if (created) {
            setSettingNotice(createdScheduleNotice(created, formatScheduledTaskTime));
          } else if (result?.message) {
            setSettingNotice(result.message);
          }
          onSchedulesChange?.();
        } else {
          const rule = composerRuleFromForm(scheduleForm);
          const created = await mutate<BotSchedule>(
            `/bots/${encodeURIComponent(bot.id)}/schedules`,
            {
              prompt: content,
              rule,
              timezone: localTimezone(),
              overlapPolicy: "skip",
            },
          );
          setSettingNotice(createdScheduleNotice(created, formatScheduledTaskTime));
          onSchedulesChange?.();
        }
      } else {
        await onDispatch({
          botId: bot.id,
          prompt: content,
          wake: true,
        });
      }
      setValue("");
      setScheduleArmed(false);
      try {
        popoverRef.current?.hidePopover();
      } catch {
        // popover might not be open
      }
    } catch (cause) {
      setError(
        scheduleErrorMessage(
          apiErrorCode(cause),
          cause instanceof Error ? cause.message : "消息发送失败，请稍后重试。",
          schedules.length,
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await sendMessage(value);
  }
  return (
    <>
      <section className="bot-chat-shell" aria-label="Bot 对话窗口">
      <header className="bot-chat-header">
        <div className="bot-chat-identity">
          <div className="bot-chat-avatar-wrap">
            <button
              type="button"
              className="bot-chat-avatar-btn"
              popoverTarget="bot-chat-avatar-popover"
              title="更换头像与颜色"
              aria-label="更换头像与颜色"
              disabled={!bot}
              onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                const popover = document.getElementById("bot-chat-avatar-popover");
                if (popover) {
                  const popoverWidth = 280;
                  const left = Math.max(16, Math.min(rect.left, window.innerWidth - popoverWidth - 16));
                  popover.style.top = `${rect.bottom + 8}px`;
                  popover.style.left = `${left}px`;
                }
              }}
            >
              <PixelAvatar
                className="bot-chat-avatar"
                avatarId={bot?.avatarId}
                color={bot?.avatarColor}
                seed={bot?.id}
                active={bot?.status === "busy"}
              />
            </button>
            {bot && onUpdateBot && (
              <div
                id="bot-chat-avatar-popover"
                popover="auto"
                className="bot-avatar-popover"
              >
                <div className="bot-avatar-picker-title">选择图形与颜色</div>
                <div className="bot-avatar-options">
                  {PIXEL_AVATARS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={`bot-avatar-option${bot.avatarId === item.id ? " is-selected" : ""}`}
                      onClick={() => void onUpdateBot(bot.id, { avatarId: item.id })}
                      title={item.label}
                      aria-label={item.label}
                      aria-pressed={bot.avatarId === item.id}
                    >
                      <PixelAvatar
                        avatarId={item.id}
                        color={bot.avatarColor}
                        seed={item.id}
                        className="pixel-avatar-mini"
                        selected={bot.avatarId === item.id}
                      />
                    </button>
                  ))}
                </div>
                <div className="bot-color-options" aria-label="选择头像颜色">
                  {PIXEL_AVATAR_COLORS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      className={`bot-color-option${bot.avatarColor === c ? " is-selected" : ""}`}
                      style={{ background: c }}
                      onClick={() => void onUpdateBot(bot.id, { avatarColor: c })}
                      aria-label={`颜色 ${c}`}
                      aria-pressed={bot.avatarColor === c}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="bot-chat-title-group">
            <div className="bot-chat-title-row">
              {editingName && bot ? (
                <div className="bot-chat-title-edit-wrap">
                  <input
                    ref={nameEditInputRef}
                    type="text"
                    className="bot-chat-title-input"
                    value={nameInput}
                    disabled={savingName}
                    onChange={(e) => setNameInput(e.target.value)}
                    onBlur={() => void handleSaveName()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        void handleSaveName();
                      } else if (e.key === "Escape") {
                        e.preventDefault();
                        setEditingName(false);
                        setNameInput(bot.name);
                      }
                    }}
                  />
                  {savingName && <LoaderCircle size={14} className="bot-spin" />}
                </div>
              ) : (
                <h1
                  className={bot ? "bot-inline-editable" : ""}
                  role={bot ? "button" : undefined}
                  tabIndex={bot ? 0 : -1}
                  onClick={() => {
                    if (!bot) return;
                    setNameInput(bot.name);
                    setEditingName(true);
                  }}
                  onKeyDown={(e) => {
                    if (bot && e.key === "Enter") {
                      setNameInput(bot.name);
                      setEditingName(true);
                    }
                  }}
                  title={bot ? "点击修改名字" : undefined}
                >
                  {bot?.name || "选择一个 Bot"}
                </h1>
              )}
              {bot && (
                <BotStatusBadge
                  status={bot.pendingQuestion ? "waiting" : bot.status}
                  label={getBotHeaderStatusText(bot, tasks)}
                />
              )}
            </div>
            {editingDesc && bot ? (
              <div className="bot-chat-desc-edit-wrap">
                <input
                  ref={descEditInputRef}
                  type="text"
                  maxLength={1000}
                  className="bot-chat-desc-input"
                  value={descInput}
                  placeholder="随时可以接活"
                  disabled={savingDesc}
                  onChange={(e) => setDescInput(e.target.value)}
                  onBlur={() => void handleSaveDesc()}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void handleSaveDesc();
                    } else if (e.key === "Escape") {
                      e.preventDefault();
                      setEditingDesc(false);
                      setDescInput(bot.description || "");
                    }
                  }}
                />
                {savingDesc && <LoaderCircle size={12} className="bot-spin" />}
              </div>
            ) : (
              <p
                className={bot ? "bot-inline-editable" : ""}
                role={bot ? "button" : undefined}
                tabIndex={bot ? 0 : -1}
                onClick={() => {
                  if (!bot) return;
                  setDescInput(bot.description && bot.description !== "随时可以接活" ? bot.description : "");
                  setEditingDesc(true);
                }}
                onKeyDown={(e) => {
                  if (bot && e.key === "Enter") {
                    setDescInput(bot.description && bot.description !== "随时可以接活" ? bot.description : "");
                    setEditingDesc(true);
                  }
                }}
                title={bot ? "点击修改描述" : undefined}
              >
                {displayedDescription}
              </p>
            )}
            {headerError && <span className="bot-inline-error">{headerError}</span>}
          </div>
        </div>
        <div className="bot-chat-header-actions">
          {bot && onOpenMemory && (
            <button className="bot-quiet-button" type="button" onClick={onOpenMemory} aria-label="打开记忆面板" title="记忆">
              <Brain size={14} />
              <span>记忆</span>
            </button>
          )}
          {bot && onUpdateBot && (
            <button
              className={"bot-quiet-button" + (onboardingEditing ? " is-active" : "")}
              type="button"
              onClick={() => {
                setOnboardingEditing((prev) => !prev);
                setSchedulePanelOpen(false);
              }}
              aria-label="打开设定"
              aria-pressed={onboardingEditing}
              title="设定"
            >
              <Settings2 size={14} />
              <span>设定</span>
            </button>
          )}
          {bot && (
            <button
              className={"bot-quiet-button" + (schedulePanelOpen ? " is-active" : "")}
              type="button"
              onClick={() => {
                setSchedulePanelOpen((prev) => !prev);
                setOnboardingEditing(false);
              }}
              aria-label="打开定时面板"
              aria-pressed={schedulePanelOpen}
              title="定时"
            >
              <Timer size={14} />
              <span>定时{schedules.length ? ` · ${schedules.length}` : ""}</span>
            </button>
          )}
          {bot && onOpenCommunications && (
            <button className="bot-quiet-button" type="button" onClick={() => onOpenCommunications()} aria-label="打开协作面板" title="协作">
              <MessageSquare size={14} />
              <span>协作{communications.length ? ` · ${communications.length}` : ""}</span>
            </button>
          )}
        </div>
      </header>
      <div
        className="bot-chat-stream"
        aria-live="polite"
        ref={streamRef}
        onScroll={(event) => {
          const stream = event.currentTarget;
          followLatest.current = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 80;
        }}
      >
        {!bot && (
          <div className="bot-chat-empty">
            <BotIcon size={30} />
            <h2>选择一个 Bot</h2>
            <p>左侧列表里的 Bot 会在这里执行任务并回传结果。</p>
          </div>
        )}
        {bot && !onboardingDone && conversationTasks.length === 0 && (
          <BotConversationalWizard
            bot={bot}
            existingNames={bots.map((b) => b.name)}
            busy={onboardingBusy}
            disabled={!onUpdateBot}
            error={onboardingError}
            onComplete={async (finalName, prompt, fact) => {
              if (!onUpdateBot) return;
              setOnboardingBusy(true);
              setOnboardingError("");
              try {
                const patch: { name?: string; systemPrompt: string } = { systemPrompt: prompt };
                if (finalName && finalName.trim() && finalName.trim() !== bot.name) {
                  patch.name = finalName.trim();
                }
                await onUpdateBot(bot.id, patch);
                if (fact && !isPreview) {
                  try {
                    await mutate(`/bots/${encodeURIComponent(bot.id)}/memory`, {
                      action: "remember",
                      content: fact,
                    });
                  } catch (e) {
                    console.warn("写入偏好记忆失败", e);
                  }
                }
                setOnboardingDone(true);
              } catch (cause) {
                setOnboardingError(cause instanceof Error ? cause.message : "工作预设保存失败，请重试。");
              } finally {
                setOnboardingBusy(false);
              }
            }}
            onSkip={async () => {
              if (onUpdateBot) {
                try {
                  await onUpdateBot(bot.id, { systemPrompt: SKIPPED_WIZARD_PROMPT });
                } catch (e) {
                  console.warn("跳过向导持久化失败", e);
                }
              }
              setOnboardingDone(true);
            }}
          />
        )}
        {bot && onboardingDone && conversationTasks.length === 0 && (
          <div className="bot-chat-empty">
            <BotIcon size={30} />
            <h2>可以开始了</h2>
            <p>把目标告诉 {bot.name}，它会在自己的运行环境中执行。</p>
          </div>
        )}
        {settingNotice && bot && (
          <div className="bot-chat-message bot-chat-event bot-chat-final bot-settings-notice">
            <PixelAvatar className="bot-chat-event-avatar" avatarId={bot.avatarId} color={bot.avatarColor} seed={bot.id} />
            <RichText text={settingNotice} />
          </div>
        )}
        {bot && rootConversationTasks.map((conversationTask) => {
          const absorbed = absorbedTasksByParent.get(conversationTask.id) || [];
          const allTaskIds = [conversationTask.id, ...absorbed.map((t) => t.id)];

          const taskCommunications = communications.filter(
            (message) =>
              allTaskIds.includes(message.taskId || "") ||
              allTaskIds.includes(message.deliveryTaskId || ""),
          );
          const communicationGroups = [...new Set(taskCommunications.map((message) => {
            return message.senderBotId === bot.id ? message.recipientBotId : message.senderBotId;
          }))]
            .map((peerId) => ({
              peerId,
              messages: taskCommunications
                .filter((message) => message.senderBotId === peerId || message.recipientBotId === peerId)
                .sort((a, b) => a.createdAt.localeCompare(b.createdAt)),
            }))
            .filter((group) => group.peerId && group.messages.length);
          const taskSender = conversationTask.senderBotId
            ? bots.find((item) => item.id === conversationTask.senderBotId)
            : undefined;
          const taskFromBot = Boolean(taskSender && taskSender.id !== bot.id);
          const initialInstruction = taskEvents.find(
            (event) => event.taskId === conversationTask.id && event.type === "instruction",
          );

          const isPeerExplanation = (text: string) => {
            const value = text.trim();
            return /(?:已向.+发送|已向.+说|协作者.+打招呼)/i.test(value)
              || /已与\s*.+?\s*完成双向消息/.test(value);
          };

          const isPeerRelatedEvent = (event: BotEvent) => {
            if (event.type === "handoff") return true;
            const content = event.content.trim();
            if (/(?:已分发给|已分发子任务|已向.+发送|已向.+说|子任务.*已回传|子任务.*完成|消息已排队投递|双向消息完成|已回复.+[：“"]|协作者.*打招呼)/i.test(content)) {
              return true;
            }
            // Merely naming a peer is not a peer event: ordinary narration
            // that mentions another bot belongs in the main chat.
            return false;
          };

          const conversationEvents = taskEvents.filter(
            (event) =>
              allTaskIds.includes(event.taskId || "") &&
              !isPeerRelatedEvent(event) &&
              !(event.id === initialInstruction?.id && event.content === conversationTask.prompt.trim()) &&
              !(["completed", "failed", "cancelled", "interrupted"].includes(conversationTask.status) && !["error", "instruction"].includes(event.type)),
          );
          const conversationArtifacts = artifacts.filter(
            (artifact) => allTaskIds.includes(artifact.taskId || ""),
          );

          const getExplanationsForPeer = (peerName: string) => {
            const lines = new Set<string>();
            for (const tid of allTaskIds) {
              const rawEvents = events.filter((e) => e.taskId === tid);
              for (const e of rawEvents) {
                if (isPeerExplanation(e.content) && (!peerName || e.content.includes(peerName))) {
                  lines.add(e.content.trim());
                }
              }
              const t = tasks.find((item) => item.id === tid);
              if (t?.result && isPeerExplanation(t.result) && (!peerName || t.result.includes(peerName))) {
                lines.add(t.result.trim());
              }
            }
            return Array.from(lines);
          };

          const latestTaskWithResult = [conversationTask, ...absorbed]
            .slice()
            .reverse()
            .find((t) => t.outcome?.summary?.trim() || (t.result && !isPeerExplanation(t.result)));

          let resultText = "";
          if (latestTaskWithResult) {
            resultText =
              latestTaskWithResult.outcome?.summary?.trim() ||
              cleanTranscriptText(latestTaskWithResult.result || "");
          } else if (conversationTask.result) {
            resultText =
              conversationTask.outcome?.summary?.trim() ||
              cleanTranscriptText(conversationTask.result || "");
          }
          return (
          <Fragment key={conversationTask.id}>
            <div className={`bot-chat-message ${taskFromBot ? "bot-chat-event bot-chat-event-handoff" : "bot-chat-user"}`}>
              {taskFromBot && (
                <PixelAvatar
                  className="bot-chat-event-avatar"
                  avatarId={taskSender?.avatarId}
                  color={taskSender?.avatarColor}
                  seed={taskSender?.id}
                />
              )}
              <RichText text={conversationTask.prompt} />
              {!taskFromBot && bot && onUpdateBot && (
                <div className="bot-bubble-actions">
                  <button
                    type="button"
                    className="bot-bubble-action-btn"
                    onClick={() => void handleSaveAsRule(conversationTask.prompt, conversationTask.id)}
                    title="记为长期约定"
                    aria-label="记为长期约定"
                  >
                    记为约定
                  </button>
                </div>
              )}
              {ruleFeedback[conversationTask.id] && (
                <div className="bot-rule-saved-notice">
                  {ruleFeedback[conversationTask.id]}
                </div>
              )}
            </div>
            {!taskFromBot &&
              looksLikeStandingInstruction(conversationTask.prompt) &&
              ["completed", "failed", "cancelled", "interrupted"].includes(conversationTask.status) &&
              !dismissedSuggestions.has(conversationTask.id) &&
              !parsePreset(bot?.systemPrompt || "").rules.includes(conversationTask.prompt.trim().slice(0, 200)) && (
                <div className="bot-standing-suggestion">
                  <span>要把这句记为长期约定吗？</span>
                  <button
                    type="button"
                    className="bot-standing-btn"
                    onClick={() => {
                      void handleSaveAsRule(conversationTask.prompt, conversationTask.id);
                      setDismissedSuggestions((prev) => new Set(prev).add(conversationTask.id));
                    }}
                  >
                    记住
                  </button>
                  <button
                    type="button"
                    className="bot-standing-btn-dismiss"
                    onClick={() => {
                      setDismissedSuggestions((prev) => new Set(prev).add(conversationTask.id));
                    }}
                  >
                    不用
                  </button>
                </div>
            )}
            <BotPlan task={conversationTask} bots={bots} />
            {conversationEvents.map((event) => event.type === "instruction" ? (
              <div className={`bot-chat-message ${event.senderBotId && event.senderBotId !== bot.id ? "bot-chat-event bot-chat-event-handoff" : "bot-chat-user"}`} key={event.id}>
                {event.senderBotId && event.senderBotId !== bot.id && (
                  <PixelAvatar
                    className="bot-chat-event-avatar"
                    avatarId={bots.find((item) => item.id === event.senderBotId)?.avatarId}
                    color={bots.find((item) => item.id === event.senderBotId)?.avatarColor}
                    seed={event.senderBotId}
                  />
                )}
                <RichText text={event.content} />
                {!event.senderBotId && bot && onUpdateBot && (
                  <div className="bot-bubble-actions">
                    <button
                      type="button"
                      className="bot-bubble-action-btn"
                      onClick={() => void handleSaveAsRule(event.content, event.id)}
                      title="记为长期约定"
                      aria-label="记为长期约定"
                    >
                      记为约定
                    </button>
                  </div>
                )}
                {ruleFeedback[event.id] && (
                  <div className="bot-rule-saved-notice">
                    {ruleFeedback[event.id]}
                  </div>
                )}
              </div>
            ) : (
              <div
                className={`bot-chat-message bot-chat-event bot-chat-event-${event.type}`}
                key={event.id}
              >
                <PixelAvatar
                  className="bot-chat-event-avatar"
                  avatarId={bot?.avatarId}
                  color={bot?.avatarColor}
                  seed={bot?.id}
                  active={conversationTask.status === "running"}
                />
                <BotMessageBody
                  content={event.content}
                  onSelectOption={sendMessage}
                  onOpenConfig={onUpdateBot ? () => setOnboardingEditing(true) : undefined}
                  disabled={busy || disabled || isTaskRunning || schedulePopoverOpen}
                />
              </div>
            ))}
            {communicationGroups.map((group) => {
              const peer = bots.find((item) => item.id === group.peerId);
              if (!peer) return null;
              const explanations = getExplanationsForPeer(peer.name);
              return (
                <BotPeerThread
                  key={`${conversationTask.id}-${peer.id}`}
                  task={conversationTask}
                  peer={peer}
                  messages={group.messages}
                  bots={bots}
                  currentBot={bot}
                  onOpenCommunications={onOpenCommunications}
                  explanations={explanations}
                />
              );
            })}
            {conversationTask.waitReason && (
              conversationTask.status === "waiting" && conversationTask.waitReason === "user" && !conversationTask.waitQuestion && !legacyDismissedTaskIds.includes(conversationTask.id) ? (
                <div className="bot-chat-notice bot-legacy-wait-row">
                  <span>这条旧任务在等待，但没有留下问题</span>
                  <button
                    type="button"
                    className="bot-legacy-wait-dismiss"
                    disabled={legacyDismissingTaskId === conversationTask.id}
                    onClick={async () => {
                      // One click sends exactly one POST: the button is disabled
                      // for the whole round trip, and a second dismiss would be
                      // rejected as TASK_NOT_WAITING (409) by the server.
                      if (legacyDismissingTaskId === conversationTask.id) return;
                      setLegacyDismissingTaskId(conversationTask.id);
                      setLegacyDismissError("");
                      try {
                        await request(`/tasks/${encodeURIComponent(conversationTask.id)}/wait`, { action: "dismiss" });
                        setLegacyDismissedTaskIds((prev) => [...prev, conversationTask.id]);
                      } catch (cause) {
                        setLegacyDismissError(
                          cause instanceof Error ? cause.message : "结束等待失败，请稍后重试。",
                        );
                      } finally {
                        setLegacyDismissingTaskId(null);
                      }
                    }}
                  >
                    {legacyDismissingTaskId === conversationTask.id ? "正在结束…" : "结束等待"}
                  </button>
                  {legacyDismissError && (
                    <span className="bot-legacy-wait-error" role="status">
                      {legacyDismissError}
                    </span>
                  )}
                </div>
              ) : !legacyDismissedTaskIds.includes(conversationTask.id) &&
                  !(conversationTask.waitQuestion && bot?.pendingQuestion?.taskId === conversationTask.id) ? (
                // A task that carries a question is already prompted by the
                // question card above the composer; repeating "等待你补充信息"
                // here would ask the same thing twice. Older tasks without a
                // question keep the original notice.
                <div className="bot-chat-notice">
                  <Timer size={13} />
                  <span>{waitReasonLabel(conversationTask.waitReason)}</span>
                </div>
              ) : null
            )}
            {resultText && (
              <div className="bot-chat-message bot-chat-event bot-chat-final">
                <PixelAvatar className="bot-chat-event-avatar" avatarId={bot.avatarId} color={bot.avatarColor} seed={bot.id} />
                <BotMessageBody
                  content={resultText}
                  onSelectOption={sendMessage}
                  onOpenConfig={onUpdateBot ? () => setOnboardingEditing(true) : undefined}
                  disabled={busy || disabled || isTaskRunning || schedulePopoverOpen}
                />
              </div>
            )}
            {conversationTask.error && cleanTranscriptText(conversationTask.error) ? (
              <div className="bot-chat-error">
                <CircleAlert size={14} />
                <span>执行失败：{cleanTranscriptText(conversationTask.error)}</span>
                {onRetry && (conversationTask.status === "failed" || conversationTask.status === "interrupted") && (
                  <button
                    type="button"
                    className="bot-chat-error-retry"
                    onClick={() => onRetry(conversationTask)}
                    disabled={disabled}
                    title="重试此任务"
                  >
                    <RotateCcw size={12} />
                    <span>重试</span>
                  </button>
                )}
              </div>
            ) : (conversationTask.status === "failed" || conversationTask.status === "interrupted") ? (
              <div className="bot-chat-error">
                <CircleAlert size={14} />
                <span>任务执行中断或失败</span>
                {onRetry && (
                  <button
                    type="button"
                    className="bot-chat-error-retry"
                    onClick={() => onRetry(conversationTask)}
                    disabled={disabled}
                    title="重试此任务"
                  >
                    <RotateCcw size={12} />
                    <span>重试</span>
                  </button>
                )}
              </div>
            ) : null}
            {conversationArtifacts.length > 0 && (
              <div className="bot-chat-artifacts">
                {conversationArtifacts.map((artifact) =>
                  isImageArtifact(artifact) ? (
                    <button
                      className="bot-image-preview-trigger"
                      key={artifact.id}
                      type="button"
                      onClick={() => setPreviewArtifact(artifact)}
                      aria-label={`预览 ${artifact.name}`}
                    >
                      <img src={artifact.url} alt={artifact.name} />
                      <span>
                        <Camera size={12} />
                        {artifact.name}
                      </span>
                    </button>
                  ) : canPreviewArtifact(artifact) ? (
                    <button
                      className="bot-file-preview-trigger"
                      key={artifact.id}
                      type="button"
                      onClick={() => setPreviewArtifact(artifact)}
                      aria-label={`预览 ${artifact.name}`}
                    >
                      <FileText size={15} />
                      <span>{artifact.name}</span>
                    </button>
                  ) : (
                    <a
                      className="bot-file-preview-trigger"
                      key={artifact.id}
                      href={artifact.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <FileText size={15} />
                      <span>{artifact.name}</span>
                    </a>
                  ),
                )}
              </div>
            )}
          </Fragment>
          );
        })}
      </div>
      {previewArtifact && <BotArtifactPreview artifact={previewArtifact} onClose={() => setPreviewArtifact(null)} />}
      {task && (task.status === "waiting" || task.status === "scheduled") &&
        onWake &&
        // While the question card is asking about this very task, waking it
        // without an answer would only drop it back into the same wait, so
        // the card's 回复 / 选项 / 结束等待 are the single prompt here.
        !(task.waitQuestion && bot?.pendingQuestion?.taskId === task.id) && (
          <div className="bot-chat-actions">
            <button
              type="button"
              className="bot-chat-secondary"
              onClick={onWake}
              disabled={disabled}
            >
              <Play size={13} />
              {task.status === "scheduled" ? "立即唤醒" : "唤醒"}
            </button>
          </div>
        )}

      <div className="bot-chat-composer-container">
        {hasPendingQuestion && bot?.pendingQuestion && (
          <div
            ref={questionCardRef}
            className={`bot-question-card${highlightQuestionCard ? " is-highlighted" : ""}`}
            role="region"
            aria-label="Bot 提问"
          >
            <div className="bot-question-card-header">
              <span className="bot-question-card-badge">等你回复</span>
              <div className="bot-question-card-actions">
                <button
                  type="button"
                  className="bot-question-card-reply-btn"
                  onClick={() => void handleAnswerWait(bot.pendingQuestion!.taskId, value.trim())}
                  disabled={busy || disabled || !value.trim()}
                  title="以输入框内容回复"
                >
                  回复
                </button>
                <button
                  type="button"
                  className="bot-question-card-dismiss"
                  onClick={() => void handleDismissWait(bot.pendingQuestion!.taskId)}
                  disabled={busy || disabled}
                  title="结束等待"
                >
                  结束等待
                </button>
              </div>
            </div>
            <div className="bot-question-card-body">
              <RichText text={bot.pendingQuestion.question} repair />
            </div>
            {bot.pendingQuestion.options && bot.pendingQuestion.options.length > 0 && (
              <div className="bot-question-card-options">
                {bot.pendingQuestion.options.map((option, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="bot-question-card-option"
                    disabled={busy || disabled}
                    onClick={() => void handleAnswerWait(bot.pendingQuestion!.taskId, option)}
                  >
                    {option}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        <form className="bot-chat-composer" onSubmit={submit}>
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={
              hasPendingQuestion
                ? "回答它的问题…"
                : `告诉 ${bot?.name || "Bot"} 现在要做什么…`
            }
            rows={1}
            disabled={disabled || busy || !bot}
            aria-label="发送给 Bot 的消息"
            title={enterToSend ? "按 Enter 发送，Shift + Enter 换行" : "按 ⌘/Ctrl + Enter 发送，Enter 换行"}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing) return;
              const sendCombo = enterToSend
                ? event.key === "Enter" && !event.shiftKey
                : (event.metaKey || event.ctrlKey) && event.key === "Enter";
              if (sendCombo) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <div className="bot-chat-composer-footer">
            <div className="bot-chat-composer-meta">
              {scheduleArmed && (
                <span className="bot-schedule-chip">
                  <Timer size={12} />
                  <span>{composerChipLabel}</span>
                  <button
                    type="button"
                    className="bot-schedule-chip-clear"
                    onClick={() => setScheduleArmed(false)}
                    aria-label="清除定时"
                    title="清除定时"
                  >
                    <X size={12} />
                  </button>
                </span>
              )}
              {scheduleQuotaText && (
                <span className="bot-schedule-quota-chip">{scheduleQuotaText}</span>
              )}
            </div>
            <div className="bot-chat-send-group">
              {isTaskRunning && onCancel ? (
                <button
                  className="bot-chat-send stop"
                  type="button"
                  onClick={onCancel}
                  disabled={disabled}
                  aria-label="停止执行"
                  title="停止执行"
                >
                  <Square size={13} fill="currentColor" />
                </button>
              ) : (
                <button
                  className="bot-chat-send"
                  type="submit"
                  disabled={disabled || busy || !value.trim() || !bot}
                  aria-label={busy ? "发送中" : hasPendingQuestion ? "回复" : scheduleArmed ? "定时执行" : "发送"}
                  title={busy ? "发送中" : hasPendingQuestion ? "回复" : scheduleArmed ? "定时执行" : "发送"}
                >
                  {busy ? (
                    <LoaderCircle className="bot-spin" size={15} />
                  ) : (
                    <Send size={15} />
                  )}
                </button>
              )}
              <button
                type="button"
                className="bot-chat-schedule-trigger"
                ref={scheduleTriggerRef}
                disabled={disabled || busy || !bot || isTaskRunning}
                aria-label="定时执行选项"
                title="定时选项"
                onClick={() => {
                  placeSchedulePopover();
                  try {
                    popoverRef.current?.togglePopover();
                  } catch {
                    // fallback
                  }
                }}
              >
                <ChevronDown size={14} />
              </button>
            </div>
            <div
              id="bot-schedule-popover"
              popover="auto"
              ref={popoverRef}
              className="bot-schedule-popover"
              onToggle={(e: any) => {
                setSchedulePopoverOpen(e.newState === "open");
              }}
            >
              <div className="bot-schedule-kind-tabs" role="tablist" aria-label="定时类型">
                {(
                  [
                    ["once", "一次"],
                    ["daily", "每天"],
                    ["weekly", "每周"],
                    ["interval", "每 N 小时"],
                  ] as const
                ).map(([kind, label]) => (
                  <button
                    key={kind}
                    type="button"
                    role="tab"
                    aria-selected={scheduleForm.kind === kind}
                    className={`bot-schedule-kind-tab${scheduleForm.kind === kind ? " is-selected" : ""}`}
                    onClick={() => {
                      setScheduleForm((current) => ({ ...current, kind }));
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {scheduleForm.kind === "once" && (
                <div className="bot-schedule-custom-panel">
                  <div className="bot-schedule-presets">
                    <button type="button" className="bot-schedule-option" onClick={() => selectSchedulePreset("1h")}>
                      <Clock3 size={14} />
                      <span>1 小时后</span>
                    </button>
                    <button type="button" className="bot-schedule-option" onClick={() => selectSchedulePreset("tonight")}>
                      <Clock3 size={14} />
                      <span>今晚 20:00</span>
                    </button>
                    <button type="button" className="bot-schedule-option" onClick={() => selectSchedulePreset("tomorrow")}>
                      <Calendar size={14} />
                      <span>明天 09:00</span>
                    </button>
                  </div>
                  <div className="bot-schedule-custom-row">
                    <select
                      className="bot-schedule-select"
                      value={scheduleForm.onceDate || scheduleDateOptions[1]?.value}
                      onChange={(e) => setScheduleForm((current) => ({ ...current, onceDate: e.target.value }))}
                      aria-label="选择日期"
                    >
                      {scheduleDateOptions.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                    <select
                      className="bot-schedule-select"
                      value={scheduleForm.onceTime}
                      onChange={(e) => setScheduleForm((current) => ({ ...current, onceTime: e.target.value }))}
                      aria-label="常用时段"
                    >
                      <option value="09:00">09:00</option>
                      <option value="12:00">12:00</option>
                      <option value="14:00">14:00</option>
                      <option value="18:00">18:00</option>
                      <option value="20:00">20:00</option>
                      <option value="22:00">22:00</option>
                    </select>
                    <input
                      type="text"
                      className="bot-schedule-time-input"
                      value={scheduleForm.onceTime}
                      placeholder="HH:mm"
                      maxLength={5}
                      onChange={(e) => setScheduleForm((current) => ({ ...current, onceTime: e.target.value }))}
                      aria-label="精确时间"
                    />
                  </div>
                </div>
              )}
              {scheduleForm.kind === "daily" && (
                <div className="bot-schedule-custom-panel">
                  <label className="bot-field">
                    <span>每天</span>
                    <input
                      type="text"
                      className="bot-schedule-time-input"
                      value={scheduleForm.atLocalTime}
                      maxLength={5}
                      onChange={(e) => setScheduleForm((current) => ({ ...current, atLocalTime: e.target.value }))}
                      aria-label="每天时间"
                    />
                  </label>
                </div>
              )}
              {scheduleForm.kind === "weekly" && (
                <div className="bot-schedule-custom-panel">
                  <div className="bot-schedule-weekdays" role="group" aria-label="星期">
                    {WEEKDAY_LABELS.map((label, weekday) => (
                      <button
                        key={label}
                        type="button"
                        className={`bot-schedule-kind-tab${scheduleForm.weekday === weekday ? " is-selected" : ""}`}
                        onClick={() => setScheduleForm((current) => ({ ...current, weekday }))}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <input
                    type="text"
                    className="bot-schedule-time-input"
                    value={scheduleForm.atLocalTime}
                    maxLength={5}
                    onChange={(e) => setScheduleForm((current) => ({ ...current, atLocalTime: e.target.value }))}
                    aria-label="每周时间"
                  />
                </div>
              )}
              {scheduleForm.kind === "interval" && (
                <div className="bot-schedule-custom-panel">
                  <div className="bot-schedule-interval-row">
                    {INTERVAL_HOUR_PRESETS.map((hours) => (
                      <button
                        key={hours}
                        type="button"
                        className={`bot-schedule-kind-tab${scheduleForm.intervalHours === hours ? " is-selected" : ""}`}
                        onClick={() => setScheduleForm((current) => ({ ...current, intervalHours: hours }))}
                      >
                        {hours} 小时
                      </button>
                    ))}
                  </div>
                  <label className="bot-field">
                    <span>自定义小时</span>
                    <input
                      type="number"
                      min={0.09}
                      step="any"
                      className="bot-schedule-select"
                      value={scheduleForm.intervalHours}
                      onChange={(e) =>
                        setScheduleForm((current) => ({
                          ...current,
                          intervalHours: Number(e.target.value),
                        }))
                      }
                      aria-label="自定义间隔小时"
                    />
                  </label>
                  {composerIntervalSeconds < 300 && (
                    <p className="bot-schedule-hint" role="status">
                      定时间隔最短 5 分钟。太频繁会持续消耗模型额度。
                    </p>
                  )}
                </div>
              )}
              {scheduleQuotaText && <p className="bot-schedule-hint">{scheduleQuotaText}</p>}
              <div className="bot-schedule-custom-actions">
                <button
                  type="button"
                  className="bot-schedule-confirm-btn"
                  disabled={Boolean(composerScheduleInvalid)}
                  onClick={confirmComposerSchedule}
                >
                  确定
                </button>
              </div>
            </div>
          </div>
          {error && (
            <p className="bot-chat-input-error" role="alert">
              {error}
            </p>
          )}
        </form>
      </div>
    </section>
    {bot && onboardingEditing && (
      <BotPresetPanel
        bot={bot}
        onClose={() => setOnboardingEditing(false)}
        onUpdateBot={onUpdateBot}
        preview={isPreview}
        presets={presets}
        models={models}
      />
    )}
    {bot && schedulePanelOpen && (
      <BotSchedulePanel
        bot={bot}
        schedules={schedules}
        tasks={tasks}
        preview={isPreview}
        onClose={() => setSchedulePanelOpen(false)}
        onChange={onSchedulesChange}
        onSelectTask={onSelectTask}
        wakeControl={
          onUpdateBot ? (
            <AutoWakeControl
              enabled={bot.wakeEnabled}
              onChange={(enabled) => {
                void onUpdateBot(bot.id, { wakeEnabled: enabled }).catch((cause) => {
                  setError(
                    cause instanceof Error ? cause.message : "自动唤醒设置保存失败。",
                  );
                });
              }}
              disabled={disabled}
            />
          ) : null
        }
      />
    )}
    </>
  );
}
export function BotWorkspace({ children }: { children?: ReactNode }) {
  return <div className="bot-workspace">{children}</div>;
}

export function BotPeerThread({
  task,
  peer,
  messages,
  bots,
  currentBot,
  onOpenCommunications,
  explanations = [],
}: {
  task: BotTask;
  peer: BotDefinition;
  messages: BotCommunication[];
  bots: BotDefinition[];
  currentBot: BotDefinition;
  onOpenCommunications?: (peerId: string) => void;
  explanations?: string[];
}) {
  const latestMessage = messages[messages.length - 1];
  const count = messages.length;

  return (
    <details className="bot-peer-thread">
      <summary className="bot-peer-thread-summary">
        <span className="bot-peer-thread-summary-main">
          <MessageSquare size={13} className="bot-peer-thread-icon" />
          <span>与 {peer.name} 的往来 · {count} 条</span>
        </span>
        <span className="bot-peer-thread-summary-side">
          {latestMessage && (
            <time className="bot-peer-thread-time" dateTime={latestMessage.createdAt}>
              {formatCompactTime(latestMessage.createdAt)}
            </time>
          )}
          {onOpenCommunications && (
            <button
              type="button"
              className="bot-peer-thread-link"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onOpenCommunications(peer.id);
              }}
            >
              在协作面板查看
            </button>
          )}
        </span>
      </summary>
      <div className="bot-peer-thread-body">
        <div className="bot-peer-thread-messages">
          {messages.map((message) => {
            const sender = bots.find((b) => b.id === message.senderBotId);
            const fromCurrent = message.senderBotId === currentBot.id;
            return (
              <div
                key={message.id}
                className={`bot-peer-thread-message ${fromCurrent ? "from-current" : "from-peer"}`}
              >
                <div className="bot-peer-thread-message-meta">
                  <PixelAvatar
                    className="bot-peer-thread-avatar"
                    avatarId={fromCurrent ? currentBot.avatarId : sender?.avatarId}
                    color={fromCurrent ? currentBot.avatarColor : sender?.avatarColor}
                    seed={fromCurrent ? currentBot.id : sender?.id}
                  />
                  <span className="bot-peer-thread-author">
                    {fromCurrent ? currentBot.name : sender?.name || "Bot"}
                  </span>
                  <span className="bot-peer-thread-sep">·</span>
                  <span className={`bot-peer-thread-kind is-${message.kind}`}>
                    {kindLabel(message.kind)}
                  </span>
                  <span className="bot-peer-thread-sep">·</span>
                  <time className="bot-peer-thread-time" dateTime={message.createdAt}>
                    {formatDate(message.createdAt)}
                  </time>
                </div>
                <div className="bot-peer-thread-content">
                  <RichText text={message.content} repair />
                </div>
              </div>
            );
          })}
        </div>
        {explanations.length > 0 && (
          <div className="bot-peer-thread-explanation">
            <div className="bot-peer-thread-explanation-header">
              <span className="bot-peer-thread-explanation-badge">Bot 的说明</span>
            </div>
            <div className="bot-peer-thread-explanation-body">
              {explanations.map((text, idx) => (
                <div key={idx} className="bot-peer-thread-explanation-item">
                  <RichText text={text} repair />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </details>
  );
}

