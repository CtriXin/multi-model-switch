import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { deliveryLabel } from '../src/message-control.ts';

const transcript = readFileSync(new URL('../src/Transcript.tsx', import.meta.url), 'utf8');

test('a late delete stays in the conversation and still shows its delivery label', () => {
  const pendingLine = transcript.split('\n').find((line) => line.includes('const pending = '));
  assert.ok(pendingLine, 'pending filter must exist');
  assert.equal(pendingLine.includes('delivered'), false, 'delivered messages are not "未执行的消息"');
  assert.match(transcript, /aria-label="未执行的消息"/);

  const turn = transcript.slice(
    transcript.indexOf('function Turn('),
    transcript.indexOf('export function Transcript'),
  );
  assert.match(turn, /deliveryLabel\(user\)/);
  assert.match(turn, /className="delivery-note"/);
  assert.match(turn, /<EventView[^>]*event=\{user\}/);

  const label = deliveryLabel({ status: 'delivered', mode: 'steer', lateCancel: true });
  assert.equal(label, '已送给模型 · 删除来晚了');
  assert.notEqual(label, '');
});
