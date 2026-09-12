import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Brain,
  Check,
  LoaderCircle,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { isPreview, mutate, request } from "./api";
import { RichText } from "./components";
import type { BotDefinition } from "./Bot";
import "./bot-memory.css";

type MemoryKind = "fact" | "task";
type MemorySource = "user" | "bot" | "task";

export interface BotMemoryNote {
  id: string;
  content: string;
  kind: MemoryKind;
  source: MemorySource;
  taskId?: string | null;
  createdAt: string;
  updatedAt: string;
}

interface MemoryLimits {
  maxFacts: number;
  maxTasks: number;
  maxContentChars: number;
}

interface MemorySettings {
  memoryEnabled: boolean;
  memoryBudgetTokens: number;
  autoCompact: boolean;
  compactAtPercent: number;
}

interface MemoryContext {
  contextWindow: number | null;
  usedTokens: number | null;
  usedPercent: number | null;
  source: "live" | "cached" | "unknown";
  lastCompactedAt: string | null;
  compactionError: string | null;
}

interface MemoryView {
  notes: BotMemoryNote[];
  limits: MemoryLimits;
  settings: MemorySettings;
  context: MemoryContext;
}

interface BotMemoryPanelProps {
  bot: BotDefinition;
  preview?: boolean;
  onClose: () => void;
}

const emptySettings: MemorySettings = {
  memoryEnabled: true,
  memoryBudgetTokens: 2000,
  autoCompact: true,
  compactAtPercent: 70,
};

function sourceLabel(source: MemorySource) {
  return source === "user" ? "用户" : source === "bot" ? "Bot" : "任务摘要";
}

function contextLabel(source: MemoryContext["source"]) {
  return source === "live" ? "实时" : source === "cached" ? "缓存" : "未知";
}

function formatDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function BotMemoryPanel({
  bot,
  preview = false,
  onClose,
}: BotMemoryPanelProps) {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<MemoryView | null>(null);
  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [settings, setSettings] = useState<MemorySettings>(emptySettings);
  const [loading, setLoading] = useState(!preview);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const requestVersion = useRef(0);

  useEffect(() => {
    setQuery("");
    setView(null);
    setDraft("");
    setEditingId(null);
    setSettings(emptySettings);
    setError("");
    setSaved("");
  }, [bot.id]);

  useEffect(() => {
    if (preview) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const version = ++requestVersion.current;
    setView(null);
    setLoading(true);
    setError("");
    const suffix = query.trim()
      ? `?query=${encodeURIComponent(query.trim())}`
      : "";
    void request<MemoryView>(
      `/bots/${encodeURIComponent(bot.id)}/memory${suffix}`,
      undefined,
      controller.signal,
    )
      .then((next) => {
        if (controller.signal.aborted || version !== requestVersion.current)
          return;
        setView(next);
        setSettings(next.settings || emptySettings);
      })
      .catch((cause) => {
        if (controller.signal.aborted || version !== requestVersion.current)
          return;
        setError(cause instanceof Error ? cause.message : "记忆暂时无法读取。");
      })
      .finally(() => {
        if (!controller.signal.aborted && version === requestVersion.current) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [bot.id, preview, query, refreshKey]);

  async function saveMemory(content: string, id?: string) {
    if (preview) {
      setError("当前是预览模式，记忆写入已禁用。");
      return;
    }
    const trimmed = content.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const next = await mutate<MemoryView>(
        `/bots/${encodeURIComponent(bot.id)}/memory`,
        { action: "remember", content: trimmed, ...(id ? { id } : {}) },
      );
      setView(next);
      setDraft("");
      setEditingId(null);
      setSettings(next.settings || settings);
      setSaved(id ? "记忆已更新" : "记忆已添加");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "记忆保存失败。");
    } finally {
      setBusy(false);
    }
  }

  async function forgetMemory(id: string) {
    if (preview) {
      setError("当前是预览模式，记忆删除已禁用。");
      return;
    }
    if (busy) return;
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const next = await mutate<MemoryView>(
        `/bots/${encodeURIComponent(bot.id)}/memory`,
        { action: "forget", id },
      );
      setView(next);
      setSettings(next.settings || settings);
      if (editingId === id) {
        setEditingId(null);
        setDraft("");
      }
      setSaved("记忆已删除");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "记忆删除失败。");
    } finally {
      setBusy(false);
    }
  }

  async function saveSettings() {
    if (preview || busy) {
      if (preview) setError("当前是预览模式，设置保存已禁用。");
      return;
    }
    setBusy(true);
    setError("");
    setSaved("");
    try {
      await mutate<BotDefinition>(`/bots/${encodeURIComponent(bot.id)}`, {
        memoryEnabled: settings.memoryEnabled,
        memoryBudgetTokens: settings.memoryBudgetTokens,
        autoCompact: settings.autoCompact,
        compactAtPercent: settings.compactAtPercent,
      });
      const next = await request<MemoryView>(
        `/bots/${encodeURIComponent(bot.id)}/memory`,
      );
      setView(next);
      setSettings(next.settings || settings);
      setSaved("设置已保存并读回");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "记忆设置保存失败，未确认读回结果。",
      );
    } finally {
      setBusy(false);
    }
  }

  const notes = view?.notes || [];
  const context = view?.context;
  return (
    <aside className="bot-memory-panel" aria-label={`${bot.name} 的记忆`}>
      <div className="bot-memory-heading">
        <div className="bot-memory-title">
          <span className="bot-memory-icon" aria-hidden="true">
            <Brain size={17} />
          </span>
          <div>
            <h2>记忆</h2>
            <p>{bot.name} 的长期信息与上下文整理</p>
          </div>
        </div>
        <button
          className="bot-memory-icon-button"
          type="button"
          onClick={onClose}
          aria-label="关闭记忆面板"
          title="关闭"
        >
          <X size={17} />
        </button>
      </div>

      <div className="bot-memory-body">
        {preview && (
          <p className="bot-memory-preview">
            预览模式：这里展示记忆面板，真实读写已禁用。
          </p>
        )}
        <label className="bot-memory-search">
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">搜索记忆</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索记忆"
          />
        </label>

        <section className="bot-memory-section">
          <div className="bot-memory-section-heading">
            <h3>已保存</h3>
            <span>{view ? `${notes.length} 条` : "读取中"}</span>
          </div>
          {loading && (
            <p className="bot-memory-muted">
              <LoaderCircle className="bot-spin" size={15} />
              正在读取记忆…
            </p>
          )}
          {!loading && !error && notes.length === 0 && (
            <p className="bot-memory-muted">还没有匹配的记忆。</p>
          )}
          <div className="bot-memory-notes">
            {notes.map((note) => (
              <article className="bot-memory-note" key={note.id}>
                <div className="bot-memory-note-meta">
                  <span>{sourceLabel(note.source)}</span>
                  <span>{note.kind === "fact" ? "事实" : "任务"}</span>
                  <time dateTime={note.updatedAt}>
                    {formatDate(note.updatedAt)}
                  </time>
                </div>
                {editingId === note.id ? (
                  <textarea
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    maxLength={view?.limits.maxContentChars || 2000}
                    aria-label="编辑记忆"
                  />
                ) : (
                  <div className="bot-memory-markdown">
                    <RichText text={note.content} repair />
                  </div>
                )}
                <div className="bot-memory-note-actions">
                  {editingId === note.id ? (
                    <button
                      type="button"
                      onClick={() => void saveMemory(draft, note.id)}
                      disabled={busy || !draft.trim()}
                    >
                      <Save size={13} />
                      保存
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setEditingId(note.id);
                        setDraft(note.content);
                      }}
                      disabled={busy}
                    >
                      编辑
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void forgetMemory(note.id)}
                    disabled={busy}
                    aria-label={`删除记忆 ${note.content.slice(0, 24)}`}
                  >
                    <Trash2 size={13} />
                    删除
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="bot-memory-section bot-memory-add">
          <div className="bot-memory-section-heading">
            <h3>{editingId ? "编辑记忆" : "新增记忆"}</h3>
          </div>
          <textarea
            value={editingId ? "" : draft}
            onChange={(event) => setDraft(event.target.value)}
            maxLength={view?.limits.maxContentChars || 2000}
            placeholder="记录一个对以后有用的事实或任务上下文…"
            aria-label="新增记忆内容"
          />
          <button
            className="bot-memory-primary"
            type="button"
            onClick={() => void saveMemory(draft)}
            disabled={preview || busy || !draft.trim()}
          >
            <Plus size={14} />
            保存记忆
          </button>
        </section>

        <section className="bot-memory-section bot-memory-context">
          <div className="bot-memory-section-heading">
            <h3>上下文</h3>
            <span>{context ? contextLabel(context.source) : "未知"}</span>
          </div>
          <div className="bot-memory-context-grid">
            <span>窗口</span>
            <strong>
              {context?.contextWindow == null
                ? "未知"
                : `${context.contextWindow.toLocaleString()} tokens`}
            </strong>
            <span>已使用</span>
            <strong>
              {context?.usedTokens == null
                ? "未知"
                : `${context.usedTokens.toLocaleString()} tokens`}
            </strong>
            <span>占用</span>
            <strong>
              {context?.usedPercent == null
                ? "未知"
                : `${Number(context.usedPercent.toFixed(1))}%`}
            </strong>
          </div>
          {context?.compactionError && (
            <p className="bot-memory-context-error">
              <AlertCircle size={14} />
              {context.compactionError}
            </p>
          )}
          {context?.lastCompactedAt && (
            <p className="bot-memory-muted">
              上次整理：{formatDate(context.lastCompactedAt)}
            </p>
          )}
        </section>

        <section className="bot-memory-section bot-memory-settings">
          <div className="bot-memory-section-heading">
            <h3>自动整理</h3>
          </div>
          <label className="bot-memory-switch">
            <input
              type="checkbox"
              checked={settings.memoryEnabled}
              onChange={(event) =>
                setSettings((current) => ({
                  ...current,
                  memoryEnabled: event.target.checked,
                }))
              }
            />
            <span>启用长期记忆</span>
          </label>
          <label className="bot-memory-switch">
            <input
              type="checkbox"
              checked={settings.autoCompact}
              onChange={(event) =>
                setSettings((current) => ({
                  ...current,
                  autoCompact: event.target.checked,
                }))
              }
            />
            <span>自动整理上下文</span>
          </label>
          <label className="bot-memory-field">
            <span>
              整理阈值 <strong>{settings.compactAtPercent}%</strong>
            </span>
            <input
              type="range"
              min={50}
              max={90}
              step={1}
              value={settings.compactAtPercent}
              onChange={(event) =>
                setSettings((current) => ({
                  ...current,
                  compactAtPercent: Number(event.target.value),
                }))
              }
            />
          </label>
          <label className="bot-memory-field">
            <span>单轮记忆预算（估算）</span>
            <input
              type="number"
              min={500}
              max={8000}
              step={100}
              value={settings.memoryBudgetTokens}
              onChange={(event) =>
                setSettings((current) => ({
                  ...current,
                  memoryBudgetTokens: Math.min(
                    8000,
                    Math.max(500, Number(event.target.value) || 500),
                  ),
                }))
              }
            />
          </label>
          <p className="bot-memory-muted">
            预算用于提示与整理参考，不承诺硬性 token 限制。
          </p>
          <button
            className="bot-memory-save-settings"
            type="button"
            onClick={() => void saveSettings()}
            disabled={preview || busy}
          >
            <Save size={14} />
            {busy ? "保存中…" : "保存设置"}
          </button>
        </section>

        {error && (
          <p className="bot-memory-error" role="alert">
            <AlertCircle size={15} />
            {error}
          </p>
        )}
        {saved && (
          <p className="bot-memory-saved" role="status">
            <Check size={15} />
            {saved}
          </p>
        )}
        {!preview && view && (
          <button
            className="bot-memory-refresh"
            type="button"
            onClick={() => setRefreshKey((current) => current + 1)}
            disabled={loading}
          >
            <RefreshCw size={13} />
            刷新
          </button>
        )}
      </div>
    </aside>
  );
}
