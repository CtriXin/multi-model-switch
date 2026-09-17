import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import esbuild from "esbuild";
import React from "react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load SessionStatus module
const sessionStatusFile = path.resolve(__dirname, "../src/SessionStatus.tsx");
const sessionStatusSource = fs.readFileSync(sessionStatusFile, "utf-8");
const sessionStatusTranspiled = esbuild.transformSync(sessionStatusSource, {
  loader: "tsx",
  format: "cjs",
}).code;

const statusMod = { exports: {} };
const statusSandbox = {
  module: statusMod,
  exports: statusMod.exports,
  require: (req) => {
    if (req === "react") return React;
    if (req === "lucide-react") return {
      Check: () => null,
      Circle: () => null,
      CircleAlert: () => null,
      Pause: () => null,
      CircleHelp: () => null,
      WifiOff: () => null,
      LoaderCircle: () => null,
      Wrench: () => null,
    };
    return {};
  },
  console,
};
vm.createContext(statusSandbox);
vm.runInContext(sessionStatusTranspiled, statusSandbox);

const {
  sessionStatus,
  activityHints,
  turnWorkingHint,
  sessionIsBusy,
  isTurnInterrupted,
  turnInterruptedNotice,
  BUSY_PHASES,
} = statusMod.exports;

import { renderToStaticMarkup } from "react-dom/server";

// Load Transcript module
const transcriptFile = path.resolve(__dirname, "../src/Transcript.tsx");
const transcriptSource = fs.readFileSync(transcriptFile, "utf-8");
const transcriptTranspiled = esbuild.transformSync(transcriptSource, {
  loader: "tsx",
  format: "cjs",
}).code;

const transcriptMod = { exports: {} };
const transcriptSandbox = {
  React,
  module: transcriptMod,
  exports: transcriptMod.exports,
  require: (req) => {
    if (req === "react") return React;
    if (req === "lucide-react") return {
      ChevronRight: () => React.createElement("span", { className: "icon-chevron-right" }),
      ChevronDown: () => React.createElement("span", { className: "icon-chevron-down" }),
      RotateCcw: () => React.createElement("span", { className: "icon-resend" }),
      CircleAlert: () => React.createElement("span", { className: "icon-alert" }),
    };
    if (req === "./SessionStatus") return statusMod.exports;
    if (req === "./components") return {
      EventView: (props) => React.createElement("div", { className: "event-view" }, props.event?.text),
      Logo: () => React.createElement("span", { className: "logo" }),
      harnessNames: {},
    };
    if (req === "./message-control") return {
      deliveryLabel: () => "小字提示",
      steerLinks: () => [],
      steerBadge: () => "",
    };
    if (req === "./ToolEvent") return {
      ToolGroup: () => React.createElement("div", { className: "tool-group" }),
      ToolEvent: () => null,
    };
    if (req === "./ConversationOutline") return { ConversationOutline: () => null };
    return {};
  },
  console,
};
vm.createContext(transcriptSandbox);
vm.runInContext(transcriptTranspiled, transcriptSandbox);

const {
  isTurnCompleted,
  evaluateTurnReplySlot,
  Turn,
} = transcriptMod.exports;

test("turnWorkingHint provides clear status hint for thinking, tool, responding and waiting", () => {
  // Thinking phase
  const thinkingSession = {
    state: "running",
    activity: { phase: "thinking" },
  };
  assert.equal(turnWorkingHint(thinkingSession), "正在思考…");

  // Tool execution with specific tool name
  const toolSession = {
    state: "running",
    activity: { phase: "tool", toolName: "read_file" },
  };
  assert.equal(turnWorkingHint(toolSession), "正在执行工具 · read_file");

  // Tool execution without tool name
  const genericToolSession = {
    state: "running",
    activity: { phase: "tool" },
  };
  assert.equal(turnWorkingHint(genericToolSession), "正在执行终端工具…");

  // Responding phase
  const respondingSession = {
    state: "running",
    activity: { phase: "responding" },
  };
  assert.equal(turnWorkingHint(respondingSession), "正在输出回复…");

  // Waiting user confirmation
  const waitingConfirmSession = {
    state: "waiting",
    activity: { phase: "waiting", method: "confirm" },
  };
  assert.equal(turnWorkingHint(waitingConfirmSession), "等待确认工具操作");

  // Waiting user input
  const waitingInputSession = {
    state: "waiting",
    activity: { phase: "waiting" },
  };
  assert.equal(turnWorkingHint(waitingInputSession), "等待你的回答");

  // Fallback for null or unknown activity: already-read idle is pending
  const idleSession = { state: "idle", activity: null };
  assert.equal(turnWorkingHint(idleSession), "就绪 · 随时发送消息");
  assert.equal(turnWorkingHint(idleSession, false, true), "本轮执行完成");
});

