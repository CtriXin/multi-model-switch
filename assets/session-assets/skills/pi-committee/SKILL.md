---
name: pi-committee
description: Dispatch the MMS isolated Pi multi-model committee and synthesize its evidence as the current parent. Use when the user explicitly invokes $pi-committee to ask Codex or Claude for independent multi-model review, debate, architecture analysis, bug diagnosis, or a committee verdict without OpenCode.
---

# Pi Committee

Use the current Codex or Claude session as the parent. Dispatch ephemeral Pi `member-NN` workers, preserve every opinion, and synthesize the final conclusion yourself.

## Boundaries

- This is an opt-in repo-local skill source. Do not assume the MMS launcher auto-injected it; load this `SKILL.md` explicitly or call its runner only after the user requests Pi committee work.
- Require an explicit verified MMS `config_root`; never fall back to a real/global root.
- Keep the worker target read-only. Do not use this skill to authorize edits, deploys, messages, or other side effects.
- Do not invoke OpenCode or start another parent/synthesizer.
- Do not install this skill globally or edit MMS preferences/config.
- Treat failed members, fallback use, and raw responses as evidence about coverage.

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

Do not ask for confirmation between dry-run and execution when the user already asked for committee dispatch and the plan stays within these boundaries.

## Synthesize

Read the returned `mms.pi_committee.parent_packet.v1` completely. Produce:

1. `结论`: the parent decision first.
2. `Committee health`: success/failure/raw/fallback coverage.
3. `共识`: only claims independently supported by at least two members; cite `member_id` and `evidence_id`.
4. `分歧`: preserve competing positions and explain which evidence is stronger.
5. `独立发现`: useful single-member findings, clearly labeled as uncorroborated.
6. `风险与建议`: actionable recommendation and remaining uncertainty.

Follow `synthesis_contract.rules` from the packet. Never invent semantic consensus from string similarity, hide minority dissent, or drop raw/failed responses. Separate inspected evidence from parent inference.

## Stop Conditions

- Do not treat a dry-run packet as a committee verdict. If dispatch was authorized and the plan is safe, proceed to the real run; otherwise stop after the plan.
- Report partial coverage when some members fail; synthesize the successful evidence only if it remains sufficient.
- Stop and report the exact error when bundle verification, route preparation, or isolation fails. Do not recover through global OAuth/default accounts.
