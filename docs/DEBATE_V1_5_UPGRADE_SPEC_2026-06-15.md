# Debate Profile v1.5 — Upgrade Spec (sharpen vs committee)

Date: 2026-06-15
Status: proposed (awaiting human sign-off before implementation)
Owner: human
Relates to:

- Issue #49 (tracking issue for this upgrade)
- Issue #11 (parent debate-profile RFC)
- PR #41 / issue #40 (MMS-MISSION cross-session correlation, merged)
- PR #42 (committee copy-forward output order, open)
- `docs/DEBATE_V1_SCOPE_DECISIONS_2026-06-15.md` (this spec revises two of its decisions; see "Decision Revisions")
- `docs/DEBATE_STATE_RESULT_CONTRACT_v1.md`
- `docs/DEBATE_HOST_RESOLUTION_RUBRIC_v1.md`
- `mms_opencode_agents.py` (`debate-host` prompt)

## Problem

v1 debate currently feels close to "committee run twice". Three reasons:

1. Both start with a blind independent pass (committee blind verdict ≈ debate
   round-1 seed).
2. v1 crossfire is summary-injection, not real dialogue — platform has "no
   native agent-to-agent chat lane", so each member just writes one more
   context-fed pass.
3. Both close with host synthesis.

The only v1 differentiators are `stance_shift` tracking, the resolution-state
vocabulary, and one opposing-summary round. That margin is thin and invisible
to the human.

## North star

Maximize what committee **structurally cannot** do:

- committee = parallel independent judgment, output = consensus / tally; members
  stay honest and isolated.
- debate = serial adversarial pressure, output = the conclusion that survives
  rebuttal + who changed their mind on what evidence.

Every v1.5 upgrade pushes on adversarial exposure, persuasion tracking, and
merit-based adjudication — the exact axes committee can't replicate.

## Host Authority Contract (hard-coded, highest priority)

The host is **not** the top decision authority and **not** a voting participant.
It is a dispatcher + faithful summarizer + rubric referee. This contract is
baked into the profile prompt so the user never has to restate "as host:
dispatch, don't modify, only summarize" on each invocation.

Hard-coded rules:

- **Authority order (highest first):** `human > deterministic facts > rubric
  applied to member outputs > host`. The host never overrides anything above it.
- **Dispatch:** send the user's one-line direction / packet to the fixed
  selected roster. Never answer in a member's place; never invent a member's
  missing position.
- **No-rewrite (lossless):** never modify, soften, beautify, merge-away, or drop
  member substance. Aggregate only by cluster + quote + attribution.
  Disagreement is preserved as-is.
- **Summarize, do not adjudicate by preference:** here "synthesize" means a
  faithful, substance-preserving summary plus the *rubric-derived*
  `resolution_state` — **not** the host's own verdict. The host casts no vote and
  injects no personal opinion.
- **One-shot trigger:** invoking the profile already means "host dispatches to
  the roster and summarizes". The role is fixed; the user does not re-instruct
  it.

Reframe of `synthesis_strategy=host_authored`: it means **"host recorded the
rubric-derived result"**, not "host authored its own judgment". The resolution
state is a deterministic function of member artifacts via the rubric; the host
executes the rubric, it does not decide by preference. (The bounded synthesizer
in ⑤ stays advisory and human-surfaced, never an override.)

## Per-profile host role and triggers (hard-coded)

The Host Authority Contract is shared, but each profile bakes in its own default
trigger and permission ceiling, so the user never restates intent:

- **review**: on a PR / request-root, the host knows to dispatch reviewers and
  aggregate a review verdict. Weak host.
- **committee**: on a thing-to-judge, the host dispatches, tallies, and produces
  a clean copy-forward packet. Weak host **+ bounded opt-in execution**: only on
  explicit user grant may it write vote files / `decision.md` / run a quorum
  checker (already in the v1 committee prompt). Default = no writes.
- **debate**: on a fork / proposition, the host runs the rounds and records the
  rubric-derived resolution. Weak host.
