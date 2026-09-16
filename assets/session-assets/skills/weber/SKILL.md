---
name: weber
description: Use when the user wants web or browser automation but tool choice is unclear. Weber is the single web skill in MMS sessions; it prefers ego-browser when that command is available, then the user's logged-in Chrome through the bundled web-access backend, then an isolated backend for tasks that need no login. Direct known routes do not need this router.
---

# Weber Skill

Weber is the single user-facing web skill. It is a router, not a replacement for browser tools: pick the smallest reliable backend for an authorized web task, then follow that backend's own instructions. `web-access` and `agent-browser` ship inside this skill as `backends-web-access/` and `backends-agent-browser/`; never look for them as separate user skills.

Backend precedence:

1. `ego-browser` when `command -v ego-browser` succeeds. It runs in its own task space, reuses the user's login state, and can hand the page to the user.
2. `web-access` CDP when the task specifically needs the user's current Chrome tab or profile and Ego is unavailable.
3. An isolated backend (`agent-browser`, Playwright, a crawler) when the task needs no login at all.

Public search, documentation lookup, static URL reading and supported structured API/CLI operations use the existing purpose-built tool; they do not need a browser or this router.

## Hard Boundaries

- Work only on authorized systems, user-owned sessions, local apps, or public data that can be accessed normally.
- Do not frame the goal as bypassing access controls, rate limits, login requirements, bans, CAPTCHAs, or platform protections.
- Before adding dependencies, changing global config, installing a browser engine, or using a paid/cloud API, explicitly tell the user what will change, where, and why.
- Prefer existing local tools before installing anything.
- Do not export cookies, tokens, localStorage, credentials, or private page data into reusable artifacts.
- For account mutation or public publishing, require user authorization for that scope. An adapter's technical capability is not permission.

## Chrome Resource Management

- Ordinary API/search work creates no browser. Spawn an isolated Chromium only for a task that needs it.
- For `ego-browser`, reuse one task space per user goal and always close or complete it when done. Use `{ keep: true }` only when the user should see the resulting page.
- After `agent-browser` or Playwright tasks, close only the task-owned named session with that backend's own close command and verify it is gone. Never use `close-all`, `kill-all`, broad `pkill`, or `killall` for routine cleanup: they can terminate the user's browser or a concurrent agent's session.
- Never leave Chrome for Testing running when the task is done.

## Host Chrome And Isolated Runtimes

- MMS sessions export `WEBER_SKILL_DIR`, `WEB_ACCESS_SKILL_DIR` and `AGENT_BROWSER_SKILL_DIR`. Use them before guessing paths; outside MMS the backends are the `backends-*` folders next to this file.
- MMS sessions also export `WEB_ACCESS_HOST_HOME` / `REAL_HOME` / `HOST_HOME`; MMS and Codex sandboxes may rewrite `HOME`/`XDG_*`, so do not assume `os.homedir()` points at the real Chrome profile. Prefer `MMS_HOST_CONTEXT_JSON` for host hints when present.
- Before declaring `web-access` unavailable from an isolated session, run its dependency check with host-home hints:

```bash
WEBER_DIR="${WEBER_SKILL_DIR:-$(cd "$(dirname "$0")" 2>/dev/null && pwd)}"
WEB_ACCESS_BACKEND_DIR="${WEB_ACCESS_SKILL_DIR:-$WEBER_DIR/backends-web-access}"
WEB_ACCESS_HOST_HOME="${WEB_ACCESS_HOST_HOME:-$(python3 -c 'import os,pwd; print(pwd.getpwuid(os.getuid()).pw_dir)')}" \
  node "$WEB_ACCESS_BACKEND_DIR/scripts/check-deps.mjs"
```

- If the proxy is stale, kill only the `3456` listener and rerun `check-deps`; do not kill/restart the user's Chrome unless explicitly asked.
- Treat `3456` as the CDP proxy and `9222` as the real Chrome debug endpoint; if `9222` is already listening, keep Chrome running and reconnect the proxy.
- Do not switch to Playwright, `agent-browser`, Camofox, or Obscura for a logged-in-user task just because the isolated agent cannot see the host Chrome profile. Diagnose the failed route once, then choose a bounded alternative instead of an open-ended repair loop.
- If using the unified adapter for a logged-in-user task, pass `requireLoggedInChrome: true` so fallback cannot jump to an isolated backend.