test("sidebar phases distinguish loading, tool, unread complete and read pending", () => {
  const disconnected = false;
  assert.equal(
    sessionStatus({ state: "running", activity: { phase: "responding" } }, disconnected).phase,
    "responding",
  );
  assert.equal(
    sessionStatus({ state: "running", activity: { phase: "responding" } }, disconnected).label,
    "正在输出",
  );
  assert.equal(
    sessionStatus({ state: "running", activity: { phase: "tool", toolName: "bash" } }, disconnected).label,
    "执行工具",
  );
  const settled = { state: "idle", activity: null };
  assert.equal(sessionStatus(settled, disconnected, true).phase, "completed");
  assert.equal(sessionStatus(settled, disconnected, true).label, "已完成");
  assert.equal(sessionStatus(settled, disconnected, false).phase, "pending");
  assert.equal(sessionStatus(settled, disconnected, false).label, "待命");
  assert.equal(sessionStatus(settled).phase, "pending");
});

test("activityHints exports correct hints for all active phases", () => {
  assert.equal(activityHints.thinking, "正在思考…");
  assert.equal(activityHints.responding, "正在输出回复…");
  assert.equal(activityHints.compacting, "正在整理上下文…");
  assert.equal(activityHints.retrying, "正在自动重试…");
  assert.equal(activityHints.tool, "正在执行终端工具…");
});

test("SessionStatus labels and sessionIsBusy align with status bar phases without backdoor", () => {
  // sessionIsBusy does not have disconnected backdoor
  assert.equal(
    sessionIsBusy({ state: "running", activity: { phase: "tool", toolName: "bash" } }, true),
    true,
    "sessionIsBusy evaluates real activity even if disconnected argument is true",
  );
  assert.equal(
    sessionIsBusy({ state: "idle", activity: { phase: "tool", toolName: "bash" } }),
    true,
    "idle state with active tool phase is busy (matches status bar)",
  );
  assert.equal(
    sessionIsBusy({ state: "idle", activity: { phase: "thinking" } }),
    true,
    "idle state with thinking phase is busy",
  );
  assert.equal(
    sessionIsBusy({ state: "idle", activity: null }),
    false,
    "idle state with null activity is not busy",
  );
  assert.equal(
    sessionIsBusy({ state: "stopped", activity: null }),
    false,
    "stopped state is not busy",
  );
});

test("isTurnCompleted mutation sensitivity: 分支 1 (有工具在跑) 独立敏感测试", () => {
  // Dataset: tool status is 'running', but session.activity is null.
  // This isolates hasRunningTool: if hasRunningTool branch is removed, this assertion MUST FAIL!
  const sessionWithNoActivity = {
    state: "running",
    activity: null,
  };
  const turnWithRunningTool = [
    { id: "u1", kind: "user", text: "sleep 60" },
    { id: "t1", kind: "tool", status: "running" },
  ];

  // Turn index 0 out of 2 turns:
  assert.equal(
    isTurnCompleted(turnWithRunningTool, 0, 2, sessionWithNoActivity, false),
    false,
    "Turn with running tool must not be marked completed even when session activity is null",
  );
});

test("isTurnCompleted mutation sensitivity: 分支 2 (activity 靶向当前回合) 独立敏感测试", () => {
  // Dataset: NO running tools in turn (all completed), but session.activity targets this turn.
  // This isolates hasActiveEvent: if hasActiveEvent branch is removed, this assertion MUST FAIL!
  const sessionTargetingTurn = {
    state: "running",
    activity: { phase: "thinking", eventId: "think1" },
  };
  const turnWithActiveThinking = [
    { id: "u1", kind: "user", text: "ponder question" },
    { id: "think1", kind: "thinking", text: "deep thoughts..." },
    { id: "t1", kind: "tool", status: "completed" },
  ];

  // Turn index 0 out of 2 turns:
  assert.equal(
    isTurnCompleted(turnWithActiveThinking, 0, 2, sessionTargetingTurn, false),
    false,
    "Turn targeted by active session activity must not be marked completed even when tools are completed",
  );
});

test("isTurnCompleted: 已经完成的回合在工具完成且无活动时正确识别为已完成", () => {
  const idleSession = {
    state: "running",
    activity: { phase: "responding", eventId: "a2" },
  };
  const finishedTurn = [
    { id: "u1", kind: "user", text: "sleep 60" },
    { id: "t1", kind: "tool", status: "completed" },
  ];
  assert.equal(
    isTurnCompleted(finishedTurn, 0, 2, idleSession, false),
    true,
    "Finished turn is marked completed when its tool is completed and active activity is elsewhere",
  );
});

