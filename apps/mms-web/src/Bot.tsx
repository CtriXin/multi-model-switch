import { Fragment, useEffect, useRef, useState } from "react";
import type { CSSProperties, FormEvent, ReactNode } from "react";
import { RichText } from "./components";
import type { BotCommunication } from "./BotCommunications";
import { BotArtifactPreview } from "./BotArtifactPreview";
import {
  ArrowLeft,
  AlarmClockCheck,
  Bot as BotIcon,
  Brain,
  Camera,
  Check,
  CircleAlert,
  Clock3,
  FileText,
  LoaderCircle,
  MessageSquare,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Send,
  Settings2,
  Square,
  Timer,
  Trash2,
  Zap,
} from "lucide-react";
import { BotPlan } from "./BotPlan";
import { previewType } from "./bot-artifact-preview";
import type { BotTaskPlan, Preset } from "./types";
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
  createdAt: string;
  updatedAt: string;
  outcome?: BotOutcome | null;
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
  message?: string;
}
export type BotAction = (
  payload: BotDispatchPayload,
) => Promise<BotDispatchResult | void> | BotDispatchResult | void;

export const PIXEL_AVATARS = [
  { id: "round", label: "圆团", rows: ["..###..", ".#####.", "#######", "##o#o##", "#######", ".#####.", "..###.."] },
  { id: "cat", label: "小猫", rows: ["#...#..", "##.##..", ".#####.", "##o.o##", "#######", ".#####.", "..###.."] },
  { id: "puff", label: "蓬蓬", rows: ["..##...", ".#####.", "#######", "##o#o##", "#######", ".#####.", "...##.."] },
  { id: "cube", label: "方方", rows: ["#######", "#######", "##o#o##", "#######", "#######", "##...##", "#######"] },
  { id: "leaf", label: "叶子", rows: ["....#..", "...##..", "..###..", ".#####.", "#######", "..###..", "...#..."] },
  { id: "ghost", label: "幽灵", rows: ["..###..", ".#####.", "#######", "##o#o##", "#######", "##.#.##", "#.#.#.#"] },
  { id: "rocket", label: "火箭", rows: ["...#...", "..###..", ".#####.", "##o#o##", "#######", "..###..", ".#.#.#."] },
  { id: "star", label: "星星", rows: ["...#...", "..###..", "#######", ".##o##.", "#######", "..###..", ".#...#."] },
  { id: "bean", label: "豆豆", rows: ["..####.", ".######", "#######", "##o#o##", "#######", ".#####.", "..###.."] },
  { id: "bot", label: "机器人", rows: [".#...#.", ".#####.", "#######", "##o#o##", "#######", ".#####.", "#.#.#.#"] },
] as const;

export const PIXEL_AVATAR_COLORS = [
  "#b9a5ff",
  "#ff9f91",
  "#73dfc7",
  "#ffd77d",
  "#8bb8ff",
  "#f18bd5",
] as const;

export function PixelAvatar({
  avatarId,
  color,
  seed = "",
  className = "bot-avatar",
}: {
  avatarId?: string;
  color?: string;
  seed?: string;
  className?: string;
}) {
  const seedValue = [...seed].reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const avatar = PIXEL_AVATARS.find((item) => item.id === avatarId) || PIXEL_AVATARS[seedValue % PIXEL_AVATARS.length];
  const avatarColor = color || PIXEL_AVATAR_COLORS[seedValue % PIXEL_AVATAR_COLORS.length];
  return (
    <span className={`${className} pixel-avatar`} style={{ "--pixel-color": avatarColor } as CSSProperties} aria-hidden="true">
      <span className="pixel-avatar-grid">
        {avatar.rows.flatMap((row, rowIndex) => [...row].map((cell, cellIndex) => (
          <i className={`pixel-cell pixel-${cell}`} key={`${rowIndex}-${cellIndex}`} />
        )))}
      </span>
    </span>
  );
}

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

