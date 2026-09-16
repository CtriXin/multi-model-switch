#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const hostHome = process.env.WEB_ACCESS_HOST_HOME
  || process.env.HOST_HOME
  || process.env.REAL_HOME
  || os.homedir();
const EXTENSION_ROOT = path.resolve(
  process.env.AD_PLACEMENT_INSPECTOR_ROOT
  || path.join(hostHome, 'auto-skills', 'CtriXin-repo', 'chrome-extensions', 'ad-placement-inspector'),
);
const PROXY = `http://127.0.0.1:${Number(process.env.CDP_PROXY_PORT || 3456)}`;
const EXPECTED_SCHEMA = 'ad-placement-inspector.handshake.v2';

function mobileViewportFor(manifest) {
  if (manifest?.context?.viewportClass !== 'mobile') return null;
  return { width: 390, height: 844, deviceScaleFactor: 1, mobile: true };
}

function parseArgs(argv) {
  const out = { url: '', evidenceDir: '', manifest: '', keepTab: false, targetId: '' };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--url') out.url = argv[++i] || '';
    else if (argv[i] === '--evidence-dir') out.evidenceDir = argv[++i] || '';
    else if (argv[i] === '--manifest') out.manifest = argv[++i] || '';
    else if (argv[i] === '--target') out.targetId = argv[++i] || '';
    else if (argv[i] === '--keep-tab') out.keepTab = true;
  }
  if (!out.url) throw new Error('--url is required');
  return out;
}

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, { ...options, signal: AbortSignal.timeout(15000) });
  const text = await response.text();
  let payload;
  try { payload = JSON.parse(text); } catch { payload = { raw: text }; }
  if (!response.ok) throw new Error(`${response.status} ${JSON.stringify(payload)}`);
  return payload;
}

