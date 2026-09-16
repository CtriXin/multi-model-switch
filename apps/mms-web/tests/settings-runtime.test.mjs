import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(__dirname, "../src");

test("SettingsPage includes 4th tab '运行环境' with Cpu icon and isolated runtime section", () => {
  const content = fs.readFileSync(path.join(srcDir, "SettingsPage.tsx"), "utf-8");

  // 4 tabs must be present in settings-tabs
  assert.match(content, /tab === "models"/);
  assert.match(content, /tab === "appearance"/);
  assert.match(content, /tab === "usage"/);
  assert.match(content, /tab === "runtime"/);
  assert.match(content, /<Cpu size=\{16\} \/>\s*运行环境/);

  // Platform capability is located in runtime tab
  assert.match(content, /runtime-settings/);
  assert.match(content, /className="platform-capability"/);
});

test("Platform capability is moved out of models page and only present in runtime tab", () => {
  const modelsContent = fs.readFileSync(path.join(srcDir, "Models.tsx"), "utf-8");
  const settingsContent = fs.readFileSync(path.join(srcDir, "SettingsPage.tsx"), "utf-8");

  // Models.tsx does not contain platform capability
  assert.doesNotMatch(modelsContent, /platform-capability/);

  // In SettingsPage, platform-capability is inside the runtime branch
  const runtimeBranchIndex = settingsContent.indexOf("runtime-settings");
  const capabilityIndex = settingsContent.indexOf('className="platform-capability"');
  assert.ok(runtimeBranchIndex > 0);
  assert.ok(capabilityIndex > runtimeBranchIndex);
});

test("Runtime tab renders status pills for launch, configure, and discoverModels capabilities", () => {
  const settingsContent = fs.readFileSync(path.join(srcDir, "SettingsPage.tsx"), "utf-8");

  // Status pill rows for launch link, config mode, and model auto discovery
  assert.match(settingsContent, /会话启动链路/);
  assert.match(settingsContent, /status-pill\s*\$\{\s*data\.capabilities\.launch\s*\?\s*"active"\s*:\s*"muted"\s*\}/);
  assert.match(settingsContent, /data\.capabilities\.launch\s*\?\s*"就绪"\s*:\s*"受限"/);

  assert.match(settingsContent, /配置模式/);
  assert.match(settingsContent, /status-pill\s*\$\{\s*data\.capabilities\.configure\s*\?\s*"active"\s*:\s*"muted"\s*\}/);
  assert.match(settingsContent, /data\.capabilities\.configure\s*\?\s*"独立可写"\s*:\s*"只读"/);

  assert.match(settingsContent, /模型自动发现/);
  assert.match(settingsContent, /status-pill\s*\$\{\s*data\.capabilities\.discoverModels\s*\?\s*"active"\s*:\s*"muted"\s*\}/);
  assert.match(settingsContent, /data\.capabilities\.discoverModels\s*\?\s*"支持"\s*:\s*"静态"/);
});

test("Runtime tab includes empty fallback when browser capabilities are absent", () => {
  const settingsContent = fs.readFileSync(path.join(srcDir, "SettingsPage.tsx"), "utf-8");

  // Fallback branch when browser array is empty
  assert.match(settingsContent, /data\.browser\s*&&\s*data\.browser\.length > 0/);
  assert.match(settingsContent, /浏览器能力:\s*独立环境/);
  assert.match(settingsContent, /className="capability-chip unavailable"/);
});

test("Runtime tab renders config and state directory paths when present", () => {
  const settingsContent = fs.readFileSync(path.join(srcDir, "SettingsPage.tsx"), "utf-8");

  // Platform paths
  assert.match(settingsContent, /data\.platform\?\.configRoot/);
  assert.match(settingsContent, /配置目录/);
  assert.match(settingsContent, /<code>\{data\.platform\.configRoot\}<\/code>/);

  assert.match(settingsContent, /data\.platform\?\.stateRoot/);
  assert.match(settingsContent, /状态目录/);
  assert.match(settingsContent, /<code>\{data\.platform\.stateRoot\}<\/code>/);
});

test("Dark theme contrast and runtime CSS classes in studio.css", () => {
  const studioCss = fs.readFileSync(path.join(srcDir, "studio.css"), "utf-8");

  // Must not use absent --surface-2 or light-on-light defaults
  assert.doesNotMatch(studioCss, /--surface-2/);
  assert.doesNotMatch(studioCss, /background:\s*#f2f2f2/);

  // Must define all 8 required runtime tab classes
  assert.match(studioCss, /\.runtime-settings\s*\{/);
  assert.match(studioCss, /\.platform-capability-header\s*\{/);
  assert.match(studioCss, /\.platform-meta\s*\{/);
  assert.match(studioCss, /\.capability-chip\s*\{[^}]*background:\s*var\(--soft\)/);
  assert.match(studioCss, /\.capability-chip\s*\{[^}]*color:\s*var\(--ink\)/);
  assert.match(studioCss, /\.capability-chip\s*\{[^}]*border:\s*1px solid var\(--line\)/);
  assert.match(studioCss, /\.capability-chip\s+\.chip-indicator\s*\{/);
  assert.match(studioCss, /\.status-pill\s*\{/);
  assert.match(studioCss, /\.status-pill\.active\s*\{/);
  assert.match(studioCss, /\.status-pill\.muted\s*\{/);
});
