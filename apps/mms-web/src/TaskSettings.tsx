import { useRef, useState } from "react";
import { RadioMenu } from "./RadioMenu";
import { ChevronDown, ArrowUpRight, Brain, Check } from "lucide-react";
import type { Model, Preset, SessionDetail } from "./types";
import type { LaunchFacts } from "./ModelExplorer";
import { effortLabels, saveRoutePreference } from "./ModelExplorer";
import { availableRoutesForModel, channelLabel } from "./modelSelection";
import { QuickModelMenu } from "./QuickModelMenu";
import { Popover } from "./Popover";

const LEVEL_ORDER = Object.keys(effortLabels);

export function sortLevels(levels: string[]): string[] {
  return [...new Set(levels)].sort((a, b) => {
    const ia = LEVEL_ORDER.indexOf(a);
    const ib = LEVEL_ORDER.indexOf(b);
    if (ia !== -1 && ib !== -1) return ia - ib;
    if (ia !== -1) return -1;
    if (ib !== -1) return 1;
    return a.localeCompare(b);
  });
}

export function EffortPicker({
  value,
  levels,
  defaultLevel,
  allowDefault = true,
  change,
  disabled = false,
  title = "思考强度",
  dataGuide = "effort",
}: {
  value: string;
  levels: string[];
  defaultLevel?: string;
  allowDefault?: boolean;
  change: (level: string) => void | Promise<boolean>;
  disabled?: boolean;
  title?: string;
  dataGuide?: string;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  async function choose(level: string, close: () => void) {
    if (disabled || inFlight.current) return;
    if (level === value) { close(); return; }
    inFlight.current = true; setPending(true); setError("");
    try {
      if (await change(level) === false) setError("思考强度未更新，请重试。");
      else close();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "思考强度未更新，请重试。");
    } finally { inFlight.current = false; setPending(false); }
  }
  const isCustom = Boolean(value && value !== "");
  const isUnsupported = Boolean(isCustom && !levels.includes(value));
  const isDefaultActive = !isCustom || !value;
  const defaultLabel = (defaultLevel && effortLabels[defaultLevel]) || defaultLevel || "无";

  const currentEffort = value || defaultLevel || levels[0] || "medium";
  const currentLabel = effortLabels[currentEffort] || currentEffort;

  return (
    <Popover
      title={title}
      className={`task-settings-trigger task-effort-trigger ${isUnsupported ? "effort-trigger-unsupported" : ""}`}
      panelWidth={220}
      disabled={disabled}
      dataGuide={dataGuide}
      label={
        isUnsupported ? (
          <>
            <Brain size={13} className="task-effort-icon task-effort-unsupported-icon" />
            <span className="task-effort-prefix">思考 · </span>
            <span className="task-effort task-effort-unsupported">此通道不支持 {value}，请重选</span>
            <ChevronDown size={13} />
          </>
        ) : (
          <>
            <Brain size={13} className="task-effort-icon" />
            <span className="task-effort-prefix">思考 · </span>
            <span className="task-effort">{pending ? "更新中…" : currentLabel}</span>
            <ChevronDown size={13} />
          </>
        )
      }
    >
      {(close, open) => (
        <RadioMenu active={open} className="effort-menu" label="选择思考强度">
          <div className="effort-menu-header">
            <span>{title}</span>
            <small>推理与分析深度</small>
          </div>
          <div className="effort-menu-list">
            {isUnsupported && (
              <div
                role="option"
                aria-selected="true"
                className="effort-menu-item effort-menu-unsupported active disabled"
              >
                <div className="effort-menu-item-info">
                  <span className="effort-menu-item-label warning-text">
                    此通道不支持 {value}，请重选
                  </span>
                  <span className="effort-menu-item-code">不支持</span>
                </div>
                <span className="effort-menu-unsupported-tag">⚠️</span>
              </div>
            )}
            {allowDefault && <button
              type="button"
              disabled={pending || disabled}
              role="menuitemradio"
              aria-checked={isDefaultActive}
              className={`effort-menu-item ${isDefaultActive ? "active" : ""}`}
              onClick={() => {
                void choose("", close);
              }}
            >
              <div className="effort-menu-item-info">
                <span className="effort-menu-item-label">
                  MMS 默认 · {defaultLabel}
                </span>
                <span className="effort-menu-item-code">默认</span>
              </div>
              {isDefaultActive && <Check size={14} className="effort-menu-check" />}
            </button>}
            {levels.map((level) => {
              const isSelected = !isUnsupported && isCustom && level === value;
              const isDefault = Boolean(defaultLevel && level === defaultLevel);
              return (
                <button
                  key={level}
                  type="button"
                  disabled={pending || disabled}
                  role="menuitemradio"
                  aria-checked={isSelected}
                  className={`effort-menu-item ${isSelected ? "active" : ""}`}
                  onClick={() => {
                    void choose(level, close);
                  }}
                >
                  <div className="effort-menu-item-info">
                    <span className="effort-menu-item-label">
                      {effortLabels[level] || level}
                    </span>
                    <span className="effort-menu-item-code">{level}</span>
                    {isDefault && (
                      <span className="effort-menu-item-tag">默认</span>
                    )}
                  </div>
                  {isSelected && <Check size={14} className="effort-menu-check" />}
                </button>
              );
            })}
          </div>
          {pending && <p className="popover-note" role="status">正在更新思考强度…</p>}
          {error && <p className="inline-alert" role="alert">{error}</p>}
        </RadioMenu>
      )}
    </Popover>
  );
}

