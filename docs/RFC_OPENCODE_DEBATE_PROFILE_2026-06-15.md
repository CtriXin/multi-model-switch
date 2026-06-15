# OpenCode Debate Profile RFC

Date: 2026-06-15
Owner: Codex
CLI: opencode / mmf
Model: GPT-5.4
Status: draft for issue + implementation planning

## Executive Summary

This RFC proposes a new MMS OpenCode `debate` profile.

It is intentionally **not** a new `committee` mode and it does **not** reuse
committee workflow semantics. It only borrows the already-validated MMS/OpenCode
surface for:

- host + selected subagent launch shape in TUI
- session-local roster generation
- provider/model routing and fallback wiring

The proposed `debate` profile is a strong, explicit workflow for structured
multi-model argument, not generic deliberation and not legacy `discuss` revival.

Target value:

- blind first pass before anchoring bias appears
- explicit clash between competing directions
- stance update after rebuttal
- honest internal conclusion instead of fake consensus

Target conclusion states:

- `converged`
- `leaning`
- `split_human_required`
- `insufficient_evidence`

## User Intent

The user wants a strong profile for structured model debate.

Desired experience:

- Ask one question to several models with the same compact packet.
- Force blind first pass before sharing any opposing view.
- Let host cluster positions into camps or distinct lines of argument.
- Run one or more rebuttal rounds with strongest-opponent summaries.
- Allow members to keep, soften, or reverse their stance.
- Produce an internal conclusion that can admit unresolved conflict.

This is closer to controlled debate than to committee tally, chat, or free-form
group discussion.

## Non-Goals

- Do not turn `committee` into a debate engine.
- Do not revive legacy `mms discuss` surface or semantics.
- Do not claim OpenCode has native direct subagent-to-subagent conversation.
- Do not require OpenCode core changes in v1.
- Do not interfere with `agent`, `review`, `committee`, `omo`, or `raw`.

## Why This Is Not Committee

Current `committee` is a general host for independent judgment. Its host prompt
defines Gate mode and Estimate mode, keeps the host boundary narrow, and says it
should not assume external request-root workflows by default.

That is the correct contract for committee, but it is the wrong contract for
debate.

`debate` needs different semantics:

- multiple rounds by design
- controlled exposure to opposing arguments
- stance-shift tracking
- internal conclusion states other than approve/reject/modify
- explicit permission for “I was persuaded by the other side”

So the boundary is:

- `committee`: independent judgment + tally + synthesis
- `debate`: blind seed + clash + revision + resolution state

The two profiles may share roster infrastructure, but they must not share host
workflow semantics.

## Current Platform Facts

The proposal is grounded in these already-verified facts:

1. OpenCode profile wiring already exists through `OPENCODE_PROFILE_OPTIONS` and
   `apply_opencode_profile()`.
2. Agent config supports `tools`, `permission`, `mode`, `steps`, and
   `maxSteps`.
3. Session prompt input supports `SubtaskPartInput { prompt, description, agent,
   model?, command? }` and `AgentPartInput { name }`.
4. Session APIs already expose `prompt_async`, `children`, `message`, and
   `todo` endpoints.
5. OpenCode can run subagents in parallel, but built-in Task join behavior is
   not a true background side lane.
6. Current roster override is still limited: it supports
   `preset/enabled/provider/model/route_policy/priority/description/prompt`, but
   not custom `tools`/`permission` per roster entry.
7. Legacy `chat`/`discuss` surfaces are intentionally maintenance-only and must
   not be silently revived.

Relevant repo references:

- `mms_opencode_profiles.py`
- `mms_opencode_agents.py`
- `mms_opencode_roster.py`
- `docs/RFC_OPENCODE_SIDE_RUNNER_PILOT_2026-06-14.md`
- `docs/legacy/CHAT_DISCUSS_PRODUCT_SPEC.md`
- `tests/test_legacy_surface_cleanup.py`

## Product Shape

### Public Profile

Planned public profile name:

- `debate`

Planned launch shape:

```text
opencode --pure --agent debate-host -m mms-builder_primary/<model>
```

Config source:

- MMS-generated session-local `opencode.json`

Use case:

- structured multi-model design/architecture/product debate
- disagreement surfacing before implementation
- controlled adversarial comparison between plausible directions

