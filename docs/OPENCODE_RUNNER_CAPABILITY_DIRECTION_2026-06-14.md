# OpenCode Runner Capability Direction

Date: 2026-06-14
Owner: Codex committee host
Status: frozen direction; phase-1 hook-fit spike returned partial_blocked

## Goal

This document lands the current decision trail around a recurring question:

- mimocode has several attractive runner-side capabilities;
- we do not want to become dependent on mimocode itself;
- we want to reuse as much as possible from the official OpenCode surface;
- we want the result to stay compatible with the two main iteration projects, `mommy` and `state-core`;
- we want a future path where the capability layer can be open-sourced, shared, and gradually replace selected runner responsibilities without becoming a new monolith.

This is not a product spec for a mimocode clone.
It is a direction memo for a runner-neutral capability layer with OpenCode as the first practical host.

## Source Inputs

### Local architecture inputs

The first five inputs below live in sibling repos under `/Users/xin/auto-skills/CtriXin-repo/`; this memo references them as architecture sources, not as files expected inside the current MMS worktree.

- `state-core/docs/decisions.md`
- `state-core/docs/runner-adapter-hooks.md`
- `state-core/docs/capability-registry.md`
- `mommy/SKILL.md`
- `mommy/references/routing.md`
- `docs/OPENCODE_LITE_LAUNCHER.md`
- `docs/CORE_LAUNCHER_SLIMMING_ROADMAP.md`
- `docs/HOST_CONTEXT_CONTRACT.md`

### Official OpenCode inputs

- `https://opencode.ai/docs/`
- `https://opencode.ai/docs/plugins/`
- `https://github.com/anomalyco/opencode`

### Committee inputs collected in this round

- runner feasibility round: `committee-gpt-5-5-7`, `committee-gemini-3-flash-agent-high-12`, `committee-qwen3-7-max-12`
- extraction/upstream round: `committee-gpt-5-5-7`, `committee-deepseek-v4-pro-7`, `committee-qwen3-7-max-12`
- official OpenCode leverage round: `committee-gpt-5-5-7`, `committee-deepseek-v4-pro-7`, `committee-qwen3-7-max-12`

## Hard Boundaries We Are Not Reopening

These come from the current `mommy` + `state-core` architecture and remain binding.

1. External harnesses are candidate runners, not workflow owners.
2. `state-core` owns canonical task-state and done-gate semantics.
3. `mommy` owns lifecycle routing and intake decisions, not done.
4. Runner adapters may consume `hydrate` / `read` / `report` / `advance`; they must not directly write task-state.
5. Valuable harness ideas may be reimplemented as runner-neutral primitives; source copy and owner drift are forbidden.

In other words: learn from runners, do not surrender authority to them.

## What The Earlier Runner Round Already Settled

The first committee round on "Should mimocode be a day-to-day runner with mommy + state-core?" did not approve direct adoption.

Consensus shape:

- `mimocode` may be treated as a candidate runner for narrow experiments.
- It must not become the default workflow authority.
- Its memory layer and any done/lifecycle ownership semantics conflict with our current architecture.
- The only acceptable path is adapter-first, with `state-core` and `mommy` remaining authoritative.

Operational takeaway:

- do not ship "use mimocode as our runner";
- do ship "extract useful runner-side capabilities into a neutral layer we own".

## Committee Summary: Extraction And OpenCode Fit

### 1. `committee-gpt-5-5-7`

Main conclusion:

- The extractable value is not mimocode-as-product; it is a set of reusable patterns.
- The right host shape is `OpenCode plugin + adapter + custom tools`, not a core transplant.

Best reusable parts it identified:

- lifecycle hook timing;
- payload allowlists for subagents;
- finish-to-done-gate bridge;
- compaction context injection;
- session-local skill/profile injection;
- runner compliance testing.

What it explicitly rejected:

- copying source/templates/prompts;
- moving memory ownership into the runner;
- putting `mommy` / `state-core` semantics into OpenCode core.

### 2. `committee-deepseek-v4-pro-7`

Main conclusion:

- The winning move is not "put mimocode into OpenCode".
- The winning move is "absorb mechanisms into an adapter-owned capability layer".

Best reusable parts it identified:

- budgeted hydrate projection;
- independent writer / scratch channel patterns;
- lifecycle-based memory separation;
- slot-scoped subagent context discipline.

What it emphasized:

