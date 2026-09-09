import { useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Search,
  Star,
  SlidersHorizontal,
  Brain,
  Image,
  Layers,
} from "lucide-react";
import type { Model, Preset } from "./types";
import { request } from "./api";
import { VendorMark, vendorTint } from "./VendorMark";

export interface LaunchFacts {
  model: {
    id?: string;
    input?: string[];
    contextWindow?: number;
    maxTokens?: number;
    reasoning?: boolean;
  };
  protocol: string;
  supportedThinkingLevels: string[];
  defaultThinkingLevel: string;
  configuredThinkingLevel: string;
  thinkingLevelMap?: Record<string, string | null>;
}
export const effortLabels: Record<string, string> = {
  off: "关闭",
  minimal: "最少",
  low: "轻量",
  medium: "均衡",
  high: "深入",
  xhigh: "更深入",
  max: "最高",
};
export function useLaunchFacts(presetId: string, workspaceId: string, retry = 0) {
  const [state, setState] = useState<{
    key: string;
    facts?: LaunchFacts;
    error?: string;
  }>({ key: "" });
  const key = presetId + "|" + workspaceId + "|" + retry;
  useEffect(() => {
    let cancelled = false;
    if (!presetId || !workspaceId) return;
    request<LaunchFacts>("/launch-options", { presetId, workspaceId })
      .then((facts) => {
        if (!cancelled) setState({ key, facts });
      })
      .catch((e) => {
        if (!cancelled) setState({ key, error: e.message });
      });
    return () => {
      cancelled = true;
    };
  }, [key, presetId, workspaceId]);
  return state.key === key ? state : { key };
}
export function readRoutePreferences(): Record<
  string,
  { note?: string; effort?: string; preferred?: boolean }
