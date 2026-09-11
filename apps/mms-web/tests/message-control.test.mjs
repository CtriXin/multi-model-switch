import test from 'node:test';
import assert from 'node:assert/strict';
import {
 availableSendModes,
 deliveryLabel,
 moveTarget,
 readQueue,
 resolveSendMode,
 steerBadge,
 steerLinks,
} from '../src/message-control.ts';

const modes = (running, caps) => availableSendModes(running, caps).map(o => o.mode);

test('an idle session sends directly and offers nothing else', () => {
 assert.deepEqual(modes(false, { steer: true }), ['direct']);
 assert.deepEqual(modes(false), ['direct']);
});

test('a running session queues, and only offers steering when the service takes it', () => {
 assert.deepEqual(modes(true), ['followUp']);
 assert.deepEqual(modes(true, {}), ['followUp']);
 assert.deepEqual(modes(true, { steer: false }), ['followUp']);
 assert.deepEqual(modes(true, { steer: true }), ['followUp', 'steer']);
});

test('a steer the service cannot deliver falls back to the queue instead of being sent anyway', () => {
 assert.equal(resolveSendMode('steer', true, { steer: true }), 'steer');
 assert.equal(resolveSendMode('steer', true, {}), 'followUp');
 assert.equal(resolveSendMode('steer', false, { steer: true }), 'direct');
 assert.equal(resolveSendMode(undefined, true, { steer: true }), 'followUp');
 assert.equal(resolveSendMode(undefined, false), 'direct');
});

test('queued messages with ids can be managed only when the service serves /queue', () => {
 const runtime = {
  pendingMessageCount: 2,
  pending: [
   { id: 'q1', text: '先补一段说明', mode: 'followUp' },
   { id: 'q2', text: '改用另一个文件', mode: 'steer' },
  ],
 };
 const managed = readQueue(runtime, { queueControl: true });
 assert.deepEqual(managed.items.map(i => i.id), ['q1', 'q2']);
 assert.deepEqual(managed.items.map(i => i.mode), ['followUp', 'steer']);
 assert.equal(managed.manageable, true);
 assert.equal(managed.note, '');

 const unmanaged = readQueue(runtime, {});
 assert.equal(unmanaged.items.length, 2);
 assert.equal(unmanaged.manageable, false);
 assert.match(unmanaged.note, /只能整队清空/);
});

test('a service that reports only queue text is read, not edited', () => {
 const view = readQueue({ pendingMessageCount: 2, queue: ['一', '二'] }, { queueControl: true });
 assert.deepEqual(view.items.map(i => i.text), ['一', '二']);
 assert.deepEqual(view.items.map(i => i.mode), ['followUp', 'followUp']);
 assert.equal(view.manageable, false);
 assert.match(view.note, /没有逐条编号/);
});

test('messages the service counted but did not list are still shown as waiting', () => {
 assert.equal(readQueue({ pendingMessageCount: 5, queue: ['一'] }).unlisted, 4);
 assert.equal(readQueue({ pendingMessageCount: 1, pending: [{ id: 'q1', text: '一', mode: 'followUp' }] }).unlisted, 0);
 assert.equal(readQueue({ pendingMessageCount: 2 }).unlisted, 2);
});

test('an empty queue produces no list and no explanation', () => {
 const view = readQueue({}, { queueControl: true });
 assert.deepEqual(view.items, []);
 assert.equal(view.manageable, false);
 assert.equal(view.note, '');
 assert.equal(view.unlisted, 0);
});

test('malformed queue entries are dropped rather than rendered as blanks', () => {
 const view = readQueue({ pending: [{ id: 'q1', text: '一', mode: 'followUp' }, { text: '无 id' }, null] }, { queueControl: true });
 assert.deepEqual(view.items.map(i => i.id), ['q1']);
});

