import { useState, useEffect, useMemo, useRef } from "react";
import { Settings2, X, Plus, Trash2, Check, LoaderCircle } from "lucide-react";
import type { BotDefinition } from "./Bot";
import type { Model, Preset } from "./types";
import { ModelPicker } from "./LaunchOptions";
import {
  parsePreset,
  buildPreset,
  WIZARD_POOL,
  getFocusOptions,
  getBranchOptionsForFocus,
  withCurrentValue,
} from "./bot-presets";
import type { OnboardingAnswers } from "./bot-presets";

interface BotPresetPanelProps {
  bot: BotDefinition;
  onClose: () => void;
  onUpdateBot?: (botId: string, patch: Partial<BotDefinition>) => Promise<void>;
  preview?: boolean;
  presets?: Preset[];
  models?: Model[];
}

function FieldChipSelector({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value?: string;
  options: string[];
  onChange: (val: string) => void;
}) {
  const [customActive, setCustomActive] = useState(false);
  const isPredefined = Boolean(value && options.includes(value));
  const showCustom = customActive || (!isPredefined && Boolean(value));

  return (
    <div className="bot-preset-field">
      <label className="bot-preset-label">{label}</label>
      <div className="bot-onboarding-chips">
        {options.map((opt) => (
          <button
            key={opt}
            type="button"
            className={`bot-onboarding-chip${!showCustom && value === opt ? " is-selected" : ""}`}
            onClick={() => {
              setCustomActive(false);
              onChange(opt);
            }}
          >
            {opt}
          </button>
        ))}
        <button
          type="button"
          className={`bot-onboarding-chip${showCustom ? " is-selected" : ""}`}
          onClick={() => {
            setCustomActive(true);
          }}
        >
          自定义
        </button>
      </div>
      {showCustom && (
        <div style={{ marginTop: 6 }}>
          <input
            type="text"
            className="bot-preset-extra-input"
            value={value || ""}
            placeholder={`输入自定义${label}`}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>
      )}
    </div>
  );
}

