from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest

from mms_web.bot_memory import (
    BotMemoryError,
    BotMemoryStore,
    DEFAULT_CONTEXT,
    DEFAULT_SETTINGS,
    MAX_CONTENT_CHARS,
)

BOT = "bot_demo123"


def test_defaults_persist_and_have_unknown_context(tmp_path):
    store = BotMemoryStore(tmp_path)
    view = store.get(BOT)
    assert view["notes"] == []
    assert view["settings"] == DEFAULT_SETTINGS
    assert view["context"] == DEFAULT_CONTEXT
    store.remember(BOT, "喜欢深色界面")
    record = json.loads((tmp_path / "bots/memory" / BOT / "memory.json").read_text())
    assert record["schema"] == 1
    assert record["facts"][0]["content"] == "喜欢深色界面"
    assert BotMemoryStore(tmp_path).get(BOT)["notes"][0]["content"] == "喜欢深色界面"


def test_remember_update_forget_and_search_are_bounded(tmp_path):
    store = BotMemoryStore(tmp_path)
    store.remember(BOT, "部署需要先跑 QA", kind="task", source="task", task_id="task_1", note_id="m1")
    store.remember(BOT, "Python 项目使用 pytest", note_id="m2")
    updated = store.remember(BOT, "Python 项目使用 pytest 和 ruff", note_id="m2")
    assert len(updated["notes"]) == 2
    assert store.get(BOT, "ruff")["notes"][0]["id"] == "m2"
    deleted = store.forget(BOT, "m1")
    assert [n["id"] for n in deleted["notes"]] == ["m2"]
    with pytest.raises(BotMemoryError):
        store.forget(BOT, "m1")
    with pytest.raises(BotMemoryError):
        store.remember(BOT, "")


def test_eviction_and_content_limit(tmp_path):
    store = BotMemoryStore(tmp_path)
    store.remember(BOT, "x" * (MAX_CONTENT_CHARS + 50))
    assert len(store.get(BOT)["notes"][0]["content"]) == MAX_CONTENT_CHARS
    for i in range(105):
        store.remember(BOT, f"fact {i}")
    view = store.get(BOT)
    assert len(view["notes"]) == 100
    assert "fact 104" in {n["content"] for n in view["notes"]}
    for i in range(205):
        store.remember(BOT, f"task {i}", kind="task", source="task")
    view = store.get(BOT)
    assert len([n for n in view["notes"] if n["kind"] == "task"]) == 200


def test_settings_and_context_validation(tmp_path):
    store = BotMemoryStore(tmp_path)
    view = store.update_settings(BOT, memoryBudgetTokens=500, compactAtPercent=90, autoCompact=False)
    assert view["settings"] == {**DEFAULT_SETTINGS, "memoryBudgetTokens": 500, "compactAtPercent": 90, "autoCompact": False}
    with pytest.raises(BotMemoryError):
        store.update_settings(BOT, memoryBudgetTokens=499)
    with pytest.raises(BotMemoryError):
        store.update_settings(BOT, compactAtPercent=91)
    view = store.update_context(BOT, contextWindow=128000, usedTokens=800, usedPercent=0.6, source="live")
    assert view["context"]["contextWindow"] == 128000
    assert view["context"]["source"] == "live"


def test_concurrent_writes_remain_valid_and_scoped(tmp_path):
    store = BotMemoryStore(tmp_path)
    def add(i):
        store.remember(BOT, f"并发事实 {i}")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(add, range(80)))
    view = store.get(BOT)
    assert len(view["notes"]) == 80
    assert len(json.loads((tmp_path / "bots/memory" / BOT / "memory.json").read_text())["facts"]) == 80
    assert store.get("bot_other")["notes"] == []


def test_bot_id_is_path_safe(tmp_path):
    store = BotMemoryStore(tmp_path)
    with pytest.raises(BotMemoryError):
        store.get("../escape")
