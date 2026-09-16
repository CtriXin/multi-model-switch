import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { compareSemverDesc, parseSemver } from "../src/semver-sort.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(__dirname, "../src");

test("compareSemverDesc sorts versions strictly descending by semver numbers", () => {
  const versions = [
    "4.2.0",
    "v4.10.0",
    "4.9.0",
    "4.16.0",
    "4.10.1",
    "v4.15.2",
    "10.0.0",
  ];
  const sorted = [...versions].sort(compareSemverDesc);
  assert.deepEqual(sorted, [
    "10.0.0",
    "4.16.0",
    "v4.15.2",
    "4.10.1",
    "v4.10.0",
    "4.9.0",
    "4.2.0",
  ]);

  assert.deepEqual(parseSemver("v4.16.0"), [4, 16, 0]);
  assert.deepEqual(parseSemver("4.1.2"), [4, 1, 2]);
  assert.equal(parseSemver("invalid"), null);
});

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
  const channelContent = fs.readFileSync(path.join(srcDir, "ChannelModels.tsx"), "utf-8");
  const settingsContent = fs.readFileSync(path.join(srcDir, "SettingsPage.tsx"), "utf-8");

  // Neither Models.tsx nor ChannelModels.tsx contains platform capability
  assert.doesNotMatch(modelsContent, /platform-capability/);
  assert.doesNotMatch(channelContent, /platform-capability/);

  // In SettingsPage, platform-capability is inside the runtime branch
  const runtimeBranchIndex = settingsContent.indexOf('runtime-settings');
  const capabilityIndex = settingsContent.indexOf('className="platform-capability"');
  assert.ok(runtimeBranchIndex > 0);
  assert.ok(capabilityIndex > runtimeBranchIndex);
});

