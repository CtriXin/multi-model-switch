import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm, rmdir, writeFile } from 'node:fs/promises';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';
import test from 'node:test';

import { isConnectedProxyHealth } from '../scripts/check-deps.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CHECK_DEPS = path.join(ROOT, 'scripts', 'check-deps.mjs');

function runCheckDeps(env, args = []) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [CHECK_DEPS, ...args], {
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

test('isConnectedProxyHealth only accepts an explicitly connected healthy proxy', () => {
  assert.equal(isConnectedProxyHealth({ status: 'ok', connected: true }), true);
  assert.equal(isConnectedProxyHealth({ status: 'ok', connected: false }), false);
  assert.equal(isConnectedProxyHealth({ status: 'ok', connected: 'true' }), false);
  assert.equal(isConnectedProxyHealth({ status: 'error', connected: true }), false);
});

test('check-deps accepts a connected proxy before sandbox browser discovery', async (t) => {
  const hostHome = await mkdtemp(path.join(os.tmpdir(), 'web-access-empty-home-'));
  const patternsDir = path.join(ROOT, 'references', 'site-patterns');
  const patternFile = path.join(patternsDir, 'test-proxy-health-pattern.md');
  await mkdir(patternsDir, { recursive: true });
  await writeFile(patternFile, '# test pattern\n');

  const server = http.createServer((req, res) => {
    assert.equal(req.url, '/health');
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({
      status: 'ok',
      connected: true,
      browser: { id: 'chrome', label: 'Chrome' },
    }));
  });

  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const { port } = server.address();
  t.after(async () => {
    await new Promise((resolve) => server.close(resolve));
    await rm(hostHome, { recursive: true, force: true });
    await rm(patternFile, { force: true });
    await rmdir(patternsDir).catch(() => {});
  });

  const result = await runCheckDeps({
    CDP_PROXY_PORT: String(port),
    WEB_ACCESS_HOST_HOME: hostHome,
  });

  assert.equal(result.code, 0, result.stderr);
  assert.match(result.stdout, /proxy: ready \(Chrome\)/);
  assert.match(result.stdout, /site-patterns: .*test-proxy-health-pattern/);
  assert.doesNotMatch(result.stdout, /browser:/);
});

test('check-deps does not early-pass when --browser conflicts with proxy health', async (t) => {
  const hostHome = await mkdtemp(path.join(os.tmpdir(), 'web-access-empty-home-'));
  const configPath = path.join(ROOT, 'config.env');
  const hadConfig = fs.existsSync(configPath);
  const configBefore = hadConfig ? await readFile(configPath) : null;
  const server = http.createServer((req, res) => {
    assert.equal(req.url, '/health');
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({
      status: 'ok',
      connected: true,
      browser: { id: 'chrome', label: 'Chrome' },
    }));
  });

  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const { port } = server.address();
  t.after(async () => {
    await new Promise((resolve) => server.close(resolve));
    await rm(hostHome, { recursive: true, force: true });
    if (hadConfig) await writeFile(configPath, configBefore);
    else await rm(configPath, { force: true });
  });

  const result = await runCheckDeps({
    CDP_PROXY_PORT: String(port),
    WEB_ACCESS_HOST_HOME: hostHome,
  }, ['--browser', 'edge']);

  assert.equal(result.code, 1, result.stderr);
  assert.match(result.stdout, /(?:browser: error — 本次指定的浏览器是 "edge"|proxy: 浏览器不一致 — 当前已连着 Chrome，但本次需要 edge)/);
  assert.doesNotMatch(result.stdout, /proxy: ready/);
});
