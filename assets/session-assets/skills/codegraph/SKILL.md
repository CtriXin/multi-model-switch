---
name: codegraph
description: Prefer CodeGraph for codebase discovery, architecture questions, caller/callee tracing, and impact analysis before broad file reads or grep.
---

# CodeGraph

Use CodeGraph as the first stop for codebase discovery. It reduces context by
querying the indexed symbol graph before reading files.

## When To Use

- User asks how a feature works, where logic lives, or why a bug happens.
- You need definitions, callers, callees, symbol relationships, or impact radius.
- A change may affect multiple call sites.
- You are tempted to run broad `rg`, `grep`, or open many files only to orient.

## Preferred Flow

1. Start with `codegraph_context` for architecture, feature, or bug-context work.
2. Use `codegraph_files` for project structure instead of filesystem scans.
3. Use `codegraph_search` for known symbol/file names.
4. Use `codegraph_explore` once when several related symbols need source together.
5. Use `codegraph_impact` before changing a shared symbol.

## Boundaries

- Do not hard-block targeted `Read`, `rg`, or file edits; use them after graph
  discovery when exact source or patches are needed.
- Do not run broad shell searches when a graph query can answer the orientation
  question.
- If the graph is missing or stale, initialize/sync only when the repo is
  writable and the task benefits from it; keep `.codegraph/` local unless the
  repo explicitly tracks it.
- For long command output, use `token-saver` / `mms-context` instead of dumping
  logs into chat. CodeGraph handles code structure; token-saver handles noisy
  output.
