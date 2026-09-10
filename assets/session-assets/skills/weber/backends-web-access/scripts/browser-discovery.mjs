// 浏览器 CDP 端口发现 + 选择 - 单一职责模块
// 被 check-deps.mjs 和 cdp-proxy.mjs 共享。
//
// 选择规则（resolution）：
//   1. 调用方传入 override 参数（来自命令行 --browser） → 严格模式，找不到则硬错
//   2. config.env 里 WEB_ACCESS_BROWSER 设了 → 严格模式，找不到则硬错
//   3. 都没设 → "ask" 模式，提示调用方询问用户
//
// 不擅自降级：偏好不可用一律硬错，让用户介入。
// 持久态只有 config.env 一处；override 是单次 spawn 通过命令行参数表达，不读 process.env。

import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CONFIG_PATH = path.join(SKILL_ROOT, 'config.env');
const FALLBACK_PORTS = [9222, 9229, 9333];

function isIsolatedHome(home) {
  return /\/(?:\.mmf|\.config\/mms|\.config\/mmf|gateway\/s|sessions)\//.test(home || '');
}

// Return a host-home decision that agents can inspect. An isolated HOME is never used as a
// Chrome profile location unless an explicit host-home handoff overrides it.
export function browserEnvironment() {
  const configuredHostHome = readConfig().WEB_ACCESS_HOST_HOME;
  const explicitHome = process.env.WEB_ACCESS_HOST_HOME || process.env.HOST_HOME || process.env.REAL_HOME || configuredHostHome;
  if (explicitHome) return { hostHome: explicitHome, source: 'explicit', isolated: false };

  const processHome = os.homedir();
  if (!isIsolatedHome(processHome)) return { hostHome: processHome, source: 'system', isolated: false };

  return { hostHome: null, source: 'missing', isolated: true, processHome };
}

function browserHome() {
  return browserEnvironment().hostHome;
}

// 加新浏览器：只改这里
export function knownBrowsers() {
  const home = browserHome();
  if (!home) return [];
  const localAppData = process.env.LOCALAPPDATA || '';
  switch (os.platform()) {
    case 'darwin':
      return [
        { id: 'chrome',        label: 'Chrome',         devToolsPath: path.join(home, 'Library/Application Support/Google/Chrome/DevToolsActivePort') },
        { id: 'chrome-canary', label: 'Chrome Canary',  devToolsPath: path.join(home, 'Library/Application Support/Google/Chrome Canary/DevToolsActivePort') },
        { id: 'chromium',      label: 'Chromium',       devToolsPath: path.join(home, 'Library/Application Support/Chromium/DevToolsActivePort') },
        { id: 'edge',          label: 'Microsoft Edge', devToolsPath: path.join(home, 'Library/Application Support/Microsoft Edge/DevToolsActivePort') },
      ];
    case 'linux':
      return [
        { id: 'chrome',   label: 'Chrome',         devToolsPath: path.join(home, '.config/google-chrome/DevToolsActivePort') },
        { id: 'chromium', label: 'Chromium',       devToolsPath: path.join(home, '.config/chromium/DevToolsActivePort') },
        { id: 'edge',     label: 'Microsoft Edge', devToolsPath: path.join(home, '.config/microsoft-edge/DevToolsActivePort') },
      ];
    case 'win32':
      return [
        { id: 'chrome',   label: 'Chrome',         devToolsPath: path.join(localAppData, 'Google/Chrome/User Data/DevToolsActivePort') },
        { id: 'chromium', label: 'Chromium',       devToolsPath: path.join(localAppData, 'Chromium/User Data/DevToolsActivePort') },
        { id: 'edge',     label: 'Microsoft Edge', devToolsPath: path.join(localAppData, 'Microsoft/Edge/User Data/DevToolsActivePort') },
      ];
    default:
      return [];
  }
}

// TCP 端口监听检测。仅用于快速排除未监听端口，不能证明它是 CDP。
export function checkPort(port, host = '127.0.0.1', timeoutMs = 2000) {
  return new Promise((resolve) => {
    const socket = net.createConnection(port, host);
    const timer = setTimeout(() => { socket.destroy(); resolve(false); }, timeoutMs);
    socket.once('connect', () => { clearTimeout(timer); socket.destroy(); resolve(true); });
    socket.once('error',   () => { clearTimeout(timer); resolve(false); });
  });
}

