---
name: onduty
description: '开工/换机/fresh session 时，从 repo-local continuity 恢复可执行上下文。'
argument-hint: [optional task/lane hint]
---

<!-- Managed by shared-skills handover continuity installer -->
# /onduty — 读取续接入口

你必须使用 `handover` skill 的 Offduty / Onduty Continuity 规则。

执行：

1. 先判断用户要恢复的实际 repo/root；不要盲用启动 cwd。若用户在 A 启动但要继续 B/C，切到 B/C 对应 root。
2. 从实际 repo root 运行：

```bash
/Users/xin/auto-skills/shared-skills/handover/scripts/onduty --root "<actual-repo-root>"
```

3. 读取输出中的 Start Here、Active Pointer、Pickup Snapshot、Recent Checkpoints、Git Status。
4. 同时读取 Lifeboat / BKC Backup：这是 native resume 或 bkc lookup 失效时的 lightweight fallback。
5. 如果用户给了 hint，只打开相关 checkpoint/archive；否则默认只读 active refs，不展开 archive。
6. 先给一句结论：现在该从哪里继续。
7. 如果 git dirty，先提示需要检查 diff，再继续编辑。

不要要求用户复制旧聊天。旧聊天不是 source of truth。
默认 `onduty` 是 lite，不主动跑 native resume 或完整 transcript replay。
