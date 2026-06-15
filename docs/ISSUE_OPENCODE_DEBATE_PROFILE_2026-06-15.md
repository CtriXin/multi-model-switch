# RFC: Add OpenCode `debate` profile

## Summary

Add a new public MMS OpenCode `debate` profile.

This profile is explicitly separate from `committee`. It should only reuse the
already-validated MMS/OpenCode host + selected-subagent TUI surface and session-
local roster/routing plumbing.

## Why

- We need a strong structured debate workflow, not just independent committee
  tally.
- The desired process is blind first pass -> stance cluster -> rebuttal ->
  stance update -> internal conclusion.
- Legacy `mms discuss` is maintenance-only; this should not revive that surface.
- `committee` must remain generic and must not absorb debate semantics.

## Required boundaries

- Do not change `committee` host workflow.
- Do not add debate as a hidden committee mode.
- Do not reuse committee vote files or committee decision artifacts.
- Do not interfere with `agent`, `review`, `committee`, `omo`, or `raw`.

## Proposed scope

1. Add public `debate` profile wiring in the OpenCode launcher profile system.
2. Add `debate-host` and debate-specific member prompt contract.
3. Reuse committee-style TUI member selection only.
4. Add debate-local artifact/state layout under `.ai/debate/<thread-id>/`.
5. Implement v1 three-round flow:
   - blind seed
   - crossfire
   - resolution
6. Add explicit resolution states:
   - `converged`
   - `leaning`
   - `split_human_required`
   - `insufficient_evidence`
7. Document current OpenCode limitations clearly:
   - no native agent-to-agent chat lane
   - no fake background guarantee from built-in Task joins
   - no roster-level custom tools/permission override yet
8. Decide which borrowed capabilities become part of the initial debate schema.
9. Implement and follow the initial contract docs:
   - `docs/DEBATE_STATE_RESULT_CONTRACT_v1.md`
   - `docs/DEBATE_HOST_RESOLUTION_RUBRIC_v1.md`

## Explicit design questions

Please answer these during implementation planning, not implicitly inside prompt
iterations:

1. What exactly should `a2a` contribute to `debate`?
   - blind first pass only
   - lens packets
   - explicit verdict vocabulary
2. What exactly should `agent-discuss` contribute to `debate`?
   - packet distill only
   - thread state and resume
   - quality-gate style validation
3. Should final resolution always use host-only synthesis, or should there be an
   optional dedicated synthesizer model pass?
4. Which disagreement flags should be first-class in v1?
5. Which deterministic signals must override model convergence when they clash?

## Cross-project capability hints

The implementation should explicitly review what to borrow from Moebius and
Hive, without importing their full product semantics.

Suggested borrow targets:

- From Moebius:
  - `quality_gate`
  - `thread_id`
  - `pushback`
  - `better_options`
  - `recommended_next_step`
  - `lens_results`
- From Hive:
  - `single -> pair -> synthesizer pass` escalation posture
  - disagreement flags such as `conclusion_opposite`, `fix_conflict`, and
    `deterministic_vs_opinion`
  - thread/room progress snapshot mindset
  - explicit separation between deterministic evidence and model opinion

## Latest committee harvest summary

All seven committee members reviewed the capability-harvest question.

Strong convergence:

- Borrow now:
  - from `a2a`: blind first pass, adversarial framing, lens-shaped packets
  - from `agent-discuss`: distilled packet, thread-local state, required
    `pushback`
  - from Moebius: `quality_gate`, `thread_id`, `better_options`,
    `recommended_next_step`, provenance/source fields
  - from Hive: `disagreement_flags`, `deterministic_vs_opinion`, synthesis
    honesty markers
- Do not borrow yet:
  - a2a token bridge / cross-CLI dispatch runtime
  - discuss adapter routing / legacy surface semantics
  - Hive AgentBus room lifecycle / majority-vote synthesis
  - Moebius full loop governance / trace lifecycle

Most requested next artifacts:

1. `debate.state.v1`
2. `debate.result.v1`
3. host resolution rubric
4. stance-shift tracking / anti-fake-convergence checks

Those contract/rubric docs now exist and should gate the first implementation
slice.

## Suggested implementation plan

### Phase 1

- Add `debate` profile entry and `apply_opencode_profile()` branch.
- Add `debate-host` with debate-only host prompt.
- Reuse selected multi-model roster flow from committee TUI.
- Wire host outputs to `docs/DEBATE_STATE_RESULT_CONTRACT_v1.md` and host
  decision behavior to `docs/DEBATE_HOST_RESOLUTION_RUBRIC_v1.md`.

### Phase 2

- Add debate-local artifact schema:
  - `brief.md`
  - `state.json`
  - `round-1-seed.json`
  - `round-2-clusters.json`
  - `round-3-crossfire.json`
  - `round-4-revision.json`
  - `resolution.json`
  - `resolution.md`

### Phase 3

- Evaluate whether managed side sessions/plugin support is needed for longer,
  non-blocking debates.

## References

- `docs/RFC_OPENCODE_DEBATE_PROFILE_2026-06-15.md`
- `docs/DEBATE_STATE_RESULT_CONTRACT_v1.md`
- `docs/DEBATE_HOST_RESOLUTION_RUBRIC_v1.md`
- `docs/RFC_OPENCODE_SIDE_RUNNER_PILOT_2026-06-14.md`
- `docs/legacy/CHAT_DISCUSS_PRODUCT_SPEC.md`
- `mms_opencode_profiles.py`
- `mms_opencode_agents.py`
- `mms_opencode_roster.py`
- `tests/test_legacy_surface_cleanup.py`
