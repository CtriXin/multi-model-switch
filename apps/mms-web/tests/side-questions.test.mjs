import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  btwSeenStorageKey,
  contextScopeLine,
  defaultExpanded,
  isInFlight,
  isSettled,
  makeBtwChoiceKey,
  mergeSideQuestions,
  readBtwCommand,
  readBtwSeen,
  resolveCardExpanded,
  routeLine,
  saveBtwSeen,
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

test('resolveCardExpanded honors explicit choices, default-expanding unseen settled and in-flight cards', () => {
  const settled = row({ btwId: 'btw-settled', status: 'completed' });
  const inFlight = row({ btwId: 'btw-inflight', status: 'running' });

  // 1. Unseen cards (choices empty or missing key): default expanded (true)
  assert.equal(resolveCardExpanded(settled, {}, 's-1'), true, 'unseen settled card defaults to expanded');
  assert.equal(resolveCardExpanded(inFlight, {}, 's-1'), true, 'unseen in-flight card defaults to expanded');

  // 2. Explicitly folded (choice is false): returns false
  const foldedChoices = { 's-1|btw-settled': false, 's-1|btw-inflight': false };
  assert.equal(resolveCardExpanded(settled, foldedChoices, 's-1'), false, 'explicitly folded settled card is collapsed');
  assert.equal(resolveCardExpanded(inFlight, foldedChoices, 's-1'), false, 'explicitly folded in-flight card is collapsed');

  // 3. Explicitly unfolded (choice is true): returns true
  const unfoldedChoices = { 's-1|btw-settled': true, 's-1|btw-inflight': true };
  assert.equal(resolveCardExpanded(settled, unfoldedChoices, 's-1'), true, 'explicitly opened settled card is expanded');
  assert.equal(resolveCardExpanded(inFlight, unfoldedChoices, 's-1'), true, 'explicitly opened in-flight card is expanded');

  // 4. Session isolation: choices for another session do not affect current session
  const otherSessionChoices = { 'other-session|btw-settled': false };
  assert.equal(resolveCardExpanded(settled, otherSessionChoices, 's-1'), true, 'unaffected by choices from other sessions');
});

