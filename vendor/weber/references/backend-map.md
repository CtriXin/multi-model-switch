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
| High-volume isolated headless | `Obscura` | Lightweight CDP. Experimental. |

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
command -v obscura
```

## Escalation Rule

Start with least invasive option. Escalate only when evidence shows insufficiency. Never retry same backend when blocked — re-route based on blocker.
