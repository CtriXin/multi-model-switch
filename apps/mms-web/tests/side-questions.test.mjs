import test from 'node:test';
import assert from 'node:assert/strict';
import {
 defaultExpanded,
 isInFlight,
 isSettled,
 mergeSideQuestions,
 readBtwCommand,
 routeLine,
 sourceLabel,
 statusLabel,
 summaryLine,
 upsertSideQuestion,
} from '../src/side-questions.ts';

const row = (over = {}) => ({
 btwId: 'btw-1',
 mainSessionId: 's-1',
 question: '现在进行到哪一步了？',
 status: 'completed',
 answer: '当前正在运行。',
 source: 'state',
 contextRevision: 'r-12',
 error: null,
 createdAt: '2026-09-11T10:00:00',
 startedAt: '2026-09-11T10:00:00',
 completedAt: '2026-09-11T10:00:01',
 ...over,
});

test('only the four final statuses count as settled', () => {
 for (const status of ['completed', 'failed', 'cancelled', 'uncertain']) {
  assert.equal(isSettled(row({ status })), true);
  assert.equal(isInFlight(row({ status })), false);
 }
 for (const status of ['prepared', 'accepted', 'running']) {
  assert.equal(isSettled(row({ status })), false);
  assert.equal(isInFlight(row({ status })), true);
 }
});

test('a card is open while answering and folded once it settles', () => {
 assert.equal(defaultExpanded(row({ status: 'running' })), true);
 assert.equal(defaultExpanded(row({ status: 'accepted' })), true);
 assert.equal(defaultExpanded(row({ status: 'completed' })), false);
 assert.equal(defaultExpanded(row({ status: 'failed' })), false);
 assert.equal(defaultExpanded(row({ status: 'cancelled' })), false);
});

test('bare /btw opens the input and /btw with text asks', () => {
 assert.deepEqual(readBtwCommand(''), { kind: 'compose' });
 assert.deepEqual(readBtwCommand('   '), { kind: 'compose' });
 assert.deepEqual(readBtwCommand('  在等审批吗？ '), {
  kind: 'ask',
  question: '在等审批吗？',
 });
});

test('merging keeps a question the session detail has not caught up with', () => {
 const local = [row({ btwId: 'btw-new', status: 'accepted', answer: null })];
 const merged = mergeSideQuestions([], local);
 assert.equal(merged.length, 1);
 assert.equal(merged[0].btwId, 'btw-new');
});

test('merging never walks a finished answer back to generating', () => {
 const settled = row({ status: 'completed', answer: '答完了' });
 const stale = row({ status: 'running', answer: null });
 assert.equal(mergeSideQuestions([stale], [settled])[0].status, 'completed');
 assert.equal(mergeSideQuestions([settled], [stale])[0].status, 'completed');
});

test('the server wins when both copies are equally far along', () => {
 const server = row({ answer: '服务端的回答' });
 const local = row({ answer: '本地旧副本' });
 assert.equal(mergeSideQuestions([server], [local])[0].answer, '服务端的回答');
});

test('merged rows are ordered oldest first and never collapse two questions', () => {
 const first = row({ btwId: 'btw-a', createdAt: '2026-09-11T10:00:00' });
 const second = row({ btwId: 'btw-b', createdAt: '2026-09-11T10:05:00' });
 const merged = mergeSideQuestions([second, first], []);
 assert.deepEqual(merged.map((r) => r.btwId), ['btw-a', 'btw-b']);
});

test('upsert appends a new row and refuses a backwards update', () => {
 const rows = [row({ status: 'running', answer: null })];
 const added = upsertSideQuestion(rows, row({ btwId: 'btw-2', status: 'accepted' }));
 assert.deepEqual(added.map((r) => r.btwId), ['btw-1', 'btw-2']);
 const forward = upsertSideQuestion(rows, row({ status: 'completed' }));
 assert.equal(forward[0].status, 'completed');
 const backward = upsertSideQuestion(forward, row({ status: 'running', answer: null }));
 assert.equal(backward[0].status, 'completed');
});

test('each status has its own visible word and tone', () => {
 assert.deepEqual(statusLabel(row({ status: 'completed' })), { text: '已回答', tone: 'done' });
 assert.deepEqual(statusLabel(row({ status: 'failed' })), { text: '未回答', tone: 'error' });
 assert.deepEqual(statusLabel(row({ status: 'cancelled' })), { text: '已取消', tone: 'cancelled' });
 assert.deepEqual(statusLabel(row({ status: 'uncertain' })), { text: '结果未知', tone: 'unknown' });
 assert.equal(statusLabel(row({ status: 'running' })).tone, 'running');
 assert.equal(statusLabel(row({ status: 'accepted' })).tone, 'running');
});

test('the answer source is named, never guessed', () => {
 assert.equal(sourceLabel(row({ source: 'state' })), 'Pilot 状态');
 assert.equal(sourceLabel(row({ source: 'completion' })), '只读旁问模型');
});

test('an unfinished question says so instead of showing an empty line', () => {
 assert.match(summaryLine(row({ status: 'running', answer: null })), /主任务继续运行/);
 assert.equal(summaryLine(row({ status: 'cancelled', answer: null, error: null })), '');
});

test('a long answer is clipped for the folded row', () => {
 const long = summaryLine(row({ answer: 'x'.repeat(400) }), 120);
 assert.equal(long.length, 121);
 assert.ok(long.endsWith('…'));
});

test('a failure shows its reason on the folded row', () => {
 const failed = row({ status: 'failed', answer: null, error: '当前环境没有可用的只读旁问模型。' });
 assert.equal(summaryLine(failed), '当前环境没有可用的只读旁问模型。');
});

test('the route line skips the parts the snapshot did not carry', () => {
 assert.equal(routeLine(row({ routeSnapshot: { modelName: 'k3', providerName: '', channel: 'x' } })), 'k3 · x');
 assert.equal(routeLine(row({ routeSnapshot: undefined })), '');
});
