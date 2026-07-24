---
name: pi-executor
description: Run one or more exact MMS-routed Pi models as independent writable coding agents in disposable git worktrees, then return Host-validated patch candidates without OpenCode or automatic apply. Use only when the user explicitly invokes $pi-executor or explicitly asks to delegate bounded implementation to Pi models.
---

# Pi Executor

Use the current Codex, Claude, or other shell-capable LLM session as Host. The Host creates an `executor.pack.v1`, dispatches exact logical models, and admits only patches that stay inside the pack scope and pass Host-run validation.

## Boundaries

- This is an explicit shared skill. It may be installed into Codex or Claude via symlink, but must not be implicitly invoked or used to edit MMS/Claude/Codex/OpenCode configuration.
- Keep `pi-committee` read-only. Use this separate skill only for authorized writable delegation.
- Require an explicit verified MMS `config_root`; never fall back to real/global config or OAuth.
- Require exact `--model` values per run. Repeat `--model` for independent competing executors; do not create persistent names such as `committee-glm`.
- Pi writes only inside a disposable detached git worktree. The runtime requires `sandbox-exec`, excludes `bash`, audits every changed path, reruns validation, saves a patch, removes the worktree, and never applies the patch.
- A worker response is not proof. Trust Host-observed changed files, scope verdict, validation output, patch hash, route evidence, and watchdog state.

## Workflow

1. Read the shared `$executor` skill and create `.ai/exec/packs/<task-id>.json` with its helper. The pack must contain a commit, non-empty `writable_files`, success criteria, and validation commands. Add explicit `read_only_files`, `forbidden_files`, and non-goals.
2. Resolve `scripts/run_pi_executor.py` relative to this `SKILL.md`.
3. Dry-run the exact pack, target repo, bundle, and models:

```bash
python3 <skill-dir>/scripts/run_pi_executor.py \
  --config-root <explicit-mms-config-root> \
  --pack <target-repo>/.ai/exec/packs/<task-id>.json \
  --target-repo <target-repo> \
  --model <logical-model> \
  --dry-run
```

4. Inspect `plan.selection`, every route/request path, `pack.base_commit`, writable/protected scopes, isolation, watchdog, and intake policy. If safe and already authorized, run without another confirmation:

```bash
python3 <skill-dir>/scripts/run_pi_executor.py \
  --config-root <explicit-mms-config-root> \
  --pack <target-repo>/.ai/exec/packs/<task-id>.json \
  --target-repo <target-repo> \
  --model <logical-model-a> \
  --model <logical-model-b> \
  --output <target-repo>/.ai/exec/results/pi-host/<task-id>-parent.json
```

5. Read the complete `mms.pi_executor.parent_packet.v1`. Compare admissible candidates against the pack. Never use a rejected/failed patch. Inspect a selected patch before applying it through the Host's normal edit/review workflow, then rerun project checks.
6. To rebuild intake from a saved raw `mms.pi_executor.result.v1` without provider calls, pass `--result <raw-result.json>`. Saved evidence is integrity-checked but remains advisory and returns `saved_result_requires_host_revalidation`, never live readiness.

The runner uses conservative 900s wall, 300s idle, bounded output/repetition, and 180s per validation defaults. Override only with evidence. See [references/pack-contract.md](references/pack-contract.md) for the accepted pack and result semantics.

## Host Conclusion

Report:

1. selected models and actual provider/protocol/request path;
2. candidate health and exact watchdog terminal reasons;
3. admissible versus rejected patches and scope violations;
4. Host validation commands/results;
5. selected patch or the reason no patch was adopted;
6. confirmation that the user's checkout and global config were not modified.

Stop on bundle verification failure, missing sandbox, unsafe pack path, scope violation, validation mutation/failure, patch limit, or no admissible candidate. Do not bypass the failure with global accounts, OpenCode, a different checkout, or automatic merge.