test("evaluateTurnReplySlot mutation sensitivity: 三槽位精准分流与真实渲染", () => {
  const stoppedSession = { state: "stopped", activity: null };
  const runningSession = { state: "running", activity: { phase: "tool", toolName: "bash" } };
  const idleSession = { state: "idle", activity: null };

  // Case A: 真正被强行收尾的回合 (force-ended tool) 且为当前最新回合 -> 产生 'interrupted' 槽位
  const forceEndedTurn = [
    { id: "u1", kind: "user", text: "long running command" },
    { id: "t1", kind: "tool", status: "error", text: "本轮已结束，未收到此工具的完成回报。" },
  ];
  const forceEndedResult = evaluateTurnReplySlot({
    events: forceEndedTurn,
    completed: true,
    isLatestTurn: true,
    isSteered: false,
    session: stoppedSession,
  });
  assert.equal(forceEndedResult.slot, "interrupted", "latest turn with force-ended tool must evaluate to interrupted slot");
  assert.equal(forceEndedResult.notice, "本轮执行被中断，未产生回复。发送新消息可继续对话。");

  // 历史完成回合 (isLatestTurn === false) 即使有 force-ended tool 标记也必须归入 'empty' (渲染 null)，绝不误出中断提示
  const historicalForceEndedResult = evaluateTurnReplySlot({
    events: forceEndedTurn,
    completed: true,
    isLatestTurn: false,
    isSteered: false,
    session: stoppedSession,
  });
  assert.equal(historicalForceEndedResult.slot, "empty", "historical turn with force-ended tool must evaluate to empty slot and never show false interrupted notice");

  // Case B: 中途引导的回合 (isSteered === true) -> 必须产生 'empty' (渲染 null)，绝不加第三档文案
  const steeredTurn = [
    { id: "u1", kind: "user", text: "执行 bash sleep 25" },
    { id: "t1", kind: "tool", status: "completed", text: "done" },
  ];
  const steeredResult = evaluateTurnReplySlot({
    events: steeredTurn,
    completed: true,
    isLatestTurn: false,
    isSteered: true,
    session: runningSession,
  });
  assert.equal(steeredResult.slot, "empty", "steered turn must evaluate to empty slot and render null without third-tier copy");

  // Case C: 历史已完成回合 (无 force-ended 痕迹) -> 必须产生 'empty' (渲染 null)，绝无中断提示
  const historicalTurnWithoutAnswer = [
    { id: "u0", kind: "user", text: "prior step" },
    { id: "t0", kind: "tool", status: "completed", text: "ok" },
  ];
  const historicalResult = evaluateTurnReplySlot({
    events: historicalTurnWithoutAnswer,
    completed: true,
    isLatestTurn: false,
    isSteered: false,
    session: idleSession,
  });
  assert.equal(historicalResult.slot, "empty", "historical completed turn must evaluate to empty slot and not show interrupted notice");

  // Case D: 正在执行中的回合 (!completed) -> 产生 'working' 槽位
  const workingResult = evaluateTurnReplySlot({
    events: steeredTurn,
    completed: false,
    isLatestTurn: true,
    isSteered: false,
    session: runningSession,
  });
  assert.equal(workingResult.slot, "working", "in-flight turn must evaluate to working status slot");

  // Case E: 有正常回答的回合 -> 产生 'answer' 槽位
  const answeredTurn = [
    { id: "u1", kind: "user", text: "hello" },
    { id: "a1", kind: "assistant", text: "world" },
  ];
  const answeredResult = evaluateTurnReplySlot({
    events: answeredTurn,
    completed: true,
    isLatestTurn: true,
    isSteered: false,
    session: idleSession,
  });
  assert.equal(answeredResult.slot, "answer", "turn with assistant text must evaluate to answer slot");
});

test("CSS: 保证 interrupted notice 与 resend button 样式合规且无裸 hex", () => {
  const cssFile = path.resolve(__dirname, "../src/transcript.css");
  const css = fs.readFileSync(cssFile, "utf-8");

  assert.ok(css.includes(".turn-interrupted-notice"), "defines .turn-interrupted-notice");
  assert.ok(css.includes(".pending-resend-button"), "defines .pending-resend-button");
  assert.doesNotMatch(css, /\.pending-messages\s*\{[^}]*border-top:\s*1px dashed/);

  const turnWorkingSection = css.slice(css.indexOf("/* Working status placeholder"));
  assert.equal(turnWorkingSection.includes("#"), false, "no bare hex in interrupted/working section");
});

