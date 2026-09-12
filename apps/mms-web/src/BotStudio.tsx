import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { ArrowLeft, CircleAlert, LoaderCircle, RefreshCw, X } from "lucide-react";
import { isPreview, mutate, request } from "./api";
import type { Bootstrap, Preset } from "./types";
import { AutoWakeControl, BotList, BotWorkspace, BotChat, PIXEL_AVATARS, PIXEL_AVATAR_COLORS } from "./Bot";
import { ModelPicker } from "./LaunchOptions";
import { BotMemoryPanel } from "./BotMemoryPanel";
import { BotCommunications } from "./BotCommunications";
import type { BotCommunication } from "./BotCommunications";
import type {
  BotAction,
  BotArtifact,
  BotDefinition,
  BotDispatchPayload,
  BotDispatchResult,
  BotEvent,
  BotTask,
} from "./Bot";

interface BotCapability {
  executor?: string;
  available?: boolean;
  browser?: boolean;
  reason?: string;
  maxConcurrent?: number;
}
interface BotBootstrap extends Bootstrap {
  bots?: BotDefinition[];
  botCapabilities?: BotCapability;
}
interface BotMessage {
  id: string;
  taskId?: string;
  senderBotId?: string | null;
  sourceKind?: BotEvent["sourceKind"];
  type: BotEvent["type"];
  content: string;
  createdAt: string;
}

type BotStudioProps = {
  data?: Bootstrap;
  onOpenSession?: (id: string) => void;
  onExit?: () => void;
};
const emptyBootstrap: Bootstrap = {
  version: "1",
  mode: "preview",
  csrfToken: "",
  capabilities: { catalogRead: false, configure: false, launch: false },
  workspaces: [],
  models: [],
  services: [],
  presets: [],
  sessions: [],
  diagnostics: [],
};

function isWorkablePreset(preset: Preset) {
  return preset.harness === "pi" && preset.available;
}
function safeUrl(value: string) {
  try {
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin) return "";
    if (
      !url.pathname.startsWith("/api/v1/tasks/") ||
      !url.pathname.endsWith("/content")
    )
      return "";
    return url.toString();
  } catch {
    return "";
  }
}
function previewMutationError() {
  return new Error(
    "当前是预览模式，真实 Bot 操作已禁用。连接 MMS 本地服务后再执行。",
  );
}
function randomItem<T>(items: readonly T[]): T {
  return items[Math.floor(Math.random() * items.length)];
}

