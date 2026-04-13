import { randomUUID } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { createRequire } from 'node:module';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);

console.log = () => {};
console.info = () => {};

function candidateNodeModuleRoots() {
  const roots = [];
  const add = (value) => {
    if (!value) return;
    const normalized = path.resolve(value);
    if (!roots.includes(normalized)) {
      roots.push(normalized);
    }
  };

  add(process.env.MMS_NODE_MODULES);
  for (const entry of String(process.env.NODE_PATH || '').split(path.delimiter)) {
    add(entry);
  }

  const execDir = path.dirname(process.execPath);
  add(path.resolve(execDir, '..', 'lib', 'node_modules'));
  add(path.resolve(execDir, '..', '..', 'lib', 'node_modules'));

  try {
    add(execFileSync('npm', ['root', '-g'], { encoding: 'utf-8' }).trim());
  } catch {}

  return roots;
}

function resolveGeminiCliCoreRoot() {
  const explicit = process.env.MMS_GEMINI_CLI_CORE_ROOT;
  if (explicit) {
    return path.resolve(explicit);
  }

  const searchRoots = candidateNodeModuleRoots();
  const packageCandidates = [
    '@google/gemini-cli-core/package.json',
    '@google/gemini-cli/package.json',
  ];

  for (const request of packageCandidates) {
    const pathOptions = searchRoots.length ? searchRoots : undefined;
    try {
      const pkgPath = require.resolve(request, pathOptions ? { paths: pathOptions } : undefined);
      if (request.includes('gemini-cli-core')) {
        return path.dirname(pkgPath);
      }
      return path.join(path.dirname(pkgPath), 'node_modules', '@google', 'gemini-cli-core');
    } catch {}
  }

  throw new Error(
    'Cannot resolve @google/gemini-cli-core. Install gemini-cli globally or set MMS_GEMINI_CLI_CORE_ROOT.',
  );
}

async function loadGeminiCliCore() {
  const coreRoot = resolveGeminiCliCoreRoot();
  const oauth2 = await import(pathToFileURL(path.join(coreRoot, 'dist/src/code_assist/oauth2.js')).href);
  const setup = await import(pathToFileURL(path.join(coreRoot, 'dist/src/code_assist/setup.js')).href);
  const server = await import(pathToFileURL(path.join(coreRoot, 'dist/src/code_assist/server.js')).href);
  const generator = await import(pathToFileURL(path.join(coreRoot, 'dist/src/core/contentGenerator.js')).href);
  return {
    getOauthClient: oauth2.getOauthClient,
    setupUser: setup.setupUser,
    CodeAssistServer: server.CodeAssistServer,
    AuthType: generator.AuthType,
  };
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf-8');
}

function createConfig() {
  return {
    getProxy() {
      return undefined;
    },
    isBrowserLaunchSuppressed() {
      return false;
    },
    getAcpMode() {
      return false;
    },
    getValidationHandler() {
      return undefined;
    },
    getBillingSettings() {
      return { overageStrategy: 'STOP' };
    },
    getCreditsNotificationShown() {
      return true;
    },
    setCreditsNotificationShown() {},
  };
}

async function main() {
  const [accountHome] = process.argv.slice(2);
  if (!accountHome) {
    throw new Error('missing account home');
  }
  process.env.GEMINI_CLI_HOME = accountHome;
  const { getOauthClient, setupUser, CodeAssistServer, AuthType } = await loadGeminiCliCore();
  const raw = await readStdin();
  const payload = JSON.parse(raw || '{}');
  const cfg = createConfig();
  const client = await getOauthClient(AuthType.LOGIN_WITH_GOOGLE, cfg);
  const user = await setupUser(client, undefined, {});
  const server = new CodeAssistServer(
    client,
    user.projectId,
    {},
    `mms-${randomUUID()}`,
    user.userTier,
    user.userTierName,
    user.paidTier,
    cfg,
  );
  const response = await server.generateContent(
    payload,
    `mms-${randomUUID()}`,
  );
  process.stdout.write(JSON.stringify(response));
}

main().catch((error) => {
  const message = error && typeof error === 'object'
    ? JSON.stringify({
        message: error.message,
        status: error.status,
        code: error.code,
        response: error.response?.data,
      })
    : String(error);
  process.stderr.write(message);
  process.exit(1);
});
