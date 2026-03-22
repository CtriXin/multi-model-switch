# AI_PROJECT_CONTEXT.md

> Last updated: 2026-03-19
> Version: 0.3.4
> Branch: feat/cli-workbench-demo (worktree)
> Maintainer: @CtriXin

---

## 1. Project Overview

**Name:** SparkRing (MMS — Multi-Model Switch)

**One-line:** A multi-model AI desktop + mobile app that orchestrates parallel LLM calls, CLI agent sessions, and visual AI workflows for both developers and non-developers.

**Core value:**
- Route any task to the best combination of AI models simultaneously
- Compare, debate, and synthesize responses across providers
- Give non-developers GUI-level access to Claude Code's full capability set
- Give developers PTY-based multi-agent orchestration (Executor → Reviewer → Omega)

**Non-goals:**
- Not a single-model wrapper (never hardcode one model)
- Not a backend service (no server; all API calls are client-direct)
- Not a replacement for the terminal (terminal coexists, GUI is additive)
- Not App Store hostile (every feature must have a sandbox-compliant path or be gated)

---

## 2. Core Concept

**System type:** Tauri (Rust + Vue 3) desktop app + Capacitor iOS app, sharing the same frontend codebase.

**What makes it different from a chat app:**
- Sends the same prompt to N models in parallel, renders responses side-by-side
- Has a Judge/Summarizer layer that synthesizes cross-model consensus and conflict
- Has a Discuss mode where models argue in structured debate rounds
- Has a CLI Workbench that spawns real `claude`/`codex` processes via PTY
- Has a GUI mode that drives `claude --output-format stream-json` as a subprocess for full tool access without exposing a terminal
- Has an Advisors panel: 12 fixed-persona AI roles that give opinionated multi-dimensional analysis

**Why multi-model:**
- No single model is best at everything; parallel calls + synthesis produces higher-quality decisions
- User can compare cost/quality tradeoffs in real time
- Models cross-check each other; divergence surfaces risk

---

## 3. Key Features

### Implemented (✅)
- Multi-provider config (OpenRouter, Anthropic-compatible, OpenAI-compatible, DashScope, mock)
- API Key storage: Web Crypto AES-256-GCM → IndexedDB, never localStorage plaintext
- Provider + key JSON import/export bundle (for team distribution)
- Chat mode: parallel streaming from N models, grid/vertical/horizontal layout
- Context strategies: summary / selected-only / full-thread, with budget limits (10 rounds / 20k chars)
- Discuss mode: structured 3-phase debate across models
- Rollup: synthesis agent produces a single actionable plan from Discuss output
- Advisors (锦囊团): 12 fixed-persona roles (broadcast mode), 6 categories × 2 roles
- CLI Workbench (PTY): spawn `claude`/`codex` in PTY, multi-agent task orchestration
  - Roles: executor / reviewer / alpha / beta / omega
  - Omega lifecycle: pending → working → quiescent → completed / blocked / needs_input / failed
  - Evidence-based completion detection via sentinel signals + file detection
- Workbench v2 (WorkbenchDashboard): QuickLaunchDialog with folder picker (Tauri dialog plugin)
- GUI mode (智能助手 `/gui`): visual Claude UI, drives `claude --print --verbose --output-format stream-json` subprocess, card-based message rendering
- Folder picker: NSOpenPanel via `@tauri-apps/plugin-dialog` (App Store compliant)
- Setup guide: first-run provider configuration flow
- Model management: dynamic model list from provider APIs, suppression, failure counting
- SparkRing speed snapshot: `GET /api/models/speed?key=...` with local daily cache fallback; lab/chat auto-pick can prefer fastest domestic SparkRing models, and CN-hinted lab auto-pick now biases toward faster non-reasoning domestic models first
- Theme: dark/light with aurora gradient background
- Sidebar: collapsible, all navigation entries

### In Progress (🔄)
- GUI mode stream-json parsing: event type mapping unverified against real claude CLI output
- GUI mode real-time streaming: currently waits for full process exit before rendering
- GUI mode multi-turn: each send = new CLI process, no context continuity yet

