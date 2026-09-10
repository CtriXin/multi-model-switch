import test from "node:test";
import assert from "node:assert/strict";
import { newRequestId } from "../../apps/mms-web/src/request-id.ts";

const shape = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

test("a secure context keeps using the platform's own generator", () => {
  const calls: number[] = [];
  const native = crypto.randomUUID.bind(crypto);
  (crypto as { randomUUID: () => string }).randomUUID = () => {
    calls.push(1);
    return native();
  };
  try {
    assert.match(newRequestId(), shape);
    assert.equal(calls.length, 1);
  } finally {
    (crypto as { randomUUID: () => string }).randomUUID = native;
  }
});

test("a plain-http origin has no randomUUID, and still gets a usable id", () => {
  // This is the whole point: on http://192.168.x.x the property is absent, and
  // reading through it used to throw before any request left the page.
  const native = crypto.randomUUID;
  delete (crypto as { randomUUID?: unknown }).randomUUID;
  try {
    const ids = new Set<string>();
    for (let index = 0; index < 500; index += 1) {
      const id = newRequestId();
      assert.match(id, shape);
      ids.add(id);
    }
    assert.equal(ids.size, 500, "ids must not repeat: they are idempotency keys");
  } finally {
    (crypto as { randomUUID?: unknown }).randomUUID = native;
  }
});

test("the fallback id is accepted by the server's requestId pattern", () => {
  // mms_web/sessions.py: ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$
  const server = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
  const native = crypto.randomUUID;
  delete (crypto as { randomUUID?: unknown }).randomUUID;
  try {
    for (let index = 0; index < 50; index += 1) {
      assert.match(newRequestId(), server);
    }
  } finally {
    (crypto as { randomUUID?: unknown }).randomUUID = native;
  }
});