test("isTurnInterrupted mutation sensitivity: isSteered short-circuit overrides force-ended tool events", () => {
  const stoppedSession = { state: "stopped", activity: null };
  const forceEndedTurnEvents = [
    { id: "u1", kind: "user", text: "long running command" },
    { id: "t1", kind: "tool", status: "error", text: "本轮已结束，未收到此工具的完成回报。" },
  ];

  // 1. isSteered=true 时必须短路返回 false（即使存在 forceEndedTool 事件文本）
  // 若移除 `if (isSteered) return false;` 突变，此断言必挂！
  assert.equal(
    isTurnInterrupted(forceEndedTurnEvents, stoppedSession, true, true),
    false,
    "isSteered=true must short-circuit and return false even with finish_pending_tools error text",
  );

  // 2. isSteered=false 且 isLatestTurn=true 时必须返回 true
  assert.equal(
    isTurnInterrupted(forceEndedTurnEvents, stoppedSession, true, false),
    true,
    "isSteered=false must return true for latest turn with finish_pending_tools error text",
  );

  // 3. 历史回合 isLatestTurn=false 时必须严格返回 false
  assert.equal(
    isTurnInterrupted(forceEndedTurnEvents, stoppedSession, false, false),
    false,
    "isLatestTurn=false must return false for historical turn",
  );
});

test("DOM/SSR: renderToStaticMarkup locks turn-interrupted-notice copy and resend button rendering", () => {
  const stoppedSession = {
    id: "s-test",
    state: "stopped",
    activity: null,
  };
  const mockDetail = {
    session: stoppedSession,
    events: [],
  };

  const forceEndedTurnEvents = [
    { id: "u1", kind: "user", text: "sleep 600", createdAt: "2026-09-16T12:00:00Z" },
    { id: "t1", kind: "tool", status: "error", text: "本轮已结束，未收到此工具的完成回报。" },
  ];

  // Case 1: Latest interrupted turn WITH onResend handler
  // Must render .turn-interrupted-notice, the exact notice text, and .pending-resend-button
  const interruptedHtml = renderToStaticMarkup(
    React.createElement(Turn, {
      events: forceEndedTurnEvents,
      completed: true,
      forced: null,
      report: () => {},
      steered: new Map(),
      isLatestTurn: true,
      isSteered: false,
      onResend: () => {},
      detail: mockDetail,
      autoCollapseProcess: true,
    })
  );

  assert.ok(
    interruptedHtml.includes('class="turn-interrupted-notice"'),
    "HTML must include turn-interrupted-notice container",
  );
  assert.ok(
    interruptedHtml.includes("本轮执行被中断，未产生回复。发送新消息可继续对话。"),
    "HTML must render the exact interrupted notice copy",
  );
  assert.ok(
    interruptedHtml.includes('class="pending-resend-button"'),
    "HTML must include pending-resend-button",
  );
  assert.ok(
    interruptedHtml.includes("重新发送"),
    "HTML must render '重新发送' button label",
  );

  // Case 2: Historical completed turn (isLatestTurn = false)
  // Must NOT render turn-interrupted-notice or pending-resend-button
  const historicalHtml = renderToStaticMarkup(
    React.createElement(Turn, {
      events: forceEndedTurnEvents,
      completed: true,
      forced: null,
      report: () => {},
      steered: new Map(),
      isLatestTurn: false,
      isSteered: false,
      onResend: () => {},
      detail: mockDetail,
      autoCollapseProcess: true,
    })
  );

  assert.equal(
    historicalHtml.includes("turn-interrupted-notice"),
    false,
    "Historical turn must NOT render turn-interrupted-notice",
  );
  assert.equal(
    historicalHtml.includes("pending-resend-button"),
    false,
    "Historical turn must NOT render pending-resend-button",
  );

  // Case 3: Steered turn (isSteered = true)
  // Must NOT render turn-interrupted-notice
  const steeredHtml = renderToStaticMarkup(
    React.createElement(Turn, {
      events: forceEndedTurnEvents,
      completed: true,
      forced: null,
      report: () => {},
      steered: new Map(),
      isLatestTurn: true,
      isSteered: true,
      onResend: () => {},
      detail: mockDetail,
      autoCollapseProcess: true,
    })
  );

  assert.equal(
    steeredHtml.includes("turn-interrupted-notice"),
    false,
    "Steered turn must NOT render turn-interrupted-notice",
  );
});