const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const inspectedUrl = new URL(args.url);
  inspectedUrl.searchParams.set('__adi_inspection', `${Date.now()}-${Math.random().toString(16).slice(2)}`);
  const manifestPath = path.join(EXTENSION_ROOT, 'manifest.json');
  const attestationPath = path.join(EXTENSION_ROOT, 'build-attestation.json');
  if (!fs.existsSync(manifestPath)) throw new Error(`extension manifest missing: ${manifestPath}`);
  if (!fs.existsSync(attestationPath)) throw new Error(`extension attestation missing: ${attestationPath}`);
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const attestation = JSON.parse(fs.readFileSync(attestationPath, 'utf8'));
  if (
    attestation.schema !== 'ad-placement-inspector.build-attestation.v1'
    || attestation.version !== manifest.version
    || !/^[a-f0-9]{64}$/i.test(attestation.buildHash || '')
  ) {
    throw new Error('canonical extension build attestation is invalid');
  }
  let acceptanceManifest = null;
  if (args.manifest) {
    const acceptancePath = path.resolve(args.manifest);
    acceptanceManifest = JSON.parse(fs.readFileSync(acceptancePath, 'utf8'));
    if (
      acceptanceManifest.schema !== 'ad-placement-inspector.manifest.v1'
      || !Array.isArray(acceptanceManifest.placements)
      || !acceptanceManifest.placements.length
      || !acceptanceManifest.source?.taskGuid
      || acceptanceManifest.source?.revision === undefined
      || !/^[a-f0-9]{64}$/i.test(acceptanceManifest.manifestHash || '')
    ) {
      throw new Error('acceptance manifest is invalid or not source-bound');
    }
  }
  const health = await jsonFetch(`${PROXY}/health`);
  if (health.status !== 'ok' || !health.connected) {
    throw new Error('web-access CDP proxy is not connected to the real Chrome instance');
  }

  let targetId = args.targetId;
  let createdTarget = false;
  const mobileViewport = mobileViewportFor(acceptanceManifest);
  if (targetId) {
    const targets = await jsonFetch(`${PROXY}/targets`);
    if (!targets.some(target => target.targetId === targetId && target.type === 'page')) {
      throw new Error('--target must be an existing task-owned page target');
    }
    if (mobileViewport) {
      await jsonFetch(`${PROXY}/setViewport?target=${encodeURIComponent(targetId)}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(mobileViewport),
      });
    }
    // Reuse one task-owned tab across a batch to avoid per-case CDP prompts.
    await jsonFetch(`${PROXY}/navigate?target=${encodeURIComponent(targetId)}`, {
      method: 'POST',
      body: inspectedUrl.href,
    });
  } else {
    // Set mobile emulation before navigation so responsive layout is verified at first render.
    const created = await jsonFetch(`${PROXY}/new`, {
      method: 'POST',
      body: mobileViewport ? 'about:blank' : inspectedUrl.href,
    });
    targetId = created.targetId;
    createdTarget = true;
    if (mobileViewport) {
      await jsonFetch(`${PROXY}/setViewport?target=${encodeURIComponent(targetId)}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(mobileViewport),
      });
      await jsonFetch(`${PROXY}/navigate?target=${encodeURIComponent(targetId)}`, {
        method: 'POST',
        body: inspectedUrl.href,
      });
    }
  }
  let result;
  try {
    let pageHandshake = null;
    for (let attempt = 0; attempt < 20; attempt++) {
      const expression = `JSON.stringify({
        enabled: document.documentElement.dataset.adPlacementInspector || null,
        schema: document.documentElement.dataset.adPlacementInspectorSchema || null,
        version: document.documentElement.dataset.adPlacementInspectorVersion || null,
        buildHash: document.documentElement.dataset.adPlacementInspectorBuildHash || null,
        url: location.href
      })`;
      const evaluated = await jsonFetch(
        `${PROXY}/eval?target=${encodeURIComponent(targetId)}`,
        { method: 'POST', body: expression },
      );
      try { pageHandshake = JSON.parse(evaluated.value); } catch { pageHandshake = null; }
      if (
        pageHandshake?.enabled === 'enabled'
        && pageHandshake?.schema === EXPECTED_SCHEMA
        && pageHandshake?.version === manifest.version
        && pageHandshake?.buildHash === attestation.buildHash
      ) break;
      await wait(250);
    }
    const extensionStatus = await jsonFetch(
      `${PROXY}/extension-status?name=${encodeURIComponent(manifest.name)}`
        + `&version=${encodeURIComponent(manifest.version)}`
        + `&buildHash=${encodeURIComponent(attestation.buildHash)}`,
    );
    let placementAcceptance = null;
    if (
      acceptanceManifest
      && pageHandshake?.url
      && extensionStatus.status === 'passed'
    ) {
      const acceptanceRequest = {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          name: manifest.name,
          version: manifest.version,
          buildHash: attestation.buildHash,
          targetUrl: pageHandshake.url,
          manifest: acceptanceManifest,
        }),
      };
      const maxAcceptanceAttempts = 20;
      for (let attempt = 1; attempt <= maxAcceptanceAttempts; attempt++) {
        placementAcceptance = await jsonFetch(
          `${PROXY}/extension-acceptance`,
          acceptanceRequest,
        );
        placementAcceptance.preflight = {
          attempts: attempt,
          maxAttempts: maxAcceptanceAttempts,
          retryIntervalMs: 250,
        };
        if (
          placementAcceptance.status === 'passed'
          && placementAcceptance.acceptance?.allPass === true
        ) break;
        if (attempt < maxAcceptanceAttempts) await wait(250);
      }
    }
    const handshakePassed = (
      pageHandshake?.enabled === 'enabled'
      && pageHandshake?.schema === EXPECTED_SCHEMA
      && pageHandshake?.version === manifest.version
      && pageHandshake?.buildHash === attestation.buildHash
      && extensionStatus.status === 'passed'
    );
    const acceptancePassed = !acceptanceManifest || (
      placementAcceptance?.status === 'passed'
      && placementAcceptance?.acceptance?.allPass === true
    );
    const passed = handshakePassed && acceptancePassed;
    result = {
      schema_version: 'web-access.ad-placement-inspector-preflight.v1',
      generated_at: new Date().toISOString(),
      status: passed ? 'passed' : 'blocked',
      real_chrome: {
        connected: true,
        browser: health.browser || null,
        cdp_proxy_port: Number(process.env.CDP_PROXY_PORT || 3456),
      },
      expected_extension: {
        root: EXTENSION_ROOT,
        name: manifest.name,
        version: manifest.version,
        build_hash: attestation.buildHash,
        handshake_schema: EXPECTED_SCHEMA,
      },
      extension_runtime: extensionStatus,
      page_handshake: pageHandshake,
      placement_acceptance: placementAcceptance,
      acceptance_manifest: acceptanceManifest,
      target: {
        id: targetId,
        requested_url: args.url,
        inspected_url: inspectedUrl.href,
        reused: !createdTarget,
      },
      blocker: passed ? null : (
        !handshakePassed
          ? '广告位检查器未安装/未启用，或真实 Chrome 加载的 version/build hash 与 canonical source 不一致。'
            + '请在真实 Chrome 从 canonical 目录 reload 后重试。'
          : '广告位与 source-bound manifest 不一致；逐项 failures 已写入 placement_acceptance。'
      ),
    };
    if (args.evidenceDir) {
      const evidenceDir = path.resolve(args.evidenceDir);
      fs.mkdirSync(evidenceDir, { recursive: true });
      const jsonPath = path.join(evidenceDir, 'ad-placement-inspector-preflight.json');
      const screenshotPath = path.join(evidenceDir, 'ad-placement-inspector-preflight.png');
      fs.writeFileSync(jsonPath, `${JSON.stringify(result, null, 2)}\n`);
      await jsonFetch(
        `${PROXY}/screenshot?target=${encodeURIComponent(targetId)}&file=${encodeURIComponent(screenshotPath)}`,
      );
      result.evidence = { json: jsonPath, screenshot: screenshotPath };
      fs.writeFileSync(jsonPath, `${JSON.stringify(result, null, 2)}\n`);
    }
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    if (!passed) process.exitCode = 2;
  } finally {
    if (createdTarget && !args.keepTab) {
      await jsonFetch(`${PROXY}/close?target=${encodeURIComponent(targetId)}`).catch(() => undefined);
    }
  }
}

main().catch(error => {
  process.stderr.write(`${JSON.stringify({ status: 'blocked', error: String(error.message || error) })}\n`);
  process.exitCode = 2;
});
