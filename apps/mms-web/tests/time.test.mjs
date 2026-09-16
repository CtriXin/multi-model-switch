import test from 'node:test';
import assert from 'node:assert/strict';
import { formatDuration, turnDuration } from '../src/time.ts';

test('durations climb through seconds, minutes, hours and days', () => {
 assert.equal(formatDuration(7_000), '7 秒');
 assert.equal(formatDuration(59_400), '59 秒');
 assert.equal(formatDuration(133_000), '2 分 13 秒');
 assert.equal(formatDuration(120_000), '2 分');
 assert.equal(formatDuration(3_840_000), '1 小时 4 分');
 assert.equal(formatDuration(7_200_000), '2 小时');
 assert.equal(formatDuration(97_200_000), '1 天 3 小时');
 assert.equal(formatDuration(172_800_000), '2 天');
});
test('a sub-second reply still reads as a duration, never as an empty label', () => {
 assert.equal(formatDuration(120), '1 秒');
 assert.equal(formatDuration(0), '1 秒');
});
test('a missing or unusable end time hides the duration instead of guessing', () => {
 assert.equal(turnDuration('2026-09-10T04:00:00Z', undefined), '');
 assert.equal(turnDuration(undefined, '2026-09-10T04:00:07Z'), '');
 assert.equal(turnDuration('nonsense', '2026-09-10T04:00:07Z'), '');
 assert.equal(formatDuration(-1_000), '');
});
test('a turn is measured from its first message to the last update of the reply', () => {
 assert.equal(turnDuration('2026-09-10T04:00:00Z', '2026-09-10T04:02:13Z'), '2 分 13 秒');
});