### TUI Surface

`debate` should reuse only one thing from `committee`:

- the host + selected subagent model picker experience

It should not reuse:

- committee Gate mode vocabulary
- committee Estimate mode output contract
- committee host prompt
- committee advisory-ballot semantics

## Key Design Questions

These questions should stay explicit during implementation instead of being
silently decided inside prompts:

1. How much of `a2a` should become first-class `debate` behavior?
   - only blind first pass?
   - also lens-specific packets?
   - also verdict vocabulary?
2. How much of `agent-discuss` should become `debate` state machinery?
   - only distilled packet + thread state?
   - also resume semantics?
   - also quality-gate style output validation?
3. Should `debate` resolution be purely host-authored, or should one dedicated
   synthesizer model always perform the final tie-break pass?
4. How many rounds are enough before `split_human_required` should trigger by
   default?
5. What deterministic signals must remain outside debate opinion, even when
   several models agree?

The current answer for v1 is conservative:

- absorb ideas, not old surfaces
- keep round count small
- prefer explicit failure/uncertainty states over fake closure
- keep deterministic facts separate from model opinion

## Cross-Project Capability Harvest

The older ideas from `a2a`, `agent-discuss`, Moebius, and Hive are useful, but
they should be harvested as capabilities rather than restored as product
surfaces.

### From `a2a`

Useful imports:

- blind first pass before bias enters
- adversarial framing instead of soft summarization
- lens-aware packet shaping
- explicit verdict/status language

Relevant evidence already reflected in prior analysis:

- structured lens outputs and verdict framing remain the strongest reusable part

### From `agent-discuss`

Useful imports:

- distilled packet instead of transcript replay
- thread-local state and resume mindset
- pushback as a required semantic field
- better options / recommended next step / open questions structure

The debate RFC keeps these as state/artifact ideas, not as a revival of legacy
`discuss` UX.

### From Moebius

Moebius already normalizes both discussion-style and a2a-style outputs into
durable schemas.

Useful imports:

- `quality_gate` as a first-class result quality signal
- `thread_id` as a durable unit of debate continuity
- `pushback`, `risks`, `better_options`, and `recommended_next_step` as
  structured fields
- `lens_results` and explicit verdict ingestion for adversarial review outputs

Evidence:

- `moebius/scripts/public_slot_invoke.py:405`-`438`
- `moebius/scripts/public_slot_invoke.py:441`-`470`
- `moebius/scripts/public_sequence.py:494`-`496`

What this suggests for `debate`:

- resolution artifacts should include a quality signal, not just a conclusion
- debate should preserve pushback and better-option fields even when it reaches
  `leaning` or `converged`
- debate can use lens-specific subagents later without changing the public
  profile concept

### From Hive

Hive has several useful partial capabilities that map well onto `debate`.

Useful imports:

- authority topology ladder: `single -> pair -> synthesizer pass`
- disagreement flags instead of binary agreement checks only
- explicit separation between deterministic failure and model opinion
- room/thread/card snapshots for debate state visibility
- discuss escalation with `quality_gate`, `thread_id`, and escalation metadata

Evidence:

- `hive/docs/authority-layer/README.md:24`-`34`
- `hive/docs/authority-layer/README.md:74`-`90`
- `hive/tests/reviewer-authority.test.ts:282`-`345`
- `hive/tests/reviewer-authority.test.ts:512`-`589`
- `hive/tests/disagreement-detector.test.ts:18`-`118`
- `hive/tests/worker-discuss-transport.test.ts:208`-`309`
- `hive/tests/discuss-gate.test.ts:224`-`278`
- `hive/src/agentbus/orchestrator.ts:127`-`194`

What this suggests for `debate`:

- do not reduce debate to naive majority vote
- record disagreement types, not just conclusion states
- preserve a clear line between model argument and deterministic proof
- expose thread/room-like progress snapshots in future status surfaces

## Capabilities To Borrow From Moebius/Hive In V1

The likely best V1 imports are:

1. Moebius-style result schema fields:
   - `quality_gate`
   - `thread_id`
   - `pushback`
   - `better_options`
   - `recommended_next_step`
2. Hive-style disagreement classification:
   - conclusion opposite
   - severity mismatch
   - fix conflict
   - deterministic vs opinion
