import { useState } from "react";
import { Check, ChevronRight, LoaderCircle, X } from "lucide-react";
import { PixelAvatar } from "./Bot";
import type { BotDefinition, BotTask } from "./Bot";
import { request } from "./api";
import type { BotFleetVerdict, BotPlanHistoryEntry, BotPlanStep } from "./types";
import "./bot-plan.css";

const UNDO_WINDOW_MS = 30_000;

const stepStatusLabels: Record<string, string> = {
  pending: "待派发",
  ready: "待启动",
  running: "执行中",
  dispatched: "执行中",
  done: "已完成",
  failed: "失败",
  skipped: "已跳过",
  blocked: "已跳过",
};

const planStatusLabels: Record<string, string> = {
  proposed: "待确认",
  auto: "自动",
  approved: "已确认",
  rejected: "已拒绝",
  running: "执行中",
  merging: "汇总中",
  done: "已完成",
  failed: "已中止",
  cancelled: "已取消",
};

type PlanAction = "approve" | "reject" | "cancel" | "retry-step" | "skip-step";

export function getPlanStatusTier(status: string): "active" | "muted" | "warning" {
  if (status === "running" || status === "merging") {
    return "active";
  }
  if (status === "done") {
    return "muted";
  }
  if (
    status === "failed" ||
    status === "cancelled" ||
    status === "proposed" ||
    status === "rejected"
  ) {
    return "warning";
  }
  return "muted";
}

function formatHistoryTime(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  return `${h}:${m}`;
}

export function formatPlanTimeline(history?: BotPlanHistoryEntry[]): string {
  if (!history || !history.length) return "";
  return history
    .map((entry, idx) => {
      if (idx === 0 && entry.from === null) {
        return entry.to;
      }
      const time = formatHistoryTime(entry.at);
      return time ? `${entry.to} ${time}` : entry.to;
    })
    .join(" → ");
}

