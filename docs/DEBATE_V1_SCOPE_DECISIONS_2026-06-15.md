# Debate Profile v1 — Scope Decisions & Round Mechanic

Date: 2026-06-15
Status: decided (human-confirmed)
Owner: human
Relates to:

- Issue #11
- `docs/RFC_OPENCODE_DEBATE_PROFILE_2026-06-15.md`
- `docs/DEBATE_STATE_RESULT_CONTRACT_v1.md`
- `docs/DEBATE_HOST_RESOLUTION_RUBRIC_v1.md`

## Purpose

Lock the three open scope questions for the OpenCode `debate` profile v1, and
record one new round-control mechanic that the RFC left open
(`split_human_required` triggering, RFC Open Question 4).

This doc only records decisions. It does not change the contract or rubric
semantics; it constrains how v1 is built against them.

## Scope Decisions

### Decision 1 — No automatic artifact validator in v1

**Verdict:** yes, v1 ships no standalone validator program.

But "no validator program" must not become "no validation". The minimum
pass/fail rules already defined in `DEBATE_STATE_RESULT_CONTRACT_v1.md`
(>=2 valid members, required `resolution.json` fields, `converged` mutually
exclusive with `conclusion_opposite` / `deterministic_vs_opinion`) ship as a
**self-check checklist inside the `debate-host` prompt**.

- validator-as-code -> v2
- validator-as-prompt-checklist -> v1, required

Reason: without the in-prompt checklist the host can author fake convergence
and the whole contract becomes decorative. A separate validator program is
unnecessary engineering for v1 and would touch more surface than the slice
needs.

### Decision 2 — Host writes `.ai/debate/<thread-id>/` by prompt, no new MMS helper command

**Verdict:** yes. v1 has `debate-host` write the artifact files directly per its
prompt contract. No new MMS helper command.

Reason:

- A new helper command would touch protected launcher/core surface
  (`AGENT_GUARDRAILS.md` high-risk files); not worth it for v1.
- OpenCode agents can already produce artifact-first structured files; RFC
  "What V1 Can Support Now" already lists this.

Known cost: path/schema consistency is enforced only by the prompt, which is
weaker than code. Accepted for v1. A helper that does atomic writes + schema
validation is deferred to v2.

### Decision 3 — Dedicated synthesizer model is v2

**Verdict:** yes, deferred to v2. v1 resolution is host-authored only.

Reason:

- The contract is already forward-compatible: `synthesis_strategy` accepts
  `host_authored | model | heuristic | skipped`, so adding `model` later needs
  no schema change.
- v1 host-only synthesis is sufficient under the rubric. A synthesizer model
  adds a routing pass + cost with unclear benefit at this stage.
- The rubric already frames it as future
  ("if a future dedicated synthesizer model is added, use `model`").

v1 default stays `synthesis_strategy = host_authored`.

## Round Mechanic — Golden Goal, No Extra Time

This resolves RFC Open Question 4 (how many rounds before
`split_human_required`).

**Decision: fixed 3 rounds as regulation time, bidirectional golden goal may
end early, no extra time.**

```text
blind seed -> crossfire -> revision   (regulation = 3 rounds, hard cap)
+ golden goal: may stop early in either direction
+ no extra time: never auto-append more crossfire rounds
+ at the 3-round cap, the host MUST emit a resolution_state
```

### No extra time

Auto-appending more crossfire/revision rounds after the cap is rejected.
Model debate is not human debate: model priors are stable, so a member that did
not move in crossfire round 1 will almost never move in round 2. Extra rounds
mainly burn tokens and slow the "one-line direction -> result" experience in
exchange for a low-probability late convergence. This is consistent with the
rubric: a dominant camp where nobody moved is not strong.

### Bidirectional golden goal (early exit)

The real signal in debate is whether anyone changed their mind on evidence, not
whether enough rounds were spent. So early exit works both ways:

- **Positive golden goal -> `converged` early:** stop before the cap when all
  valid members end in the same camp AND at least one member actually shifted.
- **Negative golden goal -> `split_human_required` early:** stop before a
  pointless revision round when crossfire shows the camps are mutually
  unreachable and not moving.

### Triggers must be deterministic

Golden goal must be machine-verifiable, not a host's subjective "I think we can
wrap up". This is the same line as Decision 1's anti-fake-convergence checklist:
early stop is allowed, but the stop reason must be checkable.

Minimum trigger conditions:

- **Positive:** `round-4-revision.json` has all members' `final_stance` in the
  same camp AND at least one `stance_shift != unchanged`.
- **Negative:** in `round-3-crossfire.json`, every member's
  `what_evidence_would_change_my_mind` is empty or marked unreachable AND there
  are >=2 camps each holding a high-confidence member.

### Interaction with the rubric

This mechanic sits on top of `DEBATE_HOST_RESOLUTION_RUBRIC_v1.md`, it does not
replace it. The rubric still owns the final decision tree and the conservative
priority order:

```text
insufficient_evidence > split_human_required > converged > leaning
```

Golden goal only decides *when* the host is allowed to stop; the rubric decides
*which* `resolution_state` is emitted. `insufficient_evidence` from the rubric
still outranks a positive golden goal.

## Summary

| Item | v1 | v2 |
|---|---|---|
| Artifact validator | prompt checklist | validator program |
| `.ai/debate/` writes | host-by-prompt | MMS helper command |
| Synthesizer | host_authored only | optional `model` pass |
| Rounds | fixed 3 + golden goal, no extra time | richer clustering / longer debates |
