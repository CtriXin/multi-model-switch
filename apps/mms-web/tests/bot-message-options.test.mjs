import test from "node:test";
import assert from "node:assert/strict";
import { parseMessageOptions } from "../src/bot-presets.ts";

test("parseMessageOptions extracts quick options from user screenshot example", () => {
  const text = `不行。当前会话绑定的就是我（MiniMax-M3），模型/账号配置不能由我擅自切换；要在 Web UI 的 Bot 配置里改。如果你只想让我用 DeepSeek 风格回答风格，我可以照做，但底层模型仍是我。要我按 DeepSeek 风格回复吗？

选项：要 | 不要`;

  const parsed = parseMessageOptions(text);
  assert.deepEqual(parsed.options, ["要", "不要"]);
  assert.equal(
    parsed.body,
    "不行。当前会话绑定的就是我（MiniMax-M3），模型/账号配置不能由我擅自切换；要在 Web UI 的 Bot 配置里改。如果你只想让我用 DeepSeek 风格回答风格，我可以照做，但底层模型仍是我。要我按 DeepSeek 风格回复吗？",
  );
  assert.equal(parsed.suggestsConfig, true);
});

test("parseMessageOptions handles full-width punctuation and comma/ideographic comma", () => {
  const t1 = "请选择推进方式：\n选项：直接顺延、先给建议、灵活决策";
  const p1 = parseMessageOptions(t1);
  assert.deepEqual(p1.options, ["直接顺延", "先给建议", "灵活决策"]);
  assert.equal(p1.body, "请选择推进方式：");

  const t2 = "请问是否确认？\n可选项：开启，关闭";
  const p2 = parseMessageOptions(t2);
  assert.deepEqual(p2.options, ["开启", "关闭"]);

  const t3 = "普通没有选项的回复。\n第二行依然正常。";
  const p3 = parseMessageOptions(t3);
  assert.deepEqual(p3.options, []);
  assert.equal(p3.body, t3);
  assert.equal(p3.suggestsConfig, false);
});
