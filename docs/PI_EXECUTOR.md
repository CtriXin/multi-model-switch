# Pi Executor

`pi-executor` is the writable companion to the read-only `pi-committee`. It lets a Host such as Codex or Claude select exact MMS logical models for one mission, gives every model/route attempt a clean detached git worktree, and returns only Host-audited patch candidates.

It does not use OpenCode, does not modify MMS launcher selection, does not install a global skill, does not write real MMS config, and never applies a patch automatically.

## Execution Contract

1. Host creates a shared `executor.pack.v1` anchored to a git commit.
2. Host supplies one or more exact `--model` names and one explicit verified MMS config root.
3. Every candidate/fallback route starts in a new disposable worktree at the same pack commit.
4. Pi receives `read,grep,find,ls,edit,write`; `bash` is disabled. macOS `sandbox-exec` denies persistent writes outside the per-run temp root.
5. Host captures the diff, rejects protected/unspecified paths and oversize patches, runs pack validation as argv without a shell, rejects validation failure/mutation, and removes the worktree.
6. The parent packet separates admissible, rejected, and failed candidates. It contains patch hashes and never applies them.

The pre-primed repo-local Pi cache can supply a read-only executable. If it is missing, `npx` uses a private per-run cache. The shared cache is not a worker write surface.

## Build a Pack

Use the shared executor helper from the target repository:

```bash
python3 /Users/xin/auto-skills/shared-skills/executor/scripts/executor.py init \
  --root <target-repo> --write

python3 /Users/xin/auto-skills/shared-skills/executor/scripts/executor.py pack \
  --root <target-repo> \
  --task-id <task-id> \
  --commit <base-commit> \
  --title '<bounded title>' \
  --objective '<one independently executable objective>' \
  --writable-file 'src/**' \
  --read-file 'README.md' \
  --forbidden-file '.env' \
  --success-criterion '<observable success condition>' \
  --validation 'python3 -m pytest tests/test_target.py -q' \
  --write
```

Anything not matched by `writable_files` is outside the admissible patch scope. `read_only_files`, `forbidden_files`, and invariant `.git/**` outrank writable globs.

## Dry-run and Execute

The canonical Host entry is the repo-local skill runner:

```bash
python3 assets/session-assets/skills/pi-executor/scripts/run_pi_executor.py \
  --config-root <explicit-verified-mms-root> \
  --pack <target-repo>/.ai/exec/packs/<task-id>.json \
  --target-repo <target-repo> \
  --model kimi-for-coding \
  --model gpt-5.5 \
  --dry-run
```

After checking routes, request paths, base commit, scope, isolation, and watchdog, remove `--dry-run` and add an output:

```bash
python3 assets/session-assets/skills/pi-executor/scripts/run_pi_executor.py \
  --config-root <explicit-verified-mms-root> \
  --pack <target-repo>/.ai/exec/packs/<task-id>.json \
  --target-repo <target-repo> \
  --model kimi-for-coding \
  --model gpt-5.5 \
  --output <target-repo>/.ai/exec/results/pi-host/<task-id>-parent.json
```

Repeated `--model` values are independent candidates. They are not persistent roles or aliases; a future mission may use a completely different lineup.

## Host Intake

Read the complete `mms.pi_executor.parent_packet.v1`:

- `admissible_candidates`: scope, patch, and Host validation passed;
- `rejected_candidates`: model completed but violated scope/intake;
- `failed_candidates`: provider/watchdog/launch failure;
- `patch_index`: path, hash, size, changed files, and validation;
- `host_intake_contract`: explicit no-auto-apply rules.

Inspect a chosen patch and apply it only through the Host's normal reviewed editing workflow. Rerun project tests after apply. Never apply a rejected or failed patch.

`--result <raw-result.json>` performs offline intake only. It rechecks the local patch/hash/bytes/diff paths/scope/validation evidence, but saved validation can be forged; therefore its status is `saved_result_requires_host_revalidation`, never live `ready_for_intake`.

## Other LLM Hosts

No global installation is needed:

- Codex: explicitly load `assets/session-assets/skills/pi-executor/SKILL.md`, then follow its pack -> dry-run -> live -> intake workflow.
- Claude: ask the current Claude session to read the same repo-local `SKILL.md` completely and use its runner. This repository does not change Claude config or start Claude automatically.
- Any shell-capable LLM/agent: call `scripts/pi_executor_parent.py` directly with the same arguments. Set `MMS_PI_EXECUTOR_ROOT=<this-repo>` only when the skill runner cannot locate its owning repo.
- A non-shell LLM cannot operate the runtime safely by itself; use Codex/Claude/another Host to create the pack and run the adapter.

The Host remains the decision maker. Pi models are ephemeral executor workers, not new top-level agents, accounts, or globally named committee members.

## Watchdog

Defaults are 900s wall per candidate, 300s idle, bounded retained stream output, repeated-event detection, process-group termination, 180s per validation, and an auto-sized whole-run deadline. Exact terminal reasons include `wall_timeout`, `idle_timeout`, `repetition_limit`, `output_limit`, and `executor_timeout`.

In the safety review, one Kimi reviewer reached the 600s committee wall limit and was terminated with `wall_timeout`; the other reviews and executor live calls completed. This demonstrates that a long-tail model is recorded and stopped instead of blocking forever.
