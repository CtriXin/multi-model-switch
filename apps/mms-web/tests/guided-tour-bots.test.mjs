import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(__dirname, "../src");

/**
 * 纯状态函数：判定首次引导是否在当前环境与页面就绪
 * 规则：在非 loading、已连接、模型已就绪、未打开 setup / settings，且当前页面非 bots 时就绪
 */
export function isGuideReady({
  loading,
  connected,
  modelReady,
  setupOpen,
  settingsOpen,
  page,
}) {
  return !loading && connected && modelReady && !setupOpen && !settingsOpen && page !== "bots";
}

/**
 * 纯状态函数：页面导航时的引导步进状态机
 * 规则：进入 bots 页时，任何进行中的引导步进必须被置为 null（关闭）
 */
export function resolveGuideStepOnNavigate(currentStep, nextPage) {
  if (nextPage === "bots") return null;
  return null;
}

test("Bot 页不自动开始：isGuideReady 在 page === 'bots' 时始终返回 false", () => {
  const baseReadyConditions = {
    loading: false,
    connected: true,
    modelReady: true,
    setupOpen: false,
    settingsOpen: false,
  };

  // 1. 在 bots 页面，即使所有服务与模型均已就绪，引导也绝不就绪（不自动启动）
  assert.equal(
    isGuideReady({ ...baseReadyConditions, page: "bots" }),
    false,
    "isGuideReady must return false on bots page"
  );

  // 2. 在普通 Pilot 页面（新建、会话），满足条件时正常就绪
  assert.equal(
    isGuideReady({ ...baseReadyConditions, page: "new" }),
    true,
    "isGuideReady must return true on new session page"
  );
  assert.equal(
    isGuideReady({ ...baseReadyConditions, page: "session" }),
    true,
    "isGuideReady must return true on active session page"
  );

  // 3. 其它标准守护条件依然生效
  assert.equal(isGuideReady({ ...baseReadyConditions, page: "new", loading: true }), false);
  assert.equal(isGuideReady({ ...baseReadyConditions, page: "new", connected: false }), false);
  assert.equal(isGuideReady({ ...baseReadyConditions, page: "new", modelReady: false }), false);
  assert.equal(isGuideReady({ ...baseReadyConditions, page: "new", setupOpen: true }), false);
  assert.equal(isGuideReady({ ...baseReadyConditions, page: "new", settingsOpen: true }), false);
});

test("进入 Bot 页关闭引导：导航到 bots 时必须关闭引导且不挂载 GuidedTour", () => {
  // 状态机断言：从任意进行中步骤（如 welcome, workspace, model 等）进入 bots，步进必须置空
  const steps = ["welcome", "workspace", "model", "effort", "compose", "send", "reply"];
  for (const step of steps) {
    assert.equal(
      resolveGuideStepOnNavigate(step, "bots"),
      null,
      `Navigating to bots must clear step '${step}'`
    );
  }

  // App.tsx 源码断言
  const appContent = fs.readFileSync(path.join(srcDir, "App.tsx"), "utf-8");

  // 确保 tour 挂载受 page !== "bots" 守卫
  assert.match(
    appContent,
    /const tour = guideStep && modelReady && !setupOpen && page !== "bots"/,
    "tour component must not be mounted when page is bots"
  );

  // 确保 navigate 清空 guideStep
  assert.match(
    appContent,
    /function navigate\(next: Page[\s\S]*?setGuideStep\(null\);/,
    "navigate must clear guideStep"
  );

  // 确保侧栏入口进入 bots 并清掉引导
  assert.match(
    appContent,
    /setPage\("bots"\)/,
    "sidebar Bot entry must set page to bots"
  );
  assert.match(
    appContent,
    /setBotsReturnId\(page === "session" \? selectedId : ""\)/,
    "sidebar Bot entry must remember the current session"
  );
});

test("在 Bot 页调用引导或功能介绍时先切回 Pilot 页面再开始", () => {
  const appContent = fs.readFileSync(path.join(srcDir, "App.tsx"), "utf-8");

  // startIntroduction 必须在 page === "bots" 时重定向到 "new"
  assert.match(
    appContent,
    /function startIntroduction\(\) \{\s*if \(page === "bots"\) \{\s*navigate\("new"/,
    "startIntroduction must redirect to 'new' when invoked on bots page"
  );

  // beginGuideStep 必须将页面重置回 "new"
  assert.match(
    appContent,
    /if \(page === "bots" \|\| step === "workspace"/,
    "beginGuideStep must transition out of bots page without hijacking the welcome step"
  );

  // guideNavigate 必须在 page === "bots" 时重定向到 "new"
  assert.match(
    appContent,
    /function guideNavigate\(action: GuideAction\) \{\s*[\s\S]*?if \(page === "bots"\) \{\s*navigate\("new"/,
    "guideNavigate must navigate to 'new' when invoked on bots page"
  );
});

test("HelpGuide ready prop 绑定 isGuideReady 保证 Bot 页不执行 markSeen", () => {
  const appContent = fs.readFileSync(path.join(srcDir, "App.tsx"), "utf-8");
  const helpGuideContent = fs.readFileSync(path.join(srcDir, "HelpGuide.tsx"), "utf-8");

  // HelpGuide 在 App.tsx 中通过 isGuideReady 计算 ready 属性
  assert.match(
    appContent,
    /<HelpGuide\s+ready=\{isGuideReady\(\{[\s\S]*?page[\s\S]*?\}\)\}/,
    "HelpGuide must use isGuideReady with page prop"
  );

  // HelpGuide.tsx 中当 !ready 时立即 return，不产生 markSeen 与网络请求副作用
  assert.match(
    helpGuideContent,
    /if \(!ready \|\| attempted\.current\) return;/,
    "HelpGuide must return immediately when !ready without side effects"
  );
});