export function BotPresetPanel({
  bot,
  presets = [],
  models = [],
  onClose,
  onUpdateBot,
  preview = false,
}: BotPresetPanelProps) {
  const [answers, setAnswers] = useState<OnboardingAnswers>({});
  const [rules, setRules] = useState<string[]>([]);
  const [other, setOther] = useState("");
  const [newRule, setNewRule] = useState("");
  const [newExtraKey, setNewExtraKey] = useState("");
  const [newExtraVal, setNewExtraVal] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");
  const [favorites, setFavorites] = useState<string[]>([]);

  const panelRef = useRef<HTMLElement>(null);
  const initialPromptRef = useRef(bot.systemPrompt || "");

  useEffect(() => {
    const parsed = parsePreset(bot.systemPrompt || "");
    setAnswers(parsed.answers || {});
    setRules(parsed.rules || []);
    setOther(parsed.other || "");
    initialPromptRef.current = bot.systemPrompt || "";
    setSaved("");
    setError("");
  }, [bot.id, bot.systemPrompt]);

  const handleSave = async () => {
    if (preview || !onUpdateBot) return;
    setSaving(true);
    setSaved("");
    setError("");
    try {
      const prompt = buildPreset({
        answers,
        rules,
        other,
      });
      await onUpdateBot(bot.id, { systemPrompt: prompt });
      initialPromptRef.current = prompt;
      setSaved("工作预设已保存");
      setTimeout(() => setSaved(""), 3000);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "预设保存失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  };

  const addRule = () => {
    const trimmed = newRule.trim();
    if (!trimmed) return;
    if (rules.length >= 12) {
      setError("最多支持添加 12 条补充约定");
      return;
    }
    const clean = trimmed.slice(0, 200);
    if (!rules.includes(clean)) {
      setRules((prev) => [...prev, clean]);
    }
    setNewRule("");
    setError("");
  };

  const removeRule = (idx: number) => {
    setRules((prev) => prev.filter((_, i) => i !== idx));
  };

  const addExtra = () => {
    const k = newExtraKey.trim();
    const v = newExtraVal.trim();
    if (!k || !v) return;
    setAnswers((prev) => ({
      ...prev,
      extra: {
        ...(prev.extra || {}),
        [k]: v,
      },
    }));
    setNewExtraKey("");
    setNewExtraVal("");
  };

  const removeExtra = (key: string) => {
    setAnswers((prev) => {
      const copy = { ...(prev.extra || {}) };
      delete copy[key];
      return { ...prev, extra: copy };
    });
  };

  const updateExtra = (key: string, val: string) => {
    setAnswers((prev) => ({
      ...prev,
      extra: {
        ...(prev.extra || {}),
        [key]: val,
      },
    }));
  };

  // 工作重点仍是 q_start 的 4 个取值；汇报方式 / 推进方式按当前 focus 收窄到对应分支，
  // 当前已保存的值不在其中时追加保留，避免掉进「自定义」输入框。
  const focusOptions = useMemo(() => getFocusOptions(), []);
  const branchOptions = useMemo(() => getBranchOptionsForFocus(answers.focus), [answers.focus]);
  const styleOptions = useMemo(
    () => withCurrentValue(branchOptions.styleOptions, answers.style),
    [branchOptions, answers.style],
  );
  const autonomyOptions = useMemo(
    () => withCurrentValue(branchOptions.autonomyOptions, answers.autonomy),
    [branchOptions, answers.autonomy],
  );

  const extraEntries = Object.entries(answers.extra || {});

  const currentPrompt = useMemo(() => {
    return buildPreset({
      answers,
      rules,
      other,
    });
  }, [answers, rules, other]);

  const isDirty = useMemo(() => {
    if (newRule.trim() || newExtraKey.trim() || newExtraVal.trim()) {
      return true;
    }
    return currentPrompt !== initialPromptRef.current;
  }, [currentPrompt, newRule, newExtraKey, newExtraVal]);

  const isDirtyRef = useRef(isDirty);
  isDirtyRef.current = isDirty;

  const handleClose = () => {
    if (isDirtyRef.current) {
      const discard =
        typeof window !== "undefined" && typeof window.confirm === "function"
          ? window.confirm("当前工作预设已修改，确定要放弃未保存的修改并关闭吗？")
          : true;
      if (discard) {
        onClose();
      }
    } else {
      onClose();
    }
  };

  useEffect(() => {
    const handlePointerDown = (e: PointerEvent) => {
      const panel = panelRef.current;
      if (!panel) return;
      const target = e.target as HTMLElement | null;
      if (!target) return;

      if (panel.contains(target)) return;

      if (target.closest?.('[aria-label="打开设定"], [title="设定"]')) {
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

  return (
    <aside ref={panelRef} className="bot-memory-panel bot-preset-panel" aria-label={`${bot.name} 的工作预设`}>
      <div className="bot-memory-heading">
        <div className="bot-memory-title">
          <span className="bot-memory-icon" aria-hidden="true">
            <Settings2 size={17} />
          </span>
          <div>
            <h2>设定</h2>
            <p>{bot.name} 的模型、唤醒与工作方式</p>
          </div>
        </div>
        <button
          className="bot-memory-icon-button"
          type="button"
          onClick={handleClose}
          aria-label="关闭设定"
          title="关闭"
        >
          <X size={17} />
        </button>
      </div>

      <div className="bot-memory-body">
        {preview && (
          <p className="bot-memory-preview">
            预览模式：真实更新已禁用。
          </p>
        )}

        <section className="bot-memory-section" id="bot-preset-model-section">
          <div className="bot-memory-section-heading">
            <h3>默认模型</h3>
          </div>
          <ModelPicker
            presets={presets.filter((item) => item.harness === "pi" && item.available)}
            models={models}
            workspaceId={bot.workspaceId || "default"}
            value={bot.presetId || ""}
            change={(presetId) => {
              void onUpdateBot?.(bot.id, { presetId: presetId || null });
            }}
            favorites={favorites}
            toggleFavorite={(id) =>
              setFavorites((old) =>
                old.includes(id) ? old.filter((item) => item !== id) : [...old, id],
              )
            }
            disabled={preview}
          />
          <label className="bot-auto-wake-control">
            <input
              type="checkbox"
              role="switch"
              checked={Boolean(bot.wakeEnabled)}
              disabled={preview}
              onChange={(event) => {
                void onUpdateBot?.(bot.id, { wakeEnabled: event.target.checked });
              }}
            />
            <span>
              <strong>自动唤醒</strong>
              <small>
                {bot.wakeEnabled ? "定时任务到点后自动开始" : "仅在手动唤醒后继续"}
              </small>
            </span>
          </label>
        </section>

        {/* 核心工作方式 */}
        <section className="bot-memory-section">
          <div className="bot-memory-section-heading">
            <h3>核心工作方式</h3>
          </div>

          <FieldChipSelector
            label="工作重点"
            value={answers.focus}
            options={focusOptions}
            onChange={(focus) => setAnswers((prev) => ({ ...prev, focus }))}
          />

          <FieldChipSelector
            label="汇报方式"
            value={answers.style}
            options={styleOptions}
            onChange={(style) => setAnswers((prev) => ({ ...prev, style }))}
          />

          <FieldChipSelector
            label="推进方式"
            value={answers.autonomy}
            options={autonomyOptions}
            onChange={(autonomy) => setAnswers((prev) => ({ ...prev, autonomy }))}
          />
        </section>

        {/* 了解到的偏好 */}
        <section className="bot-memory-section">
          <div className="bot-memory-section-heading">
            <h3>了解到的偏好</h3>
            <span>{extraEntries.length} 条</span>
          </div>
          {extraEntries.length === 0 ? (
            <p className="bot-memory-muted">暂无通过向导或对话了解到的额外偏好。</p>
          ) : (
            <div className="bot-preset-extra-list">
              {extraEntries.map(([k, v]) => {
                const q = WIZARD_POOL[k];
                const displayLabel = q ? q.shortLabel : k;
                return (
                  <div key={k} className="bot-preset-extra-item">
                    <span className="bot-preset-extra-tag" title={k}>{displayLabel}</span>
                    <input
                      type="text"
                      className="bot-preset-extra-input"
                      value={v}
                      onChange={(e) => updateExtra(k, e.target.value)}
                      placeholder="偏好内容"
                    />
                    <button
                      type="button"
                      className="bot-rule-delete-btn"
                      onClick={() => removeExtra(k)}
                      title="删除此偏好"
                      aria-label="删除此偏好"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
          <div className="bot-preset-add-extra">
            <input
              type="text"
              className="bot-preset-small-input"
              value={newExtraKey}
              onChange={(e) => setNewExtraKey(e.target.value)}
              placeholder="偏好名称（如习惯）"
            />
            <input
              type="text"
              className="bot-preset-extra-input"
              value={newExtraVal}
              onChange={(e) => setNewExtraVal(e.target.value)}
              placeholder="内容"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addExtra();
                }
              }}
            />
            <button
              type="button"
              className="bot-secondary-button bot-preset-add-btn"
              onClick={addExtra}
              disabled={!newExtraKey.trim() || !newExtraVal.trim()}
              title="添加偏好"
            >
              <Plus size={14} />
            </button>
          </div>
        </section>

        {/* 补充约定 */}
        <section className="bot-memory-section">
          <div className="bot-memory-section-heading">
            <h3>补充约定（{rules.length}/12）</h3>
          </div>
          {rules.length === 0 ? (
            <p className="bot-memory-muted">暂无补充约定，可在下方添加或在对话中标记约定。</p>
          ) : (
            <ul className="bot-onboarding-rules-list">
              {rules.map((rule, idx) => (
                <li key={idx} className="bot-onboarding-rule-item">
                  <span className="bot-onboarding-rule-text">{rule}</span>
                  <button
                    type="button"
                    className="bot-rule-delete-btn"
                    onClick={() => removeRule(idx)}
                    title="删除此约定"
                    aria-label="删除此约定"
                  >
                    <Trash2 size={13} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="bot-preset-add-rule">
            <input
              type="text"
              className="bot-preset-extra-input"
              value={newRule}
              maxLength={200}
              onChange={(e) => setNewRule(e.target.value)}
              placeholder="新增约定（最多 200 字，按回车添加）"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addRule();
                }
              }}
            />
            <button
              type="button"
              className="bot-secondary-button bot-preset-add-btn"
              onClick={addRule}
              disabled={!newRule.trim() || rules.length >= 12}
              title="添加约定"
            >
              <Plus size={14} />
            </button>
          </div>
        </section>

        {error && <p className="bot-inline-error" role="alert">{error}</p>}
        {saved && (
          <p className="bot-memory-saved" role="status">
            <Check size={14} />
            {saved}
          </p>
        )}

        <div className="bot-preset-footer">
          <button
            type="button"
            className="bot-primary-button bot-preset-save-btn"
            onClick={handleSave}
            disabled={saving || preview}
          >
            {saving ? <LoaderCircle size={14} className="bot-spin" /> : <Check size={14} />}
            <span>{saving ? "正在保存…" : "保存预设"}</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
