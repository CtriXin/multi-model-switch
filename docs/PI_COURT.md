# Pi Court

Pi Court is an opt-in, read-only role layer over the isolated Pi committee worker runtime. It does not replace `pi-committee`: the committee remains the generic model-diversity lane, while Court adds explicit seats, canonical Soul procedures, required-domain coverage, and model/role correlation evidence.

## Runtime boundary

- MMS owns verified model routes, provider fallback, isolation, watchdog, and transport evidence.
- Pi Court inherits the 30-day bundle freshness gate and the 300s Kimi per-route attempt cap from `pi-committee`.
- Pi executes each read-only seat.
- `agent-spec` owns canonical `roles/*.min.md`; Pi Court loads them by explicit root and hash.
- agent-soul runtime and memory are not called.
- The current Codex or other Parent owns semantic synthesis.

## Built-in profiles

- `general`: six Soul-free independent lenses.
- `hybrid`: required design/product/development/testing seats, one cross-cutting challenger, and one wildcard.
- `cross-functional`: two seats per required domain using `designer-soul`, `frontend-architect`, `critic`, `subtractor`, `architect`, `challenger`, `qa`, and `audit`.

Custom profiles use `mms.pi_court.profile.v1` and bind roles, not permanent model names. Mission-level `--seat-model` can intentionally place the same model in more than one seat; the Parent packet reports that correlation and forbids treating it as independent model support.

## Readiness

`mms.pi_court.parent_packet.v1` is synthesis-ready only when:

1. The inherited Pi committee member-success floor passes.
2. Every `required_domain` has at least one successful seat.

The packet separates model corroboration, perspective corroboration, and cross-role/model corroboration. Failed domains remain explicit even when total success count is high.
