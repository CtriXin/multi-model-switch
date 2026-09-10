import assert from 'node:assert/strict';
import test from 'node:test';

import { productMatchesBrowser } from '../scripts/browser-discovery.mjs';

test('fixed-port fallback only accepts the configured browser product', () => {
  assert.equal(productMatchesBrowser('Chrome/150.0.0.0', 'chrome'), true);
  assert.equal(productMatchesBrowser('Edg/150.0.0.0', 'edge'), true);
  assert.equal(productMatchesBrowser('Chrome/150.0.0.0', 'edge'), false);
  assert.equal(productMatchesBrowser('Edg/150.0.0.0', 'chrome'), false);
  assert.equal(productMatchesBrowser('Chrome/150.0.0.0', 'chrome-canary'), false);
});
