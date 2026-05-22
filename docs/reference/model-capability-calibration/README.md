# Model Capability Calibration Reference

This folder stores MMS-owned reference snapshots for model capability calibration.

## Current Snapshot

- Markdown: `2026-05-21-mms-model-capability-calibration.md`
- JSON: `2026-05-21-mms-model-capability-calibration.json`
- Original source repo: `/Users/xin/auto-skills/CtriXin-repo/moebius/docs/`
- Captured by: Codex / MMS local registry v2 planning

## Role In MMS

These files are **reference evidence**, not live runtime truth.

MMS registry work should ingest this data as `source_snapshot` / `candidate_truth`, then promote only validated facts into `approved_truth` and generated exports. Downstream projects should not read these snapshots directly.

## Guardrails

- Keep vendor official facts separate from provider catalog facts.
- Keep OpenRouter as `provider_catalog_reference`, not vendor official truth.
- Preserve exact thinking-control semantics such as `thinkingLevel`, `thinkingBudget`, `thinking.type`, and `reasoning.effort`.
- Never store or derive API keys, OAuth tokens, or account identity here.