## Default Routing

Choose by task shape:

| Need | Use |
| --- | --- |
| Any live page interaction, screenshots, clicks/forms, exploratory reading, or user handoff when `ego-browser` is installed | `ego-browser` in an ego lite task space |
| Search, source discovery, known URL extraction, official docs lookup | `web-access` search/fetch/curl/Jina, no browser |
| The user's current Chrome tab or profile is required and Ego is unavailable | `web-access` CDP (bundled backend) |
| Repeated supported-site command or reusable adapter, when `opencli` is installed | `OpenCLI`; fall back to `web-access` for one-off inspection |
| Local webapp verification, UI flow debugging, traces, accessibility snapshots, deterministic CLI steps | `playwright` skill / Playwright CLI; annotate visual evidence in red with labels outside the target region |
| Fast headless interaction with a ref-based CLI, isolated sessions, no login needed | `agent-browser` (bundled backend) |
| Large URL queues, site crawl, retries, concurrency, structured datasets in a Node project | `Crawlee` or project-native crawler code |
| Managed crawling/scraping/search API is acceptable and API keys/cost are approved | `Firecrawl` or `Browserless` |
| Production automation mixing code with natural-language page handling | `Stagehand` |
| Autonomous browser agent experiments with an LLM loop | `Browser Use` |
| Authorized pages blocked by bot-detection heuristics, geo-specific public scraping with approved proxy | `Camofox` |
| Python crawling, adaptive element tracking, large-scale structured scraping with checkpoint/resume | `Scrapling` |
| Experimental lightweight CDP-compatible engine for high-volume isolated headless work | `Obscura`, installed only when a concrete task justifies it |

When uncertain, start with the least invasive option that can prove progress, then escalate only when evidence shows it is insufficient.

## Execution Loop

1. Define success: the exact data, UI state, screenshot, trace, or artifact needed.
2. Check available local tools before installing: `command -v ego-browser`, `command -v opencli`, `command -v agent-browser`, `command -v npx`, and project package files.
3. Pick one primary backend and keep the first attempt small.
4. Validate with evidence: extracted rows/counts, current URL/title, snapshot, screenshot, trace, or output file.
5. If blocked, re-route based on the blocker instead of repeatedly retrying the same backend.

## Core Backend: ego-browser

Use `ego-browser` for general live-browser work in ego lite task spaces. It is the default local browser backend when the task needs a real page, DOM snapshot, click/form interaction, screenshot, or user handoff, and does not specifically require the user's current Chrome tab.

Safe route:

```bash
command -v ego-browser && ego-browser --version
ego-browser nodejs <<'EOF_EGO'
const task = await useOrCreateTaskSpace('inspect example page')
await openOrReuseTab('https://example.com', { wait: true, timeout: 20 })
cliLog(await snapshotText())
await completeTaskSpace(task.id, { keep: false })
EOF_EGO
```

Rules:
- Prefer the app-bundled `ego-browser` command; a copied JavaScript wrapper is not enough unless the native ego lite runtime binding is available.
- Use `handOffTaskSpace(...)` for login, CAPTCHA, manual confirmation, or when the user needs to take over. If the user takes control, do not seize it back; wait for an explicit "continue" before `takeOverTaskSpace(...)`.
- Use `web-access` search/fetch instead for static reading or source discovery that does not need a browser.
- Use Playwright instead for deterministic repo tests, traces, and CI-friendly UI evidence.

## Bundled Backend: web-access

`backends-web-access/` is the CDP route into the user's logged-in Chrome plus search/fetch helpers. Read `backends-web-access/SKILL.md` only after choosing it. Run `scripts/check-deps.mjs` with `WEB_ACCESS_HOST_HOME` set (see above) before declaring it unavailable.

## Bundled Backend: agent-browser

