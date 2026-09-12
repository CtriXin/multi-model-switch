import { useState } from "react";
import { Check, ChevronRight, LoaderCircle, X } from "lucide-react";
import { PixelAvatar } from "./Bot";
import type { BotDefinition, BotTask } from "./Bot";
import { request } from "./api";
import type { BotPlanStep } from "./types";
import "./bot-plan.css";

const UNDO_WINDOW_MS = 30_000;

const stepStatusLabels: Record<string, string> = {
  pending: "待派发",
  dispatched: "执行中",
  done: "已完成",
  failed: "失败",
  blocked: "已跳过",
};

function StepRow({ step, bots }: { step: BotPlanStep; bots: BotDefinition[] }) {
  const target = bots.find((bot) => bot.id === step.botId);
  return (
    <li className={`bot-plan-step bot-plan-step-${step.status || "pending"}`}>
      <span className="bot-plan-step-dot" aria-hidden="true" />
      {target && (
        <PixelAvatar
          className="bot-plan-step-avatar"
          avatarId={target.avatarId}
          color={target.avatarColor}
          seed={target.id}
        />
      )}
      <span className="bot-plan-step-goal">
        <strong>{target?.name || step.botId}</strong>
        {step.goal && <span>{step.goal}</span>}
      </span>
      <span className="bot-plan-step-status">{stepStatusLabels[step.status || "pending"] || step.status}</span>
    </li>
  );
}

export function BotPlan({ task, bots }: { task: BotTask; bots: BotDefinition[] }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const plan = task.coordinatorPlan;
  if (!plan || plan.mode !== "delegate" || !plan.steps?.length) return null;
  const status = plan.status || "auto";
  const undoable =
    (status === "auto" || status === "approved") &&
    Boolean(task.planExecutedAt) &&
    Date.now() - new Date(task.planExecutedAt as string).valueOf() < UNDO_WINDOW_MS;
  async function act(action: "approve" | "reject") {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await request(`/tasks/${task.id}/plan`, { action, requestId: `plan-${action}-${task.id}` });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "计划操作未完成，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className={`bot-plan bot-plan-${status}`} aria-label="分工计划">
      <div className="bot-plan-head">
        <span className="bot-plan-title">分工计划</span>
        {plan.reason && <span className="bot-plan-reason">{plan.reason}</span>}
        {plan.source === "fallback" && <span className="bot-plan-tag">关键词兜底</span>}
        {plan.source === "user" && <span className="bot-plan-tag">已修改</span>}
      </div>
      <ul className="bot-plan-steps">
        {plan.steps.map((step) => (
          <StepRow key={step.id} step={step} bots={bots} />
        ))}
      </ul>
      {plan.steps.some((step) => (step.dependsOn?.length ?? 0) > 0 || step.presetId) && (
        <details className="bot-plan-detail">
          <summary>
            <ChevronRight size={13} className="bot-plan-chevron" />
            依赖与模型
          </summary>
          <ul>
            {plan.steps.map((step) => (
              <li key={step.id}>
                {step.id}
                {step.dependsOn?.length ? ` · 等待 ${step.dependsOn.join("、")}` : " · 无前置依赖"}
                {step.presetId ? ` · 指定模型 ${step.presetId}` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
      {(status === "proposed" || undoable) && (
        <div className="bot-plan-actions">
          {status === "proposed" && (
            <button type="button" className="bot-plan-approve" onClick={() => void act("approve")} disabled={busy}>
              {busy ? <LoaderCircle className="bot-spin" size={13} /> : <Check size={13} />}
              确认分工
            </button>
          )}
          <button type="button" className="bot-plan-reject" onClick={() => void act("reject")} disabled={busy}>
            <X size={13} />
            {status === "proposed" ? "拒绝，自己做" : "撤回分工"}
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
