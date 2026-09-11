import test from 'node:test';
import assert from 'node:assert/strict';
import {
 deliveryLabel,
 moveTarget,
 readQueue,
 steerBadge,
 steerLinks,
 wireMode,
} from '../src/message-control.ts';

test('the page-only "direct" never reaches the service, which rejects it', () => {
 assert.equal(wireMode('direct'), undefined);
 assert.equal(wireMode('followUp'), 'followUp');
 assert.equal(wireMode('steer'), 'steer');
});

test('the queue is read lane by lane, steering first, because that is the delivery order', () => {
 const view = readQueue({
  pendingMessageCount: 3,
  queue: ['改用另一个文件', '先补一段说明', '最后总结'],
  queueSteering: ['改用另一个文件'],
  queueFollowUp: ['先补一段说明', '最后总结'],
 });
 assert.deepEqual(view.items.map(i => i.mode), ['steer', 'followUp', 'followUp']);
 assert.deepEqual(view.items.map(i => i.text), ['改用另一个文件', '先补一段说明', '最后总结']);
 assert.equal(view.manageable, false);
 assert.equal(view.unlisted, 0);
});

test('one empty lane does not hide the other', () => {
 assert.deepEqual(readQueue({ queueSteering: [], queueFollowUp: ['一'] }).items.map(i => i.mode), ['followUp']);
 assert.deepEqual(readQueue({ queueSteering: ['一'], queueFollowUp: [] }).items.map(i => i.mode), ['steer']);
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

test('a service that reports only one flat queue is read, not edited', () => {
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
 const items = ['a', 'b', 'c'].map(id => ({ id, mode: 'followUp' }));
 assert.deepEqual(moveTarget(items, 'b', -1), { id: 'b', toIndex: 0 });
 assert.deepEqual(moveTarget(items, 'b', 1), { id: 'b', toIndex: 2 });
 assert.equal(moveTarget(items, 'a', -1), null);
 assert.equal(moveTarget(items, 'c', 1), null);
 assert.equal(moveTarget(items, 'missing', 1), null);
});

test('a message only moves among its own kind, because lanes fix the rest', () => {
 const items = [
  { id: 's1', mode: 'steer' },
  { id: 'f1', mode: 'followUp' },
  { id: 'f2', mode: 'followUp' },
 ];
 // The only follow-up above f1 is a steer, which is delivered first no matter
 // what the order says, so there is nowhere for f1 to go.
 assert.equal(moveTarget(items, 'f1', -1), null);
 assert.deepEqual(moveTarget(items, 'f1', 1), { id: 'f1', toIndex: 2 });
 assert.equal(moveTarget(items, 's1', 1), null);
});

test('a queued message says when it will be delivered, by the mode it was sent with', () => {
 assert.match(deliveryLabel({ status: 'queued', mode: 'steer' }), /当前这批工具调用结束后送达/);
 assert.match(deliveryLabel({ status: 'queued', mode: 'followUp' }), /本轮结束后送达/);
 assert.equal(deliveryLabel({ status: 'queued' }), '排队中，尚未执行');
});

test('a message that never ran says so, and each way of not running reads differently', () => {
 assert.equal(deliveryLabel({ status: 'cancelled', mode: 'steer' }), '已取消，未执行');
 assert.equal(deliveryLabel({ status: 'interrupted', mode: 'steer' }), '已被停止打断，未执行');
 assert.equal(deliveryLabel({ status: 'failed', mode: 'steer' }), '发送失败，未执行');
 assert.equal(deliveryLabel({ status: 'error', mode: 'steer' }), '发送失败，未执行');
 assert.equal(deliveryLabel({ status: 'queued', mode: 'steer', contextUsage: { state: 'uncertain' } }), '发送结果待确认');
 assert.equal(deliveryLabel({ status: 'delivered', mode: 'followUp' }), '');
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

test('without the service saying so, the page credits the answer that came next', () => {
 const links = steerLinks([
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:00:00Z', status: 'running' },
  { id: 'u1', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:30Z', status: 'queued' },
  { id: 'a2', kind: 'assistant', createdAt: '2026-09-11T10:01:00Z' },
 ]);
 assert.deepEqual(links, [{ assistantId: 'a2', steerIds: ['u1'], confirmed: false }]);
 assert.match(steerBadge(links[0]), /生成过程中收到你的引导/);
 assert.doesNotMatch(steerBadge(links[0]), /调整过/);
});

test('the answer already on screen when the steer was sent is not the one it changed', () => {
 assert.deepEqual(steerLinks([
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:00:00Z', status: 'running' },
  { id: 'u1', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:30Z' },
 ]), []);
});

test('a steer that never reached the session marks nothing', () => {
 const events = mode => [
  { id: 'u1', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:30Z', status: mode },
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:01:00Z' },
 ];
 for (const status of ['cancelled', 'error', 'failed', 'interrupted'])
  assert.deepEqual(steerLinks(events(status)), [], status);
});

test('an ordinary follow-up never marks an answer', () => {
 assert.deepEqual(steerLinks([
  { id: 'u1', kind: 'user', mode: 'followUp', createdAt: '2026-09-11T10:00:30Z', status: 'queued' },
  { id: 'u2', kind: 'user', createdAt: '2026-09-11T10:00:40Z', status: 'queued' },
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:01:00Z' },
 ]), []);
});

test('two steers into the same answer are counted, not stacked as separate notes', () => {
 const links = steerLinks([
  { id: 'u1', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:30Z' },
  { id: 'u2', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:40Z' },
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:01:00Z' },
 ]);
 assert.equal(links.length, 1);
 assert.deepEqual(links[0].steerIds, ['u1', 'u2']);
 assert.match(steerBadge(links[0]), /2 条/);
});

test('a steer credits the first answer after it, not every later one', () => {
 const links = steerLinks([
  { id: 'a1', kind: 'assistant', createdAt: '2026-09-11T10:00:00Z', status: 'done' },
  { id: 'u1', kind: 'user', mode: 'steer', createdAt: '2026-09-11T10:00:30Z' },
  { id: 'a2', kind: 'assistant', createdAt: '2026-09-11T10:00:40Z' },
  { id: 'a3', kind: 'assistant', createdAt: '2026-09-11T10:00:50Z' },
 ]);
 assert.deepEqual(links.map(l => l.assistantId), ['a2']);
});

test('an answer with no steer carries no badge', () => {
 assert.equal(steerBadge(undefined), '');
});
