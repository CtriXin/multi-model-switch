# DSH + MMS integration

Task: b5f588a91c604408; baseline: origin/dev 60e9f14b. Prior source audit: 8b76aee15b3c41f7.

Scope: out-of-tree DSH extension/profile and dedicated local runtime. Preserve Pilot defaults and all real MMS config; consume only verified approved exports read-only. Pin DSH 0.1.6-alpha.2 and lock dependencies. No DSH source fork.

Success: Web runs with explicit MMS routes; actual selected non-Claude model request succeeds with request-path evidence; no secret in tracked/generated shareable files; missing/invalid bundles and credentials fail closed; Recipe requirements checked against selected model before generation; restart retains sessions. Integration usable from a local entrypoint.

Validation: fixture-based routing/credential/Recipe regression, isolated DSH live smoke, real Web model/effort selection, session persistence; fresh-user gate as applicable. All real requests use an existing approved non-Claude route. No global OAuth fallback.

Rollback: stop only task-owned runtime and remove dedicated profile/entrypoint when requested. No change to existing mms launchers, config, provider priorities, or running Pilot.

Tracker: original Stride task above. Source and evidence in its worktree, private runtime under ~/.local/share/mms-dsh. Dependencies initially staged task-local. Public release and whole Bot migration are outside this configuration task.

## Urgent + Important
- [x] Implement verified MMS provider adapter and dedicated DSH startup (source: @user, created: 2026-09-18, completed: 2026-09-18)
- [x] Verify a real request, model/effort selection, auth failure and restart (source: @user, created: 2026-09-18, completed: 2026-09-18)
## Important + Not Urgent
- [x] Add minimal Recipe requirement integration (source: @user, created: 2026-09-18, completed: 2026-09-18)
## Urgent + Not Important
None.
## Neither
Whole-monorepo fork deferred until an essential extension boundary is proven insufficient.

Delivered local installation: `~/Applications/MMS DSH.command`; 29 logical models / 68 routes configured. Live checks: DeepSeek Anthropic Low, GPT Responses Medium/High, Recipe success/fail-closed, restart continuity. Local evidence: `.ai/regression-reports/2026-09-18-dsh-mms.md`.
