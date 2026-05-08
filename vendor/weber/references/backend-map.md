# Backend Map

Quick reference for choosing web/browser backend.

## Routing Table

| Task Shape | Backend | Why |
|---|---|---|
| Search, docs, known URL content | `web-access` | No browser overhead. search/fetch/curl/Jina. |
| Logged-in Chrome, dynamic sites, exploration | `web-access` CDP | Reuses user session. Full JS. |
| Screenshots, traces, a11y, deterministic steps | `playwright` | Reliable, traceable, CLI-first. |
| Fast headless, simple extraction, isolated | `agent-browser` | Ref-based CLI. No install bloat. |
| Batch crawl, concurrency, structured data | `Crawlee` | Built-in queue, retry, scaling. |
| Managed API approved | `Firecrawl` / `Browserless` | Cloud-hosted. Pay per use. |
| Code + NL automation | `Stagehand` | Natural language page actions. |
| LLM-loop agent experiments | `Browser Use` | Autonomous browser agent. |
| Authorized pages blocked by bot-detection heuristics | `Camofox` | Fingerprint-consistent browser backend. REST API. |
| Python crawling, adaptive tracking, large-scale scraping | `Scrapling` | Python framework. Anti-detect + adaptive element tracking. MCP built-in. |
| High-volume isolated headless | `Obscura` | Lightweight CDP. Experimental. |

## Isolated Runtime Guardrail

For logged-in Chrome tasks, `web-access` CDP is a required route, not just a preference. In MMS/Codex sandboxes, `HOME` may point at an isolated directory, so repair `web-access` before selecting headless fallback:

```bash
WEB_ACCESS_HOST_HOME="$(python3 -c 'import os,pwd; print(pwd.getpwuid(os.getuid()).pw_dir)')" \
  node /Users/xin/.codex/skills/web-access/scripts/check-deps.mjs
```

If stuck, kill only the `3456` proxy listener and rerun the check; do not restart the user's Chrome unless explicitly asked.

## Decision Flow

```
Is it just search/fetch/docs?
  Yes → web-access
  No → Need browser?
    No → Stop, use API/library
    Yes → Need login state or user Chrome?
      Yes → web-access CDP
      No → Need screenshots/traces/reliable automation?
        Yes → playwright
        No → Fast/simple/headless only?
          Yes → agent-browser
          No → Batch/crawl/concurrency?
            Yes → Crawlee
            No → Cloud API acceptable?
              Yes → Firecrawl / Browserless
              No → NL + code mix?
                Yes → Stagehand
                No → LLM-loop experiment?
                  Yes → Browser Use
                  No → Authorized task blocked by bot-detection heuristics?
                  Yes → Camofox
                  No → Python crawling, adaptive tracking, or large-scale structured scraping?
                    Yes → Scrapling (Python, install-on-demand)
                    No → Volume high, overhead matters?
                      Yes → Obscura (experimental)
```

## Backend Details

### web-access
- **Modes**: search, fetch, curl, Jina, CDP
- **Best for**: Search, docs, static content, logged-in browsing via CDP
- **Limits**: CDP needs running Chrome

### playwright
- **Install**: `npx --yes --package @playwright/cli@latest playwright-cli`
- **Best for**: UI tests, screenshots, traces, a11y snapshots
- **Strength**: Deterministic, traceable, skill wrapper available
- **Limits**: Heavier than agent-browser for simple tasks

### agent-browser
- **Check**: `agent-browser --version`
- **Best for**: Fast headless, simple extraction, isolated sessions
- **Strength**: Ref-based CLI, no Chrome login needed
- **Limits**: Less robust than Playwright for complex flows

### Crawlee
- **Best for**: Large queues, retries, concurrency, structured datasets
- **Context**: Node project dependency, not global CLI
- **Limits**: Requires Node project setup

### Firecrawl / Browserless
- **Best for**: Managed crawling when API keys approved
- **Cost**: Per-request or subscription
- **Limits**: Network dependency, rate limits

### Stagehand
- **Best for**: Production automation mixing code with natural language
- **Strength**: NL page actions reduce brittle selectors
- **Limits**: Newer tool, fewer docs

### Browser Use
- **Best for**: Autonomous browser agent experiments with LLM loop
- **Strength**: Fully autonomous, goal-driven
- **Limits**: Unpredictable, experimental

### Scrapling
- **Language**: Python 3.10+
- **Install**: `pip install "scrapling[all]"` then `scrapling install`
- **Check**: `python3 -c "import scrapling; print(scrapling.__version__)"`
- **Best for**: Large-scale crawling with adaptive element tracking, sites that change structure frequently
- **Strength**: Elements auto-relocate when site redesigns, built-in MCP server, Scrapy-style spider with checkpoint pause/resume
- **Limits**: Python dependency in Node-heavy stack, heavier than agent-browser for simple tasks
- **When to use**: Crawlee insufficient (need adaptive tracking), Python AI pipeline, or Scrapling MCP integration needed

### Camofox
- **Install**: `npm install @askjo/camofox-browser`; then `npx camoufox-js fetch`; then start `node node_modules/@askjo/camofox-browser/server.js` (downloads a browser binary on first run)
- **Check**: `curl -s http://localhost:9377/health`
- **Best for**: Authorized pages blocked by bot-detection heuristics, geo-specific public scraping
- **Strength**: Fingerprint-consistent browser runtime, REST API, compact a11y snapshots, approved proxy/locale/timezone configuration
- **Limits**: Single instance, no existing login state; do not export or inject user cookies without explicit approval
- **Note**: Consider only when bot-detection heuristics are the blocker and the task remains authorized

### Obscura
- **Status**: Experimental. Install-on-demand only.
- **Use when all true**:
  1. Authorized public or user-owned data
  2. Batch/headless, Chrome/Playwright overhead too high
  3. No existing local backend sufficient
  4. User told what binary/source build will install
- **Smoke test after install**:
  ```bash
  obscura fetch https://example.com --eval "document.title"
  obscura fetch https://example.com --dump links
  ```
- **Rule**: Do not make default until task-specific smoke tests pass.

## Baseline Checks

Refresh before routing decisions:

```bash
agent-browser --version
npx --yes --package @playwright/cli@latest playwright-cli --version
npm view playwright @playwright/cli @playwright/mcp agent-browser version --json
curl -s http://localhost:9377/health
command -v obscura
```

## Escalation Rule

Start with least invasive option. Escalate only when evidence shows insufficiency. Never retry same backend when blocked — re-route based on blocker.
