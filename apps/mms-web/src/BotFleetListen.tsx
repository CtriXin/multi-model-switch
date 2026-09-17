import { useState } from "react";
import { ChevronRight } from "lucide-react";
import type { BotFleetVerdict, BotPlanStep } from "./types";

function shortLabel(step: BotPlanStep): string {
  const label = step.label || step.family || "模型";
  const parts = label.split("·").map((part) => part.trim());
  return parts[parts.length - 1] || label;
}

function parsePackedTake(text: string): { conclusion: string; dissent: string; risk: string } {
  const parts = String(text || "").split(/(结论|不同意|风险)\s*[:：]\s*/);
  const out = { conclusion: "", dissent: "", risk: "" };
  const map: Record<string, keyof typeof out> = {
    结论: "conclusion",
    不同意: "dissent",
    风险: "risk",
  };
  for (let i = 1; i + 1 < parts.length; i += 2) {
    const key = map[parts[i]];
    const body = parts[i + 1].replace(/\s+/g, " ").trim();
    if (key && body) out[key] = body;
  }
  return out;
}

function takeFromStep(step: BotPlanStep): { conclusion: string; dissent: string; risk: string; summary: string } {
  const raw = step.result || {};
  const blob = String(raw.conclusion || raw.summary || "");
  const packed = /不同意\s*[:：]|风险\s*[:：]/.test(blob);
  if (packed && !raw.dissent) {
    const parsed = parsePackedTake(blob);
    return { ...parsed, summary: "" };
  }
  return {
    conclusion: String(raw.conclusion || ""),
    dissent: String(raw.dissent || ""),
    risk: String(raw.risk || ""),
    summary: String(raw.summary || ""),
  };
}

function TakeBody({ step, compact = false }: { step: BotPlanStep; compact?: boolean }) {
  const take = takeFromStep(step);
  const limit = compact ? 42 : 400;
  const rows = [
    take.conclusion && ["结论", take.conclusion],
    take.dissent && ["不同", take.dissent],
    take.risk && ["风险", take.risk],
  ].filter(Boolean) as Array<[string, string]>;
  if (!rows.length && take.summary) {
    return (
      <>
        <div className="bot-fleet-take-body">
          <p>{compact ? take.summary.replace(/\s+/g, " ").slice(0, 80) + (take.summary.length > 80 ? "…" : "") : take.summary}</p>
        </div>
        {compact && <p className="bot-fleet-take-hint">点开看完</p>}
      </>
    );
  }
  if (!rows.length) {
    return <p className="bot-fleet-take-empty">还没回</p>;
  }
  return (
    <>
      <div className="bot-fleet-take-body">
        {rows.map(([label, text]) => (
          <p key={label}>
            <span>{label}</span>
            {compact && text.length > limit ? text.slice(0, limit).trimEnd() + "…" : text}
          </p>
        ))}
      </div>
      {compact && <p className="bot-fleet-take-hint">点开看完</p>}
    </>
  );
}

export function FleetPills({
  steps,
  pinnedId,
  onPin,
}: {
  steps: BotPlanStep[];
  pinnedId: string;
  onPin: (stepId: string) => void;
}) {
  return (
    <div className="bot-fleet-pills" aria-label="各家模型">
      {steps.map((step) => {
        const pinned = pinnedId === step.id;
        return (
          <div key={step.id} className={"bot-fleet-pill-wrap" + (pinned ? " is-pinned" : "")}>
            <button
              type="button"
              className={"bot-fleet-pill bot-fleet-pill-" + (step.status || "pending") + (pinned ? " is-on" : "")}
              aria-pressed={pinned}
              title="挪上来看一眼，点开看完"
              onClick={() => onPin(pinned ? "" : step.id)}
            >
              {shortLabel(step)}
            </button>
            <div className="bot-fleet-take-menu">
              <div className="bot-fleet-take-card">
                <strong>{shortLabel(step)}</strong>
                <TakeBody step={step} compact />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function VerdictItems({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) {
    return <p className="bot-fleet-verdict-empty">{empty}</p>;
  }
  return (
    <ul className="bot-fleet-verdict-list">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}

export function FleetLivePills({ steps }: { steps: BotPlanStep[] }) {
  const [pinnedId, setPinnedId] = useState("");
  const pinned = steps.find((step) => step.id === pinnedId);
  return (
    <div className="bot-fleet-live">
      <FleetPills steps={steps} pinnedId={pinnedId} onPin={setPinnedId} />
      {pinned && (
        <div className="bot-fleet-take-card is-pinned-card">
          <strong>{shortLabel(pinned)}</strong>
          <TakeBody step={pinned} />
        </div>
      )}
    </div>
  );
}

export function FleetVerdict({
  verdict,
  steps,
}: {
  verdict: BotFleetVerdict;
  steps: BotPlanStep[];
}) {
  const [pinnedId, setPinnedId] = useState("");
  const pinned = steps.find((step) => step.id === pinnedId);

  return (
    <div className="bot-fleet-verdict">
      {verdict.judgment && <p className="bot-fleet-verdict-judgment">{verdict.judgment}</p>}
      <div className="bot-fleet-verdict-scan">
        <div>
          <h3>分歧</h3>
          <VerdictItems items={verdict.disagreements} empty="没什么分歧" />
        </div>
        <div>
          <h3>风险</h3>
          <VerdictItems items={verdict.risks} empty="没提风险" />
        </div>
      </div>
      <FleetPills steps={steps} pinnedId={pinnedId} onPin={setPinnedId} />
      {pinned && (
        <div className="bot-fleet-take-card is-pinned-card">
          <strong>{shortLabel(pinned)}</strong>
          <TakeBody step={pinned} />
        </div>
      )}
      <details className="bot-fleet-verdict-consensus">
        <summary>
          <ChevronRight size={13} className="bot-plan-chevron" />
          大家都认的
        </summary>
        <VerdictItems items={verdict.consensus} empty="没单写" />
      </details>
    </div>
  );
}