### Planned (📋)
- CLI install guide: `useCliStatus` + `CliInstallGuide.vue` integrated into GuiModeView
- App Store feature flags: `VITE_APPSTORE` + Cargo `appstore` feature to gate PTY/CLI paths
- GUI mode real-time output: incremental stdout read or PTY-based approach
- GUI mode multi-turn: `--resume <session-id>` or history accumulation
- Advisors Phase 2: committee mode (parallel → synthesizer)
- Advisors Phase 3: debate mode (multi-round rebuttals)
- Judge Tier 3: committee / deep review (multi-round adversarial evaluation)
- Model pricing DB auto-update
- OAuth usage query
- Session persistence across refresh
- iOS drawer: add GUI mode entry

---

## 4. Multi-Agent Architecture

### Chat mode (parallel broadcast)
- **Trigger:** user sends prompt
- **Agents:** N model instances (user-selected), called simultaneously
- **Coordination:** none — parallel, independent responses
- **Post-processing:** Judge/Summarizer picks evaluator model (not in answering set, highest tier), synthesizes consensus/conflict/risk/recommendation

### Discuss mode (structured debate)
- **Trigger:** user sends prompt in Discuss view
- **Agents:** N models, 3 phases (opening / rebuttal / synthesis)
- **Coordination:** sequential phases; each model sees prior-round outputs
- **Post-processing:** optional Rollup agent produces single actionable plan

### Advisors mode (persona committee)
- **Trigger:** user sends prompt in Advisors view
- **Agents:** up to 12 fixed personas (Victor, Stella, Marcus, Nina, Kai, Lena, Alex, Diana, Yuki, Ravi, Chen, Maya)
- **Axis:** optimist↔pessimist × short-term↔long-term × internal↔external
- **Phase 1 (current):** broadcast — all personas respond independently
- **Phase 2 (planned):** committee — system-level moderator synthesizes
- **Phase 3 (planned):** debate — multi-round rebuttals, personas hold their stance

### CLI Workbench (PTY multi-agent)
- **Trigger:** user creates task, assigns agent slots, clicks Launch
- **Agents:** executor / reviewer / alpha / beta / omega roles
- **Each agent:** real subprocess (`claude` or `codex`) in isolated PTY with isolated HOME
- **Env isolation:** per-session `runtimeRoot`, isolated HOME, symlinked config dirs
- **Coordination:** evidence-based handoff via OMEGA_STATUS sentinel signals + file detection
- **Completion detection:** OmegaPhase state machine (pending → working → quiescent → completed/blocked/needs_input/failed/pong)

### GUI mode (single CLI agent)
- **Trigger:** user selects folder + model + sends prompt
- **Agent:** single `claude --print --verbose --output-format stream-json` subprocess
- **Auth:** injects `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` + `ANTHROPIC_MODEL` via env
- **Output:** poll subprocess stdout (600ms interval), parse stream-json lines on exit
- **Tools:** all claude CLI tools available (bash, file, WebSearch, etc.) — no restrictions from GUI side
- **Multi-turn:** NOT YET — each message = new process

---

## 5. Interaction Model

### Chat
- User selects N models via chip bar
- Textarea input (Enter = send, Shift+Enter = newline)
- Parallel SSE streams rendered as cards
- After all models respond: Judge runs automatically, summary card appears below
- Context carried forward per-session (configurable strategy)

### Discuss
- User selects N models
- System runs 3 debate phases automatically
- Each phase visible in UI
- Rollup button appears after completion

### Advisors
- User selects persona subset (or all 12)
- Broadcast: all personas respond in parallel
- Responses rendered as individual cards with persona identity

### CLI Workbench
- User defines task (title + goal)
- Assigns agent profiles (executor / reviewer roles)
- Launches → each agent opens a PTY terminal panel
- User can watch live terminal output
- Agents can hand off work via file-based protocol

### GUI mode
- User clicks folder picker → selects workspace directory
- Selects provider + model from dropdowns (provider-linked)
- Types prompt → sends
- Messages rendered as chat bubbles (user right, assistant left)
- Tool calls shown as collapsible cards (GuiToolCard)
- Running state: bouncing dots + elapsed time counter
- New session button clears history and kills current process

---

## 6. State / Memory System

