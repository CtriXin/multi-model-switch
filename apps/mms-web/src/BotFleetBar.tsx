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
  onChange: (next: BotFleetPolicy) => void;
}) {
  const locked = Boolean(disabled || busy);
  const allOn = families.length > 0 && policy.families.length === families.length
    && families.every((name) => policy.families.includes(name));
  const visibleFamilies = [...new Set([...families, ...policy.families])];

  function patch(partial: Partial<BotFleetPolicy>) {
    if (locked) return;
    onChange(normalizeFleetPolicy({ ...policy, ...partial }));
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
    if (locked) return;
    const selected = policy.families.includes(family)
      ? policy.families
      : [...policy.families, family].slice(0, 12);
    patch({
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
                  aria-haspopup="menu"
                  title={name === label ? `${name}，悬停选模型` : `${name} · ${label}`}
                  disabled={locked}
                  onClick={() => toggleFamily(name)}
                >
                  {label}
                </button>
                {options.length > 0 && (
                  <div className="bot-fleet-model-menu" role="menu" aria-label={`${name} 可选模型`}>
                    <div className="bot-fleet-model-panel">
                    {remembered && <button type="button" role="menuitemradio" aria-checked={false}
                      className="bot-fleet-model-item" disabled={locked}
                      onClick={() => patch({ models: { ...policy.models, [name]: "" } })}>
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
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            pickModel(name, preset.id);
                          }}
                        >
                          {compactModelLabel(preset.name)}
                          {options.some((other) => other.id !== preset.id && other.name === preset.name)
                            && ` · ${preset.channel || preset.providerId || preset.id}`}
                        </button>
                      );
                    })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {policy.enabled && (
        <p className="bot-fleet-preview">{fleetPreviewLabel(policy, families, presets)}</p>
      )}
    </div>
  );
}