export function BotStatusBadge({
  status,
  compact = false,
}: {
  status: BotStatus | TaskStatus;
  compact?: boolean;
}) {
  const active =
    status === "busy" || status === "starting" || status === "running";
  const label =
    status === "busy"
      ? "运行中"
      : status === "idle"
        ? "待命"
        : status === "paused"
          ? "已暂停"
          : taskStatusLabels[status as TaskStatus];
  const icon =
    status === "completed" ? (
      <Check size={14} />
    ) : status === "failed" ? (
      <CircleAlert size={14} />
    ) : status === "cancelled" ||
      status === "interrupted" ||
      status === "paused" ? (
      <Pause size={14} />
    ) : status === "queued" || status === "scheduled" ? (
      <Clock3 size={14} />
    ) : active ? (
      <LoaderCircle className="bot-spin" size={14} />
    ) : (
      <span className="bot-state-dot" aria-hidden="true" />
    );
  return (
    <span
      className={`bot-state bot-state-${status}${compact ? " bot-state-compact" : ""}`}
      title={label}
                >
      {icon}
      {!compact && label}
    </span>
  );
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
  onSelect,
  onWake,
  onEdit,
  onDelete,
}: {
  bot: BotDefinition;
  selected?: boolean;
  task?: BotTask;
  onSelect?: (bot: BotDefinition) => void;
  onWake?: (botId: string) => void;
  onEdit?: (bot: BotDefinition) => void;
  onDelete?: (bot: BotDefinition) => void;
}) {
  return (
    <article className={`bot-card bot-card-${bot.status}${selected ? " is-selected" : ""}`}>
      <button
        className="bot-card-main"
        type="button"
        onClick={() => onSelect?.(bot)}
        aria-pressed={selected}
      >
        <PixelAvatar avatarId={bot.avatarId} color={bot.avatarColor} seed={bot.id} />
        <span className="bot-card-copy">
          <span className="bot-card-title">
            <strong>{bot.name}</strong>
            <BotStatusBadge status={bot.status} />
          </span>
          <span className="bot-card-description">
            {bot.description || "MMS Bot"}
          </span>
          {task && <span className="bot-card-task">{task.prompt}</span>}
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
      {onEdit && (
        <button
          className="bot-icon-button bot-edit-button"
          type="button"
          onClick={() => onEdit(bot)}
          aria-label={`编辑 ${bot.name}`}
          title="编辑 Bot"
        >
          <Settings2 size={14} />
        </button>
      )}
      {onDelete && (
        <button
          className="bot-icon-button bot-delete-button"
          type="button"
          onClick={() => onDelete(bot)}
          aria-label={`删除 ${bot.name}`}
          title="删除 Bot"
        >
          <Trash2 size={14} />
        </button>
      )}
      {bot.wakeEnabled && (
        <span className="bot-auto-wake" title="自动唤醒已开启">
          <AlarmClockCheck size={14} />
        </span>
      )}
    </article>
  );
}

