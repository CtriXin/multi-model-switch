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
2. 先从已安装的 skill alias 解析 helper，不能使用某台开发机的绝对路径：
   - 优先使用 `<directory-containing-this-SKILL.md>/onduty`。
   - 如果看不到当前 skill 目录，就在 `${MMS_REAL_HOME:-}`、`${REAL_HOME:-}`、
     `${ORIGINAL_HOME:-}`、`$HOME` 下找这些 alias wrapper：
     `.agents/skills/onduty/onduty`、`.claude/skills/onduty/onduty`、
     `.codex/skills/onduty/onduty`、`.config/opencode/skills/onduty/onduty`、
     `.opencode/skills/onduty/onduty`。
3. 从实际 repo root 运行：

```bash
"<onduty-skill-dir>/onduty" --root "<actual-repo-root>"
```

4. 读取输出中的 Start Here、Active Pointer、Pickup Snapshot、Recent Checkpoints、Git Status。
5. 同时读取 Lifeboat / BKC Backup：这是 native resume 或 bkc lookup 失效时的 lightweight fallback。
6. 如果用户给了 hint，只打开相关 checkpoint/archive；否则默认只读 active refs，不展开 archive。
7. 先给一句结论：现在该从哪里继续。
8. 如果 git dirty，先提示需要检查 diff，再继续编辑。

不要要求用户复制旧聊天。旧聊天不是 source of truth。
默认 `onduty` 是 lite，不主动跑 native resume 或完整 transcript replay。