export function TaskSettings({
  presets,
  models,
  workspaceId,
  value,
  change,
  favorites,
  toggleFavorite,
  facts,
  effort,
  setEffort,
  planning,
  setPlanning,
  settings,
}: {
  presets: Preset[];
  models: Model[];
  workspaceId: string;
  value: string;
  change: (id: string) => void;
  favorites: string[];
  toggleFavorite: (id: string) => void;
  facts: LaunchFacts | undefined;
  effort: string;
  setEffort: (level: string) => void;
  planning: boolean;
  setPlanning: (on: boolean) => void;
  settings: () => void;
}) {
  const preset = presets.find((p) => p.id === value);
  const extraChannels = availableRoutesForModel(presets, preset).length > 1;

  const supportedLevels = facts?.supportedThinkingLevels || [];
  const hasEffort = Boolean(facts && supportedLevels.length > 0);
  const sortedLevels = sortLevels(supportedLevels);

  const handleEffortChange = (level: string) => {
    saveRoutePreference(value, { effort: level });
    setEffort(level);
  };

  return (
    <>
      <Popover
        title="本次任务设置"
        className="task-settings-trigger"
        label={
          <>
            <span className="task-model-name">{preset?.name || "选择模型"}</span>
            {extraChannels && preset && (
              <span className="task-route-name">{channelLabel(preset, models)}</span>
            )}
            {planning && <span className="task-plan">规划</span>}
            <ChevronDown size={13} />
          </>
        }
      >
        {(close, open) => open ? (
          <QuickModelMenu presets={presets} models={models} value={value} favorites={favorites}
            change={change} close={close} notice={planning ? "当前为只读规划模式。" : undefined}>
            <label className="task-setting-row">
              <span>工作方式</span>
              <select
                aria-label="新任务工作模式"
                value={planning ? "plan" : "execute"}
                onChange={(e) => setPlanning(e.target.value === "plan")}
              >
                <option value="execute">执行任务</option>
                <option value="plan">只读规划</option>
              </select>
            </label>
            <p className="popover-note">
              {planning
                ? "先分析与阅读资料，不修改工作文件。"
                : "可以读取、修改工作文件，并执行命令。"}
            </p>
            <button
              type="button"
              className="popover-footer"
              onClick={() => {
                close();
                settings();
              }}
            >
              管理模型与偏好
              <ArrowUpRight size={14} />
            </button>
          </QuickModelMenu>
        ) : null}
      </Popover>

      {hasEffort && (
        <EffortPicker
          value={effort}
          levels={sortedLevels}
          defaultLevel={facts?.defaultThinkingLevel}
          change={handleEffortChange}
          dataGuide="effort"
        />
      )}
    </>
  );
}