### Long-term (persisted)
- `providers` → localStorage (namespaced key, non-secret config)
- `accounts` → localStorage (non-secret metadata)
- API keys → IndexedDB (AES-256-GCM encrypted, key = account.id)
- `sessions` (chat history) → localStorage
- `disabled-models` → localStorage (TTL-based suppression)
- `failure-counts` → localStorage

### Session state (Pinia, in-memory)
- `appStore`: models[], presets, selectedModelIds, loading state
- `chatStore`: rounds, streaming state, context mode
- `discussStore`: discuss session, phases
- `workbenchStore`: tasks, agentSessions, handoffs, ptyPids
- `providerStore`: providers, accounts, keyStatus
- `sessionStore`: sortedSessions, currentSessionId

### GUI mode (composable, no persistence)
- `useGuiSession()`: messages[], status, error — lost on refresh/new session

### Key encoding rules
- All localStorage keys are namespaced via `namespacedStorageKey(key)` to avoid collision
- `KEYCHAIN_DB_NAME` = fixed IndexedDB name for keychain

---

## 7. Technical Constraints

### Platform
- **Mac (primary):** Tauri 2.x (Rust backend + WebView frontend)
  - Full version (DMG): PTY, CLI spawn, all features
  - App Store version: no PTY, no CLI spawn, no shell — API-only paths only
- **iOS:** Capacitor 8 (WKWebView), App Store only, strict sandbox
- **Web (dev):** Vite dev server, Tauri APIs unavailable — mock/stub paths required

### App Store sandbox rules (hard constraints)
- NO `tauri-plugin-pty` in App Store build
- NO `spawn`/`exec` of external processes
- YES HTTP API calls (direct to provider endpoints)
- YES `NSOpenPanel` (folder picker) via `tauri-plugin-dialog`
- YES file read/write on user-authorized directories (security-scoped bookmarks)
- Feature gate: `import.meta.env.VITE_APPSTORE` (frontend) + Cargo `appstore` feature (Rust)

### API / cost
- All LLM calls are direct client → provider (no proxy backend)
- Provider types: `openrouter` | `openai-compatible` | `anthropic-compatible` | `mock`
- Model ID normalization: OpenRouter keeps full prefix (`anthropic/claude-sonnet-4`); other providers strip provider prefix before sending
- `resolveApiModelId(provider, modelId)` must be called before any API request

### UI principles
- Aurora gradient background (3 blurred blobs, mouse-parallax) — never cover with solid `bg-*` on root views
- Use `bg-transparent` on view roots; use `bg-surface-N` only for contained components
- Tailwind CSS design tokens: `surface-0..4`, `text-primary/secondary/tertiary`, `border-subtle/default`, `accent`
- All surfaces respond to `html.light` CSS class for light mode
- Never use `prose-invert` directly — use app's `.md-body` class for markdown rendering
- Sidebar has collapsed (icon rail) and expanded states; both must be updated when adding navigation

### Performance
- PTY terminal: WebGL renderer default (`@xterm/addon-webgl`), Canvas fallback
- CJK: xterm.js Unicode 11, WebGL renders correctly — do not use custom `IUnicodeVersionProvider` (caused visual gaps)
- Model list: loaded from provider APIs on app init, cached in `appStore.models`

---

## 8. Current Development Status

### Completed (as of 2026-03-19)
- All core chat/discuss/advisors flows with real API
- CLI Workbench PTY multi-agent orchestration
- GUI mode basic scaffolding (view, routing, sidebar entry, CLI subprocess driver)
- Folder picker (Tauri dialog, App Store compliant)
- Provider/model linkage fixed in GUI mode
- API key lookup fixed (uses `account.id`, not `providerId`)
- GUI mode background/theme aligned with rest of app

### In Progress
- GUI mode: verifying `claude --print --verbose --output-format stream-json` actually runs and parses correctly
  - Added `console.log('[GuiSession] ...')` instrumentation — check Tauri devtools Console
  - Suspected issues: stream-json event types (`message_start`/`content_block_delta`) may differ from current parser
  - First-run `terms of service` acceptance may block CLI in isolated HOME

