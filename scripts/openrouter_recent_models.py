#!/usr/bin/env python3
"""List the newest models on OpenRouter, as a candidate source for profiles.

OpenRouter is a fallback, not the truth. It does not route most of the model
ids MMS configures, and where it does it reports the limits of whichever
upstream it currently selects, not the vendor's own figures. See
docs/reference/MODEL_CAPABILITY_SOURCES.md before copying anything from here
into config/provider-profiles.json.

    python3 scripts/openrouter_recent_models.py            # 20 newest
    python3 scripts/openrouter_recent_models.py --limit 50
    python3 scripts/openrouter_recent_models.py --missing  # not in our profiles
"""
from __future__ import annotations
import argparse
import datetime
import json
from pathlib import Path
import urllib.request

URL = "https://openrouter.ai/api/v1/models"
ROOT = Path(__file__).resolve().parent.parent


def fetch(url: str, timeout: float) -> list[dict]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8")).get("data") or []


def our_model_ids() -> set[str]:
    profiles = json.loads((ROOT / "config/provider-profiles.json").read_text()).get("profiles") or {}
    ids: set[str] = set()
    for profile in profiles.values():
        for section in ("context_windows", "max_output_tokens", "supports_vision"):
            ids.update(str(key).lower() for key in (profile.get(section) or {}))
    return ids


def row(model: dict) -> tuple[str, str, str, str, str]:
    top = model.get("top_provider") or {}
    created = model.get("created") or 0
    context = model.get("context_length") or top.get("context_length")
    return (str(model.get("id") or ""),
            str(datetime.date.fromtimestamp(created)) if created else "-",
            str(context or "-"),
            str(top.get("max_completion_tokens") or "-"),
            "yes" if "image" in ((model.get("architecture") or {}).get("input_modalities") or []) else "no")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--missing", action="store_true", help="only models we have no profile entry for")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        models = fetch(URL, args.timeout)
    except Exception as error:
        print(f"读取 OpenRouter 失败: {type(error).__name__}: {error}")
        return 2
    models.sort(key=lambda item: item.get("created") or 0, reverse=True)
    if args.missing:
        known = our_model_ids()
        # Match on the bare name too: OpenRouter namespaces ids as vendor/model.
        models = [m for m in models
                  if str(m.get("id") or "").lower() not in known
                  and str(m.get("id") or "").split("/")[-1].lower() not in known]
    models = models[: max(1, args.limit)]
    if args.json:
        print(json.dumps(models, ensure_ascii=False, indent=2))
        return 0
    print(f"{'model id':46s} {'created':11s} {'context':>9s} {'max out':>9s}  image")
    for model in models:
        model_id, created, context, output, image = row(model)
        print(f"{model_id:46s} {created:11s} {context:>9s} {output:>9s}  {image}")
    print(f"\n{len(models)} 条。OpenRouter 是备选来源，写入 profile 前先查 docs/reference/MODEL_CAPABILITY_SOURCES.md 里的官方页面。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