export function productMatchesBrowser(product, browserId) {
  const value = String(product || '').toLowerCase();
  switch (browserId) {
    case 'chrome': return value.startsWith('chrome/');
    case 'chromium': return value.startsWith('chromium/');
    case 'edge': return value.startsWith('edg/');
    // Browser.getVersion cannot reliably distinguish Chrome Canary from Chrome.
    case 'chrome-canary': return false;
    default: return false;
  }
}

// 读 config.env 文件（不写入 process.env，分清来源）
// 格式：KEY=VALUE，# 开头是注释
function readConfig() {
  const cfg = {};
  let content;
  try { content = fs.readFileSync(CONFIG_PATH, 'utf8'); }
  catch { return cfg; }
  for (const line of content.split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith('#')) continue;
    const i = t.indexOf('=');
    if (i === -1) continue;
    const k = t.slice(0, i).trim();
    const v = t.slice(i + 1).trim();
    if (k && v) cfg[k] = v;
  }
  return cfg;
}

// DevToolsActivePort gives the target WebSocket path; the proxy performs the CDP handshake.
async function detectAll() {
  const result = [];
  for (const browser of knownBrowsers()) {
    let content;
    try { content = fs.readFileSync(browser.devToolsPath, 'utf8'); }
    catch { continue; }
    const lines = content.trim().split(/\r?\n/).filter(Boolean);
    const port = parseInt(lines[0], 10);
    if (!(port > 0 && port < 65536)) continue;
    if (!(await checkPort(port))) continue;
    result.push({ ...browser, port, wsPath: lines[1] || null });
  }
  return result;
}

// 决策入口
// 参数：override — 调用方解析自命令行 --browser 的值（null 表示未传）
// 返回 { kind, browser?, source?, detected, configured, override? }
//   kind ∈ 'ok' | 'ambiguous' | 'mismatch' | 'empty'
//   source ∈ 'override' | 'preference' | undefined
//   ambiguous = 没设偏好 + 至少一个浏览器开了 toggle，需问用户
//   mismatch  = override/配偏好设了但未检测到对应 toggle，硬错
//   empty     = 0 浏览器开 toggle 且未设偏好/override
export async function selectBrowser(override = null) {
  const detected = await detectAll();
  const configured = readConfig().WEB_ACCESS_BROWSER || null;

  // Browser toggles in isolated sessions may not leave DevToolsActivePort in the host profile.
  // Treat a fixed listener as a candidate; cdp-proxy verifies Browser.getVersion on its one real connection.
  const matchingFallback = async (browserId) => {
    const fallback = await findFallbackPort();
    const browser = knownBrowsers().find((item) => item.id === browserId);
    if (!fallback || !browser) return null;
    return { ...browser, ...fallback };
  };

  // 1. 命令行 override（最高优先，单次有效）
  if (override) {
    const match = detected.find(b => b.id === override);
    if (match) return { kind: 'ok', browser: match, source: 'override', detected, configured, override };
    const fallback = await matchingFallback(override);
    if (fallback) return { kind: 'ok', browser: fallback, source: 'fallback', detected, configured, override };
    return { kind: 'mismatch', source: 'override', detected, configured, override };
  }

  // 2. config.env preference（持久）
  if (configured) {
    const match = detected.find(b => b.id === configured);
    if (match) return { kind: 'ok', browser: match, source: 'preference', detected, configured };
    const fallback = await matchingFallback(configured);
    if (fallback) return { kind: 'ok', browser: fallback, source: 'fallback', detected, configured };
    return { kind: 'mismatch', source: 'preference', detected, configured };
  }

  // 3. 无偏好 —— 一律询问用户（哪怕 detected 只有一个）
  if (detected.length === 0) {
    return { kind: 'empty', detected, configured };
  }
  return { kind: 'ambiguous', detected, configured };
}

// 兜底：扫描常用固定端口。它只是连接候选，CDP proxy 会在同一条最终连接上验证。
export async function findFallbackPort() {
  for (const port of FALLBACK_PORTS) {
    if (await checkPort(port)) return { port, wsPath: null };
  }
  return null;
}
