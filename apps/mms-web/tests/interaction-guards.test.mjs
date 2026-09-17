import test from 'node:test';
import assert from 'node:assert/strict';
import { fleetSelectionError } from '../src/bot-fleet.ts';
import { nextEvening } from '../src/bot-schedules.ts';

test('explicit one-family dispatch is rejected but automatic selection and ordinary replies are preserved', () => {
  assert.match(fleetSelectionError({enabled:true, families:['GPT']}), /至少需要 2 家/);
  assert.match(fleetSelectionError({enabled:false, families:['GPT']}, true), /至少需要 2 家/);
  assert.equal(fleetSelectionError({enabled:false, families:['GPT']}), '');
  assert.equal(fleetSelectionError({enabled:true, families:[]}), '');
  assert.equal(fleetSelectionError({enabled:true, families:['GPT','Kimi']}), '');
});
test('evening label and date agree at 20:00 and across month/year boundaries', () => {
  for (const [now, label, expected] of [
    [new Date(2026,8,17,19,59), '今晚 20:00', new Date(2026,8,17,20)],
    [new Date(2026,8,17,20), '明晚 20:00', new Date(2026,8,18,20)],
    [new Date(2026,11,31,23,59), '明晚 20:00', new Date(2027,0,1,20)],
  ]) {
    const result=nextEvening(now);
    assert.equal(result.label,label);assert.equal(result.date.getTime(),expected.getTime());
  }
});