3. Hive-style authority posture:
   - default small topology first
   - escalate only when disagreement or low confidence justifies it
4. Hive-style thread/card progress mindset for future web/TUI visibility

These should guide the `debate` data contract even before any UI upgrades ship.

## Workflow

### Round 0 — Packet Distill

Host prepares a compact packet:

- goal
- current understanding
- constraints
- optional artifacts/files
- explicit question to debate
- explicit decision boundary

This packet must stay lean. The workflow should prefer distilled context over
transcript replay.

### Round 1 — Blind First Pass

Each member receives the same packet independently.

Required output fields:

- `stance`
- `claim`
- `evidence`
- `risks`
- `recommended_path`
- `confidence`

No member sees other members in this round.

### Round 2 — Stance Cluster

Host groups outputs into camps or distinct lines, for example:

- A: separate profile
- B: committee mode
- C: skill-first pilot
- D: independent profile + reused infra

This stage is host-owned. There is no requirement to force a binary split.

### Round 3 — Crossfire

Each member receives only the strongest opposing case, not the full transcript.

Required output fields:

- `opponent_strongest_point`
- `my_rebuttal`
- `what_i_accept`
- `what_i_still_reject`
- `what_evidence_would_change_my_mind`

### Round 4 — Revision

Each member updates its own stance:

- `unchanged`
- `softened`
- `switched`

And explains why.

### Round 5 — Resolution

Host produces one internal conclusion state:

- `converged`
- `leaning`
- `split_human_required`
- `insufficient_evidence`

Host must not fake convergence when disagreement remains real.

## Internal State And Artifacts

The profile should use a debate-specific namespace, not committee vote files.

Suggested project-local layout:

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

Suggested `state.json` fields:

```json
{
  "thread_id": "20260615-example",
  "goal": "decision under debate",
  "question": "main debate prompt",
  "constraints": ["constraint 1"],
  "selected_members": ["debate-gpt-5-5", "debate-deepseek-v4-pro"],
  "round": 1,
  "current_clusters": ["A", "D"],
  "status": "running",
  "latest_artifact": ".ai/debate/<thread-id>/round-1-seed.json"
}
```

This intentionally borrows the thread/state mindset from the old
`agent-discuss` idea without reviving the old surface.

Suggested optional resolution fields inspired by Moebius/Hive:

```json
{
  "quality_gate": "pass|warn|fail",
  "disagreement_flags": ["conclusion_opposite", "fix_conflict"],
  "deterministic_inputs": ["tests failed", "smoke passed"],
  "recommended_next_step": "human arbitration or implementation path",
  "better_options": ["alternative A", "alternative B"]
}
```

## What V1 Can Support Now

OpenCode is already strong enough for these parts:

- independent blind first pass via subtask dispatch
- selected host + selected subagent TUI launch shape
- session-local agent roster generation
- compact packet passing
- artifact-first output if host asks for structured files
- one or more rebuttal rounds orchestrated by host
- honest final conclusion state

## What V1 Cannot Pretend To Solve Yet

V1 should be explicit about current limits:

- no native direct agent-to-agent chat lane
- no guaranteed non-blocking background side lane from built-in Task alone
- no built-in stance clustering primitive
- no roster-level custom `tools`/`permission` override yet
- no reason to pretend debate output is a formal committee vote

## MVP Proposal

### MVP-1

Implement a public `debate` profile with:

- its own `debate-host`
- a debate-specific prompt contract
- selected multi-model roster in TUI
- 3-round flow: blind seed -> crossfire -> resolution

### MVP-2

Add project-local debate artifacts:

- `.ai/debate/<thread-id>/...`
- minimal `state.json`
- `resolution.json` + `resolution.md`

### MVP-3

Only after the profile proves useful, consider:

- managed side-session/plugin support for longer debates
- richer stance clustering heuristics
- roster-level tool/permission overrides for debate members

## v1 Contracts

The first implementation should treat these as required companion specs:

- `docs/DEBATE_STATE_RESULT_CONTRACT_v1.md`
- `docs/DEBATE_HOST_RESOLUTION_RUBRIC_v1.md`

They are the minimum protection against profile drift and fake convergence.

### Contract intent

