# CLAUDE.md

@AGENT.md

This file exists so Claude Code auto-loads the shared repository rules. Keep shared behavior in `AGENT.md`; put only Claude-specific overrides here.

**Read [`docs/AI-ONBOARDING.md`](docs/AI-ONBOARDING.md) before doing anything substantive here.** `AGENT.md` and `docs/AGENT_GUARDRAILS.md` tell you what you may not do; the onboarding document tells you what this project is, which release line your change belongs to, how to run the gates, and the mistakes already made.

## Claude-Specific Mode

- Default to diagnosis before implementation when the user says "看下", "定位", "分析", "帮我约束一下", or similar.
- Only commit after explicit user confirmation.
- After each completed implementation stage, ask before starting another substantial stage if the next stage would broaden scope.
