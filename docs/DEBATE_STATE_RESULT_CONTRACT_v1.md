# Debate State And Result Contract v1

Date: 2026-06-15
Status: draft
Owner: Codex

## Purpose

This document defines the minimum durable contract for the MMS OpenCode
`debate` profile.

Goals:

- keep debate state resumable without replaying full transcripts
- keep round outputs machine-readable
- keep final resolution auditable
- prevent fake convergence by requiring explicit disagreement and quality fields

Non-goals:

- not a transport/runtime spec
- not a committee vote schema
- not a review-hub request-root schema

## Namespace

Debate artifacts live under:

```text
.ai/debate/<thread-id>/
```

Minimum file set for v1:

```text
.ai/debate/<thread-id>/
  brief.md
  state.json
  round-1-seed.json
  round-2-clusters.json
  round-3-crossfire.json
  round-4-revision.json
  resolution.json
  resolution.md
```

## Global rules

- Use distilled packets, not full transcript replay.
- Keep one append-only `thread_id` per debate thread.
- Create or preserve one `MMS-MISSION` block for each manual debate dispatch,
  per `docs/OPENCODE_REVIEW_MISSION_TRACE_v1.md`.
- Include the unchanged mission block in every member packet and final chat
  resolution. If the reviewed target is unclear, use `MMS-TARGET: unknown`.
- In JSON artifacts, store the block as a `mission` object with literal keys
  `MMS-MISSION`, `MMS-TARGET`, `MMS-MODE`, and `MMS-SOURCE`.
- Every round artifact must be valid JSON.
- Every member result must carry provenance and quality metadata.
- Deterministic facts must be stored separately from model opinion.

## Enum sets

### `status`

```text
running | resolved | blocked | aborted
```

### `quality_gate`

```text
pass | warn | fail
```

### `resolution_state`

```text
converged | leaning | split_human_required | insufficient_evidence
```

### `stance_shift`

```text
unchanged | softened | switched
```

### `synthesis_strategy`

```text
host_authored | model | heuristic | skipped
```

### `disagreement_flags`

```text
conclusion_opposite
severity_mismatch
fix_conflict
deterministic_vs_opinion
insufficient_evidence_flag
```

## `state.json`

### Purpose

Thread-local durable state for resume and status inspection.

### Required shape

```json
{
  "schema": "opencode.debate.state.v1",
  "thread_id": "20260615-example",
  "mission": {
    "MMS-MISSION": "debate-20260615-example-a8f31c2e",
    "MMS-TARGET": "unknown",
    "MMS-MODE": "debate",
    "MMS-SOURCE": "user-pasted"
  },
  "status": "running",
  "round": 1,
  "goal": "decide whether to add a new debate profile",
  "question": "what shape should the profile take",
  "decision_boundary": "profile shape only, no implementation yet",
  "constraints": ["do not reuse committee workflow semantics"],
  "selected_members": ["debate-gpt-5-5", "debate-glm-5-2"],
  "current_clusters": [],
  "deterministic_inputs": [],
  "latest_artifact": ".ai/debate/<thread-id>/round-1-seed.json",
  "started_at": "2026-06-15T12:00:00Z",
  "updated_at": "2026-06-15T12:00:00Z",
  "_quality_debug": {
    "normalized_confidence": "high",
    "validation_warnings": []
  }
}
```

### Required fields

- `schema`
- `thread_id`
- `mission`
- `status`
- `round`
- `goal`
- `question`
- `constraints`
- `selected_members`
- `latest_artifact`
- `started_at`
- `updated_at`

### Optional but recommended fields

- `decision_boundary`
- `current_clusters`
- `deterministic_inputs`
- `_quality_debug`

## `brief.md`

### Purpose

Shortest human-readable snapshot for resume.

### Required sections

```text
# Debate Brief

- thread_id: ...
- goal: ...
- current round: ...
- current leading camps: ...
- deterministic inputs: ...
- next action: ...
```

## `round-1-seed.json`

### Purpose

Stores blind first pass outputs from all selected members.

### Required shape