- `DEBATE_STATE_RESULT_CONTRACT_v1.md` defines durable artifacts, enum values,
  required fields, and validation rules.
- `DEBATE_HOST_RESOLUTION_RUBRIC_v1.md` defines how host moves from round
  artifacts to `converged | leaning | split_human_required |
  insufficient_evidence`.

### v1 guardrails from the contract set

- no transcript-first resume
- required `pushback`
- required `quality_gate`
- required `disagreement_flags`
- deterministic facts stay separate from model opinion
- explicit synthesis honesty fields

## Boundaries With Other Profiles

### `agent`

- `agent` stays execution-first.
- `debate` stays decision-first.

### `review`

- `review` stays request-root review workflow.
- `debate` stays argument workflow.

### `committee`

- `committee` stays independent judgment/tally.
- `debate` stays multi-round clash/revision.
- `debate` must not write committee vote files or decision files.

### `omo` and `raw`

- unchanged

## Draft Variants Considered

### Draft A — New `committee` mode

Rejected.

Reason:

- pollutes committee semantics
- enlarges committee host prompt too much
- mixes independent ballot logic with multi-round stance revision

### Draft B — Fully standalone profile with fully separate infrastructure

Partially rejected.

Reason:

- profile is correct
- but re-implementing roster/dispatch from zero is unnecessary

### Draft C — Skill/command first, no profile

Useful as a pilot idea, but not the chosen primary shape.

Reason:

- too weak as a public surface
- underuses the existing MMS/OpenCode profile selector UX

### Draft D — Independent `debate` profile, borrowing only the host +
subagent selection surface and roster plumbing

Chosen direction.

Reason:

- strong boundary
- strong UX
- low interference with other profiles
- maximum reuse of already-validated TUI/roster/routing pieces

## Effective Subagent Feedback Digest

This appendix records the useful content from the deliberation rounds that led to
this RFC. It is intentionally a structured digest, not a raw transcript dump.

### Round 1 — Restore old ideas into MMS/OpenCode

#### `committee-deepseek-v4-pro-3`

- Recommendation: standalone/near-standalone direction
- Strong point: lifecycle mismatch is the real boundary
- Useful takeaway: `agent-discuss`-style thread state should not be flattened
  into one-pass committee semantics

#### `committee-glm-5-2-3`

- Recommendation: hybrid
- Strong point: only stateless reusable parts should be absorbed; persistent
  thread semantics should stay separate
- Useful takeaway: committee must stay a general host, not a mega workflow

#### `committee-gpt-5-5-3`

- Recommendation: hybrid
- Strong point: `a2a` value is in lens/verdict/rubric; `agent-discuss` value is
  in stateful thread/process
- Useful takeaway: split reusable process from reusable runtime

#### `committee-kimi-k2-7-code-3`

- Recommendation: hybrid
- Strong point: profile wiring is easy; the hard part is preserving clean user
  semantics
- Useful takeaway: phase rollout can start from profile-level orchestration

#### `committee-mimo-v2-5-pro-3`

- Recommendation: hybrid, more conservative rollout
- Strong point: runtime/orchestration cost must be kept visible
- Useful takeaway: do not oversell native background behavior

#### `committee-minimax-m3-3`

- Recommendation: hybrid
- Strong point: naming and migration semantics matter
- Useful takeaway: do not revive `discuss` naming under legacy cleanup rules

#### `committee-qwen3-7-max-3`

- Recommendation: hybrid
- Strong point: host prompt complexity is already a risk
- Useful takeaway: debate must not be hidden inside committee prompt growth

### Round 2 — Debate capability and boundary validation

#### `committee-gpt-5-5-3`

- Recommendation: independent `debate` profile + committee infra reuse
- Strong point: debate is its own epistemic process: blind pass -> clustering ->
  rebuttal -> stance update -> conclusion state
- Useful takeaway: this is profile-grade workflow, not just a helper command

#### `committee-kimi-k2-7-code-3`

- Recommendation: independent `debate` profile + committee infra reuse
- Strong point: profile registration is cheap, while semantics separation is the
  actual product win
- Useful takeaway: debate can and should have its own workflow ID and host

#### `committee-minimax-m3-3`