- current bottleneck is still our substrate and slot completion, not runner scarcity;
- keep the capability layer thin and external;
- let OpenCode remain a host, not the truth source.

### 3. `committee-qwen3-7-max-12`

Main conclusion:

- OpenCode's official extension surface is already rich enough to host a first reference binding.

Most useful official surfaces it highlighted:

- plugins and event hooks;
- custom tools;
- skills;
- agents/subagents;
- session compaction hook.

Its optimistic position was useful but should be interpreted carefully:

- yes, OpenCode can host the first strong adapter;
- no, this does not justify pushing our full orchestration worldview into OpenCode core.

## Host Synthesis

The team's real asset is not a specific runner.
The asset is the capability layer that sits between:

- `mommy` as intake and routing authority,
- `state-core` as canonical state and done authority,
- any concrete runner such as OpenCode, Codex, Claude, or a future host.

That means we should stop framing the opportunity as:

- "How do we get mimocode into OpenCode?"

and instead frame it as:

- "Which runner-side capabilities do we want to own in a host-neutral form, and how can OpenCode host the first high-quality adapter?"

## The Capability Categories Worth Owning

The current evidence supports building a neutral capability layer around five surfaces.

### Lifecycle Surface

- `session_start`
- `before_user_turn`
- `subagent_dispatch`
- `subagent_return`
- `finish_request`
- `abort_timeout`
- `offduty_onduty`

### State Surface

- `hydrate`
- `read`
- `report`
- `advance_done`
- `advance_blocked`

### Context Surface

- thin summary projection
- budgeted projection
- `contract_ref`-only subagent dispatch
- blocker surfacing

### Continuity Surface

- pickup pointer
- session close artifact
- compaction-safe restore payload

### Compliance Surface

- no direct task-state write
- no done-gate bypass
- no full-state subagent injection
- no runner ownership drift

## What OpenCode Officially Gives Us Right Now

The official OpenCode surface is already strong enough for a serious first adapter.

### Best immediate leverage points

1. Plugin events
   - keep OpenCode's event vocabulary separate from direct plugin hook keys.
   - adapter code should consume observable events through the documented plugin event handler shape unless the plugin API explicitly exposes a typed direct hook for that name.

   Observable events:

   - `session.created`
   - `session.compacted`
   - `session.error`
   - `session.idle`
   - `todo.updated`
   - command/file/message/permission/server event families

   Direct hook keys we can currently rely on from the official docs/examples:

   - `tool.execute.before`
   - `tool.execute.after`
   - `shell.env`
   - `experimental.session.compacting`
   - tool registration via the plugin tool helper

2. Custom tools
   - expose `state-core` operations as official OpenCode tools instead of patching core behavior.
   - `state-core` custom tools are the only legal bridge surface for runner-side state operations.
   - each custom tool may only call adapter APIs that map to `hydrate`, `read`, `report`, and `advance` behavior; custom tools must not take canonical state file paths and read/write them directly.
   - any tool path that bypasses the adapter surface and touches canonical task-state directly is a boundary violation and should be blocked at launch-time or audit-time.

3. Skills
   - ship the behavior layer as session-local and project-local skills rather than hardcoding it into the host.

4. Agents + permission model
   - use official agent/subagent boundaries to express safe dispatch rules instead of reinventing a runner-internal scheduler.

5. Compaction hook
   - use official compaction injection to preserve a minimal `state-core` restore packet across long sessions.

### What OpenCode does not give us yet

- a stable external event bus contract;
- an exactly-once durable state log;
- a native cross-session external task-state protocol;
- a generic workflow DAG engine;
- a mommy-style orchestration authority model.

This is good news, not bad news.
It means our capability layer remains necessary and distinct.

## What We Should Build

### Direction

Build a runner-neutral capability layer that OpenCode can host first.

### Non-direction

Do not build:

- an OpenCode fork that absorbs our worldview;
- a mimocode clone inside MMS;
- a new monolithic runner that owns state, memory, routing, and done.

## Proposed Deliverable Split

### A. Contract layer

Purpose:

- publish the neutral execution contract;
- remain mostly documentation/schema/test driven;
- stay stable across hosts.

Suggested contents:

- lifecycle contract
- context projection schema
- subagent payload schema
- closeout semantics
- compliance rules

Must-not-depend rules:

- must not import any runner SDK, host storage format, or adapter implementation;
- must not encode OpenCode-specific agent names, event names, or file layout as contract truth.

