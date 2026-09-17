import { createElement as h } from "react";

/** What the update row may say, and how the installer escape hatch renders.
 *
 * The updater only ever installs a higher version. A 5.x install that checks
 * the stable channel therefore finds 4.x, which is not an update: calling that
 * "已是最新 4.x 稳定版" tells the user something false about the machine they
 * are on. The line check below is the single place that decision lives, and
 * the notice is the shared shape the backend's `upgradeGuidance` already has.
 */

export type UpdateChannel = "stable" | "preview";

export type UpdateCheckState = {
  currentVersion?: string;
  channel?: UpdateChannel;
  latest?: { tag?: string };
  updateAvailable?: boolean;
  checkedAt?: number;
  error?: string;
  checking?: boolean;
};

export type UpgradeGuidance = {
  required: boolean;
  title: string;
  reason: string;
  command: string;
  steps: string[];
};

export const STABLE_LINE_LABEL = "4.x 稳定版";
export const PREVIEW_LINE_LABEL = "5.x 预览版";

export function lineLabel(channel?: UpdateChannel): string {
  return channel === "preview" ? PREVIEW_LINE_LABEL : STABLE_LINE_LABEL;
}

/** The major line of a release tag, or null when it is not a version. */
export function versionLine(value?: string): number | null {
  const match = /^v?(\d+)\.\d+\.\d+$/.exec(String(value ?? "").trim());
  return match ? Number(match[1]) : null;
}

export function isCrossLine(state: UpdateCheckState): boolean {
  const installed = versionLine(state.currentVersion);
  const latest = versionLine(state.latest?.tag);
  return installed !== null && latest !== null && installed !== latest;
}

export function updateHeadline(state: UpdateCheckState): string {
  const label = lineLabel(state.channel);
  if (state.checking) return "正在检查…";
  if (state.updateAvailable) return `发现新版 ${state.latest?.tag}`;
  if (!(state.checkedAt && !state.error)) return `检查 ${label}`;
  if (isCrossLine(state)) return `当前 v${state.currentVersion} 不在 ${label} 线上`;
  if (versionLine(state.latest?.tag) === null) return "已检查，未发现可安装的更新";
  return `已是最新 ${label}`;
}

export function UpdateStatusLine({ state }: { state?: UpdateCheckState }) {
  return h("span", null, updateHeadline(state || {}));
}

export function UpgradeGuidanceNotice({ guidance, copied, onCopy }: {
  guidance: UpgradeGuidance;
  copied: boolean;
  onCopy: () => void;
}) {
  return h("section", { className: "update-migration-warning", role: "alert", "aria-label": "需要手动升级" },
    h("h3", null, guidance.title),
    h("p", null, guidance.reason),
    h("ol", null, guidance.steps.map(step => h("li", { key: step }, step))),
    h("div", { className: "update-command" },
      h("pre", null, h("code", null, guidance.command)),
      h("button", { type: "button", className: "text-button", onClick: onCopy }, copied ? "已复制" : "复制命令")),
    h("p", { className: "update-muted" }, "这次不会清空会话或运行记录；安装器会保留旧目录，确认无误后再手动备份或清理。"));
}
