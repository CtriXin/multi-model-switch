import { ChevronDown, ArrowUpRight } from "lucide-react";
import type { Model, Preset, SessionDetail } from "./types";
import type { LaunchFacts } from "./ModelExplorer";
import { EffortSelect } from "./ModelExplorer";
import { QuickModelMenu } from "./QuickModelMenu";
import { Popover } from "./Popover";

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
  return (
    <Popover
      title="本次任务设置"
      className="task-settings-trigger"
      label={
        <>
          <span className="task-model-name">{preset?.name || "选择模型"}</span>
          {planning && <span className="task-plan">规划</span>}
          <ChevronDown size={13} />
        </>
      }
    >
      {(close, open) => open ? (
        <QuickModelMenu presets={presets} models={models} value={value} favorites={favorites}
          change={change} close={close} notice={planning ? "当前为只读规划模式。" : undefined}>
          <div className="task-setting-row" data-guide="effort">
            <span>思考强度</span>
            {facts ? (
              <EffortSelect facts={facts} value={effort} change={setEffort} />
            ) : (
              <span className="muted">读取模型设置…</span>
            )}
          </div>
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
  const locked = busy || !r?.alive || !!r?.stale || ["running", "waiting"].includes(detail.session.state);
  const control = (name: string, value: unknown) =>
    action(`/sessions/${detail.session.id}/control`, { action: name, value });
  return (
    <Popover
      title="当前会话设置"
      className="task-settings-trigger"
      label={
        <>
          <span className="task-model-name">{detail.session.modelName}</span>
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
          <label className="task-setting-row" data-guide="effort">
            <span>思考强度</span>
            <select
              aria-label="Thinking 等级"
              value={r?.thinkingLevel || ""}
              disabled={locked || !r?.model?.reasoning}
              onChange={(e) => void control("thinking", e.target.value)}
            >
              <option value="" disabled>
                尚未读取
              </option>
              {[
                ...new Set([
                  ...(r?.supportedThinkingLevels || []),
                  ...(r?.thinkingLevel ? [r.thinkingLevel] : []),
                ]),
              ].map((level) => (
                <option key={level}>{level}</option>
              ))}
            </select>
          </label>
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
  );
}
