import test from 'node:test';
import assert from 'node:assert/strict';
import { modelKey, selectModelRoute } from '../src/modelSelection.ts';
const route = (provider, available = true, model = 'MiniMax-M3') => ({id: `${provider}/${model}`, modelId: `${provider}:${model}`, providerId: provider, name: model, available});

test('groups provider-qualified routes by actual model identity', () => {
 assert.equal(modelKey(route('first')), modelKey(route('second')));
 assert.notEqual(modelKey(route('first')), modelKey(route('first', true, 'MiniMax-M2.7')));
});
test('honors preferred route before favorites and keeps original fallback order', () => {
 const a=route('first'), b=route('second'), c=route('third');
 assert.equal(selectModelRoute([a,b,c],[a.modelId],{[b.id]:{preferred:true}}),b);
 assert.equal(selectModelRoute([a,b,c],[c.modelId],{}),c);
 assert.equal(selectModelRoute([a,b,c],[],{}),a);
});
test('reselecting current model preserves its explicit route and avoids an effort-resetting switch', () => {
 const a=route('first'), b=route('second');
 assert.equal(selectModelRoute([a,b],[],{[a.id]:{preferred:true}},b.id),b);
 assert.equal(selectModelRoute([a,b],[],{[a.id]:{preferred:true}},'different-model'),a);
});
test('unavailable routes never outrank available ones; all-unavailable stays disabled', () => {
 const a=route('first',false), b=route('second');
 assert.equal(selectModelRoute([a,b],[a.modelId],{[a.id]:{preferred:true}},a.id),b);
 assert.equal(selectModelRoute([a],[],{}).available,false);
});
