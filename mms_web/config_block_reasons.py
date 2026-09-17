"""Turn MMF ``registry_v2_save_plan`` blocked_reasons into user-facing Chinese.

The worker subprocess boundary only carries ``code`` / ``message`` / ``status``,
so everything the user needs to act on has to fit in one plain string. This
module is a pure mapping: it never reads the plan, root status, or any path —
only the reason codes themselves.
"""
from __future__ import annotations

# Kept for the case where the plan is not ok but MMF reported no reason codes:
# then there is genuinely nothing more specific to say.
FALLBACK_MESSAGE = "MMF 未允许这组修改，未保存。请检查是否移除了全部可用模型，或重新加载配置后再试。"

# One sentence per known code. Each must answer: what was blocked, why,
# whether it is this edit's fault, and what to do next.
_MESSAGES = {
    # The config root resolves to the retired legacy directory (basename "mms").
    # Every write on that machine is refused, regardless of the edit.
    "stable_root_human_only": (
        "这台电脑的配置来源是已退休的旧目录（名字叫 mms 的那个），Pilot 在这种目录上一律不允许写入"
        "——所以这台机器上任何修改都会被挡，不是这次改动的问题。配置的唯一来源是 ~/.config/mms-next："
        "请检查 MMS_CONFIG_ROOT / MMS_CONFIG_DIR / XDG_CONFIG_HOME 有没有还指着旧目录，清掉后重开 Pilot。"
    ),
    "no_draft_changes": "这组改动和当前已保存的配置没有区别，没有需要写入的内容。",
    "stale_preview_bundle_revision": (
        "页面加载之后，配置在别处被改过了。点「重新加载配置」拿到最新状态，再重做这次修改。"
    ),
    "route_shrink_guard": (
        "这次修改会让已发布的模型路由数量减少，MMF 拦下了以防误删。"
        "确认确实要减少的话，先重新加载配置核对当前模型，再逐个调整。"
    ),
    "route_publish_guard_blocked": (
        "路由发布被 MMF 的守卫拦下，未保存。请重新加载配置后重试；仍然失败请把这条消息发给维护者。"
    ),
}


def _describe(code: str) -> str:
    if code in _MESSAGES:
        return _MESSAGES[code]
    # Guard reasons may arrive as a full sentence ("route_shrink_guard: candidate
    # would shrink ..."); match on the prefix before the first colon.
    prefix = code.split(":", 1)[0].strip()
    if prefix in _MESSAGES:
        return _MESSAGES[prefix]
    # Unknown codes stay visible verbatim so future reports have a handle.
    return f"MMF 拒绝了这组修改（原因代码：{code}）。未保存。请把这行原文发给维护者。"


def describe_blocked_reasons(reasons: list[str]) -> str:
    """把 MMF 的 blocked_reasons 变成用户能照着做的中文。"""
    items = [str(reason).strip() for reason in (reasons or []) if str(reason).strip()]
    if not items:
        return FALLBACK_MESSAGE
    # Every reason is shown, in the order MMF reported them; joined on one line
    # so no CSS change is needed (.form-error collapses newlines).
    return "；".join(_describe(item) for item in items)
