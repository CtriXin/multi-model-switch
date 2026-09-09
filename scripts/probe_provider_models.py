#!/usr/bin/env python3
"""
probe_provider_models.py — 对 MMS/MMF 配置里的 provider×model 组合做真实可用性探测。

为什么不用 smoke_pi_matrix.py：那个脚本的 case 表是 2026-05 写死的固定路由，
只有 39 个 case，且带着当时的 blocked 标记，不覆盖 newapi 节点。本脚本直接从
config.toml 读 provider 的 fallback_models/extra_models（扣除 hidden_models），
逐个发真实请求。

已知坑（2026-09-02 实测）：
  1. newapi 的 base_url 常常不带 /v1，根路径返回的是网页 UI（HTML），必须补 /v1。
  2. gpt-5.x 系列强制流式，非流式会返回 400 "Stream must be set to true"。
     所以默认就用 stream=True 探测。

用法：
  python3 scripts/probe_provider_models.py                       # 探测所有 enabled provider
  python3 scripts/probe_provider_models.py -p newapi-personal-tokyo
  python3 scripts/probe_provider_models.py -p a,b -o report.json --workers 8
"""
from __future__ import annotations
import argparse, json, sys, time, tomllib, urllib.error, urllib.request
import concurrent.futures as cf
from pathlib import Path

DEFAULT_CFG = Path.home() / ".config" / "mms-next" / "config.toml"
PROMPT = "Reply with exactly PONG."


def load_providers(cfg_path: Path, only: set[str] | None):
    cfg = tomllib.load(open(cfg_path, "rb"))
    out = []
    for p in cfg.get("providers", []):
        pid = p.get("id") or p.get("route_provider_id")
        if not pid or (only and pid not in only):
            continue
        if not only and not p.get("enabled", True):
            continue
        base = p.get("openai_base_url") or p.get("default_openai_base_url")
        key = p.get("openai_api_key") or p.get("api_key")
        if not base or not key:
            continue
        base = base.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"          # 坑 1：newapi 根路径是网页 UI
        hidden = set(p.get("hidden_models") or [])
        models = [m for m in (p.get("fallback_models") or []) + (p.get("extra_models") or [])
                  if m not in hidden]
        out.append((pid, base, key, models))
    return out


def probe(pid: str, base: str, key: str, model: str, timeout: int):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 128,   # 太小会让 thinking 模型只吐 reasoning 就被截断
        "stream": True,           # 坑 2：gpt-5.x 强制流式
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions", data=body, method="POST",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 })
    t0 = time.time()
    try:
        text = ""
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = (json.loads(payload).get("choices") or [{}])[0].get("delta", {})
                    # thinking 模型流式时正文可能落在 reasoning_content，两者都算「活着」
                    text += (delta.get("content") or "") or (delta.get("reasoning_content") or "")
                except Exception:
                    pass
        return {"provider": pid, "model": model,
                "status": "pass" if text.strip() else "empty",
                "sec": round(time.time() - t0, 2), "detail": text.strip()[:60]}
    except urllib.error.HTTPError as e:
        return {"provider": pid, "model": model, "status": f"HTTP {e.code}",
                "sec": round(time.time() - t0, 2),
                "detail": e.read()[:200].decode("utf8", "replace")}
    except Exception as e:
        return {"provider": pid, "model": model, "status": type(e).__name__,
                "sec": round(time.time() - t0, 2), "detail": str(e)[:160]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-c", "--config", default=str(DEFAULT_CFG))
    ap.add_argument("-p", "--provider", help="逗号分隔的 provider id；省略则探测所有 enabled provider")
    ap.add_argument("-o", "--output", help="结果 JSON 输出路径")
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    only = {s.strip() for s in args.provider.split(",")} if args.provider else None
    provs = load_providers(Path(args.config), only)
    cases = [(pid, b, k, m) for pid, b, k, ms in provs for m in ms]
    if not cases:
        print("没有匹配到任何 provider×model 组合", file=sys.stderr)
        return 2

    print(f"探测 {len(cases)} 个组合，{len(provs)} 个 provider，并发 {args.workers}…", flush=True)
    results = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(probe, *c, args.timeout) for c in cases]
        for i, f in enumerate(cf.as_completed(futs), 1):
            r = f.result(); results.append(r)
            mark = "✅" if r["status"] == "pass" else "❌"
            print(f"  [{i}/{len(cases)}] {mark} {r['provider']:24} {r['model']:28} "
                  f"{r['status']:10} {r['sec']}s", flush=True)

    results.sort(key=lambda r: (r["provider"], r["model"]))
    ok = [r for r in results if r["status"] == "pass"]
    print(f"\n可用 {len(ok)}/{len(results)}")
    for pid, _, _, _ in provs:
        po = [r for r in ok if r["provider"] == pid]
        pt = [r for r in results if r["provider"] == pid]
        print(f"  {pid:26} {len(po)}/{len(pt)}")
    for r in results:
        if r["status"] != "pass":
            print(f"  ❌ {r['provider']:24} {r['model']:28} {r['status']:10} {r['detail'][:90]}")

    if args.output:
        Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"\n已写入 {args.output}")
    return 0 if len(ok) == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
