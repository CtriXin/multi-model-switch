#!/usr/bin/env node
// CDP Proxy - 通过 HTTP API 操控用户日常浏览器（Chrome / Edge / Chromium 等）
// 要求：浏览器已开启 remote debugging（chrome://inspect#remote-debugging toggle）
// Node.js 22+（使用原生 WebSocket）

import http from 'node:http';
import { URL } from 'node:url';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import net from 'node:net';
import { selectBrowser, findFallbackPort, productMatchesBrowser, browserEnvironment } from './browser-discovery.mjs';

// --- 解析命令行 --browser 参数（本次启动用哪个浏览器）---
function parseBrowserArg() {
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--browser' && argv[i + 1]) return argv[i + 1];
    if (argv[i].startsWith('--browser=')) return argv[i].slice('--browser='.length);
  }
  return null;
}
const BROWSER_OVERRIDE = parseBrowserArg();

const PORT = parseInt(process.env.CDP_PROXY_PORT || '3456');
let ws = null;
let cmdId = 0;
const pending = new Map(); // id -> {resolve, timer}
const sessions = new Map(); // targetId -> sessionId
const managedTabs = new Map(); // targetId -> { lastAccessed: number }
const TAB_IDLE_TIMEOUT = parseInt(process.env.CDP_TAB_IDLE_TIMEOUT || '900000'); // 15 min default
const CLEANUP_INTERVAL = 60000; // sweep every 60s

// --- WebSocket 兼容层 ---
let WS;
if (typeof globalThis.WebSocket !== 'undefined') {
  // Node 22+ 原生 WebSocket（浏览器兼容 API）
  WS = globalThis.WebSocket;
} else {
  // 回退到 ws 模块
  try {
    WS = (await import('ws')).default;
  } catch {
    console.error('[CDP Proxy] 错误：Node.js 版本 < 22 且未安装 ws 模块');
    console.error('  解决方案：升级到 Node.js 22+ 或执行 npm install -g ws');
    process.exit(1);
  }
}

// proxy 启动时连接到的浏览器（用于 /health 暴露给 check-deps 比较）
let connectedBrowser = null; // { id, label, source }

// pin 首次成功连接的浏览器 id。重连时只接受同一 id，避免悄悄降级到别的浏览器。
let pinnedBrowserId = null;

// --- 自动发现浏览器调试端口 ---
// 决策完全委派给 browser-discovery.selectBrowser；此处只做日志和返回结构包装。
async function discoverChromePort() {
  const result = await selectBrowser(BROWSER_OVERRIDE);
  if (result.kind === 'ok') {
    if (pinnedBrowserId && pinnedBrowserId !== result.browser.id) {
      throw new Error(
        `本次连接的浏览器已经是 ${pinnedBrowserId}，不会自动切到 ${result.browser.id}。` +
        `如果想换成 ${result.browser.id}，请先核对并停止当前 web-access proxy 的精确 PID。`
      );
    }
    pinnedBrowserId = result.browser.id;
    connectedBrowser = { id: result.browser.id, label: result.browser.label, source: result.source };
    const tag = result.source === 'override'
      ? '[--browser 指定]'
      : result.source === 'fallback'
        ? '[固定端口候选，连接后验证]'
        : '[config.env 偏好]';
    console.log(`[CDP Proxy] 选用 ${result.browser.label} (端口 ${result.browser.port}${result.browser.wsPath ? '，带 wsPath' : ''}) ${tag}`);
    return { port: result.browser.port, wsPath: result.browser.wsPath };
  }
  // mismatch：有显式偏好但未检测到 —— 硬错，绝不降级
  if (result.kind === 'mismatch') {
    const expected = result.override || result.configured;
    const src = result.source === 'override' ? '本次指定' : '默认偏好';
    throw new Error(
      `${src}的浏览器是 "${expected}"，但没连上。Agent 处理顺序：` +
      `(1) 不要从隔离会话直接启动浏览器；请让用户在宿主环境打开或使用 mms-chrome-host；` +
      `(2) 若仍失败，说明远程调试开关没启用 —— 告知用户在地址栏访问 ${expected}://inspect/#remote-debugging 勾选 "Allow remote debugging for this browser instance"。`
    );
  }
  // 已 pin 过浏览器（如首次连上 edge 后 edge 退出）：拒绝任何 fallback
  if (pinnedBrowserId) {
    throw new Error(
      `本次连接的浏览器是 ${pinnedBrowserId}，但现在没连上。Agent 处理顺序：` +
      `(1) 先用系统命令打开 ${pinnedBrowserId}（按平台选择），稍等后重试请求；` +
      `(2) 若仍失败，告知用户在地址栏访问 ${pinnedBrowserId}://inspect/#remote-debugging 重新勾选允许。` +
      `若想换成其他浏览器，请先核对并停止当前 web-access proxy 的精确 PID。`
    );
  }
  // 仅在「从未成功连接 + 无偏好/override」时允许固定端口兜底（手动 --remote-debugging-port 启动场景）
  const fallbackPort = await findFallbackPort();
  if (fallbackPort !== null) {
    connectedBrowser = { id: 'unknown', label: '未知（通过固定端口候选）', source: 'fallback' };
    console.log(`[CDP Proxy] 使用固定端口候选: ${fallbackPort.port}`);
    return { port: fallbackPort.port, wsPath: fallbackPort.wsPath };
  }
  return null;
}

