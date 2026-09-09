import { useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { Check, ChevronDown, Search, SlidersHorizontal } from "lucide-react";
import type { Model, Preset } from "./types";
import { readRoutePreferences } from "./ModelExplorer";
import { modelKey, selectModelRoute } from "./modelSelection";
import { VendorMark } from "./VendorMark";
import "./quick-model.css";

export function QuickModelMenu({ presets, models, value, favorites, change, close, disabled = false, notice, children }: {
  presets: Preset[];
  models: Model[];
  value: string;
  favorites: string[];
  change: (id: string) => void | Promise<boolean>;
  close: () => void;
  disabled?: boolean;
  notice?: string;
  children: ReactNode;
}) {
  const [query, setQuery] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const selected = presets.find(p => p.id === value);
  const groups = new Map<string, Preset[]>();
  for (const preset of presets) {
    const key = modelKey(preset);
    groups.set(key, [...(groups.get(key) || []), preset]);
  }
  const preferences = readRoutePreferences();
  const shown = [...groups.entries()]
    .filter(([key, routes]) => `${key} ${routes[0].name} ${models.find(m => m.id === routes[0].modelId)?.family || ""}`.toLowerCase().includes(query.trim().toLowerCase()))
    .sort(([, a], [, b]) => Number(b.some(p => favorites.includes(p.modelId))) - Number(a.some(p => favorites.includes(p.modelId))));
  const routes = selected ? groups.get(modelKey(selected)) || [] : [];

  async function choose(id: string, dismiss: boolean) {
    if (pending || disabled || !presets.some(p => p.id === id && p.available)) return;
    if (id === value) { if (dismiss) close(); return; }
    setPending(true); setError("");
    try {
      if (await change(id) === false) setError("切换未完成，请查看错误提示后重试。");
      else if (dismiss) close();
    } catch (e) {
      setError(e instanceof Error ? e.message : "切换未完成，请重试。");
    } finally { setPending(false); }
  }

  function moveFocus(event: KeyboardEvent<HTMLElement>) {
    if (event.nativeEvent.isComposing || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>(".quick-model-option:not(:disabled)")];
    if (!buttons.length) return;
    event.preventDefault();
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 :
      (index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
    buttons[next].focus();
  }

  return <div className="quick-model-menu" aria-busy={pending}>
    <label className="quick-model-search">
      <Search size={16} />
      <input autoFocus aria-label="搜索模型" placeholder="搜索模型…" value={query}
        onChange={e => setQuery(e.target.value)}
        onKeyDown={e => {
          if (e.key === "ArrowDown" && !e.nativeEvent.isComposing) {
            e.preventDefault();
            e.currentTarget.closest(".quick-model-menu")?.querySelector<HTMLButtonElement>(".quick-model-option:not(:disabled)")?.focus();
          }
        }} />
    </label>
    <div className="quick-model-list" role="group" aria-label="可选模型" onKeyDown={moveFocus}>
      {shown.map(([key, options]) => {
        const preset = selectModelRoute(options, favorites, preferences, value);
        const active = !!selected && modelKey(selected) === key;
        return <button type="button" key={key} className="quick-model-option" aria-pressed={active}
          disabled={disabled || pending || !preset.available}
          title={preset.available ? `使用通道：${preset.channel || preset.providerId}` : preset.reason || "此模型暂不可用"}
          onClick={() => void choose(preset.id, true)}>
          <VendorMark name={preset.name} family={models.find(m => m.id === preset.modelId)?.family} />
          <span>{preset.name}</span>
          {!preset.available ? <small>不可用</small> : active && <Check size={15} />}
        </button>;
      })}
      {!shown.length && <p className="popover-note">没有匹配的模型，换个关键词试试。</p>}
    </div>
    {(pending || notice) && <p className="popover-note" role="status">{pending ? "正在切换模型…" : notice}</p>}
    {error && <p className="inline-alert" role="alert">{error}</p>}
    <details className="quick-model-advanced" data-guide="model-advanced">
      <summary><SlidersHorizontal size={15} /><span>通道与高级选项</span><ChevronDown size={14} /></summary>
      <fieldset disabled={pending}>
        <label className="task-setting-row">
          <span>本次通道</span>
          <select aria-label="本次模型通道" value={value} disabled={disabled || !routes.length}
            onChange={e => void choose(e.target.value, false)}>
            {!selected && <option value={value}>先选择模型</option>}
            {routes.map(p => <option key={p.id} value={p.id} disabled={!p.available}>
              {p.channel || p.providerId}{preferences[p.id]?.preferred ? " · 首选" : ""}{!p.available ? " · 不可用" : ""}
            </option>)}
          </select>
        </label>
        {children}
      </fieldset>
    </details>
  </div>;
}
