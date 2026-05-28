---
name: offduty
description: '下班/换机/换 fresh session 前，自动折叠当前工作状态到 repo-local continuity。'
argument-hint: [optional note]
---

<!-- Managed by shared-skills handover continuity installer -->
# /offduty — 写入可续接交接

你必须使用 `handover` skill 的 Offduty / Onduty Continuity 规则。

执行：

1. 不要问用户 task-id、scope、lane、类型；自己从当前对话、repo docs、git status、git diff、最近 artifacts 判断。
2. 先判断实际工作归属 root，不要盲用启动 cwd：
   - 从本会话 tool `workdir`、编辑过的文件路径、运行过的 `git -C` / `cd` 命令、用户提到的 repo 路径中归纳 touched roots。
   - 对每个候选目录运行 `git -C <path> rev-parse --show-toplevel`，优先使用 git root。
   - 如果会话启动在 A，但实际改/查/测的是 B 或 C，只给 B/C 写 offduty，不要写到 A。
   - 如果同一会话实际涉及多个 repo/root，按 root 分别运行一次 offduty。
   - 只有完全无法判断实际 root 时，才 fallback 当前 cwd，并在回执里标明是 fallback。
3. 为每个 root 选择一个实际工作 cwd；通常是该 repo root，或本轮主要操作所在子目录。
4. 如果能可靠提炼，记录：当前真相、重要失败尝试/反转、validation、risk、next action、session_id、model_name。
5. 默认写入 `.agent.local/continuity/`。只有项目明确要求 legacy 时才加 `--layout legacy-ai-plan`。
   同时默认写 `.agent.local/continuity/lifeboat/*.md/json`，并 best-effort 调用 `bkc` 写 `.ai/continuity/` 备份；`bkc` 失败只记录，不阻塞。
6. 先从已安装的 skill alias 解析 helper，不能使用某台开发机的绝对路径：
   - 优先使用 `<directory-containing-this-SKILL.md>/offduty`。
   - 如果看不到当前 skill 目录，就在 `${MMS_REAL_HOME:-}`、`${REAL_HOME:-}`、
     `${ORIGINAL_HOME:-}`、`$HOME` 下找这些 alias wrapper：
     `.agents/skills/offduty/offduty`、`.claude/skills/offduty/offduty`、
     `.codex/skills/offduty/offduty`、`.config/opencode/skills/offduty/offduty`、
     `.opencode/skills/offduty/offduty`。
7. 在每个实际 repo root 运行：

```bash
"<offduty-skill-dir>/offduty" --root "<actual-repo-root>" --cwd "<actual-work-cwd>"
```

8. 如果你已经明确知道摘要/下一步/模型名，可传少量 override，但不是必须：

```bash
"<offduty-skill-dir>/offduty" --root "<actual-repo-root>" --cwd "<actual-work-cwd>" --model "<model-name>" --summary "<current truth>" --next-action "<next>"
```

9. 回执只说每个 root/cwd 写到哪些路径、session_id/hash/model 是什么、下一次 `/onduty` 或 `$onduty` 怎么恢复；不要输出长交接全文。
10. 做 deterministic 测试时可以加 `--bkc off`；只有已经有其它 capsule 时才使用 `--no-lifeboat`。

如果当前请求处于 Moebius 流程，按 Mobius continuity addon/slot 处理；Pilot/Hive/Ant/Executor 结果只作为 artifact refs 写入，不接管 continuity source of truth。
