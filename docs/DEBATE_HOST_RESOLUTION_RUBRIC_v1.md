# Debate Host Resolution Rubric v1

Date: 2026-06-15
Status: draft
Owner: Codex

## Purpose

This rubric tells `debate-host` how to move from round artifacts to a final
resolution state without faking convergence.

It is intentionally deterministic in shape, even when some inputs are model
authored.

## Core principle

`debate` is not a vote.

The host must decide based on:

1. stance distribution after revision
2. disagreement flag types
3. deterministic inputs vs model opinion
4. quality gates and confidence quality
5. whether members actually changed their minds, not just whether they repeated
   a majority position

## Inputs required

The host should not resolve without these artifacts:

- `round-1-seed.json`
- `round-2-clusters.json`
- `round-3-crossfire.json`
- `round-4-revision.json`

And should also inspect:

- `state.json`
- any deterministic inputs attached to the thread

## Step order

### Step 1 — Validate minimum completeness

Check:

- at least 2 valid member seed outputs
- every member output has `quality_gate`
- round 4 exists
- final stances are parseable
- required deterministic inputs, if any, were recorded

If any fail:

- resolution = `insufficient_evidence`
- quality_gate = `fail`

## Step 2 — Build final stance map

For each member, extract:

- initial stance
- final stance
- stance shift
- confidence
- strongest accepted opponent point
- `assigned_role` (proponent | opponent | steelman | free)
- `stance_authenticity` (honest | assigned)

Only members whose `stance_authenticity` is `honest` count toward camp
convergence. A `final_stance` self-marked `assigned` is advocacy the host
requested, not conviction: record it for provenance, but never let it create or
enlarge a convergence camp. If a member was given an `assigned_role` but did not
self-mark `stance_authenticity`, treat that stance as `assigned` (fail closed).

Produce a host-internal stance map like:

```json
{
  "cluster_A": ["member_a", "member_b"],
  "cluster_B": ["member_c"]
}
```

## Step 3 — Apply disagreement flags

Flags should be present in the final result and also used as hard constraints.

### Flag meanings

- `conclusion_opposite`: members recommend opposing directions
- `severity_mismatch`: same concern, different seriousness
- `fix_conflict`: agree on problem, disagree on remedy
- `deterministic_vs_opinion`: deterministic facts contradict model convergence
- `insufficient_evidence_flag`: evidence quality too weak to safely resolve

## Step 4 — Apply deterministic overrides

Deterministic facts outrank model opinion.

Examples:

- tests failed
- smoke failed
- hard constraint violated
- required artifact missing

Rules:

- if `deterministic_vs_opinion` is present, do not emit `converged`
- if deterministic facts invalidate the dominant camp and no repair/reframing is
  already proven, emit `split_human_required` or `insufficient_evidence`

## Step 5 — Apply quality gate rules

### Host should set `quality_gate=fail` when:

- required artifacts are missing
- fewer than 2 valid members remain
- `resolution_state=converged` but `conclusion_opposite` remains
- provenance/source is missing in final resolution

### Host should set `quality_gate=warn` when:

- some member outputs are degraded but still usable
- one or more `stance_shift` explanations are shallow
- `leaning` is emitted with unresolved non-blocking pushback

### Host should set `quality_gate=pass` when:

- all required inputs are present
- disagreement is classified honestly
- final state matches the rubric below

## Resolution decision tree

### Emit `insufficient_evidence` if any of these hold

- fewer than 2 valid member results
- final stance map cannot be built
- most member confidences are low/degraded
- evidence is largely preference-based rather than grounded in artifacts/facts
- deterministic inputs are missing where they were required
- host would otherwise need to invent missing structure

This state has higher priority than `leaning` or `converged`.

### Emit `split_human_required` if any of these hold

- `conclusion_opposite` remains after round 4
- `fix_conflict` remains on the core recommendation
- `deterministic_vs_opinion` is present and unresolved
- two or more camps retain high-confidence members after revision
- max rounds were used and the stance map still has meaningful split camps

The host must not override this with a personal preference.

### Emit `converged` only if all of these hold

- at least 2 valid members have `stance_authenticity=honest`
- all `stance_authenticity=honest` members end in the same camp (members whose
  stance is `assigned` are excluded from this check and can never satisfy it)
- no `conclusion_opposite`
- no unresolved `fix_conflict`
- no `deterministic_vs_opinion`
- quality_gate is not `fail`
- at least one of the following is true:
  - one or more members `switched`
  - one or more members `softened` and accepted the dominant case
  - all members were already aligned from round 1 with strong evidence

The host should explicitly name what caused convergence.

### Emit `leaning` when all of these hold

- among `stance_authenticity=honest` members, one camp clearly dominates, but
  minority disagreement remains
- no `conclusion_opposite`
- no unresolved `deterministic_vs_opinion`
- disagreement is mostly about severity, tradeoff, or implementation depth
- quality_gate is `pass` or `warn`

The host must preserve minority pushback instead of flattening it away.

## Priority order

When multiple states appear possible, use this order:

```text
insufficient_evidence
  > split_human_required
  > converged
  > leaning
```

This order is intentionally conservative.

## Stance-shift handling

The host should track per-member changes using:

- `unchanged`
- `softened`
- `switched`

### Interpretation

- `unchanged`: member still defends the same camp
- `softened`: member accepted meaningful opposing points but did not change camp
- `switched`: member changed camp after crossfire

### Why it matters

The host should not treat a dominant camp as strong if nobody moved and everyone
just restated their priors.

Evidence of real persuasion is stronger than raw camp count.

## Synthesis honesty rules

The final result must record:

- `synthesis_strategy`
- `synthesized_by`
- `synthesis_attempted_by`

### v1 guidance

- default `synthesis_strategy` = `host_authored`
- if a future dedicated synthesizer model is added, use `model`
- if host falls back to shallow merge due to partial data, mark `heuristic`
- if synthesis was unnecessary due to obvious alignment, mark `skipped`

The host must never imply a model synthesized the result when it did not.

## Recommended host output checklist

Before finalizing `resolution.json`, verify that it contains:

- `resolution_state`
- `quality_gate`
- `disagreement_flags`
- `resolution_reason`
- `recommended_next_step`
- `better_options`
- `pushback`
- `provenance`
- `synthesis_strategy`

## Examples

### Example A — Converged

- 4 members
- 2 started in camp A, 2 in camp B
- after crossfire, 1 switches to A, 1 softens toward A
- no deterministic contradiction
- final output: `converged`

### Example B — Leaning

- 4 members
- 3 end in camp A, 1 remains in camp B
- minority member accepts some opposing points but still dissents
- no conclusion-opposite on the top-level direction, only severity mismatch
- final output: `leaning`

### Example C — Split Human Required

- 4 members
- 2 remain strongly in camp A, 2 strongly in camp B
- `fix_conflict` remains on the actual next step
- final output: `split_human_required`

### Example D — Insufficient Evidence

- 3 members
- 2 produce degraded/low-confidence output
- deterministic inputs requested in the packet are missing
- host cannot safely compare stances
- final output: `insufficient_evidence`

## Out of scope for v1

- automatic room transport
- live debate dashboard/event stream
- model-learning loop from debate outcomes
- committee vote/quorum integration
