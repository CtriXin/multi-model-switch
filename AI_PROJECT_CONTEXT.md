# AI_PROJECT_CONTEXT.md

> Last updated: 2026-03-19
> Version: 0.3.5
> Branch: feat/daily-challenge (active)
> Maintainer: @CtriXin

---

## 1. Project Overview

**Name:** SparkRing (MMS — Multi-Model Switch)

**One-line:** A multi-model AI desktop + mobile app that orchestrates parallel LLM calls, CLI agent sessions, interactive play modes, and visual AI workflows for both developers and non-developers.

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
- Has Play Modes: 5 interactive AI-powered experiences (Daily Challenge, Story Live, Story Lite, Turtle Soup, Case Reconstruction)

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
- Advisors (锦囊团): 12 fixed-persona roles, 6 categories × 2 roles, 3 modes (broadcast / debate / committee)
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
- **Play Modes** (see §4 for architecture):
  - Daily Debate Challenge: daily topic, AI vs AI debate show, user stance + thinking pattern snapshot, IndexedDB persistence
  - Story Live (剧情共演): 3-role parallel storytelling (logic/emotion/twist), 5-stage phase machine, tension arc detection, 4-tier endings
  - Turtle Soup (海龟汤): lateral thinking puzzles, AI host yes/no answering, leak-guard verifier, hint system, 96 seeds
  - Story Lite (冒险模式): text adventure with 3 AI roles, story state tracking, choice-based branching
  - Case Reconstruction (案件重构): detective game, witness interrogation, evidence collection, reconstruction scoring

### In Progress (🔄)
- GUI mode stream-json parsing: event type mapping unverified against real claude CLI output
- GUI mode real-time streaming: currently waits for full process exit before rendering
- GUI mode multi-turn: each send = new CLI process, no context continuity yet
- Case Reconstruction: local validator skeleton complete, demo case defined, store + view exist — "freeze v1 contract" state

### Planned (📋)
- CLI install guide: `useCliStatus` + `CliInstallGuide.vue` integrated into GuiModeView
- App Store feature flags: `VITE_APPSTORE` + Cargo `appstore` feature to gate PTY/CLI paths
- GUI mode real-time output: incremental stdout read or PTY-based approach
- GUI mode multi-turn: `--resume <session-id>` or history accumulation
- Advisors Phase 3: custom roles + debate mode (multi-round rebuttals)
- Judge Tier 3: committee / deep review (multi-round adversarial evaluation)
- Model pricing DB auto-update
- OAuth usage query
- Session persistence across refresh
- iOS drawer: add play mode entries

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

### Play Modes (shared framework)
All play modes share a common `PlayModeSessionEnvelope` persistence shape and `PlayModeId` registry. Each mode has its own Pinia store and Vue view, but follows the same lifecycle pattern: seed → play → end.

#### Daily Debate Challenge (每日辩题挑战)
- **Trigger:** user picks daily topic or generates one
- **Agents:** 2+ AI models debate as "proponent" vs "opponent" with structured turn specs
- **User role:** chooses stance (agree/disagree/neutral), submits thinking pattern snapshot
- **Scoring:** 4-axis thinking profile (evidence↔intuition, decisive↔exploratory, risk-seeking↔risk-aware, self↔systems)
- **Persistence:** IndexedDB for opinion cards, localStorage for session state
- **Seeds:** 96 topic tensions across 11 categories (tech, ethics, society, etc.)

#### Story Live (剧情共演)
- **Trigger:** user provides a premise (失衡瞬间), then acts as director
- **Agents:** 3 AI roles respond in parallel per turn:
  - **Logic** (主镜头): narrative progression, action description, 200-char limit
  - **Emotion** (情绪暗流): atmosphere and emotional undertones, 80-char limit, no plot advance
  - **Twist** (异动信号): anomaly/foreshadowing, conditional trigger based on keywords + tension