function getWebSocketUrl(port, wsPath) {
  if (wsPath) return `ws://127.0.0.1:${port}${wsPath}`;
  return `ws://127.0.0.1:${port}/devtools/browser`;
}

// --- WebSocket 连接管理 ---
let chromePort = null;
let chromeWsPath = null;

let connectingPromise = null;
async function connect() {
  if (ws && (ws.readyState === WS.OPEN || ws.readyState === 1)) return;
  if (connectingPromise) return connectingPromise;  // 复用进行中的连接

  if (!chromePort) {
    const discovered = await discoverChromePort();
    if (!discovered) {
      throw new Error(
        'Chrome 未开启远程调试端口。请先在宿主浏览器地址栏打开 chrome://inspect/#remote-debugging 并允许远程调试。\n' +
        '隔离/MMF 会话不得直接启动个人 Chrome binary；需要命令启动时使用 mms-chrome-host。'
      );
    }
    chromePort = discovered.port;
    chromeWsPath = discovered.wsPath;
  }

  const wsUrl = getWebSocketUrl(chromePort, chromeWsPath);
  if (!wsUrl) throw new Error('无法获取 Chrome WebSocket URL');

  return connectingPromise = new Promise((resolve, reject) => {
    ws = new WS(wsUrl);

    const onOpen = async () => {
      cleanup();
      try {
        // Keep a single browser connection: this is both the permission-bearing connection and the CDP proof.
        const version = await sendCDP('Browser.getVersion');
        const product = version.result?.product;
        if (typeof product !== 'string') throw new Error('CDP Browser.getVersion 未返回浏览器产品信息');
        if (
          connectedBrowser?.source === 'fallback'
          && connectedBrowser.id !== 'unknown'
          && !productMatchesBrowser(product, connectedBrowser.id)
        ) {
          throw new Error(`固定端口返回 ${product}，与请求的 ${connectedBrowser.id} 不一致`);
        }
        connectedBrowser = { ...connectedBrowser, product };
        connectingPromise = null;
        console.log(`[CDP Proxy] 已连接浏览器 (端口 ${chromePort}, ${product})`);
        resolve();
      } catch (error) {
        connectingPromise = null;
        ws?.close();
        ws = null;
        chromePort = null;
        chromeWsPath = null;
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    };
    const onError = (e) => {
      cleanup();
      connectingPromise = null;
      ws = null;
      chromePort = null;
      chromeWsPath = null;
      const msg = e.message || e.error?.message || '连接失败';
      console.error('[CDP Proxy] 连接错误:', msg, '（端口缓存已清除，下次将重新发现）');
      reject(new Error(msg));
    };
    const onClose = () => {
      console.log('[CDP Proxy] 连接断开');
      ws = null;
      chromePort = null; // 重置端口缓存，下次连接重新发现
      chromeWsPath = null;
      sessions.clear();
      managedTabs.clear();
    };
    const onMessage = (evt) => {
      const data = typeof evt === 'string' ? evt : (evt.data || evt);
      const msg = JSON.parse(typeof data === 'string' ? data : data.toString());

      if (msg.method === 'Target.attachedToTarget') {
        const { sessionId, targetInfo } = msg.params;
        sessions.set(targetInfo.targetId, sessionId);
      }
      // 拦截页面对 Chrome 调试端口的探测请求（反风控）
      if (msg.method === 'Fetch.requestPaused') {
        const { requestId, sessionId: sid } = msg.params;
        sendCDP('Fetch.failRequest', { requestId, errorReason: 'ConnectionRefused' }, sid).catch(() => {});
      }
      if (msg.id && pending.has(msg.id)) {
        const { resolve, timer } = pending.get(msg.id);
        clearTimeout(timer);
        pending.delete(msg.id);
        resolve(msg);
      }
    };

    function cleanup() {
      ws.removeEventListener?.('open', onOpen);
      ws.removeEventListener?.('error', onError);
    }

    // 兼容 Node 原生 WebSocket 和 ws 模块的事件 API
    if (ws.on) {
      ws.on('open', onOpen);
      ws.on('error', onError);
      ws.on('close', onClose);
      ws.on('message', onMessage);
    } else {
      ws.addEventListener('open', onOpen);
      ws.addEventListener('error', onError);
      ws.addEventListener('close', onClose);
      ws.addEventListener('message', onMessage);
    }
  });
}

function sendCDP(method, params = {}, sessionId = null) {
  return new Promise((resolve, reject) => {
    if (!ws || (ws.readyState !== WS.OPEN && ws.readyState !== 1)) {
      return reject(new Error('WebSocket 未连接'));
    }
    const id = ++cmdId;
    const msg = { id, method, params };
    if (sessionId) msg.sessionId = sessionId;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error('CDP 命令超时: ' + method));
    }, 30000);
    pending.set(id, { resolve, timer });
    ws.send(JSON.stringify(msg));
  });
}

