# xmem Card Schema

Keep cards short. Prefer under 100 lines.

Required fields:

```yaml
id: ads.lazyload
type: invariant
title: Ads must preserve lazy-load
scope:
  feature: ads
aliases:
  - ad lazyload
truth:
  status: verified
  confidence: 0.95
  basis:
    - code_observed
    - issue_record
  last_checked_at: 2026-05-22T00:00:00Z
summary: One durable fact or rule.
evidence:
  - kind: code
    path: src/ads/lazyload.ts
```

Storage rule: this YAML card is truth. SQLite rows generated from it are disposable cache.

Truth status:

- `verified`: backed by code/test/runtime/human/source API.
- `inferred`: guessed or imported from a partially trusted source.
- `partial`: useful but incomplete.
- `stale`: tied to old git sha/source state.
- `disputed`: conflicting cards/evidence exist.
- `unknown`: no basis yet.

For invariants, include optional diff guard:

```yaml
diff_guard:
  warn_if_removed:
    - IntersectionObserver
    - loading="lazy"
```
