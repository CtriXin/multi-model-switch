"""Small display label helpers."""

from __future__ import annotations


def model_source_label(source):
    mapping = {
        "remote": "远端列表",
        "fallback": "内置回退",
        "manual": "手工列表",
        "extra": "手工补充",
        "derived_alias": "本地别名",
    }
    return mapping.get(str(source or "").strip(), str(source or "-").strip() or "-")


def ttfb_label(ttfb_ms):
    if not isinstance(ttfb_ms, (int, float)):
        return "暂无数据"
    if ttfb_ms < 1200:
        return "很快"
    if ttfb_ms < 2500:
        return "正常"
    if ttfb_ms < 4500:
        return "偏慢"
    return "很慢"


def tps_label(tps_value):
    if not isinstance(tps_value, (int, float)):
        return "暂无数据"
    if tps_value >= 80:
        return "很快"
    if tps_value >= 40:
        return "正常"
    if tps_value >= 20:
        return "偏慢"
    return "很慢"