// 已启用端口拦截的 session 集合（避免重复启用）
const portGuardedSessions = new Set();

async function ensureSession(targetId) {
  if (sessions.has(targetId)) return sessions.get(targetId);
  const resp = await sendCDP('Target.attachToTarget', { targetId, flatten: true });
  if (resp.result?.sessionId) {
    const sid = resp.result.sessionId;
    sessions.set(targetId, sid);
    // 启用调试端口探测拦截
    await enablePortGuard(sid);
    return sid;
  }
  throw new Error('attach 失败: ' + JSON.stringify(resp.error));
}

// 拦截页面对 Chrome 调试端口的探测（反风控）
// 只拦截 127.0.0.1:{chromePort} 的请求，不影响其他任何本地服务
async function enablePortGuard(sessionId) {
  if (!chromePort || portGuardedSessions.has(sessionId)) return;
  try {
    await sendCDP('Fetch.enable', {
      patterns: [
        { urlPattern: `http://127.0.0.1:${chromePort}/*`, requestStage: 'Request' },
        { urlPattern: `http://localhost:${chromePort}/*`, requestStage: 'Request' },
      ]
    }, sessionId);
    portGuardedSessions.add(sessionId);
  } catch { /* Fetch 域启用失败不影响主流程 */ }
}

// --- 闲置 Tab 自动清理 ---
function touchTab(targetId) {
  const entry = managedTabs.get(targetId);
  if (entry) entry.lastAccessed = Date.now();
}

async function cleanupIdleTabs() {
  if (!ws || (ws.readyState !== WS.OPEN && ws.readyState !== 1)) return;
  const now = Date.now();
  for (const [targetId, info] of managedTabs) {
    if (now - info.lastAccessed < TAB_IDLE_TIMEOUT) continue;
    try { await sendCDP('Target.closeTarget', { targetId }); } catch { /* tab may already be closed */ }
    sessions.delete(targetId);
    managedTabs.delete(targetId);
    console.log(`[CDP Proxy] Auto-closed idle tab: ${targetId}`);
  }
}

async function closeAllManagedTabs() {
  if (!ws || (ws.readyState !== WS.OPEN && ws.readyState !== 1)) return;
  const targets = [...managedTabs.keys()];
  for (const targetId of targets) {
    try { await sendCDP('Target.closeTarget', { targetId }); } catch { /* ignore */ }
    sessions.delete(targetId);
    managedTabs.delete(targetId);
  }
  if (targets.length) console.log(`[CDP Proxy] Shutdown: closed ${targets.length} managed tab(s)`);
}

// --- 等待页面加载 ---
async function waitForLoad(sessionId, timeoutMs = 15000) {
  // 启用 Page 域
  await sendCDP('Page.enable', {}, sessionId);

  return new Promise((resolve) => {
    let resolved = false;
    const done = (result) => {
      if (resolved) return;
      resolved = true;
      clearTimeout(timer);
      clearInterval(checkInterval);
      resolve(result);
    };

    const timer = setTimeout(() => done('timeout'), timeoutMs);
    const checkInterval = setInterval(async () => {
      try {
        const resp = await sendCDP('Runtime.evaluate', {
          expression: 'document.readyState',
          returnByValue: true,
        }, sessionId);
        if (resp.result?.result?.value === 'complete') {
          done('complete');
        }
      } catch { /* 忽略 */ }
    }, 500);
  });
}

// --- 读取 POST body ---
async function readBody(req) {
  let body = '';
  for await (const chunk of req) body += chunk;
  return body;
}

