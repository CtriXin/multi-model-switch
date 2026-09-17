import { useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Popover } from "./Popover";
import { RadioMenu } from "./RadioMenu";
import type { Preset } from "./types";
import {
  compactModelLabel,
  familyChipLabel,
  fleetPreviewLabel,
  modelsForFamily,
  normalizeFleetPolicy,
  type BotFleetPolicy,
} from "./bot-fleet";

export {
  availableFleetFamilies,
  fleetPreviewLabel,
  normalizeFleetPolicy,
  type BotFleetPolicy,
} from "./bot-fleet";

export function BotFleetBar({
  policy,
  families,
  presets = [],
  disabled,
  busy,
  onChange,
}: {
  policy: BotFleetPolicy;
  families: string[];
  presets?: Preset[];
  disabled?: boolean;
  busy?: boolean;
  onChange: (next: BotFleetPolicy) => void | Promise<void>;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const locked = Boolean(disabled || busy || pending);
  const allOn = families.length > 0 && policy.families.length === families.length
    && families.every((name) => policy.families.includes(name));
  const visibleFamilies = [...new Set([...families, ...policy.families])];

  async function patch(partial: Partial<BotFleetPolicy>) {
    if (locked || inFlight.current) return false;
    inFlight.current = true; setPending(true); setError("");
    try { await onChange(normalizeFleetPolicy({ ...policy, ...partial })); return true; }
    catch (cause) { setError(cause instanceof Error ? cause.message : "场外帮助设置未保存，请重试。"); return false; }
    finally { inFlight.current = false; setPending(false); }
  }

  function toggleFamily(name: string) {
    if (locked) return;
    const selected = policy.families.includes(name)
      ? policy.families.filter((item) => item !== name)
      : [...policy.families, name].slice(0, 12);
    patch({
      families: selected,
      maxFamilies: selected.length > 0 ? selected.length : policy.maxFamilies,
    });
  }

  function pickModel(family: string, presetId: string) {
    if (locked) return Promise.resolve(false);
    const selected = policy.families.includes(family)
      ? policy.families
      : [...policy.families, family].slice(0, 12);
    return patch({
      families: selected,
      maxFamilies: Math.max(selected.length, policy.maxFamilies),
      models: { ...policy.models, [family]: presetId },
    });
  }

  return (
    <div className={"bot-fleet-bar" + (policy.enabled ? "" : " is-collapsed")} aria-label="寻求场外帮助">
      <div className="bot-fleet-row">
        <button
          type="button"
          className={"bot-fleet-chip bot-fleet-door" + (policy.enabled ? " is-on" : "")}
          aria-pressed={policy.enabled}
          disabled={locked}
          title={policy.enabled ? "关掉就只问我" : "打开的话，发出去会再问几家"}
          onClick={() => patch({ enabled: !policy.enabled })}
        >
          寻求场外帮助
        </button>
        {policy.enabled && (
          <>
        <button
          type="button"
          className={"bot-fleet-chip" + (policy.intensity === "opinions" ? " is-on" : "")}
          disabled={locked}
          aria-pressed={policy.intensity === "opinions"}
          onClick={() => patch({ intensity: "opinions" })}
        >
          听听
        </button>
        <button
          type="button"
          className={"bot-fleet-chip" + (policy.intensity === "intense" ? " is-on" : "")}
          disabled={locked}
          aria-pressed={policy.intensity === "intense"}
          onClick={() => patch({ intensity: "intense" })}
        >
          问仔细
        </button>
        <button
          type="button"
          className={"bot-fleet-chip" + (!policy.families.length && policy.maxFamilies === 2 ? " is-on" : "")}
          disabled={locked}
          onClick={() => patch({ maxFamilies: 2, families: [] })}
        >
          2 家
        </button>
        <button
          type="button"
          className={"bot-fleet-chip" + (!policy.families.length && policy.maxFamilies === 3 ? " is-on" : "")}
          disabled={locked}
          onClick={() => patch({ maxFamilies: 3, families: [] })}
        >
          3 家
        </button>
        <button
          type="button"
          className={"bot-fleet-chip" + (allOn ? " is-on" : "")}
          disabled={locked || families.length < 2}
          onClick={() =>
            allOn
              ? patch({ families: [], maxFamilies: 2 })
              : patch({ families, maxFamilies: families.length })
          }
        >
          {allOn ? "全不选" : "全选"}
        </button>
          </>
        )}
      </div>
      {policy.enabled && visibleFamilies.length > 0 && (
        <div className="bot-fleet-row bot-fleet-families" role="group" aria-label="指定家族">
          {visibleFamilies.map((name) => {
            const on = policy.families.includes(name);
            const options = modelsForFamily(presets, name);
            const label = familyChipLabel(name, policy, presets);
            const remembered = policy.models[name];
            return (
              <div key={name} className={"bot-fleet-family-wrap" + (on ? " is-on" : "")}>
                <button
                  type="button"
                  className={"bot-fleet-chip bot-fleet-family" + (on ? " is-on" : "")}
                  aria-pressed={on}
                  title={`${on ? "取消" : "选择"} ${name}`}
                  disabled={locked}
                  onClick={() => toggleFamily(name)}
                >
                  {label}
                </button>
                {options.length > 0 && (
                  <Popover title={`选择 ${name} 的模型`} label={<ChevronDown size={14} />}
                    className="bot-fleet-chip bot-fleet-model-trigger" panelWidth={260} disabled={locked}>
                    {(close, open) => <RadioMenu active={open} className="bot-fleet-model-panel" label={`${name} 可选模型`}>
                    {remembered && <button type="button" role="menuitemradio" aria-checked={false}
                      className="bot-fleet-model-item" disabled={locked}
                      onClick={async () => { if (await patch({ models: { ...policy.models, [name]: "" } })) close(); }}>
                      自动选择
                    </button>}
                    {options.map((preset) => {
                      const active = remembered === preset.id;
                      return (
                        <button
                          key={preset.id}
                          type="button"
                          role="menuitemradio"
                          aria-checked={active}
                          className={"bot-fleet-model-item" + (active ? " is-on" : "")}
                          disabled={locked}
                          onClick={async (event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            if (await pickModel(name, preset.id)) close();
                          }}
                        >
                          {compactModelLabel(preset.name)}
                          {options.some((other) => other.id !== preset.id && other.name === preset.name)
                            && ` · ${preset.channel || preset.providerId || preset.id}`}
                        </button>
                      );
                    })}
                    </RadioMenu>}
                  </Popover>
                )}
              </div>
            );
          })}
        </div>
      )}
      {pending && <p role="status" className="bot-fleet-preview">正在保存选择…</p>}
      {error && <p role="alert" className="bot-inline-error">{error}</p>}
      {policy.enabled && (
        <p className="bot-fleet-preview">{fleetPreviewLabel(policy, families, presets)}</p>
      )}
    </div>
  );
}
