#!/usr/bin/env node
// Thin forwarder: resolve one source, download its installer, run bash, clean up.
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const RAW_HOST = "raw.githubusercontent.com";
const REPO = "CtriXin/multi-model-switch";
const TAG = /^v\d+\.\d+\.\d+$/;
const PAYLOAD_MARKERS = ['REPO_NAME="multi-model-switch"', "#!/bin/bash"];
const WINDOWS_PAYLOAD_MARKERS = ['MMS Windows Native Preview bootstrap', '$repo = "CtriXin/multi-model-switch"'];

export function parseArgs(args) {
  let selection = "stable";
  let literalRef = false;
  const forwarded = [];
  for (let i = 0; i < args.length; i++) {
    let arg = args[i];
    if (/^--(ref|channel)=/.test(arg)) {
      const at = arg.indexOf("=");
      args = [...args.slice(0, i), arg.slice(0, at), arg.slice(at + 1), ...args.slice(i + 1)];
      arg = args[i];
    }
    if (arg === "--ref" || arg === "--channel") {
      const value = args[++i];
      if (!value || value.startsWith("-")) throw new Error(`${arg} requires a value`);
      if (arg === "--channel" && !["stable", "dev", "canary"].includes(value)) throw new Error("--channel must be stable, dev or canary");
      if (arg === "--ref" && (!/^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(value) || value.includes(".."))) throw new Error("invalid ref");
      selection = value;
      literalRef = arg === "--ref";
    } else if (["--stable", "--dev", "--canary", "--main", "--latest-release", "--latest-tag"].includes(arg)) {
      literalRef = false;
      selection = arg === "--latest-release" ? "stable" : arg.slice(2);
    } else {
      forwarded.push(arg);
    }
  }
  return { selection, forwarded, literalRef };
}

async function fetchPinned(url, fetcher) {
  // Refuse redirects before following them, rather than inspecting only the final host.
  const response = await fetcher(url, { redirect: "error", signal: AbortSignal.timeout(15000), headers: { "User-Agent": "mms-install", Accept: "application/vnd.github+json" } });
  if (!response.ok) throw new Error(`could not download ${new URL(url).pathname} (HTTP ${response.status})`);
  if (response.url && new URL(response.url).host !== new URL(url).host) throw new Error("refusing a redirect off the source host");
  return response;
}

// One ref resolution for both platforms. `stable` is the latest release tag,
// never a branch: `main` is deliberately kept behind the shipped releases.
export async function resolveRef(selection, literalRef, fetcher) {
  if (literalRef) return selection;
  if (selection === "stable") {
    const release = await (await fetchPinned(`https://api.github.com/repos/${REPO}/releases/latest`, fetcher)).json();
    const ref = release.tag_name;
    if (!TAG.test(ref) || release.draft || release.prerelease) throw new Error("no valid stable MMS release found");
    return ref;
  }
  if (selection === "latest-tag") {
    const tags = await (await fetchPinned(`https://api.github.com/repos/${REPO}/tags?per_page=100`, fetcher)).json();
    const ref = tags.map(t => t.name).filter(t => TAG.test(t)).sort((a, b) => b.localeCompare(a, undefined, { numeric: true }))[0];
    if (!ref) throw new Error("no stable MMS tag found");
    return ref;
  }
  return selection;
}

export async function resolveInstaller(args, fetcher = fetch) {
  const { selection, forwarded, literalRef } = parseArgs(args);
  const ref = await resolveRef(selection, literalRef, fetcher);
  const response = await fetchPinned(`https://${RAW_HOST}/${REPO}/${encodeURIComponent(ref)}/install.sh`, fetcher);
  const script = await response.text();
  if (script.length > 2 * 1024 * 1024 || !PAYLOAD_MARKERS.every(marker => script.includes(marker))) throw new Error("the downloaded file does not look like the MMS installer");
  return { ref, script, args: [...forwarded, "--ref", ref] };
}

export function runInstaller(script, args, run = spawnSync, temporaryRoot = tmpdir()) {
  const dir = mkdtempSync(join(temporaryRoot, "mms-install-"));
  const scriptPath = join(dir, "install.sh");
  try {
    writeFileSync(scriptPath, script, { mode: 0o700 });
    const result = run("bash", [scriptPath, ...args], { stdio: "inherit" });
    if (result.error) throw new Error(`could not run bash: ${result.error.message}`);
    return result.status === null ? 1 : result.status;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

export function runWindowsBootstrap(script, args, run = spawnSync, temporaryRoot = tmpdir()) {
  const dir = mkdtempSync(join(temporaryRoot, "mms-install-"));
  const scriptPath = join(dir, "install.ps1");
  try {
    writeFileSync(scriptPath, script, "utf8");
    const powershellArgs = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath];
    for (let i = 0; i < args.length; i++) {
      const arg = args[i];
      if (arg === "--ref" || arg === "--channel") powershellArgs.push(arg === "--ref" ? "-Ref" : "-Channel", args[++i]);
      else if (arg === "--dry-run" || arg === "--no-path") powershellArgs.push(arg === "--dry-run" ? "-DryRun" : "-NoPath");
    }
    const result = run("powershell.exe", powershellArgs, { stdio: "inherit" });
    if (result.error) throw new Error(`could not run PowerShell: ${result.error.message}`);
    return result.status === null ? 1 : result.status;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

export async function resolveWindowsInstaller(args, fetcher = fetch) {
  const { selection, forwarded, literalRef } = parseArgs(args);
  const ref = await resolveRef(selection, literalRef, fetcher);
  let response;
  try {
    response = await fetchPinned(`https://${RAW_HOST}/${REPO}/${encodeURIComponent(ref)}/packages/mms-install/bin/install.ps1`, fetcher);
  } catch (error) {
    throw new Error(`${error.message}. ${ref} may predate the Windows Native Preview; try --channel dev or a newer --ref.`);
  }
  const script = await response.text();
  if (script.length > 2 * 1024 * 1024 || !WINDOWS_PAYLOAD_MARKERS.every(marker => script.includes(marker))) throw new Error("the downloaded file does not look like the MMS Windows bootstrap");
  return { ref, script, args: [...forwarded, "--ref", ref] };
}

export async function main(args = process.argv.slice(2)) {
  if (process.platform === "win32") {
    const plan = await resolveWindowsInstaller(args);
    console.log(`MMS Windows Native Preview bootstrap: ${plan.ref}`);
    return runWindowsBootstrap(plan.script, plan.args);
  }
  const plan = await resolveInstaller(args);
  console.log(`MMS installer: ${plan.ref}`);
  return runInstaller(plan.script, plan.args);
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  try { process.exitCode = await main(); }
  catch (error) { console.error(`mms-install: ${error.message}`); process.exitCode = 1; }
}