// --- HTTP API ---
const server = http.createServer(async (req, res) => {
  const parsed = new URL(req.url, `http://localhost:${PORT}`);
  const pathname = parsed.pathname;
  const q = Object.fromEntries(parsed.searchParams);
  if (q.target) touchTab(q.target);

  res.setHeader('Content-Type', 'application/json; charset=utf-8');

  try {
    // /health 不需要连接浏览器
    if (pathname === '/health') {
      const connected = ws && (ws.readyState === WS.OPEN || ws.readyState === 1);
      res.end(JSON.stringify({
        status: 'ok',
        connected,
        browser: connectedBrowser,
        environment: browserEnvironment(),
        sessions: sessions.size,
        managedTabs: managedTabs.size,
        chromePort,
      }));
      return;
    }

    await connect();

    // GET /targets - 列出所有页面
    if (pathname === '/targets') {
      const resp = await sendCDP('Target.getTargets');
      const pages = resp.result.targetInfos.filter(t => t.type === 'page');
      res.end(JSON.stringify(pages, null, 2));
    }

    // GET /extension-status?name=...&version=... - 只读核验指定 extension
    else if (pathname === '/extension-status') {
      const expectedName = String(q.name || '').trim();
      const expectedVersion = String(q.version || '').trim();
      const expectedBuildHash = String(q.buildHash || '').trim();
      if (!expectedName) {
        res.statusCode = 400;
        res.end(JSON.stringify({ status: 'blocked', error: 'name is required' }));
        return;
      }
      const resp = await sendCDP('Target.getTargets');
      const extensionTargets = resp.result.targetInfos.filter(t =>
        ['service_worker', 'background_page'].includes(t.type)
        && t.url.startsWith('chrome-extension://')
      );
      const observed = [];
      for (const target of extensionTargets) {
        try {
          const sid = await ensureSession(target.targetId);
          const evaluated = await sendCDP('Runtime.evaluate', {
            expression: `JSON.stringify({
              manifest: chrome.runtime.getManifest(),
              attestation: globalThis.AdPlacementInspectorBuildAttestation || null
            })`,
            returnByValue: true,
          }, sid);
          const raw = evaluated.result?.result?.value;
          const runtime = raw ? JSON.parse(raw) : null;
          const manifest = runtime?.manifest;
          if (!manifest) continue;
          observed.push({
            id: new URL(target.url).hostname,
            name: manifest.name,
            version: manifest.version,
            buildHash: runtime?.attestation?.buildHash || null,
            targetType: target.type,
          });
        } catch { /* inactive or protected extension target */ }
      }
      const matched = observed.find(item =>
        item.name === expectedName
        && (!expectedVersion || item.version === expectedVersion)
        && (!expectedBuildHash || item.buildHash === expectedBuildHash)
      );
      res.end(JSON.stringify({
        status: matched ? 'passed' : 'blocked',
        expected: {
          name: expectedName,
          version: expectedVersion || null,
          buildHash: expectedBuildHash || null,
        },
        matched: matched || null,
        observedCount: observed.length,
      }, null, 2));
    }

    // POST /extension-acceptance - 通过指定 extension service worker 对目标 tab 运行固定的广告位验收消息。
    // body: { name, version, targetUrl, manifest }
    else if (pathname === '/extension-acceptance') {
      if (req.method !== 'POST') {
        res.statusCode = 400;
        res.end(JSON.stringify({ status: 'blocked', error: 'POST is required' }));
        return;
      }
      const body = JSON.parse(await readBody(req));
      const expectedName = String(body.name || '').trim();
      const expectedVersion = String(body.version || '').trim();
      const expectedBuildHash = String(body.buildHash || '').trim();
      const targetUrl = String(body.targetUrl || '').trim();
      const manifest = body.manifest;
      if (
        !expectedName
        || !targetUrl
        || manifest?.schema !== 'ad-placement-inspector.manifest.v1'
        || !Array.isArray(manifest?.placements)
        || !manifest.placements.length
      ) {
        res.statusCode = 400;
        res.end(JSON.stringify({
          status: 'blocked',
          error: 'name, targetUrl and a non-empty ad-placement-inspector.manifest.v1 are required',
        }));
        return;
      }
      const targets = await sendCDP('Target.getTargets');
      const extensionTargets = targets.result.targetInfos.filter(target =>
        ['service_worker', 'background_page'].includes(target.type)
        && target.url.startsWith('chrome-extension://')
      );
      let matchedTarget = null;
      let matchedManifest = null;
      for (const target of extensionTargets) {
        try {
          const sid = await ensureSession(target.targetId);
          const evaluated = await sendCDP('Runtime.evaluate', {
            expression: `JSON.stringify({
              manifest: chrome.runtime.getManifest(),
              attestation: globalThis.AdPlacementInspectorBuildAttestation || null
            })`,
            returnByValue: true,
          }, sid);
          const raw = evaluated.result?.result?.value;
          const runtime = raw ? JSON.parse(raw) : null;
          const extensionManifest = runtime?.manifest;
          if (
            extensionManifest?.name === expectedName
            && (!expectedVersion || extensionManifest.version === expectedVersion)
            && (!expectedBuildHash || runtime?.attestation?.buildHash === expectedBuildHash)
          ) {
            matchedTarget = target;
            matchedManifest = {
              ...extensionManifest,
              buildHash: runtime?.attestation?.buildHash || null,
            };
            break;
          }
        } catch { /* inactive or protected extension target */ }
      }
      if (!matchedTarget) {
        res.end(JSON.stringify({
          status: 'blocked',
          error: 'expected extension runtime was not found',
        }));
        return;
      }
      const sid = await ensureSession(matchedTarget.targetId);
      const payload = JSON.stringify({ targetUrl, manifest });
      const expression = `(async () => {
        const input = ${payload};
        const tabs = await chrome.tabs.query({});
        const tab = tabs.find(item => item.url === input.targetUrl);
        if (!tab?.id) return { status: 'blocked', error: 'target tab not found' };
        const originPattern = new URL(input.targetUrl).origin + '/*';
        const granted = await chrome.permissions.contains({ origins: [originPattern] });
        if (!granted) return {
          status: 'blocked',
          error: 'extension origin permission is not granted',
          originPattern,
        };
        try {
          await chrome.tabs.sendMessage(tab.id, { type: 'ADI_GET_SNAPSHOT' });
        } catch (error) {
          return {
            status: 'blocked',
            error: 'declared content script is not reachable',
            detail: String(error),
            tabId: tab.id,
            originPattern,
          };
        }
        const acceptance = await chrome.tabs.sendMessage(tab.id, {
          type: 'ADI_RUN_ACCEPTANCE',
          manifest: input.manifest,
        });
        return {
          status: acceptance?.allPass ? 'passed' : 'failed',
          tabId: tab.id,
          originPattern,
          acceptance,
        };
      })()`;
      const evaluated = await sendCDP('Runtime.evaluate', {
        expression,
        returnByValue: true,
        awaitPromise: true,
      }, sid);
      if (evaluated.result?.exceptionDetails) {
        res.statusCode = 500;
        res.end(JSON.stringify({
          status: 'blocked',
          error: evaluated.result.exceptionDetails.text,
        }));
        return;
      }
      res.end(JSON.stringify({
        ...(evaluated.result?.result?.value || {
          status: 'blocked',
          error: 'extension acceptance returned no value',
        }),
        extension: {
          id: new URL(matchedTarget.url).hostname,
          name: matchedManifest.name,
          version: matchedManifest.version,
          buildHash: matchedManifest.buildHash,
        },
      }, null, 2));
    }

    // POST /new (body=URL) - 创建新后台 tab
    else if (pathname === '/new') {
      if (req.method !== 'POST') {
        res.statusCode = 400;
        res.end(JSON.stringify({
          error: 'v2.5.3 起 /new 改为 POST 传 URL（避免目标 URL 含 query 时被错误切分）',
          migration: 'references/migration-2.5.3.md',
          example: "curl -X POST --data-raw 'https://example.com' http://localhost:3456/new",
        }));
        return;
      }
      const body = (await readBody(req)).trim();
      const targetUrl = body || 'about:blank';
      const resp = await sendCDP('Target.createTarget', { url: targetUrl, background: true });
      const targetId = resp.result.targetId;
      managedTabs.set(targetId, { lastAccessed: Date.now() });

      // 等待页面加载
      if (targetUrl !== 'about:blank') {
        try {
          const sid = await ensureSession(targetId);
          await waitForLoad(sid);
        } catch { /* 非致命，继续 */ }
      }

      res.end(JSON.stringify({ targetId }));
    }

    // GET /close?target=xxx - 关闭 tab
    else if (pathname === '/close') {
      const resp = await sendCDP('Target.closeTarget', { targetId: q.target });
      sessions.delete(q.target);
      managedTabs.delete(q.target);
      res.end(JSON.stringify(resp.result));
    }

    // POST /navigate?target=xxx (body=URL) - 导航（自动等待加载）
    else if (pathname === '/navigate') {
      if (req.method !== 'POST') {
        res.statusCode = 400;
        res.end(JSON.stringify({
          error: 'v2.5.3 起 /navigate 改为 POST 传 URL（避免目标 URL 含 query 时被错误切分）',
          migration: 'references/migration-2.5.3.md',
          example: "curl -X POST --data-raw 'https://example.com' 'http://localhost:3456/navigate?target=ID'",
        }));
        return;
      }
      const targetUrl = (await readBody(req)).trim();
      const sid = await ensureSession(q.target);
      const resp = await sendCDP('Page.navigate', { url: targetUrl }, sid);

      // 等待页面加载完成
      await waitForLoad(sid);

      res.end(JSON.stringify(resp.result));
    }

    // GET /back?target=xxx - 后退
    else if (pathname === '/back') {
      const sid = await ensureSession(q.target);
      await sendCDP('Runtime.evaluate', { expression: 'history.back()' }, sid);
      await waitForLoad(sid);
      res.end(JSON.stringify({ ok: true }));
    }

    // POST /eval?target=xxx - 执行 JS
    else if (pathname === '/eval') {
      const sid = await ensureSession(q.target);
      const body = await readBody(req);
      const expr = body || q.expr || 'document.title';
      const resp = await sendCDP('Runtime.evaluate', {
        expression: expr,
        returnByValue: true,
        awaitPromise: true,
      }, sid);
      if (resp.result?.result?.value !== undefined) {
        res.end(JSON.stringify({ value: resp.result.result.value }));
      } else if (resp.result?.exceptionDetails) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: resp.result.exceptionDetails.text }));
      } else {
        res.end(JSON.stringify(resp.result));
      }
    }

    // POST /click?target=xxx - 点击（body 为 CSS 选择器）
    // POST /click?target=xxx — JS 层面点击（简单快速，覆盖大多数场景）
    else if (pathname === '/click') {
      const sid = await ensureSession(q.target);
      const selector = await readBody(req);
      if (!selector) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: 'POST body 需要 CSS 选择器' }));
        return;
      }
      const selectorJson = JSON.stringify(selector);
      const js = `(() => {
        const el = document.querySelector(${selectorJson});
        if (!el) return { error: '未找到元素: ' + ${selectorJson} };
        el.scrollIntoView({ block: 'center' });
        el.click();
        return { clicked: true, tag: el.tagName, text: (el.textContent || '').slice(0, 100) };
      })()`;
      const resp = await sendCDP('Runtime.evaluate', {
        expression: js,
        returnByValue: true,
        awaitPromise: true,
      }, sid);
      if (resp.result?.result?.value) {
        const val = resp.result.result.value;
        if (val.error) {
          res.statusCode = 400;
          res.end(JSON.stringify(val));
        } else {
          res.end(JSON.stringify(val));
        }
      } else {
        res.end(JSON.stringify(resp.result));
      }
    }

    // POST /clickAt?target=xxx — CDP 浏览器级真实鼠标点击（算用户手势，能触发文件对话框、绕过反自动化检测）
    else if (pathname === '/clickAt') {
      const sid = await ensureSession(q.target);
      const selector = await readBody(req);
      if (!selector) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: 'POST body 需要 CSS 选择器' }));
        return;
      }
      const selectorJson = JSON.stringify(selector);
      const js = `(() => {
        const el = document.querySelector(${selectorJson});
        if (!el) return { error: '未找到元素: ' + ${selectorJson} };
        el.scrollIntoView({ block: 'center' });
        const rect = el.getBoundingClientRect();
        return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2, tag: el.tagName, text: (el.textContent || '').slice(0, 100) };
      })()`;
      const coordResp = await sendCDP('Runtime.evaluate', {
        expression: js,
        returnByValue: true,
        awaitPromise: true,
      }, sid);
      const coord = coordResp.result?.result?.value;
      if (!coord || coord.error) {
        res.statusCode = 400;
        res.end(JSON.stringify(coord || coordResp.result));
        return;
      }
      await sendCDP('Input.dispatchMouseEvent', {
        type: 'mousePressed', x: coord.x, y: coord.y, button: 'left', clickCount: 1
      }, sid);
      await sendCDP('Input.dispatchMouseEvent', {
        type: 'mouseReleased', x: coord.x, y: coord.y, button: 'left', clickCount: 1
      }, sid);
      res.end(JSON.stringify({ clicked: true, x: coord.x, y: coord.y, tag: coord.tag, text: coord.text }));
    }

    // POST /key?target=xxx — 发送真实 CDP 键盘事件。
    // body: JSON { "action":"press|down|up|char", "key":"Enter", "code":"Enter", "text":"", "modifiers":["Meta"] }
    else if (pathname === '/key') {
      const sid = await ensureSession(q.target);
      const body = JSON.parse(await readBody(req));
      const modifierBits = { Alt: 1, Control: 2, Meta: 4, Shift: 8 };
      const modifiers = Array.isArray(body.modifiers)
        ? body.modifiers.reduce((bits, name) => bits | (modifierBits[name] || 0), 0)
        : (body.modifiers || 0);
      const action = body.action || 'press';
      const base = { key: body.key || '', code: body.code || '', text: body.text || undefined,
        unmodifiedText: body.unmodifiedText || undefined, modifiers,
        windowsVirtualKeyCode: body.windowsVirtualKeyCode || 0, nativeVirtualKeyCode: body.nativeVirtualKeyCode || 0 };
      if (action === 'char') await sendCDP('Input.dispatchKeyEvent', { ...base, type: 'char' }, sid);
      else if (action === 'down' || action === 'up') await sendCDP('Input.dispatchKeyEvent', { ...base, type: action === 'down' ? 'keyDown' : 'keyUp' }, sid);
      else {
        await sendCDP('Input.dispatchKeyEvent', { ...base, type: 'keyDown' }, sid);
        await sendCDP('Input.dispatchKeyEvent', { ...base, type: 'keyUp' }, sid);
      }
      res.end(JSON.stringify({ sent: true, action, key: base.key, text: body.text || '' }));
    }

    // POST /insertText?target=xxx — 向已进入编辑态的元素发送真实 CDP 文本输入。
    else if (pathname === '/insertText') {
      const sid = await ensureSession(q.target);
      const text = await readBody(req);
      if (!text) { res.statusCode = 400; res.end(JSON.stringify({ error: 'POST body 需要非空文本' })); return; }
      await sendCDP('Input.insertText', { text }, sid);
      res.end(JSON.stringify({ inserted: true, length: text.length }));
    }

    // POST /clickAtPosition?target=xxx — 在 CSS 像素坐标上发送真实鼠标点击。
    // body: JSON { "x": 100, "y": 200, "clickCount": 1 }
    else if (pathname === '/clickAtPosition') {
      const sid = await ensureSession(q.target);
      const body = JSON.parse(await readBody(req));
      if (!Number.isFinite(body.x) || !Number.isFinite(body.y)) { res.statusCode = 400; res.end(JSON.stringify({ error: '需要数值 x 和 y（CSS 像素）' })); return; }
      const clickCount = body.clickCount || 1;
      const button = body.button || 'left';
      await sendCDP('Input.dispatchMouseEvent', { type: 'mousePressed', x: body.x, y: body.y, button, clickCount }, sid);
      await sendCDP('Input.dispatchMouseEvent', { type: 'mouseReleased', x: body.x, y: body.y, button, clickCount }, sid);
      res.end(JSON.stringify({ clicked: true, x: body.x, y: body.y, clickCount, coordinateSpace: 'css' }));
    }

    // GET /viewport?target=xxx — 返回 CDP 坐标调试所需的 CSS 视口和设备倍率。
    else if (pathname === '/viewport') {
      const sid = await ensureSession(q.target);
      const resp = await sendCDP('Runtime.evaluate', {
        expression: '({innerWidth,innerHeight,devicePixelRatio,visualViewport: visualViewport ? {width:visualViewport.width,height:visualViewport.height,scale:visualViewport.scale,offsetLeft:visualViewport.offsetLeft,offsetTop:visualViewport.offsetTop} : null})',
        returnByValue: true,
      }, sid);
      res.end(JSON.stringify(resp.result?.result?.value || {}));
    }

    // POST /setViewport?target=xxx — 仅允许 task-owned tab 设置 CDP 设备视口。
    else if (pathname === '/setViewport') {
      if (req.method !== 'POST') {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: 'POST body 需要 viewport JSON' }));
        return;
      }
      if (!q.target || !managedTabs.has(q.target)) {
        res.statusCode = 403;
        res.end(JSON.stringify({ error: '只允许对通过 /new 创建的 task-owned tab 设置 viewport' }));
        return;
      }
      const body = JSON.parse(await readBody(req));
      const width = Number(body.width);
      const height = Number(body.height);
      const deviceScaleFactor = body.deviceScaleFactor === undefined ? 1 : Number(body.deviceScaleFactor);
      if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 3840 || height > 3840 || !Number.isFinite(deviceScaleFactor) || deviceScaleFactor < 0 || deviceScaleFactor > 4) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: 'viewport width/height 必须是 1-3840 的整数，deviceScaleFactor 必须在 0-4 之间' }));
        return;
      }
      const sid = await ensureSession(q.target);
      await sendCDP('Emulation.setDeviceMetricsOverride', {
        width,
        height,
        deviceScaleFactor,
        mobile: body.mobile === true,
        screenWidth: width,
        screenHeight: height,
      }, sid);
      touchTab(q.target);
      res.end(JSON.stringify({ status: 'ok', targetId: q.target, width, height, deviceScaleFactor, mobile: body.mobile === true }));
    }

    // POST /setFiles?target=xxx — 给 file input 设置本地文件（绕过文件对话框）
    // body: JSON { "selector": "input[type=file]", "files": ["/path/to/file1.png", "/path/to/file2.png"] }
    else if (pathname === '/setFiles') {
      const sid = await ensureSession(q.target);
      const body = JSON.parse(await readBody(req));
      if (!body.selector || !body.files) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: '需要 selector 和 files 字段' }));
        return;
      }
      // 获取 DOM 节点
      await sendCDP('DOM.enable', {}, sid);
      const doc = await sendCDP('DOM.getDocument', {}, sid);
      const node = await sendCDP('DOM.querySelector', {
        nodeId: doc.result.root.nodeId,
        selector: body.selector
      }, sid);
      if (!node.result?.nodeId) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: '未找到元素: ' + body.selector }));
        return;
      }
      // 设置文件
      await sendCDP('DOM.setFileInputFiles', {
        nodeId: node.result.nodeId,
        files: body.files
      }, sid);
      res.end(JSON.stringify({ success: true, files: body.files.length }));
    }

    // GET /scroll?target=xxx&y=3000 - 滚动
    else if (pathname === '/scroll') {
      const sid = await ensureSession(q.target);
      const y = parseInt(q.y || '3000');
      const direction = q.direction || 'down'; // down | up | top | bottom
      let js;
      if (direction === 'top') {
        js = 'window.scrollTo(0, 0); "scrolled to top"';
      } else if (direction === 'bottom') {
        js = 'window.scrollTo(0, document.body.scrollHeight); "scrolled to bottom"';
      } else if (direction === 'up') {
        js = `window.scrollBy(0, -${Math.abs(y)}); "scrolled up ${Math.abs(y)}px"`;
      } else {
        js = `window.scrollBy(0, ${Math.abs(y)}); "scrolled down ${Math.abs(y)}px"`;
      }
      const resp = await sendCDP('Runtime.evaluate', {
        expression: js,
        returnByValue: true,
      }, sid);
      // 等待懒加载触发
      await new Promise(r => setTimeout(r, 800));
      res.end(JSON.stringify({ value: resp.result?.result?.value }));
    }

    // GET /screenshot?target=xxx&file=/tmp/x.png - 截图
    else if (pathname === '/screenshot') {
      const sid = await ensureSession(q.target);
      const format = q.format || 'png';
      const resp = await sendCDP('Page.captureScreenshot', {
        format,
        quality: format === 'jpeg' ? 80 : undefined,
      }, sid);
      if (q.file) {
        fs.writeFileSync(q.file, Buffer.from(resp.result.data, 'base64'));
        res.end(JSON.stringify({ saved: q.file }));
      } else {
        res.setHeader('Content-Type', 'image/' + format);
        res.end(Buffer.from(resp.result.data, 'base64'));
      }
    }

    // GET /info?target=xxx - 获取页面信息
    else if (pathname === '/info') {
      const sid = await ensureSession(q.target);
      const resp = await sendCDP('Runtime.evaluate', {
        expression: 'JSON.stringify({title: document.title, url: location.href, ready: document.readyState})',
        returnByValue: true,
      }, sid);
      res.end(resp.result?.result?.value || '{}');
    }

    else {
      res.statusCode = 404;
      res.end(JSON.stringify({
        error: '未知端点',
        endpoints: {
          '/health': 'GET - 健康检查',
          '/targets': 'GET - 列出所有页面 tab',
          '/extension-status?name=...&version=...': 'GET - 核验指定 Chrome extension 的 service worker manifest',
          '/extension-acceptance': 'POST JSON - 通过指定 extension 对目标 tab 运行广告位 manifest 验收',
          '/new': 'POST body=URL - 创建新后台 tab（自动等待加载）',
          '/close?target=': 'GET - 关闭 tab',
          '/navigate?target=': 'POST body=URL - 导航（自动等待加载）',
          '/back?target=': 'GET - 后退',
          '/info?target=': 'GET - 页面标题/URL/状态',
          '/eval?target=': 'POST body=JS表达式 - 执行 JS',
          '/click?target=': 'POST body=CSS选择器 - 点击元素',
          '/clickAt?target=': 'POST body=CSS选择器 - 真实鼠标点击',
          '/clickAtPosition?target=': 'POST JSON {x,y,clickCount?} - 在 CSS 像素坐标真实点击',
          '/key?target=': 'POST JSON {action?,key,code?,text?,modifiers?} - 真实 CDP 键盘事件',
          '/insertText?target=': 'POST body=文本 - 向已进入编辑态的元素输入文本',
          '/viewport?target=': 'GET - CSS 视口、devicePixelRatio 和 visualViewport',
          '/setViewport?target=': 'POST JSON {width,height,deviceScaleFactor?,mobile?} - 仅 task-owned tab 的 CDP 设备视口',
          '/scroll?target=&y=&direction=': 'GET - 滚动页面',
          '/screenshot?target=&file=': 'GET - 截图',
        },
      }));
    }
  } catch (e) {
    res.statusCode = 500;
    res.end(JSON.stringify({ error: e.message }));
  }
});