test('SideQuestions.tsx enforces seen semantics without activeIds or position heuristics', () => {
  const componentPath = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    '../src/SideQuestions.tsx',
  );
  const code = fs.readFileSync(componentPath, 'utf8');

  // Must call resolveCardExpanded
  assert.ok(
    code.includes('resolveCardExpanded'),
    'SideQuestions.tsx must use resolveCardExpanded to determine card expansion',
  );

  // Must NOT contain position-based guess heuristics
  assert.ok(
    !code.includes('rows.length - 1'),
    'SideQuestions.tsx must not guess seen state from array index/newest position',
  );

  // Must NOT contain activeIds ref or in-flight mount sniffing
  assert.ok(
    !code.includes('activeIds'),
    'SideQuestions.tsx must not use activeIds to guess user seen state',
  );

  // Must NOT force-settle seen on session switch
  assert.ok(
    !code.includes('lastSessionId'),
    'SideQuestions.tsx must not force-settle seen on session switch',
  );
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

test('a card is open while answering, whatever its place in the list', () => {
 assert.equal(defaultExpanded(row({ status: 'running' })), true);
 assert.equal(defaultExpanded(row({ status: 'accepted' })), true);
});

test('an unseen question stays open until seen, while seen settled questions fold', () => {
 for (const status of ['completed', 'failed', 'cancelled', 'uncertain']) {
  assert.equal(defaultExpanded(row({ status }), false), true, `unseen ${status}`);
  assert.equal(defaultExpanded(row({ status }), true), false, `seen ${status}`);
 }
 for (const status of ['prepared', 'accepted', 'running']) {
  assert.equal(defaultExpanded(row({ status }), false), true, `unseen in-flight ${status}`);
  assert.equal(defaultExpanded(row({ status }), true), true, `seen in-flight ${status}`);
 }
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
 assert.equal(
  sourceLabel(row({ source: 'completion', runner: 'pi-extension' })),
  'Pi 扩展',
 );
 // Rows persisted before the runner field existed still read as host answers.
 assert.equal(sourceLabel(row({ source: 'completion', runner: undefined })), '只读旁问模型');
});

test('the context scope line reports what each runner saw', () => {
 assert.equal(
  contextScopeLine(row({ source: 'completion', runner: 'pi-extension', contextScope: { mode: 'branch', entries: 7, truncated: false } })),
  '主会话分支 7 条',
 );
 assert.equal(
  contextScopeLine(row({ source: 'completion', contextScope: { recentTurns: 4, totalTurns: 9, truncated: true } })),
  '最近 4 轮 · 共 9 轮 · 已截断',
 );
 assert.equal(contextScopeLine(row({ contextScope: null })), '');
 assert.equal(contextScopeLine(row({})), '');
 assert.equal(contextScopeLine(row({ contextScope: { mode: 'branch' } })), '');
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
 const answered = { source: 'completion', startedAt: '2026-09-11T10:00:00', answer: '答完了' };
 assert.equal(routeLine(row({ ...answered, routeSnapshot: { modelName: 'k3', providerName: '', channel: 'x' } })), 'k3 · x');
 assert.equal(routeLine(row({ ...answered, routeSnapshot: undefined })), '');
});

test('a model is named only when one actually answered', () => {
 const snapshot = { modelName: 'k3', providerName: 'p', channel: 'c' };
 // Answered from the session snapshot: no model was asked.
 assert.equal(routeLine(row({ source: 'state', routeSnapshot: snapshot })), '');
 // Failed closed: nothing was sent, so nothing may be credited.
 assert.equal(routeLine(row({
  source: 'completion', status: 'failed', answer: null, startedAt: null,
  error: '没有可用路由', routeSnapshot: snapshot,
 })), '');
 // A real answer names the route it came from.
 assert.equal(routeLine(row({
  source: 'completion', startedAt: '2026-09-11T10:00:00', answer: '在跑测试。', routeSnapshot: snapshot,
 })), 'k3 · p · c');
});

test('makeBtwChoiceKey formats key with or without sessionId', () => {
 assert.equal(makeBtwChoiceKey('session-1', 'btw-42'), 'session-1|btw-42');
 assert.equal(makeBtwChoiceKey(undefined, 'btw-42'), 'btw-42');
 assert.equal(makeBtwChoiceKey('', 'btw-42'), 'btw-42');
});

test('readBtwSeen and saveBtwSeen safely serialize and deserialize choices', () => {
 const store = {};
 const mockStorage = {
  getItem(k) { return store[k] || null; },
  setItem(k, v) { store[k] = String(v); },
 };

 assert.deepEqual(readBtwSeen(mockStorage), {});

 saveBtwSeen({ 's1|b1': false, 's1|b2': true }, mockStorage);
 assert.deepEqual(readBtwSeen(mockStorage), { 's1|b1': false, 's1|b2': true });

 // Overwrites / updates
 saveBtwSeen({ 's1|b1': true }, mockStorage);
 assert.deepEqual(readBtwSeen(mockStorage), { 's1|b1': true });
});

test('readBtwSeen handles malformed, missing, and throwing storage gracefully', () => {
 assert.deepEqual(readBtwSeen(undefined), {});

 const badStorage = {
  getItem() { return 'not valid json {{{'; },
 };
 assert.deepEqual(readBtwSeen(badStorage), {});

 const throwingStorage = {
  getItem() { throw new Error('security error in private browsing'); },
 };
 assert.deepEqual(readBtwSeen(throwingStorage), {});

 const nonBooleanStorage = {
  getItem() { return JSON.stringify({ valid: false, badNum: 123, badStr: 'true', badObj: {} }); },
 };
 assert.deepEqual(readBtwSeen(nonBooleanStorage), { valid: false });
});

test('saveBtwSeen handles throwing storage and caps to 1000 items', () => {
 const store = {};
 const mockStorage = {
  getItem(k) { return store[k] || null; },
  setItem(k, v) { store[k] = String(v); },
 };

 const bigMap = {};
 for (let i = 0; i < 1200; i++) {
  bigMap[`s|b${i}`] = i % 2 === 0;
 }
 saveBtwSeen(bigMap, mockStorage);
 const readBack = readBtwSeen(mockStorage);
 assert.equal(Object.keys(readBack).length, 1000);
 // First 200 were sliced off, newest 1000 kept
 assert.equal(readBack['s|b0'], undefined);
 assert.equal(readBack['s|b1199'], false);

 const throwingStorage = {
  setItem() { throw new Error('QuotaExceededError'); },
 };
 assert.doesNotThrow(() => saveBtwSeen({ 's|b': true }, throwingStorage));
});

test('readBtwSeen and saveBtwSeen never throw even if global localStorage getter throws SecurityError', () => {
  const hadWindow = 'window' in globalThis;
  const originalWindow = globalThis.window;

  try {
    const mockWindow = {};
    Object.defineProperty(mockWindow, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('SecurityError: The operation is insecure.');
      },
    });
    globalThis.window = mockWindow;

    assert.doesNotThrow(() => {
      const res = readBtwSeen();
      assert.deepEqual(res, {});
    });

    assert.doesNotThrow(() => {
      saveBtwSeen({ 's|b': false });
    });
  } finally {
    if (hadWindow) {
      globalThis.window = originalWindow;
    } else {
      delete globalThis.window;
    }
  }
});

