import test from 'node:test';
import assert from 'node:assert/strict';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import { remarkReadable } from '../src/remarkReadable.ts';
const parser = unified().use(remarkParse).use(remarkGfm).use(remarkReadable);
const parse = (source) => parser.runSync(parser.parse(source), {value:source});

test('repairs observed missing heading space and glued sequential bold list entries', () => {
 const root = parse('###赛道 A\n\n1. **适配** — 已经做了的2. **隔离** — 可以保留的3. **诊断** — 易读\n4. **复用** — 可以分享');
 assert.equal(root.children[0].type,'heading');
 assert.equal(root.children[0].depth,3);
 assert.equal(root.children[0].children[0].value,'赛道 A');
 const items = root.children[1].children;
 assert.equal(items.length,4);
 assert.deepEqual(items.map(i=>i.children[0].children[0].children[0].value),['适配','隔离','诊断','复用']);
});

test('leaves literal syntax, code, escapes, versions and non-sequential numbers intact', () => {
 const samples = [
  '```md\n###原文\n1. **第一**已做2. **第二**\n```',
  '    ###原文\n    1. **第一**已做2. **第二**',
  '\\###原文', '#标签', '#######标题',
  '1. `文本2. **代码**`', '1. 文本3. **非连续**',
  '1. Python 2. **普通说明**', '1. 版本1.2. **版本说明**',
  '1. [文本2. **链接**](https://example.org)',
  '普通句子2. **正文**',
 ];
 for (const source of samples) {
  const plain=unified().use(remarkParse).use(remarkGfm).parse(source);
  assert.deepEqual(parse(source), plain, source);
 }
});

test('preserves CommonMark numbering, GFM tables/tasks and nested lists', () => {
 for(const source of [
  '3. 第三\n4. 第四', '1. 第一\n1. 第二\n1. 第三',
  '|名称|状态|\n|---|---|\n|本地|可用|',
  '- [x] 完成\n- [ ] 等待',
  '1. 第一\n   - 子项\n   - 子项\n2. 第二',
  '## 正常标题\n\n[链接](https://example.org) 和 **加粗**',
 ]) {
  const plain=unified().use(remarkParse).use(remarkGfm).parse(source);
  assert.deepEqual(parse(source), plain, source);
 }
});

test('handles streaming prefixes without mutating original text', () => {
 const source='###赛道 A\n\n1. **适配**已做2. **隔离**保留\n\n```md\n###原文\n```';
 for(let i=0;i<=source.length;i++) assert.doesNotThrow(()=>parse(source.slice(0,i)));
 assert.equal(source.includes('已做2.'),true);
});
