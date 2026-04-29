---
name: weber
description: Use when the user wants web or browser automation but tool choice is unclear, including authorized browser interaction, local webapp UI testing, screenshots/traces, public crawling or scraping, batch data extraction, headless browser backends, or choosing between web-access, Playwright, agent-browser, Crawlee, Firecrawl/Browserless, Browser Use/Stagehand, and Obscura.
---

# Weber Skill

Weber is a router, not a replacement for browser tools. Use it to choose the smallest reliable backend for an authorized web task, then load/follow the chosen tool's own skill or docs.

## Hard Boundaries

- Work only on authorized systems, user-owned sessions, local apps, or public data that can be accessed normally.
- Do not frame the goal as bypassing access controls, rate limits, login requirements, bans, CAPTCHAs, or platform protections.
- Before adding dependencies, changing global config, installing a browser engine, or using a paid/cloud API, explicitly tell the user what will change, where, and why.
- Prefer existing local tools before installing anything.
- Do not export cookies, tokens, localStorage, credentials, or private page data into reusable artifacts.

## Default Routing

Choose by task shape:

| Need | Use |
| --- | --- |
| Search, source discovery, known URL extraction, official docs lookup | `web-access` with search/fetch/curl/Jina as appropriate |
| Logged-in user Chrome, internal sites, dynamic pages, social/content sites, exploratory browser navigation | `web-access` CDP |
| Local webapp verification, UI flow debugging, screenshots, traces, accessibility snapshots, deterministic CLI steps | `playwright` skill / Playwright CLI wrapper; for visual/UI evidence, create QA-ready red annotated screenshots with labels outside the target region and connector lines |
| Fast headless interaction with ref-based CLI, simple extraction, isolated sessions, no user Chrome login needed | `agent-browser` |
| Large URL queues, site crawl, retries, concurrency, structured datasets in a Node project | `Crawlee` or project-native crawler code |
| Managed crawling/scraping/search API is acceptable and API keys/cost are approved | `Firecrawl` or `Browserless` |
| Production automation mixing code with natural-language page handling | `Stagehand` |
| Autonomous browser agent experiments with an LLM loop | `Browser Use` |
| Experimental lightweight CDP-compatible engine for high-volume isolated headless work | `Obscura`, installed only when a concrete task justifies it |

When uncertain, start with the least invasive option that can prove progress, then escalate only when evidence shows it is insufficient.

## Execution Loop

1. Define success: the exact data, UI state, screenshot, trace, or artifact needed.
2. Check available local tools before installing: `command -v agent-browser`, `command -v npx`, `command -v obscura`, and project package files.
3. Pick one primary backend and keep the first attempt small.
4. Validate with evidence: extracted rows/counts, current URL/title, snapshot, screenshot, trace, or output file.
5. For visual/UI evidence, annotate full-page screenshots by marking the exact changed, broken, or verified region in red; prefer browser/Playwright locator bounding boxes, keep labels outside important content, and use connector lines.
6. If blocked, re-route based on the blocker instead of repeatedly retrying the same backend.

## Installed Baseline Checks

Use these commands to refresh assumptions; versions change over time:

```bash
agent-browser --version
npx --yes --package @playwright/cli@latest playwright-cli --version
npm view playwright @playwright/cli @playwright/mcp agent-browser version --json
```

The ClawSkills `thesethrose/agent-browser` entry is the same tool family as the local `agent-browser` skill/CLI. Do not install it again if `agent-browser --version` works.

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

## References

Read `references/backend-map.md` when comparing new tools, deciding whether to install Obscura or a crawler, or updating this router.