```json
{
  "schema": "opencode.debate.round1.v1",
  "thread_id": "20260615-example",
  "mission": {
    "MMS-MISSION": "debate-20260615-example-a8f31c2e",
    "MMS-TARGET": "unknown",
    "MMS-MODE": "debate",
    "MMS-SOURCE": "user-pasted"
  },
  "round": 1,
  "member_results": [
    {
      "member_id": "debate-gpt-5-5",
      "mission": {
        "MMS-MISSION": "debate-20260615-example-a8f31c2e",
        "MMS-TARGET": "unknown",
        "MMS-MODE": "debate",
        "MMS-SOURCE": "user-pasted"
      },
      "lens": "proponent",
      "stance": "independent debate profile",
      "claim": "debate should be separate from committee",
      "evidence": ["RFC boundary requires separation"],
      "risks": ["profile sprawl"],
      "recommended_path": "independent profile, reused roster infra",
      "confidence": 0.82,
      "pushback": ["do not hide debate under committee"],
      "quality_gate": "pass",
      "provenance": {
        "model": "gpt-5.5",
        "provider_id": "example",
        "route_source": "mms"
      }
    }
  ]
}
```

### Required per-member fields

- `member_id`
- `mission`
- `stance`
- `claim`
- `evidence`
- `risks`
- `recommended_path`
- `confidence`
- `pushback`
- `quality_gate`
- `provenance`

### Rules

- `pushback` is semantically required.
- `evidence` should prefer concrete artifacts/facts over vague preference.
- Missing required fields should degrade `quality_gate` to `warn` or `fail`.

## `round-2-clusters.json`

### Purpose

Host-owned clustering result after blind first pass.

### Required shape

```json
{
  "schema": "opencode.debate.round2.v1",
  "thread_id": "20260615-example",
  "mission": {
    "MMS-MISSION": "debate-20260615-example-a8f31c2e",
    "MMS-TARGET": "unknown",
    "MMS-MODE": "debate",
    "MMS-SOURCE": "user-pasted"
  },
  "round": 2,
  "clusters": [
    {
      "cluster_id": "A",
      "label": "independent profile",
      "members": ["debate-gpt-5-5", "debate-glm-5-2"],
      "summary": "keep debate separate from committee",
      "strongest_evidence": ["workflow semantics differ"]
    }
  ],
  "open_conflicts": ["profile vs skill-first rollout"]
}
```

## `round-3-crossfire.json`

### Purpose

Stores opponent-summary rebuttal outputs.

### Required shape

```json
{
  "schema": "opencode.debate.round3.v1",
  "thread_id": "20260615-example",
  "mission": {
    "MMS-MISSION": "debate-20260615-example-a8f31c2e",
    "MMS-TARGET": "unknown",
    "MMS-MODE": "debate",
    "MMS-SOURCE": "user-pasted"
  },
  "round": 3,
  "member_results": [
    {
      "member_id": "debate-gpt-5-5",
      "mission": {
        "MMS-MISSION": "debate-20260615-example-a8f31c2e",
        "MMS-TARGET": "unknown",
        "MMS-MODE": "debate",
        "MMS-SOURCE": "user-pasted"
      },
      "opponent_strongest_point": "skill-first rollout reduces risk",
      "my_rebuttal": "it weakens public product surface",
      "what_i_accept": ["risk is lower"],
      "what_i_still_reject": ["it hides the workflow"],
      "what_evidence_would_change_my_mind": ["proof that skill usage is discoverable enough"],
      "quality_gate": "pass",
      "provenance": {
        "model": "gpt-5.5"
      }
    }
  ]
}
```

### Rules

- Do not attach full opponent transcript.
- Use strongest-opposing-case summaries only.

## `round-4-revision.json`

### Purpose

Stores stance updates after crossfire.

### Required shape