- **State machine:** premise → directing → live → wrapping → ended (5 stages)
- **Story state tracking:** local heuristic (regex-based entity/character/goal extraction, zero LLM calls), injected into each role's prompt to prevent contradictions
- **Twist system:** 2-layer keyword tiers (HIGH_CONFIDENCE: unconditional; SOFT: tension≥3 required), stagnation detection via `calcSimilarity` with stop-word filtering
- **Ending detection:** 4 grades (failure/normal/hidden/optimal) based on tension arc analysis, unresolved clue count, session length
- **Director memory:** auto-summarized history chunks (3-turn windows), injected as context. Validation warnings with confidence ≥0.5 persist into memory
- **Persistence:** localStorage with `normalizeRecord` migration for backwards compatibility
- **Key files:** `features/play-modes/story-live/` (types, state-utils, twist-trigger, validation, prompts, useStoryFlow), `stores/storyLive.ts` + `stores/story-live-helpers.ts`, `views/StoryLiveView.vue`

#### Turtle Soup (海龟汤)
- **Trigger:** user selects puzzle from 7 categories × 3 difficulty levels
- **Agents:** Host AI answers yes/no questions; Verifier AI prevents truth leakage
- **Leak-guard:** dual-model system — verifier monitors host output and flags/warns if truth is revealed
- **Hints:** 3 progressive hint levels per puzzle
- **Completion:** game recap with question history
- **Seeds:** 96+ puzzles in `puzzles/seeds.ts` with structured schema (categories, difficulty, truth, hints)
- **Persistence:** IndexedDB for game records
- **Key files:** `features/turtle-soup/` (types, prompts, leak-guard, puzzles/), `stores/turtleSoup.ts`, `views/TurtleSoupView.vue`

#### Story Lite (冒险模式)
- **Trigger:** user starts text adventure from a seed premise
- **Agents:** 3 AI roles (logic, emotion, twist) with sequential response pattern
- **Story state:** act/suspicion/danger/trust/clues tracking, choice-based branching
- **Lifecycle:** seed → briefing → agents_response → player_choice → resolve → check_ending → ended (7 phases)
- **Status:** mock data + prompts defined, early implementation stage
- **Key files:** `features/play-modes/story-lite/` (types, prompts, mock, constants), `views/StoryLiteView.vue`

#### Case Reconstruction (案件重构)
- **Trigger:** user selects a detective case
- **Canon engine:** reveal gates (evidence_count, fact_discovered), 3-tier facts (surface/gated/hidden)
- **Phases:** case_select → scene_zero → investigation_turn → checkpoint → final_reconstruction → verdict → ended (7 phases)
- **Witness system:** interrogation with testimony collection
- **Scoring:** culprit/timeline/evidence/motive breakdown
- **Status:** validator skeleton + demo case complete, "freeze v1 contract"
- **Key files:** `features/play-modes/case-reconstruction/` (types, demo-case, validator), `stores/caseReconstruction.ts`, `views/CaseReconstructionView.vue`

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

### Daily Debate Challenge
- User picks today's debate topic (from daily seed or random)
- AI models debate as proponent vs opponent in structured turns
- User submits stance (agree/disagree/neutral) with optional reasoning
- Thinking pattern snapshot generated and saved to profile
- Opinion cards with debate summary displayed

### Story Live
- User writes or picks a premise (失衡瞬间)
- Types action/direction per turn → 3 AI roles respond in parallel (logic/emotion/twist)
- Director memory auto-summarizes old turns to keep context fresh
- Twist events fire conditionally (keyword + tension thresholds)
- User can trigger story wrap (story draft or script draft)
- 4-tier ending system (failure/normal/hidden/optimal) based on tension arc

### Turtle Soup
- User selects a puzzle from category/difficulty grid
- Asks yes/no questions → AI host answers with tags (yes/no/irrelevant/close)
- Verifier AI runs in background to prevent truth leakage
- Progressive hint system (3 levels) available
- Game ends when user guesses correctly, or requests answer reveal
- Game recap with full question history on completion

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
- `committeeStore`: committee mode (broadcast/debate/committee), role-model assignment, phase management
- `personaStore`: 12 preset persona definitions, stance axes, debate pairing
- `workbenchStore`: tasks, agentSessions, handoffs, ptyPids
- `providerStore`: providers, accounts, keyStatus
- `sessionStore`: sortedSessions, currentSessionId
- `dailyChallengeStore`: topic generation, AI debate orchestration, stance tracking, thinking patterns
- `storyLiveStore`: 3-role model management, turn-by-turn streaming, story state, twist evaluation, localStorage persistence
- `storyLiveHelpers`: envelope construction, director memory, model assignment, migration (extracted from store)
- `turtleSoupStore`: puzzle selection, host/verifier AI, hint system, game lifecycle, IndexedDB persistence
- `caseReconstructionStore`: case selection, investigation turns, evidence collection, reconstruction scoring

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
- Advisors Phase 1+2 (broadcast + committee modes)
- Daily Debate Challenge: full flow with topic seeds, AI debate, stance tracking, thinking patterns
- Story Live (剧情共演): full flow with 3-role parallel streaming, twist system, ending detection
- Turtle Soup (海龟汤): full flow with host/verifier dual model, leak-guard, hint system
- Story Live code review: store refactored (811→521 lines), P0 `startStory` crash fixed, validation/tension/migration bugs patched

