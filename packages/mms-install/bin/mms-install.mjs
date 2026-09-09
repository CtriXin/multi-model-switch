#!/usr/bin/env node
// Thin forwarder: fetch the MMS installer and hand it to bash.
//
// This package downloads and executes a shell script, so it stays deliberately
// small and auditable. The source host is pinned, redirects off that host are
// refused, and the payload is checked before anything runs. It holds no install
// logic of its own: everything lives in install.sh, which means a cached copy of
// this wrapper still installs the current MMS.

import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const RAW_HOST = "raw.githubusercontent.com";
const REPO = "CtriXin/multi-model-switch";
const DEFAULT_REF = "main";
// Present in every version of the installer; a page that lacks it is not it.
const PAYLOAD_MARKERS = ['REPO_NAME="multi-model-switch"', "#!/bin/bash"];

function fail(message) {
  console.error(`mms-install: ${message}`);
  process.exit(1);
}

// The installer script and the source it installs must come from the same
// place. Picking a channel or a ref moves both, or the user ends up running a
// new script against old sources.
function resolveRef(args) {
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--ref" && args[index + 1]) return args[index + 1];
    if (arg.startsWith("--ref=")) return arg.slice("--ref=".length);
    if (arg === "--channel" && args[index + 1]) return channelRef(args[index + 1]);
    if (arg.startsWith("--channel=")) return channelRef(arg.slice("--channel=".length));
    if (arg === "--dev") return "dev";
    if (arg === "--canary") return "canary";
  }
  return DEFAULT_REF;
}

function channelRef(channel) {
  if (channel === "dev" || channel === "canary") return channel;
  return DEFAULT_REF;
}

async function download(ref) {
  const url = `https://${RAW_HOST}/${REPO}/${encodeURIComponent(ref)}/install.sh`;
  let response;
  try {
    response = await fetch(url, { redirect: "follow" });
  } catch (error) {
    fail(`could not reach ${RAW_HOST}: ${error.message}`);
  }
  if (!response.ok) {
    fail(`could not download the installer for "${ref}" (HTTP ${response.status})`);
  }
  if (new URL(response.url).host !== RAW_HOST) {
    fail(`refusing a redirect off ${RAW_HOST} to ${response.url}`);
  }
  const script = await response.text();
  for (const marker of PAYLOAD_MARKERS) {
    if (!script.includes(marker)) {
      fail(`the downloaded file does not look like the MMS installer`);
    }
  }
  return script;
}

async function main() {
  if (process.platform === "win32") {
    fail(
      "Windows is not supported. The MMS installer needs bash, so run it from WSL or install on macOS/Linux.",
    );
  }

  const args = process.argv.slice(2);
  const ref = resolveRef(args);
  const script = await download(ref);

  const dir = mkdtempSync(join(tmpdir(), "mms-install-"));
  const scriptPath = join(dir, "install.sh");
  try {
    writeFileSync(scriptPath, script, { mode: 0o700 });
    // stdio is inherited, so the installer's closing question reaches the
    // terminal directly instead of being swallowed the way `curl | bash` does.
    const result = spawnSync("bash", [scriptPath, ...args], { stdio: "inherit" });
    if (result.error) {
      fail(`could not run bash: ${result.error.message}`);
    }
    process.exit(result.status === null ? 1 : result.status);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

await main();