```json
{
  "schema": "opencode.debate.round4.v1",
  "thread_id": "20260615-example",
  "mission": {
    "MMS-MISSION": "debate-20260615-example-a8f31c2e",
    "MMS-TARGET": "unknown",
    "MMS-MODE": "debate",
    "MMS-SOURCE": "user-pasted"
  },
  "round": 4,
  "member_results": [
    {
      "member_id": "debate-gpt-5-5",
      "mission": {
        "MMS-MISSION": "debate-20260615-example-a8f31c2e",
        "MMS-TARGET": "unknown",
        "MMS-MODE": "debate",
        "MMS-SOURCE": "user-pasted"
      },
      "final_stance": "independent profile",
      "stance_shift": "unchanged",
      "shift_reason": "opposing case lowered risk concerns but not enough to change boundary judgment",
      "confidence": 0.79,
      "quality_gate": "pass",
      "provenance": {
        "model": "gpt-5.5"
      }
    }
  ]
}
```

## `resolution.json`

### Purpose

Final machine-readable outcome of the debate thread.

### Required shape

```json
{
  "schema": "opencode.debate.result.v1",
  "thread_id": "20260615-example",
  "mission": {
    "MMS-MISSION": "debate-20260615-example-a8f31c2e",
    "MMS-TARGET": "unknown",
    "MMS-MODE": "debate",
    "MMS-SOURCE": "user-pasted"
  },
  "status": "resolved",
  "resolution_state": "leaning",
  "quality_gate": "pass",
  "disagreement_flags": ["fix_conflict"],
  "deterministic_inputs": ["tests passed", "no request-root dependency found"],
  "synthesis_strategy": "host_authored",
  "synthesized_by": "debate-host",
  "synthesis_attempted_by": "debate-host",
  "resolution_reason": "most members converged on separate profile, but implementation depth still differs",
  "recommended_next_step": "write state/result contract and host rubric before code changes",
  "better_options": ["start with minimal 3-round workflow"],
  "pushback": ["do not over-import Hive runtime"],
  "risks": ["fake convergence if disagreement flags are ignored"],
  "open_questions": ["should v1 use host-only synthesis or optional synthesizer model"],
  "clusters": [
    {
      "cluster_id": "A",
      "label": "independent profile",
      "members": ["debate-gpt-5-5", "debate-kimi-k2-7"]
    }
  ],
  "stance_shifts": [
    {
      "member_id": "debate-mimo-v2-5-pro",
      "previous_stance": "skill-first",
      "final_stance": "independent profile",
      "stance_shift": "switched"
    }
  ],
  "provenance": {
    "source_schema": "opencode.debate.round4.v1",
    "source_path": ".ai/debate/<thread-id>/round-4-revision.json"
  },
  "ingested_at": "2026-06-15T12:00:00Z"
}
```

### Required fields

- `schema`
- `thread_id`
- `mission`
- `status`
- `resolution_state`
- `quality_gate`
- `disagreement_flags`
- `synthesis_strategy`
- `resolution_reason`
- `recommended_next_step`
- `provenance`
- `ingested_at`

### Optional but recommended fields

- `deterministic_inputs`
- `synthesized_by`
- `synthesis_attempted_by`
- `better_options`
- `pushback`
- `risks`
- `open_questions`
- `clusters`
- `stance_shifts`

## `resolution.md`

### Purpose

Human-readable closeout view.

### Required sections

```text
# Debate Resolution

- thread_id: ...
- resolution_state: ...
- quality_gate: ...
- disagreement_flags: ...

## Main judgment
...

## Pushback retained
...

## Better options
...

## Recommended next step
...
```

## Validation rules

### Minimum pass rules

- `thread_id` must be present in every artifact
- every round artifact must have matching `schema`
- `round-1-seed.json` must have at least 2 valid member results
- every member result must carry `quality_gate`
- `resolution.json` must carry `resolution_state`, `quality_gate`, and
  `disagreement_flags`

### Failure rules

Mark `quality_gate=fail` if:

- fewer than 2 valid member results exist
- required fields are missing from final resolution
- `resolution_state=converged` while `conclusion_opposite` or
  `deterministic_vs_opinion` remains present
- provenance/source fields are absent in final resolution

## Out of scope for v1

- native room transport
- background side-lane promises
- automatic model learning/scoring
- committee vote files
- external formal quorum semantics