### In Progress
- GUI mode: verifying `claude --print --verbose --output-format stream-json` actually runs and parses correctly
  - Suspected issues: stream-json event types (`message_start`/`content_block_delta`) may differ from current parser
  - First-run `terms of service` acceptance may block CLI in isolated HOME
- Case Reconstruction: v1 contract frozen, local validator skeleton + demo case ready
- Story Live View: UI i18n pass (English labels), mobile layout alignment

### Immediate next steps (P0)
1. GUI mode: verify stream-json parsing against real `claude --print --verbose --output-format stream-json` output
2. Context strategy: implement 3 context modes (summary/selected/full) with frontend chip toggle
3. Merge `feat/daily-challenge` branch into main
4. Play mode session restore robustness testing

---

## 9. Future Roadmap

### Near term
- Context strategy implementation (summary/selected/full modes with chip toggle)
- GUI mode real-time streaming (incremental stdout or PTY approach)
- GUI mode multi-turn conversation (`--resume` flag or accumulated history)
- Merge `feat/daily-challenge` branch into main
- CLI install guide (check if `claude` is in PATH, show install instructions)
- App Store feature flag build system (DMG vs App Store builds)

### Medium term
- Advisors Phase 3: custom roles + multi-round debate mode
- Judge Tier 3: adversarial committee review
- Case Reconstruction: beyond v1 (more cases, scoring polish, multiplayer)
- Story Lite: complete implementation from mock stage
- Session persistence for GUI mode
- Model pricing database auto-update
- iOS mobile drawer: add play mode entries

### Long term
- iOS GUI mode (pure API path, no CLI, App Store compliant)
- Single-model compatibility mode (Planner/Critic/Judge role decomposition)
- Gateway model slot coexistence
- OAuth usage query integration
- Play mode social features (share sessions, leaderboards)

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
- Protected files (mms_core.py, mms_launchers.py, etc.) require explicit authorization

### Common pitfalls to avoid
- Do NOT use `bg-[#0a0a0f]` or any hardcoded dark hex on view roots
- Do NOT use `getApiKey(providerId)` — use `getFetchRuntime()` instead
- Do NOT send raw compound model IDs (e.g. `company/glm-5-turbo`) to non-OpenRouter APIs
- Do NOT use `prose-invert` for markdown — use `.md-body`
- Do NOT add `--output-format stream-json` without `--verbose` when using `--print`
- Do NOT forget to update the collapsed sidebar icon rail when adding a nav entry
- Do NOT poll `appStore.models` without ensuring `appStore.initialize()` has run

### Play Mode conventions
- **Persistence:** All play modes use `PlayModeSessionEnvelope` as canonical shape. Store in localStorage (with `normalizeRecord` migration) or IndexedDB for larger data.
- **Model picking:** Never hardcode provider. Use `appStore.preferFree` + tier logic. `chooseModelIds()` picks diverse providers when possible.
- **Store size:** Single store file ≤ 800 lines. Extract module-level helpers to a co-located `*-helpers.ts` file when approaching limit.
- **Shared types:** `features/play-modes/shared/` contains the envelope type, phase guards, ending grades, history entry types. All modes import from here.
- **Validation:** Local heuristic validation (regex, string matching) runs on role outputs. Confidence-scored warnings (≥0.5) feed into director memory; below threshold are discarded as likely false positives.

---

## 11. Project Structure (apps/web-v2)

