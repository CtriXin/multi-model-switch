# OpenCode Review Mission Trace v1

Status: draft implementation contract
Issue: https://github.com/CtriXin/multi-model-switch/issues/40
Profiles: `review`, `committee`, `debate`

## Purpose

MMS-managed OpenCode review flows need a human-visible correlation anchor for
parallel windows and repeated review/fix cycles. A commit hash identifies the
code target. It does not identify a specific manual dispatch.

This contract adds a dispatch-local mission block that Review Hub, Committee,
and Debate hosts must create and repeat in chat output and delegated briefs.

## Mission Block

Required fields:

```text
MMS-MISSION: <profile>-<stable-source-or-date>-<hash-or-nonce>
MMS-TARGET: <pr/commit/branch/diff target, or unknown>
MMS-MODE: <review|gate|advisory|estimate|execution_packet|debate|...>
MMS-SOURCE: <review-hub-request|github-pr|local-diff|commit|user-pasted|unknown>
```

Rules:

- `MMS-MISSION` identifies this manual dispatch, not the code commit.
- `MMS-TARGET` identifies the reviewed object when known.
- For committee, prefer the declared `decision_mode` value such as `gate` or
  `review`; do not prefix it as `committee-gate`.
- If the target is unclear, write exactly `MMS-TARGET: unknown` and describe
  the observed source evidence. Do not invent a PR or commit.
- Prefer an existing stable request id, request-root basename, PR plus commit,
  or branch plus commit when constructing the mission id.
- If no stable source exists, generate a compact id using the profile name,
  current date/time if known, and an 8-character nonce/hash.

## Host Requirements

For every non-trivial `review`, `committee`, or `debate` task, the host must:

1. create or preserve one mission block before delegation;
2. include the unchanged mission block in every delegated reviewer/member brief;
3. include a visible mission trace in the final chat synthesis, preferably in
   the copy-forward, provenance, or trace area rather than before the human
   summary;
4. end the final chat synthesis with at least `MMS-MISSION` and `MMS-TARGET`;
5. preserve the same mission id across retries within the same manual dispatch.

The body trace and final footer identify the same current manual dispatch. They
are not previous/next pointers.

Every new manual dispatch after executor repair should get a new
`MMS-MISSION`, even if it belongs to the same issue or PR. The `MMS-TARGET`
usually changes when the PR head commit changes.

## Member Requirements

Reviewers, committee members, and debate members must copy any host-provided
mission block unchanged into their artifact or compact chat response.

## Non-Goals

- No automatic executor session routing in v1.
- No requirement that executor/planner sessions pre-generate mission ids.
- No changes to merge authority, formal vote rules, or real `~/.config/mms/**`
  config.
