#!/usr/bin/env python3
"""
sync_pi_models.py — 把 MMS 全部 enabled provider 的模型目录一次性写成 Pi 的 models.json。

为什么需要它：
  MMS 只在启动 pi 会话时写 models.json，且只写【当次选中的 provider】，落在
  ~/.config/mms-next/pi-gateway/s/<sid>/.pi/agent/。而 runtimia daemon 直接 exec `pi`，
  读的是 PI_CODING_AGENT_DIR（默认 ~/.pi/agent），于是永远停在某次会话的旧快照上。
  实测 2026-09-02：~/.pi 那份停在 7-31，缺 glm-5.3 / grok-4.6；而当天的会话快照有
  glm-5.3 却缺 CRS gpt 系 —— 两份各缺一半。

本脚本遍历所有 enabled provider，合并成一份全量表，供 daemon 常驻使用。

用法：
  python3 scripts/sync_pi_models.py --out ~/.pi-daemon/agent          # 写 daemon 专用目录
  python3 scripts/sync_pi_models.py --out ~/.pi/agent                 # 覆盖全局（会被手动会话再覆盖）
  python3 scripts/sync_pi_models.py --dry-run                         # 只打印，不写
  python3 scripts/sync_pi_models.py --provider newapi-personal-tokyo  # 限定 provider
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tomllib             # noqa: E402
import mms_pi_support      # noqa: E402

DEFAULT_CFG = Path.home() / ".config" / "mms-next" / "config.toml"


def load_runtimes(only: set[str] | None, cfg_path: Path = DEFAULT_CFG):
    """直接读 config.toml。

    不用 mms_core.load_config()：它返回的 provider 已被剥掉 base_url / api_key
    （MMS 在启动时才按 route bundle 解析），传给 payload builder 会报
    「当前 provider 还没有配置 API 地址和 API Key」。原始 toml 里这些字段是全的。
    """
    cfg = tomllib.load(open(cfg_path, "rb"))
    out = []
    for p in cfg.get("providers", []) or []:
        pid = p.get("id") or p.get("route_provider_id")
        if not pid:
            continue
        if only and pid not in only:
            continue
        if not only and not p.get("enabled", True):
            continue
        out.append((pid, dict(p)))
    return out


def build_full_payload(runtimes, verbose=True):
    """把每个 provider 的每个模型都跑一遍 payload 构建，再合并 providers 段。"""
    merged: dict = {}
    stats = []
    for pid, runtime in runtimes:
        hidden = set(runtime.get("hidden_models") or [])
        models = [m for m in (runtime.get("fallback_models") or []) + (runtime.get("extra_models") or [])
                  if m not in hidden]
        added, failed = 0, []
        for model in models:
            try:
                payload, _ref = mms_pi_support._pi_build_models_payload(runtime, model)
            except Exception as exc:                      # 单模型失败不影响整体
                failed.append((model, f"{type(exc).__name__}: {exc}"))
                continue
            for ref, block in (payload.get("providers") or {}).items():
                slot = merged.setdefault(ref, {**block, "models": []})
                have = {m.get("id") for m in slot["models"]}
                for m in block.get("models") or []:
                    if m.get("id") not in have:
                        slot["models"].append(m)
                        have.add(m.get("id"))
                        added += 1
        stats.append((pid, len(models), added, failed))
        if verbose:
            mark = "✅" if added else "⚠️"
            print(f"  {mark} {pid:26} 模型 {len(models):2} 个 → 展开 {added:2} 条"
                  + (f"，失败 {len(failed)}" if failed else ""))
            for m, why in failed[:3]:
                print(f"       ✗ {m}: {why[:90]}")
    return {"providers": merged}, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(Path.home() / ".pi-daemon" / "agent"),
                    help="Pi agent 目录（写入 models.json），默认 ~/.pi-daemon/agent")
    ap.add_argument("--provider", help="逗号分隔的 provider id；省略则全部 enabled provider")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    only = {s.strip() for s in args.provider.split(",")} if args.provider else None
    runtimes = load_runtimes(only)
    if not runtimes:
        print("没有匹配到 provider", file=sys.stderr)
        return 2
    print(f"遍历 {len(runtimes)} 个 provider：")
    payload, _stats = build_full_payload(runtimes)

    provs = payload["providers"]
    total = sum(len(p.get("models") or []) for p in provs.values())
    print(f"\n合并结果：provider {len(provs)} 个 / 模型 {total} 条")
    ORDER = ["off", "minimal", "low", "medium", "high", "xhigh", "max"]
    for ref, block in sorted(provs.items()):
        for m in block.get("models") or []:
            lv = [k for k in ORDER if (m.get("thinkingLevelMap") or {}).get(k)]
            print(f"    {ref}/{m['id']:28} {', '.join(lv) if lv else '-'}")

    if args.dry_run:
        print("\ndry-run：未写入")
        return 0

    agent_dir = Path(os.path.expanduser(args.out))
    agent_dir.mkdir(parents=True, exist_ok=True)
    dest = agent_dir / "models.json"
    if dest.exists():
        bak = dest.with_suffix(".json.bak")
        bak.write_text(dest.read_text())
        print(f"\n已备份旧表 → {bak}")
    mms_pi_support.atomic_write_text(str(dest), json.dumps(payload, indent=2) + "\n", mode=0o600)
    print(f"已写入 {dest}")
    print(f"\n让 runtimia daemon 用这份表：PI_CODING_AGENT_DIR={agent_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