// 检查端口是否被占用
function checkPortAvailable(port) {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.once('error', () => resolve(false));
    s.once('listening', () => { s.close(); resolve(true); });
    s.listen(port, '127.0.0.1');
  });
}

async function main() {
  // 检查是否已有 proxy 在运行
  const available = await checkPortAvailable(PORT);
  if (!available) {
    // 验证已有实例是否健康
    try {
      const ok = await new Promise((resolve) => {
        http.get(`http://127.0.0.1:${PORT}/health`, { timeout: 2000 }, (res) => {
          let d = '';
          res.on('data', c => d += c);
          res.on('end', () => resolve(d.includes('"ok"')));
        }).on('error', () => resolve(false));
      });
      if (ok) {
        console.log(`[CDP Proxy] 已有实例运行在端口 ${PORT}，退出`);
        process.exit(0);
      }
    } catch { /* 端口占用但非 proxy，继续报错 */ }
    console.error(`[CDP Proxy] 端口 ${PORT} 已被占用`);
    process.exit(1);
  }

  server.listen(PORT, '127.0.0.1', () => {
    console.log(`[CDP Proxy] 运行在 http://localhost:${PORT}`);
    // 启动时尝试连接 Chrome（非阻塞）
    connect().catch(e => console.error('[CDP Proxy] 初始连接失败:', e.message, '（将在首次请求时重试）'));
  });

  // 定时清理闲置 tab
  const cleanupTimer = setInterval(cleanupIdleTabs, CLEANUP_INTERVAL);
  cleanupTimer.unref();

  const shutdown = async (sig) => {
    console.log(`[CDP Proxy] ${sig}, cleaning up...`);
    clearInterval(cleanupTimer);
    await closeAllManagedTabs();
    process.exit(0);
  };
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
}

// 防止未捕获异常导致进程崩溃
process.on('uncaughtException', (e) => {
  console.error('[CDP Proxy] 未捕获异常:', e.message);
});
process.on('unhandledRejection', (e) => {
  console.error('[CDP Proxy] 未处理拒绝:', e?.message || e);
});

main();
