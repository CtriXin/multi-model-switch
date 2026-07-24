---
name: pi-committee
description: Dispatch the MMS isolated Pi multi-model committee and synthesize its evidence as the current parent. Use when the user explicitly invokes $pi-committee to ask Codex or Claude for independent multi-model review, debate, architecture analysis, bug diagnosis, or a committee verdict without OpenCode.
---

# Pi Committee

Use the current Codex or Claude session as the parent. Dispatch ephemeral Pi `member-NN` workers, preserve every opinion, and synthesize the final conclusion yourself.

## Boundaries

- This is an opt-in shared skill source. It may be installed into Codex or Claude via symlink, but must still run only after the user requests Pi committee work.
- Do not assume the MMS launcher auto-injected it; skill discovery and explicit invocation remain Parent responsibilities.
- Require an explicit verified MMS `config_root`; never fall back to a real/global root.
- Keep the worker target read-only. Do not use this skill to authorize edits, deploys, messages, or other side effects.
- Do not invoke OpenCode or start another parent/synthesizer.
- Do not edit MMS preferences/config or real/global account state. Installation should be a symlink to the shared skill source, not a copied divergent global fork.
- Treat failed members, fallback use, and raw responses as evidence about coverage.
- Treat this as an agentic workload: the defaults are a 900s member wall budget and a conservative 300s no-output budget. Do not infer that `anthropic_messages` is broken from timeout correlation alone.
- Reject timestamped latest-approved bundles older than 30 days before model selection. The plan must expose the resolved config root, manifest path, bundle age, and freshness status. Use `--max-bundle-age-days 0` only for an intentional historical replay.
- Route attempts share the member wall budget. Kimi additionally has a default 300s cap per route attempt, so Tokyo cannot consume the entire member budget before Tencent/direct are tried. A fallback with less than one second remaining must be recorded as `skipped / no_budget_remaining`, not launched or reported as a provider timeout. Count `fallback_members` only when a fallback actually started.
- Kimi defaults are dynamic: choose the newest eligible Kimi version from the fresh verified bundle (`k3` outranks `kimi-k2.x-code`), prefer coding/code within the same version, and expect route order to be Tokyo primary, Tencent fallback, direct later. Do not interpret a non-direct Kimi primary as drift.
- Quorum early-stop is disabled by default. Do not enable it unless the mission explicitly values an early partial answer over every selected opinion.

## Dispatch

Resolve `scripts/run_pi_committee.py` relative to this `SKILL.md`.

1. Put a bounded mission in a UTF-8 task file. State the target, decision needed, evidence standard, and non-goals.
2. Run a dry-run first and inspect the selected models, families, routes, and isolation block:

```bash
python3 <skill-dir>/scripts/run_pi_committee.py \
  --config-root <explicit-mms-config-root> \
  --task-file <mission-file> \
  --cwd <read-only-target> \
  --dry-run
```

3. If the plan matches the request, run the same command without `--dry-run`. Use `--output <artifact.json>` when durable evidence is needed.
4. Use `--add-family`, `--add-model`, `--model`, or `--selection-profile balanced` only when the user or task evidence justifies changing the default frontier lineup.
5. To resynthesize a saved raw committee result without provider calls, pass `--result <result.json>`.
6. Inspect `bundle.freshness` and `watchdog` in the plan. `--committee-timeout 0` auto-sizes the total budget by concurrency waves. Override `--timeout`, `--kimi-attempt-timeout`, `--idle-timeout`, output/repetition limits, or opt-in quorum only when task evidence justifies it.

Do not ask for confirmation between dry-run and execution when the user already asked for committee dispatch and the plan stays within these boundaries.

## Synthesize

Read the returned `mms.pi_committee.parent_packet.v1` completely. Produce:

1. `结论`: the parent decision first.
2. `Committee health`: success/failure/raw/fallback coverage.
3. `共识`: only claims independently supported by at least two members; cite `member_id` and `evidence_id`.
4. `分歧`: preserve competing positions and explain which evidence is stronger.
5. `独立发现`: useful single-member findings, clearly labeled as uncorroborated.
6. `风险与建议`: actionable recommendation and remaining uncertainty.

Follow `synthesis_contract.rules` from the packet. Never invent semantic consensus from string similarity, hide minority dissent, or drop raw/failed responses. Separate inspected evidence from parent inference. Only synthesize when `ready_for_synthesis=true`; the default floor is at least half of planned members, rounded up (`7` members requires `4` successes). Otherwise report insufficient coverage.

## Stop Conditions

- Do not treat a dry-run packet as a committee verdict. If dispatch was authorized and the plan is safe, proceed to the real run; otherwise stop after the plan.
- Report partial coverage when some members fail; do not turn `1/7` into a committee conclusion.
- When a worker stops, report its exact `terminal_reason`. Distinguish `wall_timeout`, `idle_timeout`, `repetition_limit`, `output_limit`, `committee_timeout`, and `quorum_reached` from provider request errors.
- Stop and report the exact error when bundle verification, route preparation, or isolation fails. Do not recover through global OAuth/default accounts.