export function SessionSettings({
  detail,
  busy,
  action,
  more,
  presets, models, favorites, toggleFavorite,
}: {
  detail: SessionDetail;
  busy: boolean;
  action: (path: string, payload: Record<string, unknown>) => Promise<boolean>;
  more: () => void;
  presets: Preset[]; models: Model[]; favorites: string[];
  toggleFavorite: (id: string) => void;
}) {
  const r = detail.runtime;
  const locked = busy || !r?.alive || !!r?.stale || ["running", "waiting"].includes(detail.session.state) || !detail.session.capabilities.send;
  const currentPreset = presets.find((item) => item.id === detail.session.presetId);
  const extraChannels = availableRoutesForModel(presets, currentPreset).length > 1;
  const control = (name: string, value: unknown) =>
    action(`/sessions/${detail.session.id}/control`, { action: name, value });

  const rawLevels = [
    ...new Set([
      ...(r?.supportedThinkingLevels || []),
      ...(r?.thinkingLevel ? [r.thinkingLevel] : []),
    ]),
  ];
  const hasEffort = Boolean(r && rawLevels.length > 0);
  const sortedLevels = sortLevels(rawLevels);

  return (
    <>
      <Popover
        title="当前会话设置"
        className="task-settings-trigger"
        label={
          <>
            <span className="task-model-name">{detail.session.modelName}</span>
            {extraChannels && (
              <span className="task-route-name">
                {detail.session.providerName || detail.session.channel}
              </span>
            )}
            {r?.planning && <span className="task-plan">规划</span>}
            <ChevronDown size={13} />
          </>
        }
      >
        {(close, open) => open ? (
          <QuickModelMenu presets={presets.filter(p => p.harness === "pi")} models={models}
            value={detail.session.presetId || ""} favorites={favorites} close={close}
            change={presetId => action(`/sessions/${detail.session.id}/model`, {presetId})}
            disabled={busy || ["running", "waiting"].includes(detail.session.state) || !detail.session.capabilities.send}
            notice={busy || ["running", "waiting"].includes(detail.session.state)
              ? "本轮完成或停止后可切换模型。"
              : !detail.session.capabilities.send ? "这条会话目前只支持查看。"
              : r?.planning ? "当前为只读规划模式。" : undefined}>
            <label className="task-setting-row">
              <span>工作方式</span>
              <select
                aria-label="工作模式"
                value={r?.planning ? "plan" : "execute"}
                disabled={locked}
                onChange={(e) => void control("plan", e.target.value === "plan")}
              >
                <option value="execute">执行任务</option>
                <option value="plan">只读规划</option>
              </select>
            </label>
            <p className="popover-note">
              {!r?.alive || r?.stale
                ? "选择模型可恢复这条会话；启动后可调整更多参数。"
                : locked
                ? "当前工作结束后可以调整。"
                : "切换模型会保留当前对话，并采用新模型的默认思考强度。"}
            </p>
            <button
              type="button"
              className="popover-footer"
              onClick={() => {
                close();
                more();
              }}
            >
              上下文、用量与高级参数
              <ArrowUpRight size={14} />
            </button>
          </QuickModelMenu>
        ) : null}
      </Popover>

      {hasEffort && (
        <EffortPicker
          value={r?.thinkingLevel || ""}
          levels={sortedLevels}
          allowDefault={false}
          change={(level) => control("thinking", level)}
          disabled={locked}
          dataGuide="effort"
        />
      )}
    </>
  );
}