function VerdictList({ items, empty }: { items: string[]; empty: string }) {
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

export function FleetVerdict({ verdict }: { verdict: BotFleetVerdict }) {
  return (
    <div className="bot-fleet-verdict">
      {verdict.judgment && (
        <section className="bot-fleet-verdict-block">
          <h3>判断</h3>
          <p className="bot-fleet-verdict-judgment">{verdict.judgment}</p>
        </section>
      )}
      <section className="bot-fleet-verdict-block">
        <h3>分歧</h3>
        <VerdictList items={verdict.disagreements} empty="没有实质分歧" />
      </section>
      <section className="bot-fleet-verdict-block">
        <h3>风险</h3>
        <VerdictList items={verdict.risks} empty="没标出额外风险" />
      </section>
      <details className="bot-fleet-verdict-consensus">
        <summary>
          <ChevronRight size={13} className="bot-plan-chevron" />
          共识{verdict.consensus.length ? ` · ${verdict.consensus.length}` : ""}
        </summary>
        <VerdictList items={verdict.consensus} empty="没有单独列出的共识" />
      </details>
    </div>
  );
}

export function stepDisplayName(step: BotPlanStep, bots: BotDefinition[]): string {
  if (step.kind === "fleet" || step.label) {
    return step.label || step.family || step.presetId || "模型";
  }
  return bots.find((bot) => bot.id === step.botId)?.name || step.botId;
}

function StepRow({
  step,
  bots,
  busy,
  onAction,
}: {
  step: BotPlanStep;
  bots: BotDefinition[];
  busy: boolean;
  onAction: (action: PlanAction, stepId?: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const target = bots.find((bot) => bot.id === step.botId);
  const botName = stepDisplayName(step, bots);
  const fleetStep = step.kind === "fleet";
  const summary = step.result?.summary;
  const canExpand = Boolean(!fleetStep && summary && (summary.length > 50 || summary.includes("\n")));

  return (
    <li className={`bot-plan-step bot-plan-step-${step.status || "pending"}`}>
      <span className="bot-plan-step-dot" aria-hidden="true" />
      {target && !fleetStep && (
        <PixelAvatar
          className="bot-plan-step-avatar"
          avatarId={target.avatarId}
          color={target.avatarColor}
          seed={target.id}
        />
      )}
      <span className="bot-plan-step-bot-name" title={botName}>
        <strong>{botName}</strong>
      </span>
      <div className="bot-plan-step-content">
        {!fleetStep && step.goal && <div className="bot-plan-step-goal">{step.goal}</div>}
        {summary && (
          <div className="bot-plan-step-summary-wrap">
            <div className={`bot-plan-step-summary ${expanded ? "is-expanded" : "is-clamped"}`}>
              {summary}
            </div>
            {canExpand && (
              <button
                type="button"
                className="bot-plan-summary-toggle"
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? "收起" : "展开"}
              </button>
            )}
          </div>
        )}
      </div>
      <div className="bot-plan-step-trailing">
        {step.status === "failed" && !fleetStep && (
          <div className="bot-plan-step-btns">
            <button
              type="button"
              className="bot-plan-step-btn bot-plan-approve"
              onClick={() => onAction("retry-step", step.id)}
              disabled={busy}
            >
              重试
            </button>
            <button
              type="button"
              className="bot-plan-step-btn bot-plan-reject"
              onClick={() => onAction("skip-step", step.id)}
              disabled={busy}
            >
              跳过
            </button>
          </div>
        )}
        <span className="bot-plan-step-status">
          {stepStatusLabels[step.status || "pending"] || step.status}
        </span>
      </div>
    </li>
  );
}

export function BotPlan({ task, bots }: { task: BotTask; bots: BotDefinition[] }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const plan = task.coordinatorPlan;
  if (!plan || (plan.mode !== "delegate" && plan.mode !== "fleet") || !plan.steps?.length) return null;
  const status = plan.status || "auto";
  const fleet = plan.mode === "fleet";
  const doneCount = plan.steps.filter((step) => ["done", "skipped", "failed"].includes(step.status || "")).length;
  const statusLabel = fleet && status === "running"
    ? `${doneCount}/${plan.steps.length} 已回`
    : (planStatusLabels[status] || status);
  const statusTier = getPlanStatusTier(status);
  const timeline = formatPlanTimeline(plan.history);
  const hasDeps = !fleet && plan.steps.some((step) => (step.dependsOn?.length ?? 0) > 0 || step.presetId);
  const hasDetails = Boolean(!fleet && (timeline || hasDeps));

  const undoable =
    (status === "auto" || status === "approved" || status === "running") &&
    Boolean(task.planExecutedAt) &&
    Date.now() - new Date(task.planExecutedAt as string).valueOf() < UNDO_WINDOW_MS;

  async function act(action: PlanAction, stepId?: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await request(`/tasks/${task.id}/plan`, {
        action,
        ...(stepId ? { stepId } : {}),
        requestId: `plan-${action}-${stepId || "all"}-${task.id}-${Date.now()}`,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "计划操作未完成，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`bot-plan bot-plan-${status}`} aria-label={plan.mode === "fleet" ? "模型意见" : "分工计划"}>
      <div className="bot-plan-head">
        <span className="bot-plan-title">{plan.mode === "fleet" ? "模型意见" : "分工计划"}</span>
        <span className={`bot-plan-tag bot-plan-tag-${statusTier}`}>
          {statusLabel}
        </span>
        {plan.reason && <span className="bot-plan-reason">{plan.reason}</span>}
        {plan.notice && <p className="bot-plan-notice">{plan.notice}</p>}
        {plan.source === "fallback" && <span className="bot-plan-tag bot-plan-tag-muted">关键词兜底</span>}
        {plan.source === "user" && <span className="bot-plan-tag bot-plan-tag-muted">已修改</span>}
      </div>
      {fleet && plan.verdict && <FleetVerdict verdict={plan.verdict} />}
      {(!fleet || !plan.verdict) && (
      <ul className="bot-plan-steps">
        {plan.steps.map((step) => (
          <StepRow
            key={step.id}
            step={step}
            bots={bots}
            busy={busy}
            onAction={(action, stepId) => void act(action, stepId)}
          />
        ))}
      </ul>
      )}
      {fleet && plan.verdict && (
        <details className="bot-plan-detail">
          <summary>
            <ChevronRight size={13} className="bot-plan-chevron" />
            各家原文
          </summary>
          <ul className="bot-plan-steps">
            {plan.steps.map((step) => (
              <StepRow
                key={step.id}
                step={step}
                bots={bots}
                busy={busy}
                onAction={(action, stepId) => void act(action, stepId)}
              />
            ))}
          </ul>
        </details>
      )}
      {hasDetails && (
        <details className="bot-plan-detail">
          <summary>
            <ChevronRight size={13} className="bot-plan-chevron" />
            依赖与模型
          </summary>
          <div className="bot-plan-detail-body">
            {timeline && (
              <div className="bot-plan-timeline">
                <span className="bot-plan-timeline-label">时间线：</span>
                <span className="bot-plan-timeline-track">{timeline}</span>
              </div>
            )}
            {hasDeps && (
              <ul>
                {plan.steps.map((step) => (
                  <li key={step.id}>
                    {step.id}
                    {step.dependsOn?.length ? ` · 等待 ${step.dependsOn.join("、")}` : " · 无前置依赖"}
                    {step.presetId ? ` · 指定模型 ${step.presetId}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </details>
      )}
      {!fleet && (status === "proposed" || undoable || status === "running") && (
        <div className="bot-plan-actions">
          {status === "proposed" && (
            <button type="button" className="bot-plan-approve" onClick={() => void act("approve")} disabled={busy}>
              {busy ? <LoaderCircle className="bot-spin" size={13} /> : <Check size={13} />}
              确认分工
            </button>
          )}
          {(status === "proposed" || undoable) && (
            <button type="button" className="bot-plan-reject" onClick={() => void act("reject")} disabled={busy}>
              <X size={13} />
              {status === "proposed" ? "拒绝，自己做" : "撤回分工"}
            </button>
          )}
          {status === "running" && (
            <button type="button" className="bot-plan-reject" onClick={() => void act("cancel")} disabled={busy}>
              <X size={13} />
              取消计划
            </button>
          )}
        </div>
      )}
      {fleet && status === "running" && (
        <div className="bot-plan-actions">
          <button type="button" className="bot-plan-reject" onClick={() => void act("cancel")} disabled={busy}>
            <X size={13} />
            停止
          </button>
        </div>
      )}
      {error && (
        <p className="bot-plan-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

