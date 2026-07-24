---
name: pi-court
description: Convene the MMS isolated Pi multi-model court with explicit design, product, development, testing, or custom role seats and synthesize cross-role evidence as the current Parent. Use when the user explicitly invokes $pi-court for cross-functional review, role-aware architecture/product/design/QA deliberation, Soul-guided critique, same-role multi-model comparison, or a court verdict without OpenCode.
---

# Pi Court

Use the current Parent as judge and secretary. Dispatch read-only Pi seats whose role procedure comes from canonical `agent-spec` Soul cards, then synthesize both model diversity and role/domain diversity.

## Boundaries

- Run only after the user explicitly requests Pi Court work.
- Require an explicit verified MMS `config_root`; never fall back to a real/global root or OAuth account.
- Keep every Pi seat read-only. Use `$pi-executor` for bounded writable work.
- Do not invoke OpenCode, agent-soul runtime, agent-soul memory, or another synthesizer.
- For Soul profiles, require an explicit `agent_spec_root`. Load `index.json` plus `roles/<role_id>.min.md` fail-closed; never copy or silently replace a missing card.
- Keep `pi-committee` unchanged as the generic independent committee. Pi Court is an opt-in role-aware sibling.
- Treat repeated use of one model across seats as correlated evidence, not independent model corroboration.

## Choose a profile

- `hybrid` (default): one required seat for design, product, development, and testing; one cross-cutting challenger; one Soul-free wildcard.
- `cross-functional`: two seats in each required domain for deeper product/application review.
- `general`: six legacy-style independent lenses without Soul cards; use as an A/B baseline.
- `--profile-file`: custom `mms.pi_court.profile.v1`; read [profile-contract.md](references/profile-contract.md) before authoring or validating one.

## Dispatch

Resolve `scripts/run_pi_court.py` relative to this file.

1. Write a bounded mission containing target, decision, evidence standard, and non-goals.
2. Dry-run first and inspect profile, seats, role hashes, model assignment, routes, required domains, and same-model correlation:

```bash
python3 <skill-dir>/scripts/run_pi_court.py \
  --config-root <explicit-mms-config-root> \
  --agent-spec-root <explicit-agent-spec-root> \
  --profile hybrid \
  --task-file <mission-file> \
  --cwd <read-only-target> \
  --dry-run
```

3. If the plan matches the mission, run the same command without `--dry-run`. Use `--output <packet.json>` for durable evidence.
4. Do not hardcode permanent `committee-*` model identities. Let the verified bundle supply the dynamic frontier pool, or override only this mission:

```bash
--seat-model design-direction=k3 \
--seat-model development-architecture=k3 \
--seat-model testing-contract=kimi-for-coding
```

5. `--max-seats-per-model` bounds intentional model reuse. The default is profile-owned (`2` for role profiles, `1` for general).
6. To resynthesize a saved raw Court result without provider calls, pass `--result <result.json>`.

## Synthesize

Read the complete `mms.pi_court.parent_packet.v1`.

1. Report Court health and every failed/raw/fallback seat.
2. Check `ready_for_synthesis`. It requires both the normal member-success floor and at least one successful seat in every required domain.
3. Classify agreement:
   - `model_corroboration`: different model families support the same role/domain claim.
   - `perspective_corroboration`: different roles/domains agree but use the same model; preserve correlation warning.
   - `cross_role_model_corroboration`: both roles/domains and model families differ; strongest support.
4. Preserve dissent and Soul-free wildcard findings.
5. Cite seat id, domain, role id, model, and evidence id. Never infer consensus from string similarity.

## Stop conditions

- Stop if bundle verification, profile validation, Soul loading, route preparation, or isolation fails.
- Do not synthesize when a required domain is missing, even if the numeric member floor passed.
- Distinguish watchdog terminal reasons and no-budget fallback skips exactly as `$pi-committee` does.
- Do not convert role output contracts into writes or side effects.
