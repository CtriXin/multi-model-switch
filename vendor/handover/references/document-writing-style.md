# Handover Document Writing Style

Date: 2026-04-25
Status: global guidance candidate for shared `handover`

## Conclusion

Future agents should not treat handover as only short status files.

For durable project direction, architecture, user intent, execution rules, and long-term roadmap, agents should write full narrative documents in the same style as the Moebius long-term vision and boundary docs.

This rule should apply across projects, not only Hive.

## Why This Matters

Short handoff files are good for immediate continuation.

They are not enough for:

- preserving the user's long-term product intent
- explaining why a project exists
- preventing future agents from shrinking the goal
- recording architectural boundaries
- documenting what is not built yet
- making future tradeoffs understandable
- proving why a rule exists

If a future model only sees compact task status, it may execute correctly but optimize for the wrong goal.

## Two Documentation Modes

### Compact Handoff Mode

Use for immediate execution transfer.

Examples:

- `current.md`
- `handoff.md`
- `packet.json`
- `progress/<id>.md`

Style:

- compact
- refs over long text
- exact next action
- validation and risk
- owner / CLI / model / task id

### Durable Narrative Mode

Use for long-lived project understanding.

Examples:

- product north star
- architecture boundary
- long-term user intent
- module responsibility split
- HumanGate policy
- evaluation/proof strategy
- recurring pain points
- roadmap and non-goals
- decisions that future agents must not forget

Style:

- clear title and date
- conclusion first
- explain why it exists
- record user intent in concrete words
- separate current pain, unfinished work, risks, and future roadmap
- include concrete paths and commands
- include what future LMs must not forget

## Required Sections For Durable Narrative Docs

Use these sections when relevant. Do not force all of them into every small note.

### Executive Summary

One short statement of what this document decides or preserves.

### User Intent

Record what the user actually wants, in plain language.

Include:

- final desired experience
- examples of natural-language requests
- what the user does not want
- what level of autonomy is expected

### Current Pain Points

Record what is broken today.

Examples:

- too many confirmations
- session loss
- sandbox friction
- fake done
- stale issue records
- unclear ownership
- benchmark scores not matching real user value

### Current Architecture / Boundaries

Record which module owns what.

Do not blur responsibility.

### What Is Done

Record completed pieces with file paths, commands, and validation.

### What Is Not Done

Record unfinished pieces explicitly.

This prevents future agents from assuming the system is more capable than it is.

### HumanGate / Safety Boundaries

Record where the agent must stop and ask.

Use concrete thresholds where possible.

### Constraints And Limitations

Record what the system cannot safely do yet.

### Proof / Evaluation Strategy

Record how to prove the project is working.

Prefer real fixtures and commands over abstract claims.

### Roadmap

Record staged next steps.

Keep stages small enough to execute.

### Future LMs Must Not Forget

Include a concise list of principles, decisions, and risks that should survive session compaction.

## Writing Rules

- Write in Simplified Chinese when the user-facing context is Chinese, but keep technical terms in English.
- Conclusion first.
- Use concrete paths and commands.
- Distinguish facts from assumptions.
- Do not hide unfinished work.
- Do not turn docs into a transcript.
- Do not write generic slogans without proof steps.
- Prefer "what must happen next" over vague future ideas.
- If this doc changes future behavior, link it from `current.md`, `packet.json`, or the project README.

## Template

```md
# <Project / Topic> <Decision / Vision / Boundary>

Date: <date>
Owner: <agent>
Status: <draft | active | superseded>

## Executive Summary

<conclusion first>

## User Intent

<what the user wants, examples, non-goals>

## Current Pain Points

<what is broken or expensive today>

## Current State

<what exists now, with paths>

## Boundaries

<module responsibilities / what this does not own>

## Not Done Yet

<explicit gaps>

## HumanGate / Safety

<where to stop and ask>

## Proof Strategy

<fixtures, commands, checks>

## Roadmap

<staged plan>

## Future LMs Must Not Forget

<short list>
```

## Relationship To Compact Handoff

Durable narrative docs do not replace compact handoff.

Use both:

- durable doc preserves long-term meaning
- packet/current/handoff/progress transfers immediate execution state

If a durable doc is created, add it to the relevant packet refs.