### B. Capability layer

Purpose:

- package reusable behavior that is not tied to one host.

Suggested contents:

- hydrate/summary policy
- closeout bridge policy
- continuity bridge policy
- recorder/evidence bridge policy
- subagent dispatch discipline

Must-not-depend rules:

- must not depend on a concrete adapter binding such as `adapter-opencode`;
- must not call runner-native APIs directly or assume a specific host event model.

### C. Adapter layer

Purpose:

- bind the contract to a concrete runner.

Suggested adapters:

- `adapter-opencode`
- `adapter-codex`
- `adapter-claude`
- later, if still useful, `adapter-mimocode-experimental`

Must-not-depend rules:

- must not directly write canonical state or bypass `state-core` done-gate;
- must not hold canonical state path assumptions outside the adapter-owned bridge surface.

### D. Wrapper/profile layer

Purpose:

- keep end-user launch UX simple.

This is where MMS remains valuable.

Must-not-depend rules:

- must not parse capability-layer internal policy semantics;
- must not introduce a new public workflow mode during the first adapter phase.

Initial exposure rule:

- do not create a new public MMS mode for this work in phase one;
- attach the capability pack through a hidden/internal profile shape or explicit session-local capability-pack injection only.

## The OpenCode Reference Binding

OpenCode should be the first serious reference binding because it already exposes enough official extension points.

### Use official surfaces first

- plugins for event hooks and guardrails
- custom tools for `state-core` bridge operations
- skills for behavior packs
- agents/permissions for bounded dispatch
- compaction hook for restore packet injection

Reference binding rule:

- model the adapter as three distinct bindings, not one generic hook bus.
- event observation handles session/todo/status-style lifecycle signals, normally through the plugin event callback plus `event.type` checks.
- direct interception uses only officially documented direct hook keys, currently `tool.execute.before`, `tool.execute.after`, `shell.env`, and `experimental.session.compacting`.
- callable bridge operations should be custom tools and bounded agents/permissions, not synthetic lifecycle events.
- do not treat every listed OpenCode event name as a writable or interceptable direct hook.

### Do not start with core patches

Avoid touching:

- OpenCode session storage schema
- agent scheduler core
- compaction engine internals
- permission resolution core
- skill loader core

If we later need upstream help, ask first for thinner extension points, not for architecture ownership.

## MMS Link Plan

The user also asked how this should connect back into MMS.

The current repo already exposes a healthy OpenCode modularization seam.

Relevant current modules from the existing roadmap:

- `mms_opencode_config.py`
- `mms_opencode_agents.py`
- `mms_opencode_env.py`
- `mms_opencode_launch.py`
- `mms_opencode_profiles.py`
- `mms_opencode_resolver.py`
- `mms_opencode_roster.py`
- `mms_opencode_routes.py`
- `mms_opencode_session.py`
- `mms_opencode_health.py`
- `mms_opencode_preflight.py`

### Recommended MMS integration split

1. `mms_opencode_profiles.py`
   - declare one capability-pack aware OpenCode profile shape;
   - do not expose this as a heavy new public mode yet.
   - use a hidden/internal profile or session-local capability-pack attachment first; do not add a new public `mms <mode>` entry during the MVP phase.

2. `mms_opencode_env.py`
   - inject only safe session-local env hints needed by the adapter;
   - use the host context contract rather than copying host auth state.

3. `mms_opencode_session.py`
   - materialize session-local plugin/skill/tool directories and config pointers;
   - keep the adapter install session-local, not global.

4. `mms_opencode_launch.py`
   - launch OpenCode with the capability pack attached;
   - keep launch behavior thin and fail-closed.

5. `mms_opencode_roster.py`
   - keep roster/agent naming generic enough that the capability pack does not depend on one historical naming scheme.

6. `mms_opencode_health.py`
   - later, add lightweight health evidence for adapter presence and version compatibility, not for workflow truth.

### What MMS should not become

- not a new workflow engine;
- not a second `state-core`;
- not the owner of task truth;
- not a hidden replacement for `mommy`.

Its job remains launcher/session/runtime management plus capability-pack attachment.

## Second-Pass Review Packet

The user asked to land this now and have a fresh agent review it again.

Suggested next review questions:

1. Is the capability split clean enough between contract/capability/adapter/profile?
2. Does the OpenCode reference binding rely only on official extension points?
3. Is the MMS link plan thin enough to preserve launcher-first boundaries?
4. Are any `state-core` or `mommy` concepts leaking into the public adapter API too early?
5. Which part should be open-sourced first: contract, capability layer, or OpenCode adapter?

Suggested reviewer focus split:

- reviewer A: architecture boundary audit
- reviewer B: OpenCode official extension fit audit
- reviewer C: MMS integration thinness audit

Additional second-pass checks added after the first reviewer pass:

- verify that event observation and direct hook usage are not conflated in the reference binding plan;
- verify that custom tools cannot directly read/write canonical state paths;
- verify that the first MVP is defined by measurable host/runtime evidence rather than architecture intent.

## Proposed Work Sequence

1. freeze this direction memo
2. run a second-pass multi-agent review on the memo itself
3. run an `opencode-hook-fit-spike` to verify that official OpenCode surfaces provide the timing and payload shape our lifecycle surface requires
4. draft the runner-neutral contract package, gated on spike evidence
5. draft the OpenCode reference adapter MVP, gated on spike evidence
6. map the adapter onto the existing `mms_opencode_*` modules and attach it through a hidden/internal profile or session-local capability pack
7. only after local proof, decide whether any thin upstream OpenCode RFC is worthwhile

### Hook-fit spike scope

The spike should prove, with evidence, that the following official surfaces are sufficient for the MVP:

- plugin event observation for `session.created`-style lifecycle signals
- `tool.execute.before`
- `tool.execute.after`
- `shell.env`
- `experimental.session.compacting`
- custom tools
- agent permissions / bounded subagent dispatch

The spike is successful only if it demonstrates payload shape and timing fit, not merely that the APIs exist.

### MVP Acceptance Criteria

- OpenCode plugin registers at least the lifecycle surfaces needed for startup, compaction, and tool interception, and emits structured adapter-side trace evidence.
- At least one `state-core` bridge operation is exposed as a custom tool and passes a local round-trip compliance test.
- The compaction hook injects a minimal restore packet that survives a real compaction cycle and remains readable after compaction.
- The adapter never writes canonical task-state directly; all mutations route through the compliance surface and are covered by a deny-list test.
- Subagent dispatch uses only `contract_ref`-bounded or budgeted payloads; a negative test rejects full-state injection.
- Session-local plugin/skill/tool directories are created without persisting artifacts into the global `~/.config/opencode/` root.
- One end-to-end loop proves: open task -> hydrate -> work -> finish request -> done-gate mediated closeout, with `mommy` + `state-core` remaining the only workflow authorities.

## Phase-1 Spike Result Update

Phase 1 of `opencode-local/spikes/opencode-hook-fit/` returned `partial_blocked` on 2026-06-14.

Key result:

- session-local OpenCode plugins load correctly;
- legacy `/session/{sessionID}/summarize` can trigger `experimental.session.compacting`;
- `/api/session/{sessionID}/compact` exists in OpenAPI but returned 503 `V2 session compact is not available yet` in OpenCode `1.15.13`;
- the hook return string was not proven to survive as a durable restore packet after compaction;
- boundary kill-switch B was not run because fail-fast stopped at kill-switch A.

Updated implication:

- do not start the OpenCode adapter MVP yet;
- treat compaction restore as experimental/optional until a future run proves durable post-compaction restore;
- required continuity should be narrowed toward external session-close / pickup artifacts controlled by `opencode-local` or MMF adapter, with compaction injection as an optimization.

Evidence:

- `opencode-local/spikes/opencode-hook-fit/PHASE1_EVIDENCE.md`
- `opencode-local/spikes/opencode-hook-fit/RESULT.md`

## Final Decision Snapshot

- yes: absorb useful mimocode-inspired runner capabilities
- yes: use official OpenCode extension surfaces aggressively
- yes: keep the result compatible with `mommy` + `state-core`
- yes: design for future open-source extraction
- no: do not bind the capability asset to mimocode
- no: do not bind the capability asset to OpenCode core
- no: do not let MMS turn into a monolithic workflow owner

## Recommended Immediate Next Artifacts

- `opencode-hook-fit-spike` outline and pass/fail evidence template
- `runner-neutral-contract` outline
- `opencode-reference-adapter-mvp` outline
- post-spike review packet for the next fresh agent round
- MMS integration checklist keyed to the existing `mms_opencode_*` modules