function BotEditor({
  bot,
  presets,
  models,
  preview,
  onClose,
  onSaved,
}: {
  bot?: BotDefinition;
  presets: Preset[];
  models: Bootstrap["models"];
  preview: boolean;
  onClose: () => void;
  onSaved: (bot: BotDefinition) => void;
}) {
  const [name, setName] = useState(bot?.name || "");
  const [description, setDescription] = useState(bot?.description || "");
  const [systemPrompt, setSystemPrompt] = useState(bot?.systemPrompt || "");
  const [presetId, setPresetId] = useState(bot?.presetId || "");
  const [wakeEnabled, setWakeEnabled] = useState(bot?.wakeEnabled || false);
  const [avatarId, setAvatarId] = useState(() => bot?.avatarId || randomItem(PIXEL_AVATARS).id);
  const [avatarColor, setAvatarColor] = useState(() => bot?.avatarColor || randomItem(PIXEL_AVATAR_COLORS));
  const [favorites, setFavorites] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    if (!name.trim() || busy || preview) return;
    setBusy(true);
    setError("");
    try {
      const payload = {
        name: name.trim(),
        description: description.trim(),
        systemPrompt,
        presetId: presetId || null,
        wakeEnabled,
        avatarId,
        avatarColor,
      };
      const saved = bot
        ? await mutate<BotDefinition>(
            `/bots/${encodeURIComponent(bot.id)}`,
            payload,
          )
        : await mutate<BotDefinition>("/bots", payload);
      onSaved(saved);
      onClose();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Bot 保存失败，请稍后重试。",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className="bot-dialog-scrim"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="bot-create-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bot-editor-title"
      >
        <div className="bot-dialog-heading">
          <div>
            <h2 id="bot-editor-title">{bot ? "编辑 Bot" : "新建 Bot"}</h2>
            <p>
              {preview
                ? "预览模式只展示表单，保存已禁用。"
                : "定义它的工作范围和默认运行环境。"}
            </p>
          </div>
          <button
            className="bot-icon-button"
            type="button"
            onClick={onClose}
            aria-label="关闭"
          >
            <X size={16} />
          </button>
        </div>
        <label>
          Bot 名称
          <input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={80}
            placeholder="例如：发布协调器"
          />
        </label>
        <label>
          职责说明
          <input
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="例如：整理需求、执行任务并回传结果"
          />
        </label>
        <div className="bot-avatar-picker" aria-label="选择头像">
          <span className="bot-picker-label">头像</span>
          <div className="bot-avatar-options">
            {PIXEL_AVATARS.map((avatar) => (
              <button
                key={avatar.id}
                type="button"
                className={`bot-avatar-option${avatarId === avatar.id ? " is-selected" : ""}`}
                onClick={() => setAvatarId(avatar.id)}
                aria-label={avatar.label}
                aria-pressed={avatarId === avatar.id}
              >
                <span className="pixel-avatar-mini" style={{ "--pixel-color": avatarColor } as CSSProperties}>
                  <span className="pixel-avatar-grid">
                    {avatar.rows.flatMap((row, rowIndex) => [...row].map((cell, cellIndex) => (
                      <i className={`pixel-cell pixel-${cell}`} key={`${rowIndex}-${cellIndex}`} />
                    )))}
                  </span>
                </span>
              </button>
            ))}
          </div>
          <div className="bot-color-options" aria-label="选择头像颜色">
            {PIXEL_AVATAR_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                className={`bot-color-option${avatarColor === color ? " is-selected" : ""}`}
                style={{ background: color }}
                onClick={() => setAvatarColor(color)}
                aria-label={`颜色 ${color}`}
                aria-pressed={avatarColor === color}
              />
            ))}
          </div>
        </div>
        <label className="bot-model-field">
          <span>默认模型</span>
          <ModelPicker
            presets={presets.filter(isWorkablePreset)}
            models={models}
            workspaceId={bot?.workspaceId || "default"}
            value={presetId}
            change={setPresetId}
            favorites={favorites}
            toggleFavorite={(id) => setFavorites((old) => old.includes(id) ? old.filter((item) => item !== id) : [...old, id])}
            disabled={preview}
          />
          <small className="bot-model-hint">模型和通道分开选择；留空时使用 MMS 默认模型。</small>
        </label>
        <p className="bot-shared-machine-note">
          共享全局电脑 · 目录由 Bot 自己处理
        </p>
        <label>
          角色指引
          <textarea
            value={systemPrompt}
            onChange={(event) => setSystemPrompt(event.target.value)}
            rows={4}
            placeholder="例如：先确认目标，再执行，并用简短结论回报。"
          />
        </label>
        <label className="bot-check">
          <input
            type="checkbox"
            checked={wakeEnabled}
            onChange={(event) => setWakeEnabled(event.target.checked)}
          />
          <span>允许定时任务自动唤醒</span>
        </label>
        {error && (
          <p className="bot-inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="bot-dialog-actions">
          <button className="bot-quiet-button" type="button" onClick={onClose}>
            取消
          </button>
          <button
            className="bot-primary-button"
            type="button"
            onClick={() => void save()}
            disabled={preview || busy || !name.trim()}
          >
            {busy ? (
              <>
                <LoaderCircle className="bot-spin" size={15} />
                保存中…
              </>
            ) : (
              "保存 Bot"
            )}
          </button>
        </div>
      </section>
    </div>
  );
}

