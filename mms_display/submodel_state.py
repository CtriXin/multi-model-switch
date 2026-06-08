"""State helpers for the submodel picker TUI."""

from __future__ import annotations

from mms_runtime.i18n import pick as _L


def _load_speed_entry():
    try:
        from mms_runtime.speed_stats import get_speed_entry
    except Exception:
        return None
    return get_speed_entry


def format_ttfb(value):
    if isinstance(value, (int, float)):
        return f"{value:.0f}ms"
    return "-"


def format_age(seconds):
    if not isinstance(seconds, (int, float)):
        return "-"
    if seconds < 3600:
        minutes = max(1, int(seconds // 60) or 1)
        return f"{minutes}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


class SubmodelProviderState:
    def __init__(
        self,
        sorted_models,
        *,
        provider_options=None,
        provider_options_loader=None,
        get_speed_entry=None,
    ):
        self.sorted_models = list(sorted_models or [])
        self.provider_options_cache = dict(provider_options or {})
        self.provider_options_loader = provider_options_loader
        self.get_speed_entry = get_speed_entry if get_speed_entry is not None else _load_speed_entry()
        self.provider_overrides = {}
        self.priority_changes = {}

    @property
    def has_changes(self):
        return bool(self.provider_overrides or self.priority_changes)

    def priority_change_key(self, opt):
        if not isinstance(opt, dict):
            return ""
        pid = str(opt.get("provider_id", "")).strip()
        if not pid:
            return ""
        family = str(
            opt.get("priority_family")
            or (opt.get("provider_ctx") or {}).get("priority_family")
            or ""
        ).strip()
        return f"{pid}||{family}" if family else pid

    def effective_priority(self, opt):
        change_key = self.priority_change_key(opt)
        if change_key and change_key in self.priority_changes:
            return int(self.priority_changes[change_key])
        return int((opt.get("provider_ctx") or {}).get("priority", 100) or 100)

    def provider_options_for_model(self, model_name):
        model_key = str(model_name or "").strip()
        if not model_key:
            return []
        if model_key in self.provider_options_cache:
            return self.provider_options_cache[model_key]
        if callable(self.provider_options_loader):
            try:
                self.provider_options_cache[model_key] = list(self.provider_options_loader(model_key) or [])
            except Exception:
                self.provider_options_cache[model_key] = []
        else:
            self.provider_options_cache[model_key] = []
        return self.provider_options_cache[model_key]

    def provider_choices(self, model_entry):
        if not isinstance(model_entry, dict):
            return []

        choices = []
        seen = set()
        current = {
            "provider_name": model_entry.get("provider_name", ""),
            "provider_id": model_entry.get("provider_id", ""),
            "provider_ctx": model_entry.get("provider_ctx", {}),
        }
        current_id = current.get("provider_id")
        if current_id:
            choices.append(current)
            seen.add(current_id)

        for opt in self.provider_options_for_model(model_entry.get("model")):
            pid = opt.get("provider_id", "")
            if not pid or pid in seen:
                continue
            choices.append(opt)
            seen.add(pid)

        choices.sort(
            key=lambda opt: (
                -self.effective_priority(opt),
                opt.get("provider_name", ""),
            )
        )
        return choices

    def active_provider_choice(self, model_entry):
        if not isinstance(model_entry, dict):
            return {"provider_name": "", "provider_id": "", "provider_ctx": {}}
        override = self.provider_overrides.get(model_entry.get("model"))
        if override:
            return override
        choices = self.provider_choices(model_entry)
        if choices:
            return choices[0]
        return {
            "provider_name": model_entry.get("provider_name", ""),
            "provider_id": model_entry.get("provider_id", ""),
            "provider_ctx": model_entry.get("provider_ctx", {}),
        }

    def get_provider_info(self, model_entry):
        active = self.active_provider_choice(model_entry)
        return (
            active.get("provider_name", ""),
            active.get("provider_id", ""),
            self.effective_priority(active),
        )

    def get_result(self, model_entry):
        active = self.active_provider_choice(model_entry)
        result = {
            **model_entry,
            "provider_name": active.get("provider_name", ""),
            "provider_id": active.get("provider_id", ""),
            "provider_ctx": {
                **(active.get("provider_ctx", {}) or {}),
                "priority": self.effective_priority(active),
            },
        }
        if self.priority_changes:
            result["priority_changes"] = dict(self.priority_changes)
        return result

    def record_priority_swap(self, model_entry, chosen):
        new_pid = chosen.get("provider_id", "")
        orig_pid = model_entry.get("provider_id", "")
        if not new_pid or not orig_pid or new_pid == orig_pid:
            return

        orig_opt = {
            "provider_id": orig_pid,
            "provider_ctx": model_entry.get("provider_ctx", {}),
        }
        orig_pri = self.effective_priority(orig_opt)
        new_base = self.effective_priority(chosen)
        new_key = self.priority_change_key(chosen)
        orig_key = self.priority_change_key(orig_opt)

        if new_key:
            self.priority_changes.setdefault(new_key, min(200, max(new_base, orig_pri) + 5))
        if orig_key:
            self.priority_changes.setdefault(orig_key, max(0, min(orig_pri, new_base) - 5))

    def adjust_provider_priority(self, opt, delta):
        change_key = self.priority_change_key(opt)
        if not change_key:
            return
        current = self.effective_priority(opt)
        self.priority_changes[change_key] = max(0, min(200, current + delta))

    def build_family_autosort_plan(self):
        if not callable(self.get_speed_entry):
            return {
                "items": [],
                "changes": {},
                "can_apply": False,
                "summary": _L("本地测速模块不可用", "Local speed stats unavailable"),
            }

        aggregated = {}
        for model_entry in self.sorted_models:
            model_name = str(model_entry.get("model") or "").strip()
            if not model_name:
                continue
            seen = set()
            for opt in self.provider_choices(model_entry):
                change_key = self.priority_change_key(opt)
                if not change_key or change_key in seen:
                    continue
                seen.add(change_key)
                entry = aggregated.setdefault(
                    change_key,
                    {
                        "change_key": change_key,
                        "provider_id": opt.get("provider_id", ""),
                        "provider_name": opt.get("provider_name", ""),
                        "provider_ctx": dict(opt.get("provider_ctx") or {}),
                        "current_priority": self.effective_priority(opt),
                        "available_models": 0,
                        "fresh_samples": 0,
                        "fresh_ttfb_sum": 0.0,
                        "fresh_models": 0,
                        "stale_samples": 0,
                        "stale_ttfb_sum": 0.0,
                        "stale_models": 0,
                        "warming_models": 0,
                        "best_age_seconds": None,
                    },
                )
                entry["available_models"] += 1
                speed = self.get_speed_entry(model_name, provider=opt.get("provider_ctx"))
                if not isinstance(speed, dict):
                    continue
                ttfb = speed.get("ttfb_avg_ms")
                samples = int(speed.get("samples") or 0)
                age_seconds = speed.get("age_seconds")
                if isinstance(age_seconds, (int, float)):
                    best_age = entry.get("best_age_seconds")
                    if best_age is None or age_seconds < best_age:
                        entry["best_age_seconds"] = float(age_seconds)
                if speed.get("warming_up"):
                    entry["warming_models"] += 1
                if not isinstance(ttfb, (int, float)) or samples <= 0:
                    continue
                if speed.get("is_stale"):
                    entry["stale_samples"] += samples
                    entry["stale_ttfb_sum"] += float(ttfb) * samples
                    entry["stale_models"] += 1
                else:
                    entry["fresh_samples"] += samples
                    entry["fresh_ttfb_sum"] += float(ttfb) * samples
                    entry["fresh_models"] += 1

        items = []
        for entry in aggregated.values():
            fresh_avg = (
                round(entry["fresh_ttfb_sum"] / entry["fresh_samples"], 2)
                if entry["fresh_samples"] > 0
                else None
            )
            stale_avg = (
                round(entry["stale_ttfb_sum"] / entry["stale_samples"], 2)
                if entry["stale_samples"] > 0
                else None
            )
            if fresh_avg is not None:
                state = "fresh"
                effective_ttfb = fresh_avg
                samples = entry["fresh_samples"]
            elif stale_avg is not None:
                state = "stale"
                effective_ttfb = stale_avg
                samples = entry["stale_samples"]
            else:
                state = "none"
                effective_ttfb = None
                samples = 0
            measured_models = int(entry["fresh_models"] + entry["stale_models"])
            item = dict(entry)
            item.update(
                {
                    "state": state,
                    "effective_ttfb_ms": effective_ttfb,
                    "samples": samples,
                    "measured_models": measured_models,
                    "sort_key": (
                        {"fresh": 0, "stale": 1, "none": 2}.get(state, 2),
                        float(effective_ttfb) if isinstance(effective_ttfb, (int, float)) else float("inf"),
                        -measured_models,
                        -samples,
                        str(entry.get("provider_name") or ""),
                        str(entry.get("provider_id") or ""),
                    ),
                }
            )
            items.append(item)

        items.sort(key=lambda item: item["sort_key"])
        base_priority = max((int(item.get("current_priority", 100) or 100) for item in items), default=100)
        changes = {}
        measured_count = 0
        for idx, item in enumerate(items):
            suggested = max(0, min(200, base_priority - idx * 5))
            item["suggested_priority"] = suggested
            item["priority_diff"] = suggested - int(item.get("current_priority", 100) or 100)
            if item.get("state") != "none":
                measured_count += 1
            if suggested != int(item.get("current_priority", 100) or 100):
                changes[item["change_key"]] = suggested

        if not items:
            summary = _L("当前 family 没有可排序的通道", "No sortable channels in this family")
        elif measured_count < 2:
            summary = _L(
                "测速数据不足：至少需要 2 条通道有有效样本",
                "Not enough speed samples: need at least two measured channels",
            )
        elif not changes:
            summary = _L("当前顺序已经和测速结果一致", "Current order already matches speed stats")
        else:
            summary = _L(
                "规则：fresh 优先，其次 stale；同状态按 TTFB 更快优先；无数据放最后",
                "Rule: fresh first, then stale; faster TTFB wins; no-data goes last",
            )

        return {
            "items": items,
            "changes": changes,
            "can_apply": measured_count >= 2 and bool(changes),
            "summary": summary,
            "measured_count": measured_count,
        }

    def apply_family_autosort(self, sync_provider_cursor=None):
        plan = self.build_family_autosort_plan()
        if plan.get("can_apply"):
            self.priority_changes.update(plan.get("changes") or {})
            if callable(sync_provider_cursor):
                for model_entry in self.sorted_models:
                    active = self.active_provider_choice(model_entry)
                    sync_provider_cursor(model_entry, active.get("provider_id", ""))
        return plan