```
apps/web-v2/
├── src/
│   ├── features/
│   │   ├── play-modes/           # Play mode framework + all modes
│   │   │   ├── shared/           # Envelope types, phase guards, ending grades, registry
│   │   │   ├── story-live/       # 剧情共演 (types, prompts, state-utils, twist-trigger, validation, useStoryFlow)
│   │   │   ├── story-lite/       # 冒险模式 (types, prompts, mock, constants)
│   │   │   ├── turtle-soup/      # 海龟汤 (types, prompts, leak-guard, puzzles/)
│   │   │   └── case-reconstruction/  # 案件重构 (types, demo-case, validator)
│   │   ├── challenge/            # Daily Debate Challenge (types, prompts, topicSeeds)
│   │   └── committee/            # Advisors (role definitions, debate types, synthesis)
│   ├── stores/                   # Pinia stores
│   │   ├── app.ts                # Model list, selection, tier system
│   │   ├── provider.ts           # Provider/account config, keychain, JSON import/export
│   │   ├── chat.ts               # Chat rounds, streaming, context modes
│   │   ├── discuss.ts            # 3-phase debate, rollup
│   │   ├── committee.ts          # Broadcast/debate/committee modes
│   │   ├── persona.ts            # 12 preset personas, stance axes
│   │   ├── session.ts            # Session persistence (localStorage)
│   │   ├── dailyChallenge.ts     # Daily debate: topic, debate, thinking patterns (IndexedDB)
│   │   ├── storyLive.ts          # Live storytelling: 3-role, twist, endings (localStorage)
│   │   ├── story-live-helpers.ts # Story live helpers (extracted from store)
│   │   ├── turtleSoup.ts         # Lateral puzzles: host/verifier, hints (IndexedDB)
│   │   └── caseReconstruction.ts # Detective game: investigation, scoring (localStorage)
│   ├── views/                    # Page-level components (one per route)
│   │   ├── ChatView.vue          # /chat — parallel multi-model chat
│   │   ├── DiscussView.vue       # /discuss — structured debate
│   │   ├── AdvisorsView.vue      # /advisors — 12-role committee
│   │   ├── DailyChallengeView.vue # /challenge — daily debate
│   │   ├── StoryLiveView.vue     # /story-live — co-storytelling
│   │   ├── StoryLiteView.vue     # /story-lite — text adventure
│   │   ├── TurtleSoupView.vue    # /turtle-soup — lateral puzzles
│   │   ├── CaseReconstructionView.vue # /case-reconstruction — detective
│   │   ├── SettingsView.vue      # /settings — provider config, version display
│   │   └── ModelsView.vue        # /models — model management
│   ├── services/                 # API & security
│   │   ├── api.ts                # Unified API layer (OpenRouter/OpenAI/Anthropic)
│   │   ├── runtime.ts            # Model runtime resolution, account failover
│   │   ├── keychain.ts           # AES-256-GCM encrypted key storage (IndexedDB)
│   │   └── shareBundle.ts        # PBKDF2 + AES-256-GCM provider bundle encryption
│   ├── composables/              # Reusable reactive logic
│   ├── components/               # Shared UI components
│   │   ├── layout/               # Sidebar, IOSTabBar
│   │   ├── shared/               # IOSModelSheet, ToastContainer, CommandPalette
│   │   ├── chat/                 # ModelChipBar, InputBar, ModelResponseCard
│   │   ├── advisors/             # CommitteeModelPoolPicker, debate cards
│   │   └── challenge/            # TopicPicker, StanceInput, DebateStage
│   └── utils/                    # Utility functions
├── src-tauri/                    # Tauri Rust backend
└── package.json                  # Version: 0.3.5
```

Additional working notes:
- `apps/web-v2/src/views/StoryLiveView.vue` on mobile should collapse long director cues into compact A/B actions and keep transcript scroll pinned to the latest exchange.
- `apps/web-v2/src/views/StoryLiteView.vue` should use vivid transitional copy while the next scene is being generated, instead of a static spinner-only wait state.
- `apps/web-v2/src/views/MultiLifeView.vue` mobile header must stay low-density; when fast-pick reuses a provider, describe it as a speed bias rather than a provider shortage.
- `apps/web-v2/src/views/StoryLiteView.vue` should archive the previous chapter immediately after a choice is made; never leave old copy visible under the next-scene waiting state.
- `apps/web-v2/src/views/MultiLifeView.vue` should render only the newest round as the live scene and collapse previous rounds into an archived stack so chronology stays clear.
- `apps/web-v2/src/stores/app.ts` should deprioritize lab auto-pick models that timed out twice in the same day before escalating to full suppression.
