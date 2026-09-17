import type { Preset } from "./types";

// 对话里换模型的名称匹配。规则与后端 mms_web/bot_executor.py 的
// normalize_model_query / match_presets 相同，两端钉同一份样例
// apps/mms-web/tests/fixtures/model-match-cases.json（后端测试也读它），
// 任何一端漂移都会有一侧测试变红。已知差异：Python 与 JS 的 \s / strip / trim
// 字符集不同，BOM / NEL / FS 这类不可见控制符两端剥法不一致，
// 见 fixture 的 knownDivergent。

export function normalizeModelQuery(value: string) {
  return value.trim().replace(/[吧。！!]+$/, "").toLowerCase().replace(/[\s._:/-]+/g, "");
}

function fieldKey(value: string) {
  return value.toLowerCase().replace(/[\s._:/-]+/g, "");
}

export function availablePresets(presets: Preset[]) {
  return presets.filter((item) => item.harness === "pi" && item.available);
}

export function matchAvailablePresets(query: string, presets: Preset[]) {
  const needle = normalizeModelQuery(query);
  if (!needle) return [] as Preset[];
  return availablePresets(presets).filter((item) =>
    [item.id, item.name, item.modelId, item.channel].some((value) => fieldKey(value).includes(needle)),
  );
}

export type ModelSwitchReply = {
  patch: { pendingPresetId: string } | null;
  message: string;
};

// 匹配不到就问，不要猜：0 条列出可选项，多条返回候选，只有恰好 1 条才切换。
// 切换写成 pendingPresetId，下一轮任务起生效，与后端 model switch 同一语义。
// 命中当前已经在用的模型时不发 patch（避免白扔一整个会话历史）。
export function resolveModelSwitch(query: string, presets: Preset[], currentPresetId?: string | null, pendingPresetId?: string | null): ModelSwitchReply {
  const matches = matchAvailablePresets(query, presets);
  if (!matches.length) {
    const names = availablePresets(presets).map((item) => item.name);
    return {
      patch: null,
      message: `我没找到「${query.trim()}」这个可用模型。${names.length ? `当前可用：${names.join("、")}。` : ""}你可以说得更具体一点。`,
    };
  }
  if (matches.length > 1) {
    return {
      patch: null,
      message: `「${query.trim()}」能匹配到多个模型：${matches.map((item) => `${item.name} · ${item.channel}`).join("、")}。请说得更具体一点。`,
    };
  }
  const preset = matches[0];
  if (currentPresetId && preset.id === currentPresetId) {
    return pendingPresetId
      ? { patch: { pendingPresetId: "" }, message: `已取消待生效的切换，继续使用 ${preset.name}。` }
      : { patch: null, message: `已经在用 ${preset.name} 了，没有需要切换的。` };
  }
  return {
    patch: { pendingPresetId: preset.id },
    message: `好，已记下：下一轮起使用 ${preset.name} · ${preset.channel}，本轮仍是当前模型。`,
  };
}

/** Pickers use the same next-round boundary as conversational model changes. */
export function botModelSelectionPatch(presetId: string, currentPresetId?: string | null) {
  return { pendingPresetId: presetId === currentPresetId ? "" : presetId };
}
