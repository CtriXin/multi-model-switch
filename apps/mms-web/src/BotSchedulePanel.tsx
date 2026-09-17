import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  AlarmClockCheck,
  LoaderCircle,
  Pause,
  Play,
  Timer,
  Trash2,
  X,
} from "lucide-react";
import { mutate } from "./api";
import { formatScheduledTaskTime } from "./bot-visual-system.ts";
import type { BotDefinition, BotTask } from "./Bot";
import {
  MAX_PROMPT_CHARS,
  MAX_SCHEDULES_PER_BOT,
  WEEKDAY_LABELS,
  apiErrorCode,
  composerRuleFromForm,
  defaultComposerForm,
  describeRule,
  formFromRule,
  localTimezone,
  overlapPolicyLabel,
  remainingScheduleQuota,
  scheduleErrorMessage,
  scheduleRunState,
  skipNote,
  validateComposerForm,
  type BotSchedule,
  type ComposerScheduleForm,
  type OverlapPolicy,
} from "./bot-schedules";
import "./bot-memory.css";

interface BotSchedulePanelProps {
  bot: BotDefinition;
  schedules: BotSchedule[];
  tasks?: BotTask[];
  preview?: boolean;
  onClose: () => void;
  onChange?: () => void;
  onSelectTask?: (task: BotTask) => void;
  wakeControl?: ReactNode;
}

export function scheduleEnablePath(botId: string, scheduleId: string, enabled: boolean): string {
  const action = enabled ? "enable" : "disable";
  return `/bots/${encodeURIComponent(botId)}/schedules/${encodeURIComponent(scheduleId)}/${action}`;
}

function scheduleDeletePath(botId: string, scheduleId: string): string {
  return `/bots/${encodeURIComponent(botId)}/schedules/${encodeURIComponent(scheduleId)}/delete`;
}

function scheduleEditPath(botId: string, scheduleId: string): string {
  return `/bots/${encodeURIComponent(botId)}/schedules/${encodeURIComponent(scheduleId)}`;
}

