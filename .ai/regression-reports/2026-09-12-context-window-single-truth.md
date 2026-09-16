# 回归报告：统一 context window 来源

- 时间：2026-09-12（Asia/Singapore）
- 范围：合入 PR #233 后，四个 harness 共用 context-window resolver；发布 v4.19.4。
- 修改：版本元数据、Pilot bundle、release note、回归记录。

## 验证

- PR #233 CI：pytest、digger、redline 全部 SUCCESS。
- PR #233 fresh-user gate：653 passed / 0 failed。
- PR #233 对比回归：没有 base 通过而 head 失败的测试。
- `python3 scripts/build_mms_web_release.py --skip-install`：通过，bundle v4.19.4。
- `git diff --check`：通过。

## 边界

- 当前真实本机 Pilot 未停止或重启；本报告没有修改 `~/.config/mms-next`。
- MiMo Anthropic endpoint 的平名与 `[1m]` selector 仍按 provider profile 区分。