`backends-agent-browser/` is a ref-based headless CLI for isolated sessions that need no login. Read `backends-agent-browser/SKILL.md` only after choosing it, and close the task-owned session when done.

## Optional Backend: OpenCLI

Use `OpenCLI` when `command -v opencli` works and the task is or should become a stable command surface instead of one-off page driving. Prefer it over raw browser control when an adapter exists and a same-session smoke test returns complete data; fall back to `web-access` after one small diagnostic instead of looping retries. Do not run account-mutating commands without explicit user confirmation of the exact target/content/action.

## Optional Backend: Scrapling

Python scraping framework with adaptive element tracking. Install-on-demand.

Use when:
- Crawlee insufficient: sites change structure frequently, need elements to auto-relocate
- Python AI pipeline needs crawling with MCP integration
- Large-scale crawling with checkpoint pause/resume needed

Install:
```bash
pip install "scrapling[all]" && scrapling install
```

Smoke test:
```bash
python3 -c "from scrapling import Fetcher; print(Fetcher('https://example.com').status)"
```

Key API: `Fetcher` (HTTP), `StealthyFetcher` (anti-detect), `DynamicFetcher` (Playwright), `Adaptor.find_similar()` (adaptive tracking).

Limitations: Python 3.10+ required, heavier than Node alternatives for simple tasks.

## Optional Backend: Camofox

Anti-detection headless browser server wrapping Camoufox (Firefox fork with C++ fingerprint spoofing). REST API on `localhost:9377`.

Use when:
- An authorized page is inaccessible to simpler automation because of bot-detection heuristics, and the task does not require bypassing login, CAPTCHA, bans, or access controls
- Need geo-specific public scraping with an approved proxy/locale/timezone setup
- Need compact a11y snapshots instead of raw HTML dumps

Install:
```bash
npm install @askjo/camofox-browser
npx camoufox-js fetch   # download ~300MB binary on first run
node node_modules/@askjo/camofox-browser/server.js  # start server
```

Smoke test:
```bash
curl -s http://localhost:9377/health
curl -s -X POST http://localhost:9377/tabs -H 'Content-Type: application/json' -d '{"url":"https://example.com"}'
```

Key API: `POST /tabs` (create), `GET /tabs/:id/snapshot` (a11y), `POST /tabs/:id/click` (by ref), `POST /tabs/:id/navigate`, `DELETE /tabs/:id` (close).

Limitations: Single instance, no existing login state; do not export or inject user cookies unless the user explicitly approves that flow.

## Optional Backend: Obscura

Treat Obscura as experimental and install-on-demand only.

Use it when all are true:

- The task is authorized public or user-owned data extraction.
- The workload is batch/headless enough that Chrome/Playwright overhead matters.
- No existing local backend is sufficient.
- The user has been told what binary or source build will be installed.

Safe smoke test after install:

```bash
obscura fetch https://example.com --eval "document.title"
obscura fetch https://example.com --dump links
```

Do not make Obscura the default backend until it passes task-specific smoke tests on the user's machine.

## Unified Browser Adapter

`lib/` 目录提供跨后端统一接口，屏蔽 Camoufox/Playwright/agent-browser/web-access 差异。

```typescript
import { createBrowser } from './lib'

// 自动选后端 + 降级
const browser = await createBrowser({ backend: 'auto' })
const session = await browser.exec(a => a.open('https://example.com'))
await browser.exec(a => a.click(session, 'button.submit'))
const shot = await browser.exec(a => a.screenshot(session, { path: '/tmp/result.png' }))
await browser.exec(a => a.close(session))

// 登录态 Chrome 任务：禁止降级到 isolated backend
const browser = await createBrowser({ requireLoggedInChrome: true })

// 指定后端
const browser = await createBrowser({ backend: 'camoufox' })
```

降级链：`web-access → playwright → agent-browser → camoufox`（可配置）

各 adapter 详见：`lib/adapters/` 目录。

## References

Read `references/backend-map.md` when comparing new tools, deciding whether to install Obscura or a crawler, or updating this router.