export function BotSchedulePanel({
  bot,
  schedules,
  tasks = [],
  preview = false,
  onClose,
  onChange,
  onSelectTask,
  wakeControl,
}: BotSchedulePanelProps) {
  const panelRef = useRef<HTMLElement>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ComposerScheduleForm>(() => defaultComposerForm());
  const [prompt, setPrompt] = useState("");
  const [overlapPolicy, setOverlapPolicy] = useState<OverlapPolicy>("skip");
  const [baseline, setBaseline] = useState("");
  const [busyId, setBusyId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const currentSnapshot = useMemo(
    () =>
      JSON.stringify({
        editingId,
        prompt,
        overlapPolicy,
        form,
      }),
    [editingId, prompt, overlapPolicy, form],
  );
  const isDirty = Boolean(editingId) && currentSnapshot !== baseline;
  const isDirtyRef = useRef(isDirty);
  isDirtyRef.current = isDirty;

  const handleClose = () => {
    if (isDirtyRef.current) {
      const discard =
        typeof window !== "undefined" && typeof window.confirm === "function"
          ? window.confirm("当前定时已修改，确定要放弃未保存的修改并关闭吗？")
          : true;
      if (!discard) return;
    }
    onClose();
  };

  useEffect(() => {
    const handlePointerDown = (e: PointerEvent) => {
      const panel = panelRef.current;
      if (!panel) return;
      const target = e.target as HTMLElement | null;
      if (!target) return;
      if (panel.contains(target)) return;
      if (target.closest?.('[aria-label="打开定时面板"], [title="定时"]')) {
        return;
      }
      handleClose();
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        handleClose();
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  function startEdit(schedule: BotSchedule) {
    const nextForm = formFromRule(schedule.rule);
    const nextPrompt = schedule.prompt;
    const nextOverlap = schedule.overlapPolicy === "queue" ? "queue" : "skip";
    setEditingId(schedule.id);
    setForm(nextForm);
    setPrompt(nextPrompt);
    setOverlapPolicy(nextOverlap);
    setBaseline(
      JSON.stringify({
        editingId: schedule.id,
        prompt: nextPrompt,
        overlapPolicy: nextOverlap,
        form: nextForm,
      }),
    );
    setError("");
  }

  function cancelEdit() {
    setEditingId(null);
    setBaseline("");
    setError("");
  }

  async function toggleEnabled(schedule: BotSchedule) {
    if (preview || busyId) return;
    setBusyId(schedule.id);
    setError("");
    try {
      await mutate(scheduleEnablePath(bot.id, schedule.id, !schedule.enabled), {});
      onChange?.();
    } catch (cause) {
      setError(
        scheduleErrorMessage(
          apiErrorCode(cause),
          cause instanceof Error ? cause.message : "启停定时失败，请稍后重试。",
          schedules.length,
        ),
      );
    } finally {
      setBusyId("");
    }
  }

  async function removeSchedule(schedule: BotSchedule) {
    if (preview || busyId) return;
    const confirmed =
      typeof window !== "undefined" && typeof window.confirm === "function"
        ? window.confirm("删除这条定时？已经跑出来的任务会保留。")
        : true;
    if (!confirmed) return;
    setBusyId(schedule.id);
    setError("");
    try {
      await mutate(scheduleDeletePath(bot.id, schedule.id), {});
      if (editingId === schedule.id) cancelEdit();
      onChange?.();
    } catch (cause) {
      setError(
        scheduleErrorMessage(
          apiErrorCode(cause),
          cause instanceof Error ? cause.message : "删除定时失败，请稍后重试。",
          schedules.length,
        ),
      );
    } finally {
      setBusyId("");
    }
  }

  async function saveEdit() {
    if (!editingId || preview || saving) return;
    const trimmed = prompt.trim();
    if (!trimmed) {
      setError("请填写定时要执行的内容。");
      return;
    }
    if (trimmed.length > MAX_PROMPT_CHARS) {
      setError(`内容不能超过 ${MAX_PROMPT_CHARS} 字。`);
      return;
    }
    const invalid = validateComposerForm(form);
    if (invalid) {
      setError(invalid);
      return;
    }
    setSaving(true);
    setError("");
    try {
      const rule = composerRuleFromForm(form);
      await mutate(scheduleEditPath(bot.id, editingId), {
        prompt: trimmed,
        rule,
        timezone: localTimezone(),
        overlapPolicy,
      });
      cancelEdit();
      onChange?.();
    } catch (cause) {
      setError(
        scheduleErrorMessage(
          apiErrorCode(cause),
          cause instanceof Error ? cause.message : "保存定时失败，请稍后重试。",
          schedules.length,
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  const quota = remainingScheduleQuota(schedules.length);
  const gated = bot.wakeEnabled === false;

  return (
    <aside ref={panelRef} className="bot-memory-panel bot-schedule-panel" aria-label={`${bot.name} 的定时`}>
      <div className="bot-memory-heading">
        <div className="bot-memory-title">
          <span className="bot-memory-icon" aria-hidden="true">
            <Timer size={17} />
          </span>
          <div>
            <h2>定时</h2>
            <p>
              {bot.name} · {schedules.length}/{MAX_SCHEDULES_PER_BOT}
            </p>
          </div>
        </div>
        <button
          className="bot-memory-icon-button"
          type="button"
          onClick={handleClose}
          aria-label="关闭定时"
          title="关闭"
        >
          <X size={17} />
        </button>
      </div>

      <div className="bot-memory-body">
        {preview && <p className="bot-memory-preview">预览模式：真实更新已禁用。</p>}
        {wakeControl && <div className="bot-schedule-master">{wakeControl}</div>}
        {gated && schedules.length > 0 && (
          <p className="bot-schedule-gate-note" role="status">
            自动唤醒已关闭，列表里的定时都被总闸拦住，到点不会触发。这不是单条「已暂停」。
          </p>
        )}
        {quota && <p className="bot-schedule-quota">{quota}</p>}
        {error && (
          <p className="bot-inline-error" role="alert">
            {error}
          </p>
        )}
        {!schedules.length ? (
          <div className="bot-schedule-empty">
            <p>这个 Bot 现在没有定时安排。</p>
            <p>在聊天框右边的定时按钮里选周期，或者直接跟它说「每天早上九点…」。</p>
            <p className="bot-schedule-empty-bound">Pilot 关着的时候定时不会触发，这是本机应用的边界。</p>
          </div>
        ) : (
          <ul className="bot-schedule-list">
            {schedules.map((schedule) => {
              const state = scheduleRunState(schedule, new Date(), { wakeEnabled: bot.wakeEnabled });
              const missed = skipNote(schedule);
              const lastTask = tasks.find((item) => item.id === schedule.lastTaskId);
              const editing = editingId === schedule.id;
              return (
                <li
                  key={schedule.id}
                  className={`bot-schedule-row is-${state.kind}${gated ? " is-gated" : ""}${
                    schedule.enabled ? "" : " is-paused"
                  }`}
                >
                  <div className="bot-schedule-row-main">
                    <strong>{describeRule(schedule.rule)}</strong>
                    <span className={`bot-schedule-state is-${state.kind}`}>{state.label}</span>
                  </div>
                  <p className="bot-schedule-prompt" title={schedule.prompt}>
                    {schedule.prompt}
                  </p>
                  {state.detail && <p className="bot-schedule-meta">{state.detail}</p>}
                  {schedule.nextRunAt && state.kind !== "completed" && state.kind !== "invalid" && (
                    <p className="bot-schedule-meta">
                      下次 {formatScheduledTaskTime(schedule.nextRunAt)}
                    </p>
                  )}
                  {schedule.lastRunAt && (
                    <p className="bot-schedule-meta">
                      上次 {formatScheduledTaskTime(schedule.lastRunAt)}
                      {lastTask && onSelectTask && (
                        <button
                          type="button"
                          className="bot-schedule-link"
                          onClick={() => onSelectTask(lastTask)}
                        >
                          查看上次任务
                        </button>
                      )}
                    </p>
                  )}
                  {missed && <p className="bot-schedule-meta">{missed}</p>}
                  <p className="bot-schedule-meta">{overlapPolicyLabel(schedule.overlapPolicy)}</p>
                  <div className="bot-schedule-actions">
                    <button
                      type="button"
                      className="bot-quiet-button"
                      disabled={preview || busyId === schedule.id || state.kind === "invalid"}
                      onClick={() => void toggleEnabled(schedule)}
                    >
                      {busyId === schedule.id ? (
                        <LoaderCircle size={13} className="bot-spin" />
                      ) : schedule.enabled ? (
                        <Pause size={13} />
                      ) : (
                        <Play size={13} />
                      )}
                      <span>{schedule.enabled ? "暂停" : "恢复"}</span>
                    </button>
                    <button
                      type="button"
                      className="bot-quiet-button"
                      disabled={preview || busyId === schedule.id}
                      onClick={() => (editing ? cancelEdit() : startEdit(schedule))}
                    >
                      {editing ? "收起" : "编辑"}
                    </button>
                    <button
                      type="button"
                      className="bot-quiet-button"
                      disabled={preview || busyId === schedule.id}
                      onClick={() => void removeSchedule(schedule)}
                    >
                      <Trash2 size={13} />
                      <span>删除</span>
                    </button>
                  </div>
                  {editing && (
                    <div className="bot-schedule-edit">
                      <label className="bot-field">
                        <span>内容</span>
                        <textarea
                          value={prompt}
                          rows={3}
                          maxLength={MAX_PROMPT_CHARS}
                          onChange={(event) => setPrompt(event.target.value)}
                        />
                      </label>
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
                            onClick={() => setForm((current) => ({ ...current, kind }))}
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
                            onChange={(event) =>
                              setForm((current) => ({ ...current, onceDate: event.target.value }))
                            }
                            aria-label="日期"
                          />
                          <input
                            type="text"
                            className="bot-schedule-time-input"
                            value={form.onceTime}
                            maxLength={5}
                            onChange={(event) =>
                              setForm((current) => ({ ...current, onceTime: event.target.value }))
                            }
                            aria-label="时间"
                          />
                        </div>
                      )}
                      {form.kind === "daily" && (
                        <label className="bot-field">
                          <span>每天</span>
                          <input
                            type="text"
                            className="bot-schedule-time-input"
                            value={form.atLocalTime}
                            maxLength={5}
                            onChange={(event) =>
                              setForm((current) => ({ ...current, atLocalTime: event.target.value }))
                            }
                            aria-label="每天时间"
                          />
                        </label>
                      )}
                      {form.kind === "weekly" && (
                        <div className="bot-schedule-weekdays" role="group" aria-label="星期">
                          {WEEKDAY_LABELS.map((label, weekday) => (
                            <button
                              key={label}
                              type="button"
                              className={`bot-schedule-kind-tab${form.weekday === weekday ? " is-selected" : ""}`}
                              onClick={() => setForm((current) => ({ ...current, weekday }))}
                            >
                              {label}
                            </button>
                          ))}
                          <input
                            type="text"
                            className="bot-schedule-time-input"
                            value={form.atLocalTime}
                            maxLength={5}
                            onChange={(event) =>
                              setForm((current) => ({ ...current, atLocalTime: event.target.value }))
                            }
                            aria-label="每周时间"
                          />
                        </div>
                      )}
                      {form.kind === "interval" && (
                        <label className="bot-field">
                          <span>间隔小时</span>
                          <input
                            type="number"
                            min={0.09}
                            step="any"
                            className="bot-schedule-select"
                            value={form.intervalHours}
                            onChange={(event) =>
                              setForm((current) => ({
                                ...current,
                                intervalHours: Number(event.target.value),
                              }))
                            }
                            aria-label="间隔小时"
                          />
                        </label>
                      )}
                      <label className="bot-field">
                        <span>重叠</span>
                        <select
                          className="bot-schedule-select"
                          value={overlapPolicy}
                          onChange={(event) =>
                            setOverlapPolicy(event.target.value === "queue" ? "queue" : "skip")
                          }
                        >
                          <option value="skip">上一轮在跑就跳过</option>
                          <option value="queue">排队执行</option>
                        </select>
                      </label>
                      <p className="bot-schedule-meta">时区 {schedule.timezone}</p>
                      <div className="bot-schedule-custom-actions">
                        <button type="button" className="bot-schedule-back-btn" onClick={cancelEdit}>
                          取消
                        </button>
                        <button
                          type="button"
                          className="bot-schedule-confirm-btn"
                          disabled={saving || Boolean(validateComposerForm(form))}
                          onClick={() => void saveEdit()}
                        >
                          {saving ? "保存中…" : "保存"}
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        <p className="bot-schedule-footnote">
          <AlarmClockCheck size={12} />
          Pilot 关着的时候定时不会触发。
        </p>
      </div>
    </aside>
  );
}