> {
  try {
    return JSON.parse(
      localStorage.getItem("mms-web-route-preferences") || "{}",
    );
  } catch {
    return {};
  }
}
export function saveRoutePreference(
  id: string,
  patch: { note?: string; effort?: string; preferred?: boolean },
) {
  const value = readRoutePreferences();
  value[id] = { ...value[id], ...patch };
  try {
    localStorage.setItem("mms-web-route-preferences", JSON.stringify(value));
  } catch {
    /* Browser storage unavailable: current choice still works. */
  }
}
export function modelKey(p: Preset) {
  return p.modelId.startsWith(p.providerId + ":")
    ? p.modelId.slice(p.providerId.length + 1)
    : p.name;
}
export function quickPresets(presets: Preset[], favorites: string[]) {
  const prefs = readRoutePreferences();
  const sorted = presets
    .filter((p) => p.available)
    .sort(
      (a, b) =>
        Number(favorites.includes(b.modelId)) -
          Number(favorites.includes(a.modelId)) ||
        Number(!!prefs[b.id]?.preferred) - Number(!!prefs[a.id]?.preferred),
    );
  return sorted
    .filter(
      (p, i) => sorted.findIndex((q) => modelKey(q) === modelKey(p)) === i,
    )
    .slice(0, 4)
    .map(
      (p) =>
        presets.find(
          (q) =>
            q.available &&
            modelKey(q) === modelKey(p) &&
            prefs[q.id]?.preferred,
        ) || p,
    );
}
export function EffortSelect({
  facts,
  value,
  change,
  disabled = false,
}: {
  facts: LaunchFacts;
  value: string;
  change: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="effort-field">
      <Brain size={16} />
      <span className="sr-only">思考强度</span>
      <select
        aria-label="新任务 effort"
        disabled={disabled}
        value={value}
        onChange={(e) => change(e.target.value)}
      >
        <option value="">MMS 默认 · {facts.defaultThinkingLevel}</option>
        {value && !facts.supportedThinkingLevels.includes(value) && (
          <option value={value} disabled>
            此通道不支持 {value}，请重选
          </option>
        )}
        {facts.supportedThinkingLevels.map((l) => (
          <option key={l} value={l}>
            {effortLabels[l]} · {l}
          </option>
        ))}
      </select>
    </label>
  );
}
export function ModelExplorer({
  presets,
  models,
  workspaceId,
  value,
  change,
  favorites,
  toggleFavorite,
  choose,
  effortChanged,
}: {
  presets: Preset[];
  models: Model[];
  workspaceId: string;
  value: string;
  change: (id: string) => void;
  favorites: string[];
  toggleFavorite: (id: string) => void;
  choose?: () => void;
  effortChanged?: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [onlyFavorite, setOnlyFavorite] = useState(false);
  const [revision, setRevision] = useState(0);
  const selected = presets.find((p) => p.id === value);
  const { facts, error } = useLaunchFacts(value, workspaceId);
  const prefs = readRoutePreferences();
  const groups = useMemo(() => {
    const map = new Map<string, Preset[]>();
    for (const p of presets) {
      const key = modelKey(p);
      map.set(key, [...(map.get(key) || []), p]);
    }
    return [...map.entries()];
  }, [presets]);
  const shown = groups.filter(([, routes]) =>
    routes.some(
      (p) =>
        (!onlyFavorite || favorites.includes(p.modelId)) &&
        `${p.name} ${p.channel} ${p.description}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    ),
  );
  const routes =
    groups.find(([key]) => selected && key === modelKey(selected))?.[1] || [];
  const info = models.find((m) => m.id === selected?.modelId);
  function patch(p: { note?: string; effort?: string; preferred?: boolean }) {
    if (!selected) return;
    saveRoutePreference(selected.id, p);
    if (p.effort !== undefined) effortChanged?.(selected.id);
    setRevision(revision + 1);
  }
  return (
    <div className="model-explorer">
      <div className="explorer-search">
        <label className="picker-search">
          <Search size={17} />
          <input
            autoFocus
            aria-label="搜索模型或通道"
            placeholder="搜索模型、公司或通道…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <button
          type="button"
          className={"filter-button " + (onlyFavorite ? "active" : "")}
          aria-pressed={onlyFavorite}
          onClick={() => setOnlyFavorite(!onlyFavorite)}
        >
          <Star size={15} />
          常用
        </button>
      </div>
      <div className="explorer-columns">
        <div className="model-groups" aria-label="模型目录">
          <p className="eyebrow">
            {shown.length} 个模型 · {presets.length} 条通道
          </p>
          {shown.map(([key, ps]) => (
            <button
              type="button"
              key={key}
              className={
                "model-group " +
                (selected && modelKey(selected) === key ? "selected" : "")
              }
              onClick={() =>
                change(
                  ps.find((p) => p.available && prefs[p.id]?.preferred)?.id ||
                    ps.find((p) => p.available && favorites.includes(p.modelId))
                      ?.id ||
                    ps.find((p) => p.available)?.id ||
                    ps[0].id,
                )
              }
            >
              <span
                className="model-monogram"
                style={{
                  background: vendorTint(
                    models.find((m) => m.id === ps[0].modelId)?.family,
                    ps[0].name,
                  ),
                }}
              >
                <VendorMark
                  family={models.find((m) => m.id === ps[0].modelId)?.family}
                  name={ps[0].name}
                />
              </span>
              <span>
                <strong>{ps[0].name}</strong>
                <small>
                  {ps.length} 条通道
                  {ps.some((p) => favorites.includes(p.modelId))
                    ? " · 已收藏"
                    : ""}
                </small>
              </span>
              <ChevronRight size={15} />
            </button>
          ))}
          {!shown.length && (
            <p className="empty-results">没有匹配项，换个关键词试试。</p>
          )}
        </div>
        <div className="model-detail">
          {selected ? (
            <>
              <div className="model-detail-scroll">
                <div className="model-detail-heading">
                  <span className="eyebrow">
                    {info?.family || "模型"} / {selected.harness.toUpperCase()}
                  </span>
                  <h3>{selected.name}</h3>
                  <p>同一个模型，查看各通道的实际能力与配置。</p>
                </div>
                <div className="model-facts">
                  <span>
                    <Layers size={15} />
                    {facts?.model.contextWindow
                      ? `${Math.round(facts.model.contextWindow / 1000)}K 上下文`
                      : info?.contextLabel || "上下文待读取"}
                  </span>
                  <span>
                    <Image size={15} />
                    {facts
                      ? facts.model.input?.includes("image")
                        ? "文本与图片"
                        : "文本输入"
                      : "能力读取中"}
                  </span>
                  <span>
                    <Brain size={15} />
                    {facts
                      ? `默认 ${facts.defaultThinkingLevel}`
                      : "读取 MMS 默认"}
                  </span>
                </div>
                <div className="channel-heading">
                  <h4>默认通道</h4>
                  <span>{routes.length} 条</span>
                </div>
                <div className="channel-list">
                  {routes.map((p) => (
                    <div
                      key={p.id}
                      className={
                        "channel-choice " + (p.id === value ? "selected" : "")
                      }
                    >
                      <button
                        className="channel-select"
                        type="button"
                        disabled={!p.available}
                        onClick={() => change(p.id)}
                      >
                        <span className="channel-radio">
                          {p.id === value && <Check size={12} />}
                        </span>
                        <span>
                          <strong>{p.channel || p.providerId}</strong>
                          <small>
                            {prefs[p.id]?.note || p.description}
                            {prefs[p.id]?.preferred ? " · Web 首选" : ""}
                          </small>
                          {!p.available && <small>{p.reason}</small>}
                        </span>
                      </button>
                      <button
                        type="button"
                        className={
                          "icon-button favorite " +
                          (favorites.includes(p.modelId) ? "active" : "")
                        }
                        aria-label={
                          (favorites.includes(p.modelId)
                            ? "取消常用 "
                            : "设为常用 ") +
                          p.name +
                          " " +
                          p.channel
                        }
                        onClick={() => toggleFavorite(p.modelId)}
                      >
                        <Star
                          size={16}
                          fill={
                            favorites.includes(p.modelId)
                              ? "currentColor"
                              : "none"
                          }
                        />
                      </button>
                    </div>
                  ))}
                </div>
                {error && (
                  <p className="inline-alert" role="alert">
                    {error}
                  </p>
                )}
                <details className="quick-config">
                  <summary>
                    {facts && (
                  <div className="route-summary">
                    <span>当前通道默认</span>
                    <strong>
                      {effortLabels[facts.defaultThinkingLevel]} ·{" "}
                      {facts.defaultThinkingLevel}
                    </strong>
                    <small>
                      {facts.protocol} · 支持{" "}
                      {facts.supportedThinkingLevels
                        .map((l) =>
                          facts.thinkingLevelMap?.[l] &&
                          facts.thinkingLevelMap[l] !== l
                            ? `${l} → ${facts.thinkingLevelMap[l]}`
                            : l,
                        )
                        .join(" / ")}
                    </small>
                    {facts.configuredThinkingLevel !==
                      facts.defaultThinkingLevel && (
                      <small>
                        MMS 配置为 {facts.configuredThinkingLevel}；Pi
                        此通道采用 {facts.defaultThinkingLevel}。
                      </small>
                    )}
                  </div>
                    )}
                    <span className="quick-config-more">
                      <SlidersHorizontal size={15} />
                      更多设置
                      <ChevronDown size={13} />
                    </span>
                  </summary>
                  <label>
                    通道备注
                    <input
                      key={selected.id}
                      defaultValue={prefs[selected.id]?.note || ""}
                      maxLength={100}
                      placeholder="例如：公司额度 / 个人备用"
                      onChange={(e) => patch({ note: e.target.value })}
                    />
                  </label>
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={!!prefs[selected.id]?.preferred}
                      onChange={(e) => {
                        for (const p of routes)
                          saveRoutePreference(p.id, { preferred: false });
                        patch({ preferred: e.target.checked });
                      }}
                    />
                    设为这个模型的 Web 首选通道
                  </label>
                  {facts && (
                    <label>
                      Web 默认 effort
                      <select
                        aria-label="Web 默认 effort"
                        value={prefs[selected.id]?.effort || ""}
                        onChange={(e) => patch({ effort: e.target.value })}
                      >
                        <option value="">
                          跟随 MMS · {facts.defaultThinkingLevel}
                        </option>
                        {facts.supportedThinkingLevels.map((l) => (
                          <option key={l} value={l}>
                            {effortLabels[l]} · {l}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <small>
                    保存在当前浏览器。MMS 的模型配置与路由优先级保持原值。
                  </small>
                </details>
              </div>
              {choose && (
                <button
                  type="button"
                  className="button primary use-model"
                  disabled={!selected.available || !facts}
                  onClick={choose}
                >
                  使用 {selected.name}
                  <ChevronRight size={16} />
                </button>
              )}
            </>
          ) : (
            <p className="empty-results">
              从左侧选择一个模型，查看它的通道与参数。
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
