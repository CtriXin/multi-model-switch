import { useState } from "react";
import { ChevronRight } from "lucide-react";
import type { BotFleetVerdict, BotPlanStep } from "./types";

function shortLabel(step: BotPlanStep): string {
  const label = step.label || step.family || "模型";
  const parts = label.split("·").map((part) => part.trim());
  return parts[parts.length - 1] || label;
}

function clip(text: string, limit: number): string {
  const value = String(text || "").trim();
  if (value.length <= limit) return value;
  return value.slice(0, limit).trimEnd() + "…";
}

function TakeBody({ step, compact = false }: { step: BotPlanStep; compact?: boolean }) {
  const take = step.result;
  const limit = compact ? 72 : 400;
  if (take?.conclusion || take?.dissent || take?.risk) {
    return (
      <>
        {take.conclusion && (
          <p>
            <span>结论</span>
            {clip(take.conclusion, limit)}
          </p>
        )}
        {take.dissent && (
          <p>
            <span>不同</span>
            {clip(take.dissent, limit)}
          </p>
        )}
        {take.risk && (
          <p>
            <span>风险</span>
            {clip(take.risk, limit)}
          </p>
        )}
        {compact && <p className="bot-fleet-take-hint">点开看完</p>}
      </>
    );
  }
  if (take?.summary) {
    return (
      <>
        <p>{clip(take.summary, compact ? 90 : 600)}</p>
        {compact && <p className="bot-fleet-take-hint">点开看完</p>}
      </>
    );
  }
  return <p className="bot-fleet-take-empty">还没回</p>;
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