### Immediate next steps (P0)
1. Open Tauri devtools (right-click → Inspect), send a GUI message, read `[GuiSession]` logs
2. Verify `launch result.ok === true` and `pid` is set
3. Verify poll shows `alive: true` then transitions to `alive: false`
4. Check `stderr` content from final poll result
5. Fix `parseStreamJson()` event type mapping to match real claude stream-json output

---

## 9. Future Roadmap

### Near term
- GUI mode real-time streaming (incremental stdout or PTY approach)
- GUI mode multi-turn conversation (`--resume` flag or accumulated history)
- CLI install guide (check if `claude` is in PATH, show install instructions)
- App Store feature flag build system (DMG vs App Store builds)
- iOS mobile drawer: add GUI mode entry

### Medium term
- Advisors Phase 2: committee synthesis mode
- Advisors Phase 3: multi-round debate mode
- Judge Tier 3: adversarial committee review
- Session persistence for GUI mode
- Model pricing database auto-update

### Long term
- iOS GUI mode (pure API path, no CLI, App Store compliant)
- Single-model compatibility mode (Planner/Critic/Judge role decomposition)
- Gateway model slot coexistence
- OAuth usage query integration

---

## 10. Instructions for AI Assistants

### Before making any change
1. Read the file you intend to modify. Never edit code you haven't read.
2. Check if the change affects App Store compliance. If yes, ensure a sandbox-safe fallback exists.
3. Check `CLAUDE.md` in the repo root — protected files listed there require explicit user authorization before modification.

### Architecture rules
- **Model IDs:** Always call `resolveApiModelId(provider, modelId)` before sending to any non-OpenRouter API. OpenRouter keeps the full prefix; others strip it.
- **API keys:** Always retrieve via `getFetchRuntime(providerId)` or `getApiKey(account.id)`. Never use `getApiKey(providerId)` — keys are stored under `account.id`.
- **Provider models:** Use `appStore.models.filter(m => m.provider === providerId)` for provider-specific model lists. `appStore.models` contains all providers' models.
- **View backgrounds:** Use `bg-transparent` on view root `<div>`. The aurora gradient comes from `App.vue`. Never use hardcoded colors like `bg-[#0a0a0f]` on full-page views.
- **Markdown rendering:** Use `.md-body` CSS class (defined in `src/style.css`), not `prose prose-invert`.
- **Sidebar navigation:** When adding a new route, update BOTH the collapsed (icon rail) AND expanded sidebar sections in `src/components/layout/Sidebar.vue`.
- **CLI env injection for `claude`:** Use pattern from `launchSpec.ts` — inject `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL` (strip `/v1` suffix), `ANTHROPIC_MODEL`, plus all `ANTHROPIC_DEFAULT_*_MODEL` variants.
- **stream-json format:** `claude --print --verbose --output-format stream-json` emits newline-delimited JSON. Event types are `message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop`. Do NOT assume type `assistant` or `tool_result` at top level.

### Code style
- Vue 3 Composition API with `<script setup lang="ts">`
- Pinia stores for shared state
- Composables (`src/composables/`) for reusable reactive logic
- Single-file components, scoped styles when needed
- Tailwind utility classes, design tokens from `tailwind.config.js`

### Behavioral rules (from CLAUDE.md)
- Conservative by default: diagnose before implementing
- Only modify code when user explicitly requests it with clear scope
- After each independently deliverable iteration, ask if user wants to commit
- Never change default model, default provider, default bridge, or fallback behavior without authorization
- Never overlap changes across unconfirmed iterations
- Protected files (ccs_core.py, ccs_launchers.py, etc.) require explicit authorization

### Common pitfalls to avoid
- Do NOT use `bg-[#0a0a0f]` or any hardcoded dark hex on view roots
- Do NOT use `getApiKey(providerId)` — use `getFetchRuntime()` instead
- Do NOT send raw compound model IDs (e.g. `company/glm-5-turbo`) to non-OpenRouter APIs
- Do NOT use `prose-invert` for markdown — use `.md-body`
- Do NOT add `--output-format stream-json` without `--verbose` when using `--print`
- Do NOT forget to update the collapsed sidebar icon rail when adding a nav entry
- Do NOT poll `appStore.models` without ensuring `appStore.initialize()` has run