export function BotList({
  bots,
  tasks = [],
  selectedBotId,
  onSelect,
  onWake,
  onCreate,
  onEdit,
  onDelete,
}: {
  bots: BotDefinition[];
  tasks?: BotTask[];
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
  const [runAt, setRunAt] = useState("");
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
      await onDispatch({
        botId,
        prompt: prompt.trim(),
        runAt: runAt ? new Date(runAt).toISOString() : undefined,
        wake,
        parentTaskId,
      });
      setPrompt("");
      setRunAt("");
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
      <label className="bot-field">
        <span>
          <span>执行时间</span>
          <small>留空立即执行</small>
        </span>
        <input
          type="datetime-local"
          value={toDateTimeValue(runAt)}
          onChange={(event) => setRunAt(event.target.value)}
          disabled={disabled || busy}
        />
      </label>
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
                  {task.runAt && task.status === "scheduled"
                    ? ` · ${formatLocalDateTime(task.runAt)}`
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

export function TaskInspector({
  task,
  bot,
  events,
  artifacts,
  bots,
  onCancel,
  onWake,
  onAccept,
  onFollowUp,
  onSubtask,
  onOpenSession,
  onRetry,
  disabled = false,
}: {
  task: BotTask;
  bot?: BotDefinition;
  events: BotEvent[];
  artifacts: BotArtifact[];
  bots: BotDefinition[];
  onCancel?: () => void;
  onWake?: () => void;
  onAccept?: () => void;
  onFollowUp?: (content: string) => Promise<void> | void;
  onSubtask?: BotAction;
  onOpenSession?: (id: string) => void;
  onRetry?: (task: BotTask) => void;
  disabled?: boolean;
}) {
  const [followUp, setFollowUp] = useState("");
  const [followUpBusy, setFollowUpBusy] = useState(false);
  const [followUpError, setFollowUpError] = useState("");
  const [showSubtask, setShowSubtask] = useState(false);
  const active = [
    "queued",
    "scheduled",
    "starting",
    "running",
    "waiting",
  ].includes(task.status);
  const wakeableWait =
    task.status === "waiting" &&
    !["approval", "confirm", "connection", "connect", "stopping", "stop"].some(
      (word) => task.waitReason?.toLowerCase().includes(word),
    );
  const canWake = wakeableWait || task.status === "scheduled";
  return (
    <section className="bot-inspector" aria-label="任务详情">
      <div className="bot-inspector-heading">
        <div>
          <h2>任务详情</h2>
          <p>
            {bot?.name || task.botId} · {taskStatusLabels[task.status]}
          </p>
        </div>
        <BotStatusBadge status={task.status} />
      </div>
      <p className="bot-task-prompt">{task.prompt}</p>
      {task.waitReason && (
        <p className="bot-wait-reason">
          <Timer size={14} />
          {waitReasonLabel(task.waitReason)}
        </p>
      )}
      {task.queueReason && task.status === "queued" && (
        <p className="bot-wait-reason">
          <Timer size={14} />
          {task.queueReason}
        </p>
      )}
      {task.coordinatorPlan?.mode === "delegate" && (
        <details className="bot-coordinator-plan">
          <summary>协作计划</summary>
          <p>{task.coordinatorPlan.reason}</p>
          {!!task.coordinatorPlan.candidates?.length && (
            <ul>
              {task.coordinatorPlan.candidates.map((candidate) => <li key={candidate.id}>{candidate.name}</li>)}
            </ul>
          )}
        </details>
      )}
      {task.result && (
        <div className="bot-result">
          <h3>结果</h3>
          <RichText text={task.result} repair />
        </div>
      )}
      {task.error && (
        <div className="bot-error">
          <h3>错误</h3>
          <p>{task.error}</p>
        </div>
      )}
      <div className="bot-inspector-actions">
        {active && onCancel && (
          <button
            className="bot-quiet-button danger"
            type="button"
            onClick={onCancel}
            disabled={disabled}
          >
            <Square size={14} />
            取消任务
          </button>
        )}
        {canWake && onWake && (
          <button
            className="bot-quiet-button"
            type="button"
            onClick={onWake}
            disabled={disabled}
          >
            <Play size={14} />
            {task.status === "scheduled" ? "立即唤醒" : "唤醒任务"}
          </button>
        )}
        {(task.status === "failed" || task.status === "interrupted") &&
          onRetry && (
            <button
              className="bot-quiet-button"
              type="button"
              onClick={() => onRetry(task)}
              disabled={disabled}
            >
              <RotateCcw size={14} />
              用原任务重试
            </button>
          )}
        {task.status === "completed" && !task.acceptedAt && onAccept && (
          <button
            className="bot-primary-button"
            type="button"
            onClick={onAccept}
            disabled={disabled}
          >
            <Check size={14} />
            接受结果
          </button>
        )}
        {task.sessionId && onOpenSession && (
          <button
            className="bot-quiet-button"
            type="button"
            onClick={() => onOpenSession(task.sessionId!)}
          >
            <BotIcon size={14} />
            打开会话
          </button>
        )}
        <button
          className="bot-quiet-button"
          type="button"
          onClick={() => setShowSubtask((value) => !value)}
          disabled={disabled}
        >
          <Zap size={14} />
          派给其他 Bot
        </button>
      </div>
      {task.acceptedAt && (
        <p className="bot-accepted">
          <Check size={13} />
          结果已接受
        </p>
      )}
      <div className="bot-follow-up">
        <label htmlFor="bot-follow-up">继续告诉 Bot</label>
        <div>
          <input
            id="bot-follow-up"
            value={followUp}
            onChange={(event) => setFollowUp(event.target.value)}
            placeholder="补充信息或提出修改"
            disabled={disabled}
          />
          <button
            type="button"
            className="bot-icon-button"
            aria-label="发送跟进消息"
            onClick={async () => {
              if (!followUp.trim() || !onFollowUp) return;
              setFollowUpBusy(true);
              setFollowUpError("");
              try {
                await onFollowUp(followUp.trim());
                setFollowUp("");
              } catch (cause) {
                setFollowUpError(
                  cause instanceof Error ? cause.message : "跟进消息发送失败。",
                );
              } finally {
                setFollowUpBusy(false);
              }
            }}
            disabled={disabled || followUpBusy || !followUp.trim()}
          >
            <Send size={14} />
          </button>
        </div>
      </div>
      {followUpError && (
        <p className="bot-inline-error" role="alert">
          {followUpError}
        </p>
      )}
      {showSubtask && onSubtask && (
        <div className="bot-subtask-form">
          <DispatchForm
            bots={bots.filter((item) => item.id !== task.botId)}
            defaultBotId={bots.find((item) => item.id !== task.botId)?.id}
            parentTaskId={task.id}
            onDispatch={onSubtask}
            disabled={disabled}
            label="派给另一个 Bot"
          />
        </div>
      )}
      {events.length > 0 && (
        <details className="bot-message-history">
          <summary>查看任务消息（{events.length}）</summary>
          <EventFeed events={events} bots={bots} limit={events.length} />
        </details>
      )}
    </section>
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
          {enabled ? "定时任务到点后自动开始" : "仅在手动唤醒后继续"}
        </small>
      </span>
    </label>
  );
}

type OnboardingAnswers = { focus?: string; style?: string; autonomy?: string };
const onboardingQuestions = [
  { key: "focus", title: "你最想让我先帮你处理哪一类事？", options: ["工作与项目", "资料整理与写作", "生活安排", "都可以，按事情判断"] },
  { key: "style", title: "你希望我怎么回报？", options: ["只说结论", "结论加关键依据", "需要时再展开"] },
  { key: "autonomy", title: "平时我应该怎么推进？", options: ["能直接做就直接做", "先给我一个简短计划", "涉及外部操作先问我"] },
] as const;

function readOnboardingAnswers(prompt: string): OnboardingAnswers {
  const normalized = prompt.replace(/\\n/g, "\n");
  const read = (label: string) => normalized.split("\n").find((line) => line.startsWith("- " + label + "："))?.split("：").slice(1).join("：").trim();
  return { focus: read("主要帮我处理"), style: read("回报方式"), autonomy: read("执行方式") };
}

function onboardingPrompt(answers: OnboardingAnswers) {
  return [
    "这是创建时确认的工作预设，请持续遵守：",
    answers.focus ? "- 主要帮我处理：" + answers.focus : "",
    answers.style ? "- 回报方式：" + answers.style : "",
    answers.autonomy ? "- 执行方式：" + answers.autonomy : "",
    "- 结果优先，过程保持安静；遇到无法安全判断的关键分歧时再询问。",
  ].filter(Boolean).join("\n");
}

function BotOnboarding({
  bot,
  answers,
  busy,
  disabled,
  error,
  onAnswer,
  onEditAnswer,
  onComplete,
}: {
  bot: BotDefinition;
  answers: OnboardingAnswers;
  busy: boolean;
  disabled: boolean;
  error?: string;
  onAnswer: (key: keyof OnboardingAnswers, value: string) => void;
  onEditAnswer?: (key: keyof OnboardingAnswers) => void;
  onComplete: () => Promise<void>;
}) {
  const current = onboardingQuestions.find((question) => !answers[question.key]);
  const complete = !current;
  return (
    <div className="bot-onboarding" aria-label="创建 Bot 的工作预设">
      <div className="bot-onboarding-greeting">
        <PixelAvatar className="bot-chat-event-avatar" avatarId={bot.avatarId} color={bot.avatarColor} seed={bot.id} />
        <div>
          <strong>嗨，我是 {bot.name}。</strong>
          <p>先用几个小问题告诉我你的习惯，之后我会把它当成默认工作方式。</p>
        </div>
      </div>
      {Object.entries(answers).filter(([, value]) => value).map(([key, value]) => (
        <button className="bot-onboarding-answer" type="button" key={key} onClick={() => onEditAnswer?.(key as keyof OnboardingAnswers)} disabled={disabled || busy}>
          <span>{onboardingQuestions.find((question) => question.key === key)?.title}</span>
          <b>{value}</b>
        </button>
      ))}
      {current && (
        <div className="bot-onboarding-question">
          <strong>{current.title}</strong>
          <div className="bot-onboarding-options">
            {current.options.map((option) => (
              <button
                key={option}
                type="button"
                disabled={disabled || busy}
                onClick={() => onAnswer(current.key, option)}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
      )}
      {complete && (
        <button className="bot-onboarding-save" type="button" disabled={disabled || busy} onClick={() => void onComplete()}>
          {busy ? "正在记住…" : "保存为工作预设"}
        </button>
      )}
      {error && <p className="bot-onboarding-error" role="alert">{error}</p>}
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
  presets = [],
  onUpdateBot,
  onExit,
  disabled = false,
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
  presets?: Preset[];
  onUpdateBot?: (botId: string, patch: Partial<Pick<BotDefinition, "name" | "presetId" | "systemPrompt" | "description">>) => Promise<void>;
  onExit?: () => void;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");
  const [runAt, setRunAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [previewArtifact, setPreviewArtifact] = useState<BotArtifact | null>(null);
  const [onboarding, setOnboarding] = useState<{ focus?: string; style?: string; autonomy?: string }>({});
  const [onboardingBusy, setOnboardingBusy] = useState(false);
  const [onboardingDone, setOnboardingDone] = useState(false);
  const [onboardingEditing, setOnboardingEditing] = useState(false);
  const [onboardingError, setOnboardingError] = useState("");
  const [settingNotice, setSettingNotice] = useState("");
  const streamRef = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  useEffect(() => {
    followLatest.current = true;
    setOnboarding(bot?.systemPrompt ? readOnboardingAnswers(bot.systemPrompt) : {});
    const saved = bot?.systemPrompt ? readOnboardingAnswers(bot.systemPrompt) : {};
    setOnboardingDone(Boolean(saved.focus && saved.style && saved.autonomy));
    setOnboardingEditing(false);
    setOnboardingError("");
    setSettingNotice("");
  }, [bot?.id]);
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
  const conversationTasks = tasks
    .filter((item) => item.botId === bot?.id)
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  const onboardingMode = Boolean(bot && (!bot.systemPrompt.trim() || bot.systemPrompt.includes("这是创建时确认的工作预设")));
  async function submit(event: FormEvent) {
    event.preventDefault();
    const content = value.trim();
    if (!content || busy || disabled || !bot) return;
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
      await onDispatch({
        botId: bot.id,
        prompt: content,
        wake: true,
        ...(runAt ? { runAt: new Date(runAt).toISOString() } : {}),
      });
      setValue("");
      setRunAt("");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "消息发送失败，请稍后重试。",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="bot-chat-shell" aria-label="Bot 对话窗口">
      <header className="bot-chat-header">
        <div className="bot-chat-identity">
          <PixelAvatar className="bot-chat-avatar" avatarId={bot?.avatarId} color={bot?.avatarColor} seed={bot?.id} />
          <div>
            <h1>{bot?.name || "选择一个 Bot"}</h1>
            <p>{bot?.description || "随时可以接活"}</p>
          </div>
        </div>
        <div className="bot-chat-header-actions">
          {bot && onOpenMemory && (
            <button className="bot-memory-trigger" type="button" onClick={onOpenMemory} aria-label="打开记忆面板" title="记忆">
              <Brain size={14} />
              记忆
            </button>
          )}
          {bot && onboardingDone && onUpdateBot && (
            <button className="bot-memory-trigger" type="button" onClick={() => setOnboardingEditing(true)} aria-label="调整工作预设" title="工作预设">
              <Settings2 size={14} />
              预设
            </button>
          )}
          {bot && onOpenCommunications && (
            <button className="bot-memory-trigger" type="button" onClick={() => onOpenCommunications()} aria-label="打开协作面板" title="协作">
              <MessageSquare size={14} />
              协作{communications.length ? ` · ${communications.length}` : ""}
            </button>
          )}
          {bot && <BotStatusBadge status={bot.status} />}
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
        {bot && ((onboardingMode && !onboardingDone) || onboardingEditing) && (
          (!onboardingMode || (onboardingDone && !onboardingEditing)) ? (
            <div className="bot-chat-empty">
              <BotIcon size={30} />
              <h2>可以开始了</h2>
              <p>把目标告诉 {bot.name}，它会在自己的运行环境中执行。</p>
              {onboarding.focus && onboarding.style && onboarding.autonomy && (
                <button className="bot-onboarding-edit" type="button" onClick={() => setOnboardingEditing(true)}>调整工作预设</button>
              )}
            </div>
          ) : (
            <BotOnboarding
              bot={bot}
              answers={onboarding}
              busy={onboardingBusy}
              disabled={disabled || !onUpdateBot}
              onAnswer={(key, value) => {
                const next = { ...onboarding, [key]: value };
                setOnboarding(next);
                if (onUpdateBot) {
                  void onUpdateBot(bot.id, { systemPrompt: onboardingPrompt(next) }).catch((cause) => {
                    setOnboardingError(cause instanceof Error ? cause.message : "工作预设保存失败，请重试。");
                  });
                }
              }}
              onEditAnswer={(key) => setOnboarding((current) => ({ ...current, [key]: undefined }))}
              onComplete={async () => {
                if (!onUpdateBot || !onboarding.focus || !onboarding.style || !onboarding.autonomy) return;
                setOnboardingBusy(true);
                setOnboardingError("");
                try {
                  const prompt = [
                    "这是创建时确认的工作预设，请持续遵守：",
                    `- 主要帮我处理：${onboarding.focus}`,
                    `- 回报方式：${onboarding.style}`,
                    `- 执行方式：${onboarding.autonomy}`,
                    "- 结果优先，过程保持安静；遇到无法安全判断的关键分歧时再询问。",
                  ].join("\n");
                  await onUpdateBot(bot.id, { systemPrompt: prompt });
                  setOnboardingDone(true);
                  setOnboardingEditing(false);
                } catch (cause) {
                  setOnboardingError(cause instanceof Error ? cause.message : "工作预设保存失败，请重试。");
                } finally {
                  setOnboardingBusy(false);
                }
              }}
              error={onboardingError}
            />
          )
        )}
        {settingNotice && bot && (
          <div className="bot-chat-message bot-chat-event bot-chat-final bot-settings-notice">
            <PixelAvatar className="bot-chat-event-avatar" avatarId={bot.avatarId} color={bot.avatarColor} seed={bot.id} />
            <RichText text={settingNotice} />
          </div>
        )}
        {bot && conversationTasks.map((conversationTask) => {
          const taskCommunications = communications.filter(
            (message) =>
              message.taskId === conversationTask.id ||
              message.deliveryTaskId === conversationTask.id,
          );
          const communicationGroups = [...new Set(taskCommunications.map((message) => {
            return message.senderBotId === bot.id ? message.recipientBotId : message.senderBotId;
          }))]
            .map((peerId) => ({
              peerId,
              messages: taskCommunications.filter(
                (message) => message.senderBotId === peerId || message.recipientBotId === peerId,
              ),
            }))
            .filter((group) => group.peerId && group.messages.length);
          const taskSender = conversationTask.senderBotId
            ? bots.find((item) => item.id === conversationTask.senderBotId)
            : undefined;
          const taskFromBot = Boolean(taskSender && taskSender.id !== bot.id);
          const initialInstruction = taskEvents.find(
            (event) => event.taskId === conversationTask.id && event.type === "instruction",
          );
          const conversationEvents = taskEvents.filter(
            (event) =>
              event.taskId === conversationTask.id &&
              !(event.id === initialInstruction?.id && event.content === conversationTask.prompt.trim()) &&
              !(["completed", "failed", "cancelled", "interrupted"].includes(conversationTask.status) && !["error", "instruction"].includes(event.type)),
          );
          const conversationArtifacts = artifacts.filter(
            (artifact) => artifact.taskId === conversationTask.id,
          );
          const resultText =
            conversationTask.outcome?.summary?.trim() ||
            cleanTranscriptText(conversationTask.result || "");
          return (
          <Fragment key={conversationTask.id}>
            <div className={`bot-chat-message ${taskFromBot ? "bot-chat-event bot-chat-event-handoff" : "bot-chat-user"}`}>
              <span className="bot-chat-message-label">{taskFromBot ? `来自 ${taskSender?.name || "Bot"}` : "你"}</span>
              <RichText text={conversationTask.prompt} />
            </div>
            <BotPlan task={conversationTask} bots={bots} />
            {conversationEvents.map((event) => event.type === "instruction" ? (
              <div className={`bot-chat-message ${event.senderBotId && event.senderBotId !== bot.id ? "bot-chat-event bot-chat-event-handoff" : "bot-chat-user"}`} key={event.id}>
                <span className="bot-chat-message-label">{event.senderBotId && event.senderBotId !== bot.id ? `来自 ${bots.find((item) => item.id === event.senderBotId)?.name || "Bot"}` : "你"}</span>
                <RichText text={event.content} />
              </div>
            ) : (
              <div
                className={`bot-chat-message bot-chat-event bot-chat-event-${event.type}`}
                key={event.id}
              >
                <span className="bot-chat-event-mark">
                  {event.type === "result" ? (
                    <Check size={14} />
                  ) : event.type === "error" ? (
                    <CircleAlert size={14} />
                  ) : (
                    <LoaderCircle size={14} />
                  )}
                </span>
                <div>
                  <span className="bot-chat-message-label">
                    {event.type === "handoff"
                      ? "交接"
                      : event.type === "result"
                        ? "结果"
                        : event.type === "error"
                          ? "错误"
                          : bot?.name || "Bot"}
                  </span>
                  <RichText text={event.content} repair />
                </div>
              </div>
            ))}
            {communicationGroups.map((group) => {
              const peer = bots.find((item) => item.id === group.peerId);
              if (!peer || !onOpenCommunications) return null;
              const sent = group.messages.some((message) => message.senderBotId === bot.id);
              return (
                <button
                  className="bot-communications-marker"
                  key={`${conversationTask.id}-${peer.id}`}
                  type="button"
                  onClick={() => onOpenCommunications(peer.id)}
                  aria-label={`${sent ? "已发消息给" : "消息来自"} ${peer.name}，${group.messages.length}条消息往来`}
                >
                  <MessageSquare size={13} />
                  {sent ? `已发消息给 ${peer.name}` : `消息来自 ${peer.name}`}
                  <small>{group.messages.length}条消息往来</small>
                </button>
              );
            })}
            {conversationTask.waitReason && (
              <div className="bot-chat-notice">
                <Timer size={14} />
                {waitReasonLabel(conversationTask.waitReason)}
              </div>
            )}
            {resultText && (
              <div className="bot-chat-message bot-chat-event bot-chat-final">
                <PixelAvatar className="bot-chat-event-avatar" avatarId={bot.avatarId} color={bot.avatarColor} seed={bot.id} />
                <div>
                  <span className="bot-chat-message-label">{bot.name}</span>
                  <RichText text={resultText} repair />
                </div>
              </div>
            )}
            {conversationTask.error && cleanTranscriptText(conversationTask.error) && (
              <div className="bot-chat-error">
                <CircleAlert size={15} />
                <div>
                  <strong>执行失败</strong>
                  <RichText text={cleanTranscriptText(conversationTask.error)} repair />
                </div>
              </div>
            )}
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
                        <Camera size={13} />
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
                      <FileText size={16} />
                      <span>{artifact.name}</span>
                    </button>
                  ) : (
                    <a
                      key={artifact.id}
                      href={artifact.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <FileText size={16} />
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
      {task && (
        <div className="bot-chat-actions">
          {["queued", "scheduled", "starting", "running", "waiting"].includes(
            task.status,
          ) &&
            onCancel && (
              <button
                type="button"
                className="bot-chat-secondary"
                onClick={onCancel}
                disabled={disabled}
              >
                <Square size={13} />
                取消
              </button>
            )}
          {(task.status === "waiting" || task.status === "scheduled") &&
            onWake && (
              <button
                type="button"
                className="bot-chat-secondary"
                onClick={onWake}
                disabled={disabled}
              >
                <Play size={13} />
                {task.status === "scheduled" ? "立即唤醒" : "唤醒"}
              </button>
            )}
          {(task.status === "failed" || task.status === "interrupted") &&
            onRetry && (
              <button
                type="button"
                className="bot-chat-secondary"
                onClick={() => onRetry(task)}
                disabled={disabled}
              >
                <RotateCcw size={13} />
                重试
              </button>
            )}
        </div>
      )}
      <form className="bot-chat-composer" onSubmit={submit}>
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={`告诉 ${bot?.name || "Bot"} 现在要做什么…`}
          rows={1}
          disabled={disabled || busy || !bot}
          aria-label="发送给 Bot 的消息"
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <div className="bot-chat-composer-footer">
          <label>
            <Timer size={13} />
            <input
              type="datetime-local"
              value={runAt}
              onChange={(event) => setRunAt(event.target.value)}
              disabled={disabled || busy}
              aria-label="定时执行时间"
            />
            <span>{runAt ? "已安排执行" : "立即执行"}</span>
          </label>
          <button
            className="bot-chat-send"
            type="submit"
            disabled={disabled || busy || !value.trim() || !bot}
          >
            {busy ? (
              <LoaderCircle className="bot-spin" size={16} />
            ) : (
              <Send size={16} />
            )}
            <span>{busy ? "发送中" : "发送"}</span>
          </button>
        </div>
        {error && (
          <p className="bot-chat-input-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}
export function BotWorkspace({ children }: { children?: ReactNode }) {
  return <div className="bot-workspace">{children}</div>;
}