- Recommendation: independent `debate` profile + committee infra reuse
- Strong point: committee advisory/tally rules conflict with debate convergence
  semantics
- Useful takeaway: keep debate conclusion separate from any formal vote path

#### `committee-mimo-v2-5-pro-3`

- Recommendation: skill/command first
- Strong point: orchestration is the hard part, not profile registration
- Useful takeaway: keep MVP narrow and honest about platform limits

### Round 3 — Capability harvest from `a2a` / `agent-discuss` / Moebius / Hive

This round asked all seven members a narrower question: which capabilities should
`debate` borrow now, and which tempting pieces should stay out of v1.

#### Cross-member convergence

Strong convergence appeared on these imports:

- from `a2a`: blind first pass, adversarial framing, and lens-shaped packet
  control
- from `agent-discuss`: distilled packet, thread-local state, required
  `pushback`, and debate-local quality signaling
- from Moebius: normalized result schema fields such as `thread_id`,
  `quality_gate`, `pushback`, `better_options`, `recommended_next_step`, and
  provenance/source fields
- from Hive: disagreement flag taxonomy and explicit separation between
  deterministic facts and model opinion

Strong convergence also appeared on these exclusions for v1:

- do not borrow a2a token bridge or cross-CLI dispatch runtime
- do not borrow `agent-discuss` adapter routing or old surface semantics
- do not borrow Hive AgentBus room lifecycle or naive majority-vote synthesis
- do not borrow Moebius full loop / trace governance / commit lifecycle rules

#### `committee-deepseek-v4-pro-3`

- Strongest recommendation: only three pieces are non-negotiable in v1:
  blind-first-pass, required `pushback`, and `deterministic_vs_opinion`
- Most valuable missing piece: append-only stance-shift ledger showing what
  evidence changed whose mind

#### `committee-glm-5-2-3`

- Strongest recommendation: import disagreement flags as first-class schema and
  keep deterministic facts outside model opinion
- Most valuable missing piece: a host-side rubric that mechanically maps stance
  distribution and disagreement flags into final resolution states

#### `committee-gpt-5-5-3`

- Strongest recommendation: borrow process and schema, not transport or old
  product surfaces
- Most valuable missing piece: strict `debate.result.v1` and `debate.state.v1`
  schemas plus resolution classifier tests before richer UI or more agents

#### `committee-kimi-k2-7-code-3`

- Strongest recommendation: debate should reuse thread-state and deterministic
  disagreement handling, but not old adapter/runtime assumptions
- Most valuable missing piece: an explicit host resolution rubric with stance
  distribution rules and confidence thresholds

#### `committee-mimo-v2-5-pro-3`

- Strongest recommendation: keep debate host as the synthesizer in v1 and avoid
  Hive-style room/runtime complexity
- Most valuable missing piece: deterministic stance-shift tracker that explains
  why members softened or switched

#### `committee-minimax-m3-3`

- Strongest recommendation: borrow only capability seeds, not product shapes;
  keep fields such as `quality_gate`, `thread_id`, and `disagreement_flags`
  while rejecting transport/runtime imports
- Most valuable missing piece: lightweight in-process evaluator that prevents
  host-authored fake convergence by enforcing disagreement/deterministic checks

#### `committee-qwen3-7-max-3`

- Strongest recommendation: debate should import required `pushback`,
  `deterministic_vs_opinion`, synthesis honesty markers, and perspective-shaped
  packets
- Most valuable missing piece: per-member perspective/lens assignment with
  packet shaping so disagreement is structural, not accidental

## Initial Issue Scope

The implementation issue should ask for:

1. add public `debate` profile wiring
2. add `debate-host` and debate member prompt contract
3. reuse committee-style TUI member selection only
4. add debate-local artifact/state layout
5. keep strict non-interference with `committee`
6. document current platform limits and no-fake-background guarantee
7. define which Moebius/Hive-style fields enter the initial debate result schema
8. define explicit open questions for a2a/discuss capability harvesting

## Final Decision

Proceed with a new public `debate` profile.

This profile:

- is separate from `committee`
- borrows only the validated MMS/OpenCode host + subagent selection surface
- absorbs the useful ideas from `a2a` and `agent-discuss`
- keeps a strong, explicit workflow contract
- does not silently alter other profiles
