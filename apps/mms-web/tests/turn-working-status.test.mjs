import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import esbuild from "esbuild";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sessionStatusFile = path.resolve(__dirname, "../src/SessionStatus.tsx");
const source = fs.readFileSync(sessionStatusFile, "utf-8");

const transpiled = esbuild.transformSync(source, {
  loader: "tsx",
  format: "cjs",
}).code;

const mod = { exports: {} };
const sandbox = {
  module: mod,
  exports: mod.exports,
  require: (req) => {
    if (req === "react") return { createElement: () => null };
    if (req === "lucide-react") return {};
    return {};
  },
  console,
};
vm.createContext(sandbox);
vm.runInContext(transpiled, sandbox);

const { sessionStatus, activityHints, turnWorkingHint } = mod.exports;

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

  // Waiting confirmation
  const confirmSession = {
    state: "waiting",
    activity: { phase: "waiting", method: "confirm" },
  };
  assert.equal(turnWorkingHint(confirmSession), "等待确认工具操作");

  // Waiting user answer
  const answerWaitSession = {
    state: "waiting",
    activity: { phase: "waiting" },
  };
  assert.equal(turnWorkingHint(answerWaitSession), "等待你的回答");

  // Disconnected
  assert.equal(turnWorkingHint(thinkingSession, true), "状态未同步，等待重新连接…");
});

test("transcript.css declares turn-working placeholder and animation tokens", () => {
  const cssFile = path.resolve(__dirname, "../src/transcript.css");
  const css = fs.readFileSync(cssFile, "utf-8");

  assert.ok(css.includes(".turn-working-message"), "defines .turn-working-message");
  assert.ok(css.includes(".turn-working-indicator"), "defines .turn-working-indicator");
  assert.ok(css.includes("turn-working-fade-in"), "defines turn-working-fade-in animation");
  assert.ok(css.includes(".turn-working-label"), "defines .turn-working-label");
  assert.ok(css.includes(".turn-process-live-dot"), "defines .turn-process-live-dot");

  // Verify token compliance: no bare hex in turn-working definitions
  const turnWorkingSection = css.slice(css.indexOf("/* Working status placeholder"));
  assert.equal(turnWorkingSection.includes("#"), false, "no bare hex color in turn-working section");
});

test("findActiveAnswer distinguishes streaming final reply from intermediate tool preface", () => {
  const transcriptSource = fs.readFileSync(path.resolve(__dirname, "../src/Transcript.tsx"), "utf-8");
  
  // Extract findActiveAnswer function
  const match = transcriptSource.match(/function findActiveAnswer[\s\S]*?\n\}/);
  assert.ok(match, "findActiveAnswer function is present in Transcript.tsx");
  
  const transpiledFunc = esbuild.transformSync(match[0], {
    loader: "ts",
    format: "cjs",
  }).code;
  
  const fnMod = { exports: {} };
  const fnSandbox = { module: fnMod, exports: fnMod.exports };
  vm.createContext(fnSandbox);
  vm.runInContext(`${transpiledFunc}; module.exports = findActiveAnswer;`, fnSandbox);
  const findActiveAnswer = fnMod.exports;

  // Case 1: intermediate explanation before a tool call should not be captured as answer
  const intermediateEvents = [
    { id: "1", kind: "user", text: "check alerts" },
    { id: "2", kind: "assistant", text: "好的我来看一下" },
    { id: "3", kind: "tool", title: "read_file" },
  ];
  assert.equal(findActiveAnswer(intermediateEvents), undefined, "preface before tool is not final answer");

  // Case 2: reply after all tool calls are completed is captured as streaming answer
  const streamingEvents = [
    { id: "1", kind: "user", text: "check alerts" },
    { id: "2", kind: "tool", title: "read_file" },
    { id: "3", kind: "assistant", text: "根据日志发现以下两项报警原因：" },
  ];
  const captured = findActiveAnswer(streamingEvents);
  assert.ok(captured, "captured final reply");
  assert.equal(captured.id, "3");
});