test("Dark theme contrast: capability chip uses semantic tokens and avoids hardcoded light backgrounds", () => {
  const studioCss = fs.readFileSync(path.join(srcDir, "studio.css"), "utf-8");

  // Must not use absent --surface-2 or light-on-light defaults
  assert.doesNotMatch(studioCss, /--surface-2/);
  assert.doesNotMatch(studioCss, /background:\s*#f2f2f2/);

  // Must use Pilot semantic tokens
  assert.match(studioCss, /\.capability-chip\s*\{[^}]*background:\s*var\(--soft\)/);
  assert.match(studioCss, /\.capability-chip\s*\{[^}]*color:\s*var\(--ink\)/);
  assert.match(studioCss, /\.capability-chip\s*\{[^}]*border:\s*1px solid var\(--line\)/);
});

test("Settings tabs, models, appearance, usage and channel-models share unified horizontal insets", () => {
  const studioCss = fs.readFileSync(path.join(srcDir, "studio.css"), "utf-8");
  const channelCss = fs.readFileSync(path.join(srcDir, "channel-models.css"), "utf-8");

  // settings-page and general-settings unified width & margin
  assert.match(studioCss, /\.settings-shell \.settings-page,\s*\.settings-shell \.general-settings\s*\{[^}]*width:\s*100%/);
  assert.match(studioCss, /\.settings-shell \.settings-page,\s*\.settings-shell \.general-settings\s*\{[^}]*max-width:\s*none/);

  // channel-models container width & margin flush with settings
  assert.match(channelCss, /\.channel-models\s*\{[^}]*width:\s*100%/);
  assert.match(channelCss, /\.channel-models\s*\{[^}]*max-width:\s*none/);
});

test("Channel save footer is sticky with full width, border and scroll occlusion prevention", () => {
  const channelCss = fs.readFileSync(path.join(srcDir, "channel-models.css"), "utf-8");
  const studioCss = fs.readFileSync(path.join(srcDir, "studio.css"), "utf-8");

  // channel-save sticky properties
  assert.match(channelCss, /\.channel-save\s*\{[^}]*position:\s*sticky/);
  assert.match(channelCss, /\.channel-save\s*\{[^}]*bottom:\s*0/);
  assert.match(channelCss, /\.channel-save\s*\{[^}]*z-index:\s*10/);
  assert.match(channelCss, /\.channel-save\s*\{[^}]*width:\s*100%/);
  assert.match(channelCss, /\.channel-save\s*\{[^}]*background:\s*var\(--surface\)/);
  assert.match(channelCss, /\.channel-save\s*\{[^}]*border-top:\s*1px solid var\(--line\)/);

  // scroll padding to prevent occluding the bottom content
  assert.match(studioCss, /scroll-padding-bottom:\s*72px/);
});

test("Home page does not automatically display WhatsNew card", () => {
  const appContent = fs.readFileSync(path.join(srcDir, "App.tsx"), "utf-8");

  // Home scroll/content must not contain automatic WhatsNew card
  assert.doesNotMatch(appContent, /<WhatsNew/);
});

test("HelpGuide contains '版本更新' directory entry, calls /update/history, and is default-collapsed", () => {
  const guideContent = fs.readFileSync(path.join(srcDir, "HelpGuide.tsx"), "utf-8");

  // Nav directory entry
  assert.match(guideContent, /版本更新/);
  assert.match(guideContent, /更新历史与变更记录/);

  // Endpoint call
  assert.match(guideContent, /\/update\/history/);

  // Default collapsed state
  assert.match(guideContent, /useState<Set<string>>\(\(\)\s*=>\s*new Set\(\)\)/);
  assert.match(guideContent, /isExpanded \? <ChevronUp/);

  // Markdown rendering
  assert.match(guideContent, /<Markdown remarkPlugins=\{\[remarkGfm\]\} skipHtml>/);
});

test("BotEditor renders PixelAvatar previews and PixelAvatar is exported", () => {
  const botContent = fs.readFileSync(path.join(srcDir, "Bot.tsx"), "utf-8");
  const botStudioContent = fs.readFileSync(path.join(srcDir, "BotStudio.tsx"), "utf-8");
  const botCss = fs.readFileSync(path.join(srcDir, "bot.css"), "utf-8");

  // PixelAvatar is exported
  assert.match(botContent, /export function PixelAvatar/);

  // BotStudio uses PixelAvatar in avatar options
  assert.match(botStudioContent, /<PixelAvatar\s+avatarId=\{avatar\.id\}/);

  // Avatar option has size definition in css
  assert.match(botCss, /\.bot-avatar-option \.pixel-avatar,\s*\.bot-avatar-picker-preview\s*\{[^}]*width:\s*32px/);
});

test("Bot wake checkbox is aligned inline and not stretched by 100% width", () => {
  const botCss = fs.readFileSync(path.join(srcDir, "bot.css"), "utf-8");

  // Inputs in dialog exclude checkbox from full width
  assert.match(botCss, /\.bot-create-dialog input:not\(\[type="checkbox"\]\)/);

  // Bot-check is inline-flex with fixed 16px input
  assert.match(botCss, /\.bot-check\s*\{[^}]*display:\s*inline-flex/);
  assert.match(botCss, /\.bot-check input\[type="checkbox"\],\s*\.bot-check input\s*\{[^}]*width:\s*16px/);
});

test("BotChat respects enterToSend setting and BotArtifactPreview provides copy action", () => {
  const botContent = fs.readFileSync(path.join(srcDir, "Bot.tsx"), "utf-8");
  const botStudioContent = fs.readFileSync(path.join(srcDir, "BotStudio.tsx"), "utf-8");
  const previewContent = fs.readFileSync(path.join(srcDir, "BotArtifactPreview.tsx"), "utf-8");
  const botCss = fs.readFileSync(path.join(srcDir, "bot.css"), "utf-8");

  // enterToSend prop in BotChat and BotStudio
  assert.match(botContent, /enterToSend\s*=\s*true/);
  assert.match(botContent, /sendCombo = enterToSend/);
  assert.match(botStudioContent, /enterToSend\?: boolean/);
  assert.match(botStudioContent, /enterToSend=\{enterToSend\}/);

  // Artifact copy button
  assert.match(previewContent, /copyText\(state\.text\)/);
  assert.match(previewContent, /className=\{`bot-preview-copy/);
  assert.match(botCss, /\.bot-preview-copy\s*\{/);
});

test("ModelExplorer has inline retry button on launch options error", () => {
  const explorerContent = fs.readFileSync(path.join(srcDir, "ModelExplorer.tsx"), "utf-8");
  const stylesCss = fs.readFileSync(path.join(srcDir, "styles.css"), "utf-8");

  assert.match(explorerContent, /setRetry\(\(r\)\s*=>\s*r \+ 1\)/);
  assert.match(explorerContent, /className="inline-retry-button"/);
  assert.match(stylesCss, /\.inline-alert-retryable/);
  assert.match(stylesCss, /\.inline-retry-button/);
});
