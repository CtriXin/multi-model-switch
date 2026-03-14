import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import process from 'node:process';

import { getOauthClient } from '/Users/xin/.nvm/versions/node/v22.19.0/lib/node_modules/@google/gemini-cli/node_modules/@google/gemini-cli-core/dist/src/code_assist/oauth2.js';
import { setupUser } from '/Users/xin/.nvm/versions/node/v22.19.0/lib/node_modules/@google/gemini-cli/node_modules/@google/gemini-cli-core/dist/src/code_assist/setup.js';
import { CodeAssistServer } from '/Users/xin/.nvm/versions/node/v22.19.0/lib/node_modules/@google/gemini-cli/node_modules/@google/gemini-cli-core/dist/src/code_assist/server.js';
import { AuthType } from '/Users/xin/.nvm/versions/node/v22.19.0/lib/node_modules/@google/gemini-cli/node_modules/@google/gemini-cli-core/dist/src/core/contentGenerator.js';

console.log = () => {};
console.info = () => {};

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
