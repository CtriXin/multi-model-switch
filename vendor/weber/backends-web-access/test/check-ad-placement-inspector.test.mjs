import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';
import test from 'node:test';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CHECKER = path.join(ROOT, 'scripts', 'check-ad-placement-inspector.mjs');

function runChecker(args, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [CHECKER, ...args], {
      env: { ...process.env, ...env },
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.once('error', reject);
    child.once('close', (code, signal) => resolve({ code, signal, stdout, stderr }));
  });
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
}

test('reuses the supplied task-owned target without creating or closing a tab', async (t) => {
  const tempDir = await mkdtemp(path.join(os.tmpdir(), 'adi-reuse-target-'));
  const extensionRoot = path.join(tempDir, 'extension');
  const acceptancePath = path.join(tempDir, 'acceptance.json');
  const buildHash = 'a'.repeat(64);
  await mkdir(extensionRoot);
  await writeFile(path.join(extensionRoot, 'manifest.json'), JSON.stringify({ name: '广告位检查器', version: '0.8.0' }));
  await writeFile(path.join(extensionRoot, 'build-attestation.json'), JSON.stringify({
    schema: 'ad-placement-inspector.build-attestation.v1',
    version: '0.8.0',
    buildHash,
  }));
  await writeFile(acceptancePath, JSON.stringify({
    schema: 'ad-placement-inspector.manifest.v1',
    placements: [{ slot: 'home_1' }],
    source: { taskGuid: 't103490', revision: 1 },
    manifestHash: 'b'.repeat(64),
  }));

  let newCalls = 0;
  let closeCalls = 0;
  let navigatedUrl = '';
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    res.setHeader('Content-Type', 'application/json');
    if (url.pathname === '/health') {
      res.end(JSON.stringify({ status: 'ok', connected: true, browser: { id: 'chrome' } }));
    } else if (url.pathname === '/targets') {
      res.end(JSON.stringify([{ targetId: 'task-owned', type: 'page' }]));
    } else if (url.pathname === '/navigate') {
      navigatedUrl = await readBody(req);
      res.end(JSON.stringify({ frameId: 'frame-1' }));
    } else if (url.pathname === '/eval') {
      res.end(JSON.stringify({ value: JSON.stringify({
        enabled: 'enabled',
        schema: 'ad-placement-inspector.handshake.v2',
        version: '0.8.0',
        buildHash,
        url: navigatedUrl,
      }) }));
    } else if (url.pathname === '/extension-status') {
      res.end(JSON.stringify({ status: 'passed' }));
    } else if (url.pathname === '/extension-acceptance') {
      res.end(JSON.stringify({ status: 'passed', acceptance: { allPass: true } }));
    } else if (url.pathname === '/new') {
      newCalls++;
      res.statusCode = 500;
      res.end(JSON.stringify({ error: 'must not create a tab' }));
    } else if (url.pathname === '/close') {
      closeCalls++;
      res.statusCode = 500;
      res.end(JSON.stringify({ error: 'must not close a reused tab' }));
    } else {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: `unexpected ${url.pathname}` }));
    }
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const { port } = server.address();
  t.after(async () => {
    await new Promise((resolve) => server.close(resolve));
    await rm(tempDir, { recursive: true, force: true });
  });

  const result = await runChecker([
    '--url', 'https://example.test/reader',
    '--target', 'task-owned',
    '--manifest', acceptancePath,
  ], {
    AD_PLACEMENT_INSPECTOR_ROOT: extensionRoot,
    CDP_PROXY_PORT: String(port),
  });

  assert.equal(result.code, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.status, 'passed');
  assert.equal(report.target.reused, true);
  assert.equal(newCalls, 0);
  assert.equal(closeCalls, 0);
  assert.match(navigatedUrl, /^https:\/\/example\.test\/reader\?.*__adi_inspection=/);
});

test('sets mobile emulation on a reused task-owned target before navigation', async (t) => {
  const tempDir = await mkdtemp(path.join(os.tmpdir(), 'adi-mobile-target-'));
  const extensionRoot = path.join(tempDir, 'extension');
  const acceptancePath = path.join(tempDir, 'acceptance.json');
  const buildHash = 'c'.repeat(64);
  await mkdir(extensionRoot);
  await writeFile(path.join(extensionRoot, 'manifest.json'), JSON.stringify({ name: '广告位检查器', version: '0.8.0' }));
  await writeFile(path.join(extensionRoot, 'build-attestation.json'), JSON.stringify({
    schema: 'ad-placement-inspector.build-attestation.v1',
    version: '0.8.0',
    buildHash,
  }));
  await writeFile(acceptancePath, JSON.stringify({
    schema: 'ad-placement-inspector.manifest.v1',
    placements: [{ slot: 'read_1' }],
    source: { taskGuid: 't103490', revision: 1 },
    context: { viewportClass: 'mobile' },
    manifestHash: 'd'.repeat(64),
  }));

  const calls = [];
  let navigatedUrl = '';
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    const body = await readBody(req);
    calls.push({ path: url.pathname, body });
    res.setHeader('Content-Type', 'application/json');
    if (url.pathname === '/health') {
      res.end(JSON.stringify({ status: 'ok', connected: true, browser: { id: 'chrome' } }));
    } else if (url.pathname === '/targets') {
      res.end(JSON.stringify([{ targetId: 'task-owned', type: 'page' }]));
    } else if (url.pathname === '/setViewport') {
      res.end(JSON.stringify({ status: 'ok' }));
    } else if (url.pathname === '/navigate') {
      navigatedUrl = body;
      res.end(JSON.stringify({ frameId: 'frame-1' }));
    } else if (url.pathname === '/eval') {
      res.end(JSON.stringify({ value: JSON.stringify({
        enabled: 'enabled', schema: 'ad-placement-inspector.handshake.v2', version: '0.8.0', buildHash, url: navigatedUrl,
      }) }));
    } else if (url.pathname === '/extension-status') {
      res.end(JSON.stringify({ status: 'passed' }));
    } else if (url.pathname === '/extension-acceptance') {
      res.end(JSON.stringify({ status: 'passed', acceptance: { allPass: true } }));
    } else {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: `unexpected ${url.pathname}` }));
    }
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const { port } = server.address();
  t.after(async () => {
    await new Promise((resolve) => server.close(resolve));
    await rm(tempDir, { recursive: true, force: true });
  });

  const result = await runChecker([
    '--url', 'https://example.test/reader', '--target', 'task-owned', '--manifest', acceptancePath,
  ], { AD_PLACEMENT_INSPECTOR_ROOT: extensionRoot, CDP_PROXY_PORT: String(port) });

  assert.equal(result.code, 0, result.stderr);
  assert.deepEqual(JSON.parse(calls.find((call) => call.path === '/setViewport').body), {
    width: 390, height: 844, deviceScaleFactor: 1, mobile: true,
  });
  assert.ok(calls.findIndex((call) => call.path === '/setViewport') < calls.findIndex((call) => call.path === '/navigate'));
});