test('a queued message moves one step and stops at the ends', () => {
 const items = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
 assert.deepEqual(moveTarget(items, 'b', -1), { id: 'b', toIndex: 0 });
 assert.deepEqual(moveTarget(items, 'b', 1), { id: 'b', toIndex: 2 });
 assert.equal(moveTarget(items, 'a', -1), null);
 assert.equal(moveTarget(items, 'c', 1), null);
 assert.equal(moveTarget(items, 'missing', 1), null);
});

test('a queued message says when it will be delivered, by the mode it was sent with', () => {
 assert.match(deliveryLabel({ status: 'queued', mode: 'steer' }), /当前这批工具调用结束后送达/);
 assert.match(deliveryLabel({ status: 'queued', mode: 'followUp' }), /本轮结束后送达/);
 assert.equal(deliveryLabel({ status: 'queued' }), '排队中，尚未执行');
});

test('a message that never ran says so, and an unconfirmed send is not called delivered', () => {
 assert.equal(deliveryLabel({ status: 'cancelled', mode: 'steer' }), '已取消，未执行');
 assert.equal(deliveryLabel({ status: 'error', mode: 'steer' }), '发送失败，未执行');
 assert.equal(deliveryLabel({ status: 'queued', mode: 'steer', contextUsage: { state: 'uncertain' } }), '发送结果待确认');
 assert.equal(deliveryLabel({ status: 'done', mode: 'followUp' }), '');
});

test('the service is believed about which answer a steer changed', () => {
 const links = steerLinks([
  { id: 'u1', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:30Z' },
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:00:00Z', steeredBy: ['u1'] },
 ]);
 assert.deepEqual(links, [{ assistantId: 'a1', steerIds: ['u1'], confirmed: true }]);
 assert.match(steerBadge(links[0]), /按你的引导调整过/);
});

test('without the service saying so, the page claims only what the timeline proves', () => {
 const links = steerLinks([
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:00:00Z', status: 'running' },
  { id: 'u1', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:30Z', status: 'queued' },
 ]);
 assert.deepEqual(links, [{ assistantId: 'a1', steerIds: ['u1'], confirmed: false }]);
 assert.match(steerBadge(links[0]), /生成过程中收到你的引导/);
 assert.doesNotMatch(steerBadge(links[0]), /调整过/);
});

test('an answer that was already finished is not blamed on a later steer', () => {
 assert.deepEqual(steerLinks([
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:00:00Z', updatedAt: '2026-09-11T10:00:10Z', status: 'done' },
  { id: 'u1', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:30Z' },
 ]), []);
});

test('a steer that never reached the session marks nothing', () => {
 const events = mode => [
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:00:00Z', status: 'running' },
  { id: 'u1', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:30Z', status: mode },
 ];
 assert.deepEqual(steerLinks(events('cancelled')), []);
 assert.deepEqual(steerLinks(events('error')), []);
});

test('an ordinary follow-up never marks an answer', () => {
 assert.deepEqual(steerLinks([
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:00:00Z', status: 'running' },
  { id: 'u1', kind: 'user', mode: 'followUp', createdAt: '2026-09-11T10:00:30Z', status: 'queued' },
  { id: 'u2', kind: 'user', createdAt: '2026-09-11T10:00:40Z', status: 'queued' },
 ]), []);
});

test('two steers into the same answer are counted, not stacked as separate notes', () => {
 const links = steerLinks([
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:00:00Z', status: 'running' },
  { id: 'u1', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:30Z' },
  { id: 'u2', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:40Z' },
 ]);
 assert.equal(links.length, 1);
 assert.deepEqual(links[0].steerIds, ['u1', 'u2']);
 assert.match(steerBadge(links[0]), /2 条/);
});

test('a steer lands in the answer that was open, not the one before it', () => {
 const links = steerLinks([
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:00:00Z', updatedAt: '2026-09-11T10:00:10Z', status: 'done' },
  { id: 'a2', kind: 'assistant', createdAt: '2026-09-11T10:00:20Z', status: 'running' },
  { id: 'u1', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:30Z' },
 ]);
 assert.deepEqual(links.map(l => l.assistantId), ['a2']);
});

test('an answer with no steer carries no badge', () => {
 assert.equal(steerBadge(undefined), '');
});