export function BotStudio({
  data = emptyBootstrap,
  onOpenSession,
  onExit,
}: BotStudioProps) {
  const initial = data as BotBootstrap;
  const [bots, setBots] = useState<BotDefinition[]>(initial.bots || []);
  const [tasks, setTasks] = useState<BotTask[]>([]);
  const [capability, setCapability] = useState<BotCapability | undefined>(
    initial.botCapabilities,
  );
  const [selectedBotId, setSelectedBotId] = useState<string>();
  const [selectedTaskId, setSelectedTaskId] = useState<string>();
  const [messages, setMessages] = useState<BotMessage[]>([]);
  const [artifacts, setArtifacts] = useState<BotArtifact[]>([]);
  const [loadError, setLoadError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [editor, setEditor] = useState<BotDefinition | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<BotDefinition | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [communicationsOpen, setCommunicationsOpen] = useState(false);
  const [communicationPeerId, setCommunicationPeerId] = useState<string>();
  const [communications, setCommunications] = useState<BotCommunication[]>([]);
  const [communicationsError, setCommunicationsError] = useState("");
  const [communicationsRefreshKey, setCommunicationsRefreshKey] = useState(0);
  const selectedTask = tasks.find((task) => task.id === selectedTaskId);
  const selectedBot = bots.find(
    (bot) => bot.id === selectedTask?.botId || bot.id === selectedBotId,
  );
  const activeBot = bots.find((bot) => bot.id === selectedBotId) || bots[0];
  useEffect(() => {
    if (!bots.length) return;
    if (!selectedBotId || !bots.some((bot) => bot.id === selectedBotId)) {
      setSelectedBotId(bots[0].id);
    }
  }, [bots, selectedBotId]);
  useEffect(() => {
    if (selectedTaskId || !selectedBotId) return;
    const latest = tasks.find((item) => item.botId === selectedBotId);
    if (latest) setSelectedTaskId(latest.id);
  }, [selectedBotId, selectedTaskId, tasks]);
  useEffect(() => {
    setMemoryOpen(false);
    setCommunicationsOpen(false);
    setCommunicationPeerId(undefined);
  }, [selectedBotId, communicationsRefreshKey]);

  const sync = useCallback(async (signal?: AbortSignal) => {
    if (isPreview) return;
    const [botResponse, taskResponse, statusResponse] = await Promise.all([
      request<{ bots: BotDefinition[] }>("/bots", undefined, signal),
      request<{ tasks: BotTask[] }>("/tasks", undefined, signal),
      request<BotCapability>("/bots/status", undefined, signal),
    ]);
    setBots(botResponse.bots || []);
    setTasks(taskResponse.tasks || []);
    setCapability(statusResponse);
  }, []);
  useEffect(() => {
    if (isPreview) return;
    let disposed = false;
    let active: AbortController | null = null;
    let timer = 0;
    const poll = async () => {
      if (disposed) return;
      active = new AbortController();
      try {
        await sync(active.signal);
        if (!disposed) setLoadError("");
      } catch (cause) {
        if (
          !disposed &&
          !(cause instanceof DOMException && cause.name === "AbortError")
        )
          setLoadError(
            cause instanceof Error ? cause.message : "Bot 状态暂时无法读取。",
          );
      } finally {
        active = null;
        if (!disposed) timer = window.setTimeout(poll, 3000);
      }
    };
    void poll();
    return () => {
      disposed = true;
      active?.abort();
      window.clearTimeout(timer);
    };
  }, [sync]);
  useEffect(() => {
    const botTasks = selectedBotId
      ? tasks.filter((item) => item.botId === selectedBotId)
      : [];
    if (isPreview || !selectedBotId || botTasks.length === 0) {
      setMessages([]);
      setArtifacts([]);
      setDetailError("");
      return;
    }
    let disposed = false;
    let active: AbortController | null = null;
    let timer = 0;
    const poll = async () => {
      if (disposed) return;
      active = new AbortController();
      const signal = active.signal;
      try {
        const details = await Promise.all(
          botTasks.map(async (item) => {
            const [messageResponse, artifactResponse] = await Promise.all([
              request<{ messages: BotMessage[] }>(
                `/tasks/${encodeURIComponent(item.id)}/messages`,
                undefined,
                signal,
              ),
              request<{ artifacts: BotArtifact[] }>(
                `/tasks/${encodeURIComponent(item.id)}/artifacts`,
                undefined,
                signal,
              ),
            ]);
            return {
              taskId: item.id,
              messages: (messageResponse.messages || []).map((message) => ({
                ...message,
                taskId: item.id,
              })),
              artifacts: (artifactResponse.artifacts || []).map((artifact) => ({
                ...artifact,
                taskId: item.id,
              })),
            };
          }),
        );
        if (!disposed) {
          setMessages(details.flatMap((detail) => detail.messages));
          setArtifacts(
            details
              .flatMap((detail) => detail.artifacts)
              .map((item) => ({ ...item, url: safeUrl(item.url) }))
              .filter((item) => item.url),
          );
          setDetailError("");
        }
      } catch (cause) {
        if (
          !disposed &&
          !(cause instanceof DOMException && cause.name === "AbortError")
        )
          setDetailError(
            cause instanceof Error ? cause.message : "任务详情暂时无法读取。",
          );
      } finally {
        active = null;
        if (!disposed) timer = window.setTimeout(poll, 2500);
      }
    };
    void poll();
    return () => {
      disposed = true;
      active?.abort();
      window.clearTimeout(timer);
    };
  }, [selectedBotId, tasks]);

  useEffect(() => {
    if (isPreview || !selectedBotId) {
      setCommunications([]);
      setCommunicationsError("");
      return;
    }
    let disposed = false;
    let active: AbortController | null = null;
    let timer = 0;
    const poll = async () => {
      if (disposed) return;
      active = new AbortController();
      try {
        const response = await request<{ messages: BotCommunication[] }>(
          `/bots/${encodeURIComponent(selectedBotId)}/communications`,
          undefined,
          active.signal,
        );
        if (!disposed) {
          setCommunications(response.messages || []);
          setCommunicationsError("");
        }
      } catch (cause) {
        if (!disposed && !(cause instanceof DOMException && cause.name === "AbortError")) {
          setCommunicationsError(
            cause instanceof Error ? cause.message : "协作记录暂时无法读取。",
          );
        }
      } finally {
        active = null;
        if (!disposed) timer = window.setTimeout(poll, 2500);
      }
    };
    void poll();
    return () => {
      disposed = true;
      active?.abort();
      window.clearTimeout(timer);
    };
  }, [selectedBotId]);

  const run = useCallback(
    async <T,>(path: string, payload: Record<string, unknown> = {}) => {
      if (isPreview) throw previewMutationError();
      return mutate<T>(path, payload);
    },
    [],
  );
  const deleteBot = useCallback(async () => {
    if (!deleteTarget || deleteBusy) return;
    setDeleteBusy(true);
    setDeleteError("");
    try {
      await run(`/bots/${encodeURIComponent(deleteTarget.id)}/delete`);
      const deletedId = deleteTarget.id;
      setBots((current) => current.filter((item) => item.id !== deletedId));
      setTasks((current) => current.filter((item) => item.botId !== deletedId));
      if (selectedBotId === deletedId) {
        setSelectedBotId(undefined);
        setSelectedTaskId(undefined);
      }
      setDeleteTarget(null);
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : "Bot 删除失败，请稍后重试。");
    } finally {
      setDeleteBusy(false);
    }
  }, [deleteBusy, deleteTarget, run, selectedBotId]);
  const refreshInBackground = useCallback(() => {
    void sync().catch((cause) =>
      setLoadError(
        cause instanceof Error ? cause.message : "Bot 状态刷新失败。",
      ),
    );
  }, [sync]);
  const dispatch: BotAction = useCallback(
    async (payload: BotDispatchPayload): Promise<BotDispatchResult> => {
      const task = await run<BotTask>(
        `/bots/${encodeURIComponent(payload.botId)}/tasks`,
        {
          prompt: payload.prompt,
          ...(payload.runAt ? { runAt: payload.runAt } : {}),
          wake: payload.wake,
          ...(payload.parentTaskId
            ? { parentTaskId: payload.parentTaskId }
            : {}),
        },
      );
      setSelectedTaskId(task.id);
      setTasks((current) => [
        task,
        ...current.filter((item) => item.id !== task.id),
      ]);
      refreshInBackground();
      return { task };
    },
    [refreshInBackground, run],
  );
  const autoDispatch = useCallback(
    async (prompt: string) => {
      const result = await run<{ task: BotTask; bot: BotDefinition }>(
        "/bots/auto/tasks",
        { prompt, wake: true },
      );
      setSelectedBotId(result.bot.id);
      setSelectedTaskId(result.task.id);
      setTasks((current) => [
        result.task,
        ...current.filter((item) => item.id !== result.task.id),
      ]);
      refreshInBackground();
    },
    [refreshInBackground, run],
  );
  const wake = useCallback(
    async (taskId: string) => {
      const task = await run<BotTask>(
        `/tasks/${encodeURIComponent(taskId)}/wake`,
      );
      setTasks((current) =>
        current.map((item) => (item.id === task.id ? task : item)),
      );
      refreshInBackground();
    },
    [refreshInBackground, run],
  );
  const cancel = useCallback(
    async (taskId: string) => {
      const task = await run<BotTask>(
        `/tasks/${encodeURIComponent(taskId)}/cancel`,
      );
      setTasks((current) =>
        current.map((item) => (item.id === task.id ? task : item)),
      );
      refreshInBackground();
    },
    [refreshInBackground, run],
  );
  const followUp = useCallback(
    async (taskId: string, content: string) => {
      await run(`/tasks/${encodeURIComponent(taskId)}/messages`, { content });
      refreshInBackground();
    },
    [refreshInBackground, run],
  );
  const retry = useCallback(
    async (task: BotTask) => {
      await dispatch({
        botId: task.botId,
        prompt: task.prompt,
        wake: true,
        parentTaskId: task.parentTaskId || undefined,
      });
    },
    [dispatch],
  );
  const allEvents: BotEvent[] = useMemo(
    () =>
      messages.map((message) => ({
        id: message.id,
        taskId: message.taskId,
        senderBotId: message.senderBotId,
        sourceKind: message.sourceKind,
        type: message.type,
        content: message.content,
        createdAt: message.createdAt,
      })),
    [messages],
  );
  const editorBot = editor === "new" ? undefined : editor || undefined;
  const onBotSaved = (bot: BotDefinition) => {
    setBots((current) => {
      const exists = current.some((item) => item.id === bot.id);
      return exists
        ? current.map((item) => (item.id === bot.id ? bot : item))
        : [bot, ...current];
    });
    setSelectedBotId(bot.id);
  };
  const createDraftBot = useCallback(async () => {
    if (isPreview) {
      setEditor("new");
      return;
    }
    try {
      const draft = await run<BotDefinition>("/bots", {
        name: "新 Bot",
        description: "随时可以接活",
        systemPrompt: "",
        presetId: null,
        wakeEnabled: true,
      });
      onBotSaved(draft);
      setSelectedTaskId(undefined);
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "新建 Bot 失败，请稍后重试。");
    }
  }, [isPreview, onBotSaved, run]);
  const previewNotice = isPreview
    ? "预览模式：这里不会创建 Bot、启动任务或调用本地执行器。"
    : capability?.available === false
      ? `Pi 执行器暂不可用${capability.reason ? `：${capability.reason}` : "。"}`
      : capability?.available === true
      ? `Pi 执行器可用${capability.maxConcurrent ? ` · 最多并行 ${capability.maxConcurrent} 个任务` : ""}${capability.browser ? " · Ego 浏览器已接入" : " · Ego 浏览器未安装"}`
        : "执行器状态尚未读取。";
  return (
    <BotWorkspace>
      {editor && (
        <BotEditor
          bot={editorBot}
          presets={data.presets}
          models={data.models}
          preview={isPreview}
          onClose={() => setEditor(null)}
          onSaved={onBotSaved}
        />
      )}
      <aside className="bot-sidebar">
        <BotList
          bots={bots}
          tasks={tasks}
          selectedBotId={selectedBotId}
          onSelect={(bot) => {
            setSelectedBotId(bot.id);
            setSelectedTaskId(undefined);
          }}
          onWake={(botId) => {
            const waiting = tasks.find(
              (task) => task.botId === botId && task.status === "waiting",
            );
            if (waiting)
              void wake(waiting.id).catch((cause) =>
                setLoadError(
                  cause instanceof Error ? cause.message : "任务唤醒失败。",
                ),
              );
          }}
          onEdit={(bot) => setEditor(bot)}
          onDelete={(bot) => {
            setDeleteError("");
            setDeleteTarget(bot);
          }}
          onCreate={() => void createDraftBot()}
        />
        <AutoWakeControl
          enabled={Boolean(activeBot?.wakeEnabled)}
          onChange={(enabled) => {
            const bot = activeBot;
            if (bot)
              void run<BotDefinition>(`/bots/${encodeURIComponent(bot.id)}`, {
                name: bot.name,
                description: bot.description,
                systemPrompt: bot.systemPrompt,
                presetId: bot.presetId,
                wakeEnabled: enabled,
              })
                .then((saved) => {
                  setBots((current) =>
                    current.map((item) =>
                      item.id === saved.id ? saved : item,
                    ),
                  );
                  refreshInBackground();
                })
                .catch((cause) =>
                  setLoadError(
                    cause instanceof Error
                      ? cause.message
                      : "自动唤醒设置保存失败。",
                  ),
                );
          }}
          disabled={isPreview || !activeBot}
        />
        {onExit && (
          <button
            className="bot-pilot-return"
            type="button"
            onClick={onExit}
            title="返回 MMS Pilot"
          >
            <ArrowLeft size={14} />
            返回 Pilot
          </button>
        )}
      </aside>
      {deleteTarget && (
        <div className="bot-dialog-scrim" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget && !deleteBusy) setDeleteTarget(null);
        }}>
          <section className="bot-create-dialog bot-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="bot-delete-title">
            <div className="bot-dialog-heading">
              <div>
                <h2 id="bot-delete-title">删除 {deleteTarget.name}？</h2>
                <p>会移除这个 Bot 的长期记忆、聊天记录和成果文件，其他 Bot 不受影响。</p>
              </div>
              <button className="bot-icon-button" type="button" onClick={() => setDeleteTarget(null)} disabled={deleteBusy} aria-label="关闭"><X size={16} /></button>
            </div>
            {deleteError && <p className="bot-inline-error" role="alert">{deleteError}</p>}
            <div className="bot-dialog-actions">
              <button className="bot-quiet-button" type="button" onClick={() => setDeleteTarget(null)} disabled={deleteBusy}>取消</button>
              <button className="bot-danger-button" type="button" onClick={() => void deleteBot()} disabled={deleteBusy}>{deleteBusy ? "删除中…" : "删除 Bot"}</button>
            </div>
          </section>
        </div>
      )}
      <main className="bot-main">
        <div className="bot-chat-toolbar">
          <div className="bot-header-actions">
            {onExit && <button className="bot-quiet-button bot-exit-button" type="button" onClick={onExit} title="返回 MMS Pilot"><ArrowLeft size={14} /> Pilot</button>}
            <span
              className={`bot-executor ${capability?.available === true ? "available" : capability?.available === false ? "unavailable" : "unknown"}`}
            >
              <span />
              {previewNotice}
            </span>
            <button
              className="bot-quiet-button"
              type="button"
              onClick={() => {
                setRefreshing(true);
                void sync()
                  .catch((cause) =>
                    setLoadError(
                      cause instanceof Error
                        ? cause.message
                        : "Bot 状态刷新失败。",
                    ),
                  )
                  .finally(() => setRefreshing(false));
              }}
              disabled={isPreview || refreshing}
              title="刷新 Bot 和任务"
            >
              <RefreshCw className={refreshing ? "bot-spin" : ""} size={14} />
              刷新
            </button>
          </div>
        </div>
        {loadError && (
          <p className="bot-banner bot-banner-error" role="alert">
            <CircleAlert size={15} />
            {loadError}
          </p>
        )}
        {detailError && (
          <p className="bot-banner bot-banner-error" role="alert">
            <CircleAlert size={15} />
            {detailError}
          </p>
        )}
        <BotChat
          bot={activeBot || selectedBot}
          bots={bots}
          tasks={tasks}
          task={selectedTask}
          events={allEvents}
          artifacts={artifacts}
          onSelectBot={(bot) => setSelectedBotId(bot.id)}
          onSelectTask={(task) => setSelectedTaskId(task.id)}
          onDispatch={dispatch}
          onAutoDispatch={autoDispatch}
          onFollowUp={(content) =>
            selectedTask ? followUp(selectedTask.id, content) : undefined
          }
          onCancel={() =>
            selectedTask &&
            void cancel(selectedTask.id).catch((cause) =>
              setDetailError(
                cause instanceof Error ? cause.message : "任务取消失败。",
              ),
            )
          }
          onWake={() =>
            selectedTask &&
            void wake(selectedTask.id).catch((cause) =>
              setDetailError(
                cause instanceof Error ? cause.message : "任务唤醒失败。",
              ),
            )
          }
          onRetry={(task) =>
            void retry(task).catch((cause) =>
              setLoadError(
                cause instanceof Error ? cause.message : "任务重试失败。",
              ),
            )
          }
          onOpenMemory={() => setMemoryOpen(true)}
          presets={data.presets}
          onUpdateBot={async (botId, patch) => {
            const current = bots.find((item) => item.id === botId);
            if (!current) return;
            const saved = await run<BotDefinition>(`/bots/${encodeURIComponent(botId)}`, {
              name: patch.name ?? current.name,
              description: patch.description ?? current.description,
              systemPrompt: patch.systemPrompt ?? current.systemPrompt,
              presetId: patch.presetId ?? current.presetId,
              wakeEnabled: current.wakeEnabled,
              avatarId: current.avatarId,
              avatarColor: current.avatarColor,
            });
            setBots((items) => items.map((item) => (item.id === saved.id ? saved : item)));
          }}
          onExit={onExit}
          communications={communications}
          onOpenCommunications={(peerBotId) => {
            setCommunicationPeerId(peerBotId);
            setCommunicationsOpen(true);
          }}
          disabled={isPreview || capability?.available === false}
        />
        {memoryOpen && activeBot && (
          <BotMemoryPanel
            bot={activeBot}
            preview={isPreview}
            onClose={() => setMemoryOpen(false)}
          />
        )}
        {communicationsOpen && (activeBot || selectedBot) && (
          <BotCommunications
            bot={(activeBot || selectedBot)!}
            bots={bots}
            messages={communications}
            peerBotId={communicationPeerId}
            preview={isPreview}
            error={communicationsError}
            onClose={() => {
              setCommunicationsOpen(false);
              setCommunicationPeerId(undefined);
            }}
            onRefresh={() => {
              setCommunicationsError("");
              setCommunicationsRefreshKey((current) => current + 1);
            }}
            onWake={async (message) => {
              if (isPreview || !(activeBot || selectedBot)) return;
              await mutate(
                `/bots/${encodeURIComponent((activeBot || selectedBot)!.id)}/communications/${encodeURIComponent(message.id)}/wake`,
                {},
              );
            }}
          />
        )}
      </main>
    </BotWorkspace>
  );
}
