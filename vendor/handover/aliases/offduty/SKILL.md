---
name: offduty
description: Codex `$offduty` / handoff closeout entry. 下班、换机、fresh session 前，把当前会话自动折叠到 repo-local continuity；不要要求用户填写 task-id/scope/type。
---

# Offduty Alias

Use this alias when the user types `$offduty`, `/offduty`, or asks to 下班交接 / 换机续接 / fresh session checkpoint.

## Required Behavior

1. Do not ask the user for task-id, scope, lane, or type.
2. Infer actual touched roots before writing anything:
   - Use this session's tool workdirs, edited file paths, `git -C` / `cd` commands, and explicit repo paths from the chat.
   - For each candidate, run `git -C <path> rev-parse --show-toplevel` and use the git root when available.
   - If the session started in repo A but the work happened in repo B or C, write only to B/C.
   - If multiple repos/roots were touched, run one offduty per root.
   - Fall back to cwd only when no actual root can be inferred, and say it was a fallback.
3. Choose an actual work cwd for each root; usually the repo root or the touched subdirectory.
4. Infer the concrete task line from current chat, repo docs, git branch, git status, git diff, and recent artifacts for each root.
5. Preserve useful failed attempts, reversals, validation, risks, exact next action, session id, and model name.
6. From each actual repo root, run:

```bash
/Users/xin/auto-skills/shared-skills/handover/scripts/offduty --root "<actual-repo-root>" --cwd "<actual-work-cwd>"
```

   This writes `.agent.local/continuity/` plus a lightweight
   `.agent.local/continuity/lifeboat/*.md/json` capsule and best-effort `bkc`
   backup when the local session can be resolved. Do not call native resume here.

7. If the current truth, next action, and visible model name are already clear, pass only concise overrides:

```bash
/Users/xin/auto-skills/shared-skills/handover/scripts/offduty --root "<actual-repo-root>" --cwd "<actual-work-cwd>" --model "<model-name>" --summary "<current truth>" --next-action "<next>"
```

8. Reply briefly with the written paths per root, plus cwd/session_id/session_hash/model, and tell the user to use `$onduty` or `/onduty` in the target repo fresh session.

## Rules

- Default output is `.agent.local/continuity/`; legacy `.ai/plan` requires `--layout legacy-ai-plan`.
- For Codex, `$offduty` is the preferred explicit trigger.
- For Claude/OpenCode, `/offduty` may route through the skill alias; legacy command symlinks are cleaned to avoid duplicate entries.
- Root ownership follows actual touched repo/root, not the session launch folder.
- Task ids must stay short; use a concrete task id, not a long summary.
- Side sessions should not take the active pointer unless the helper decides the task owns main scope.
- Moebius treats this as a continuity slot; Pilot/Hive/Ant/Executor artifacts are refs, not the source of truth.
- `bkc` failure is recorded but non-blocking unless `--bkc required` is passed.
- Use `--bkc off` for deterministic tests; use `--no-lifeboat` only when another capsule is already written.