- **execute / agent**: the host does the work itself. This is where the user
  goes when they want the host to act, not orchestrate.

Rule: if the user wants the host to "just handle it", that is the execute
profile — not review/committee/debate. Those three keep weak hosts; committee is
the only one of the three with a bounded, opt-in sliver of execution.

## Copy-forward packet (clean handoff to execute)

A weakened host separates reader-only meta from a clean copy-forward packet, so
its output can be pasted straight into the execute profile:

1. **Human review notes** (reader-only): status, risks / dissent, scorecard.
2. **Copy-forward packet**: clean, self-contained, labeled safe-to-forward; no
   scorecard / meta / host-private advice.
3. **Host recommendation**: at the very bottom.

Committee already implements this (PR #42, currently open with conflicts).
Debate's `resolution.md` should follow the same split: a clean forwardable
resolution packet separate from the reader-only persuasion ledger / scorecard.

The MMS-MISSION correlation id (PR #41 / issue #40, merged) must stay in **both**
the reader notes and the copy-forward packet, so a forwarded packet remains
linkable across sessions.

## Scope of v1.5

- Full, prompt-level: ① assigned sides, ② persuasion ledger, ③ trigger-contract
  split.
- Bounded, partial pull-forward from v2: ④ directed pivot cross-examination
  (capped at 1 volley), ⑤ conditional advisory synthesizer-judge (split/leaning
  only).
- Still v2 / not in scope: full multi-turn agent-to-agent debate via managed
  side-sessions, always-on synthesizer, native room transport, live dashboard,
  model-learning from outcomes.

## ③ Trigger-contract split (input shape)

The cheapest reason debate feels like committee: both are fed the same kind of
input. Fix the contract:

- **debate input = a fork or proposition**: "A vs B", "should we do X",
  "which direction before implementation".
- **committee input = an artifact to judge**: "review this PR/plan/output".

Host rule: if a debate thread is opened with a pure judge-this-artifact task and
no fork, `debate-host` must either reframe it into an explicit proposition or
hand it back as "use committee". Profile summaries in `mms_opencode_profiles.py`
should state this split so selection is unambiguous.

## ① Assigned adversarial sides

Committee members must give honest independent verdicts. Debate may **assign**
sides — this is the single biggest structural wedge.

- `debate-host` MAY assign a role per member: `proponent | opponent | steelman |
  free`. Seed and crossfire are argued from the assigned role.
- **Two-phase honesty**: assigned-advocacy rounds are explicitly labeled; the
  final revision round requires each member's `final_stance` to be their
  **honest post-debate position**, recorded separately from the role they were
  assigned, so sophistry is visible and never counted as conviction.

Contract additions:

- round-1 / round-3 member result: `assigned_role`
  (`proponent | opponent | steelman | free`).
- round-4 / resolution: `stance_authenticity` (`honest | assigned`) so the
  rubric never treats assigned advocacy as genuine agreement.

Guardrail: assigned sides must not corrupt deterministic facts. Deterministic
inputs stay outside assigned advocacy and still outrank opinion.

## ② Persuasion ledger (first-class, surfaced)

The "most valuable missing piece" from the committee harvest: an append-only
record of what evidence changed whose mind.

- New artifact `persuasion-ledger.json` (or embed as `persuasion_ledger` in
  `resolution.json`). Each entry:
  `{ member_id, from_stance, to_stance, trigger_evidence, round }`.
- Resolution weighting: a position that **survived attack** or **won converts**
  weighs higher than an unchallenged prior. `resolution_reason` must cite the
  ledger, not just camp counts.
- `resolution.md` gains a "Who moved and why" section, surfaced to the human.

Why committee can't: its blind pass has no exposure, so there is no movement to
track.

## ④ Directed pivot cross-examination (bounded partial of v2)

Upgrade crossfire from generic summary to targeted, and allow one focused extra
volley on the single pivot.

- Crossfire becomes **claim-targeted**: host pairs each member with the single
  strongest counter aimed at *their specific claim*, not a generic camp summary.
- **One optional directed volley** on the pivot, fired only when, after round-3,
  exactly one core conflict (`conclusion_opposite` or `fix_conflict`) remains
  between exactly two high-confidence camps. Hard cap = 1 exchange, deterministic
  trigger.
- Optional artifact `round-3b-pivot.json`.

This is a bounded directed exchange, **not** open-ended dialogue; full
multi-turn cross-examination still needs v2 side-sessions.

## ⑤ Conditional advisory synthesizer-judge (bounded partial of v2)

Default stays host-authored. Pull forward a *bounded* synthesizer.

- A dedicated synthesizer model runs **only** when host resolution is
  `split_human_required` or `leaning` AND `quality_gate=pass`.
- It produces an **advisory** merit adjudication: which argument survived best on
  the merits, with reasons and the dissent still standing. It does **not** change
  `resolution_state` and does **not** override the conservative rubric or
  deterministic overrides.

Contract additions:

- `synthesis_strategy = model` allowed in this bounded path; `synthesized_by`
  records the real synthesizer model id honestly.
- new `merit_adjudication`:
  `{ winning_argument, reasons, dissent_still_standing }`.

Why committee can't: a tally is not a merit adjudication of clashing arguments.

## Retained v1 guardrails (unchanged)

- in-prompt anti-fake-convergence self-check (still no validator program; new
  artifacts are still host-written, no helper command);
- deterministic facts outrank model opinion;
- conservative priority order
  `insufficient_evidence > split_human_required > converged > leaning`;
- no committee vote files / verdict vocabulary / request roots;
- golden-goal early stop still requires deterministic triggers.

## Decision Revisions (explicit — vs `DEBATE_V1_SCOPE_DECISIONS_2026-06-15.md`)

These two v1 decisions are consciously refined here, not silently dropped:

- **R1 — "no extra time"** → refined to **"no *open-ended* extra time; at most
  one bounded, deterministically-triggered pivot volley (④)."** Auto-appending
  generic rounds is still forbidden.
- **R2 — "synthesizer model deferred, v1 host_authored only" (Decision 3)** →
  refined to **"host_authored is the default; a bounded *advisory* synthesizer
  runs only on `split_human_required` / `leaning` (⑤)."** Always-on synthesizer
  is still v2.

## Contract / code deltas (for the implementation issue)

| Area | Change |
|---|---|
| `debate-host` prompt | hard-coded Host Authority Contract (dispatch + lossless summary + rubric referee, host not decider); trigger-split reframing; optional `assigned_role`; two-phase honesty; claim-targeted crossfire + 1 pivot volley; conditional synthesizer trigger; cite persuasion ledger in resolution |
| profile summaries | state debate=fork vs committee=artifact split |
| contract doc | add `assigned_role`, `stance_authenticity`, `persuasion_ledger` / `persuasion-ledger.json`, `round-3b-pivot.json`, `merit_adjudication`; allow `synthesis_strategy=model` in bounded path |
| rubric doc | weight survived/converted positions over unchallenged priors; advisory synthesizer cannot override priority order or deterministic overrides |
| routing | a synthesizer model route, used only on the bounded path |

## Committee sibling change (separate, protected surface)

The same root problem exists in `committee-host`: its prompt currently says the
host "dispatches, verifies facts, collects ballots, tallies, and **synthesizes**"
(`mms_opencode_agents.py:960`) with no explicit no-rewrite / host-not-decider
contract — which is why the user restates "dispatch, don't modify, only
summarize" every time. The same Host Authority Contract should be mirrored into
`committee-host`.

But the committee host workflow is a protected surface (`AGENT_GUARDRAILS.md`).
So this is its **own** issue, not folded into the debate work, and needs
explicit human go-ahead before touching committee. The contract text is shared;
the landing path is separate.

## Implementation note

This is a behavior change touching `mms_opencode_agents.py` and the contract/
rubric docs, and adds a synthesizer route. Per repo workflow it must land via an
issue + isolated worktree + PR + committee review, not a direct dev edit.