test('resolveCardExpanded and storage lifecycle form an end-to-end contract that resists position heuristics and lost persistence', () => {
  const row0 = row({ btwId: 'btw-0', question: '第一条旁问' });
  const row1 = row({ btwId: 'btw-1', question: '第二条旁问' });
  const rows = [row0, row1];

  // Resistance to Mutation 1: Persistence removed (e.g. storage never consulted, empty state)
  // Given storage containing persisted choices: card 0 folded, card 1 opened
  const storageMap = { 'session-1|btw-0': false, 'session-1|btw-1': true };
  const mockStore = {
    [btwSeenStorageKey]: JSON.stringify(storageMap),
  };
  const mockStorage = {
    getItem(k) { return mockStore[k] || null; },
    setItem(k, v) { mockStore[k] = String(v); },
  };

  const choicesFromStorage = readBtwSeen(mockStorage);
  assert.deepEqual(choicesFromStorage, storageMap, 'readBtwSeen must restore persisted record');

  // If choices are correctly passed from storage, card 0 is collapsed and card 1 is expanded
  assert.equal(
    resolveCardExpanded(rows[0], choicesFromStorage, 'session-1'),
    false,
    'persisted fold must be respected for card 0',
  );
  assert.equal(
    resolveCardExpanded(rows[1], choicesFromStorage, 'session-1'),
    true,
    'persisted expand must be respected for card 1',
  );

  // If someone mutated to useState({}) ignoring storage, card 0 would falsely auto-expand:
  const brokenChoices = {};
  assert.notEqual(
    resolveCardExpanded(rows[0], brokenChoices, 'session-1'),
    resolveCardExpanded(rows[0], choicesFromStorage, 'session-1'),
    'empty choices without persistence fails to maintain fold',
  );

  // Resistance to Mutation 2: Position heuristic (e.g. index + 1 === rows.length ? true : false)
  // Under seen semantics:
  // Card 0 (index 0, older question) with NO user choices MUST be expanded (true)
  assert.equal(
    resolveCardExpanded(rows[0], {}, 'session-1'),
    true,
    'unseen older card (index 0) must auto-expand, never collapsed by position',
  );
  // Card 1 (index 1, newest question) with user choice false MUST be collapsed (false)
  assert.equal(
    resolveCardExpanded(rows[1], { 'session-1|btw-1': false }, 'session-1'),
    false,
    'folded newest card (index 1) must remain collapsed, never forced open by position',
  );

  // Simulated toggleExpanded writes back to storage
  const nextChoices = { ...choicesFromStorage, 'session-1|btw-0': true };
  saveBtwSeen(nextChoices, mockStorage);
  const updatedFromStorage = readBtwSeen(mockStorage);
  assert.equal(updatedFromStorage['session-1|btw-0'], true, 'toggleExpanded updates persisted state');
});

test('SideQuestions.tsx enforces persistence wiring and strictly bans position heuristics in JSX', () => {
  const componentPath = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    '../src/SideQuestions.tsx',
  );
  const code = fs.readFileSync(componentPath, 'utf8');

  // 1. Must wire up readBtwSeen in useState initialization (mutation resistance: useState(readBtwSeen))
  assert.ok(
    code.includes('useState<Record<string, boolean>>(readBtwSeen)') || code.includes('useState(readBtwSeen)'),
    'SideQuestions.tsx must initialize choices with readBtwSeen',
  );

  // 2. Must persist choices on change via saveBtwSeen(choices)
  assert.ok(
    code.includes('saveBtwSeen(choices)'),
    'SideQuestions.tsx must persist choices via saveBtwSeen(choices)',
  );

  // 3. Must pass expanded directly via isExpanded(row), completely banning rows.length or index based heuristics
  assert.ok(
    code.includes('expanded={isExpanded(row)}'),
    'SideQuestions.tsx must pass expanded={isExpanded(row)} directly to Card',
  );
  assert.ok(
    !code.includes('rows.length - 1') &&
    !code.includes('index === rows.length') &&
    !code.includes('index + 1 === rows.length'),
    'SideQuestions.tsx must not use position/index heuristics for card expansion',
  );
  assert.ok(
    !code.includes('activeIds'),
    'SideQuestions.tsx must not use activeIds',
  );
  assert.ok(
    !code.includes('lastSessionId'),
    'SideQuestions.tsx must not use lastSessionId',
  );
});


