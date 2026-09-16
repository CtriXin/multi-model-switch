import test from 'node:test';
import assert from 'node:assert/strict';
import { sendsOnEnter } from '../src/composer-keys.ts';
const key = (key, mods = {}) => ({ key, shiftKey: false, metaKey: false, ctrlKey: false, ...mods });

test('Enter sends and Shift + Enter types while the setting is on', () => {
 assert.equal(sendsOnEnter(key('Enter'), true), true);
 assert.equal(sendsOnEnter(key('Enter', { shiftKey: true }), true), false);
});
test('turning the setting off gives Enter back to the textarea', () => {
 assert.equal(sendsOnEnter(key('Enter'), false), false);
 assert.equal(sendsOnEnter(key('Enter', { shiftKey: true }), false), false);
});
test('the modifier sends in either mode', () => {
 for (const on of [true, false]) {
  assert.equal(sendsOnEnter(key('Enter', { metaKey: true }), on), true);
  assert.equal(sendsOnEnter(key('Enter', { ctrlKey: true }), on), true);
 }
});
test('other keys never send', () => {
 assert.equal(sendsOnEnter(key('a'), true), false);
 assert.equal(sendsOnEnter(key('Escape', { metaKey: true }), false), false);
});
