"""MMS 智能路由：3-tier (light/medium/heavy) + 置信度 + sticky escalation + 自学习关键词。

策略：
1. Guardrail：提到关键文件/关键词 → 直接 heavy（零延迟）
2. 关键词 fast-path：明确 light/heavy 关键词命中 → 直接对应档（零延迟）
   - 内置默认关键词 + 用户配置关键词 + 自动学习关键词
3. LLM 分类：二分类 + 置信度 → 低置信度归 medium（~300ms）
4. 默认 medium（安全中间档）
5. Sticky escalation：进入 heavy 后保持 N 轮不降级

关键词来源（优先级：用户配置 > 自动学习 > 内置默认）：
- 内置：代码中硬编码
- 用户配置：~/.config/mms/route_keywords.json（手动编辑）
- 自动学习：LLM 连续 N 次对相似 pattern 给出相同高置信分类 → 自动 promote 为关键词
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime

try:
    import httpx as _httpx
except ImportError:
    _httpx = None

# ── 路径 ──
_CONFIG_DIR = os.path.expanduser("~/.config/mms")
_LOG_PATH = os.path.join(_CONFIG_DIR, "lb_route.log")
_KEYWORDS_PATH = os.path.join(_CONFIG_DIR, "route_keywords.json")
_LEARNED_PATH = os.path.join(_CONFIG_DIR, "route_learned.json")

# Sticky escalation 默认衰减轮数
STICKY_DECAY_TURNS = 5

# 自动学习：LLM 连续 N 次高置信分类相同 → promote 为关键词
_LEARN_THRESHOLD = 3

# ── 内置默认关键词 ──

_BUILTIN_GUARDRAIL_FILES = {
    "ccs_core", "ccs_launchers", "ccs_bridge", "ccs_router", "ccs_tui",
    "ccs_adapter_registry", "ccs_account_state",
    "auth", "schema", "migration", "security", "config.toml",
}

_BUILTIN_HEAVY = [
    (r"\brefactor\b.*(?:entire|across|all|multiple)", "refactor multi-file"),
    (r"\bbreaking\s+change", "breaking change"),
    (r"\bmigrat(?:e|ion)\b", "migration"),
    (r"\barchitect(?:ure)?\b", "architecture"),
    (r"\bsecurity\b", "security"),
    (r"\bcritical\b", "critical"),
    (r"\bproduction\b.*(?:deploy|release|hotfix)", "production deploy"),
    (r"\bconcurren(?:t|cy)\b", "concurrency"),
    (r"\brace\s+condition", "race condition"),
    (r"\bdeadlock\b", "deadlock"),
    (r"重构", "重构"),
    (r"架构", "架构"),
    (r"安全", "安全"),
    (r"迁移", "迁移"),
    (r"全量", "全量"),
    (r"新增功能", "新增功能"),
    (r"并发", "并发"),
    (r"死锁", "死锁"),
    (r"生产环境", "生产环境"),
    (r"上线", "上线"),
    (r"灰度", "灰度"),
    (r"回滚", "回滚"),
]

_BUILTIN_LIGHT = [
    (r"\bfix\s+typo\b", "fix typo"),
    (r"\btypo\b", "typo"),
    (r"\blint\b", "lint"),
    (r"\bformat(?:ting)?\b", "format"),
    (r"\bdocstring\b", "docstring"),
    (r"\bnit\b", "nit"),
    (r"\bimport\s+sort\b", "import sort"),
    (r"错别字", "错别字"),
    (r"拼写错误", "拼写错误"),
    (r"排版", "排版"),
    (r"改[个一]?注释", "改注释"),
    (r"加[个一]?注释", "加注释"),
    (r"补[个一]?注释", "补注释"),
    (r"改[个一]?文案", "改文案"),
    (r"改[个一]?名[字]?", "改名"),
    (r"重命名", "重命名"),
    (r"改[个一]?变量名", "改变量名"),
    (r"删[掉除]?注释", "删注释"),
    (r"整理[一下]?import", "整理import"),
    (r"加[个一]?todo", "加todo"),
]


# ── 关键词加载（内置 + 用户配置 + 自动学习，合并去重） ──

def _load_json_safe(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json_safe(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError:
        pass


def _compile_keywords(builtin, user_list, learned_list):
    """合并内置 + 用户 + 学习到的关键词，返回 [(compiled_re, label)]。"""
    seen_patterns = set()
    result = []
    # 用户配置优先
    for item in user_list:
        if isinstance(item, str):
            pattern, label = item, item
        elif isinstance(item, list) and len(item) >= 2:
            pattern, label = item[0], item[1]
        else:
            continue
        if pattern not in seen_patterns:
            seen_patterns.add(pattern)
            result.append((re.compile(pattern, re.IGNORECASE), label))
    # 自动学习
    for item in learned_list:
        if isinstance(item, str):
            pattern, label = item, f"learned:{item}"
        elif isinstance(item, list) and len(item) >= 2:
            pattern, label = item[0], f"learned:{item[1]}"
        else:
            continue
        if pattern not in seen_patterns:
            seen_patterns.add(pattern)
            result.append((re.compile(pattern, re.IGNORECASE), label))
    # 内置默认
    for pattern, label in builtin:
        if pattern not in seen_patterns:
            seen_patterns.add(pattern)
            result.append((re.compile(pattern, re.IGNORECASE), label))
    return result


def _load_all_keywords():
    """加载并合并所有关键词来源。返回 (guardrail_files, heavy_re, light_re)。"""
    user_cfg = _load_json_safe(_KEYWORDS_PATH)
    learned = _load_json_safe(_LEARNED_PATH)

    # guardrail files
    guardrail = set(_BUILTIN_GUARDRAIL_FILES)
    guardrail.update(user_cfg.get("guardrail_files", []))

    # heavy
    heavy_re = _compile_keywords(
        _BUILTIN_HEAVY,
        user_cfg.get("heavy", []),
        learned.get("heavy", []),
    )
    # light
    light_re = _compile_keywords(
        _BUILTIN_LIGHT,
        user_cfg.get("light", []),
        learned.get("light", []),
    )
    return guardrail, heavy_re, light_re


# 模块加载时初始化，后续 classify_task 每次调用都用（热重载见下方）
_GUARDRAIL_FILES, _heavy_re, _light_re = _load_all_keywords()
_keywords_mtime = {
    "user": os.path.getmtime(_KEYWORDS_PATH) if os.path.exists(_KEYWORDS_PATH) else 0,
    "learned": os.path.getmtime(_LEARNED_PATH) if os.path.exists(_LEARNED_PATH) else 0,
}


def _maybe_reload_keywords():
    """检查配置文件是否变化，变化则热重载关键词。"""
    global _GUARDRAIL_FILES, _heavy_re, _light_re, _keywords_mtime
    changed = False
    for key, path in [("user", _KEYWORDS_PATH), ("learned", _LEARNED_PATH)]:
        try:
            mt = os.path.getmtime(path) if os.path.exists(path) else 0
        except OSError:
            mt = 0
        if mt != _keywords_mtime[key]:
            _keywords_mtime[key] = mt
            changed = True
    if changed:
        _GUARDRAIL_FILES, _heavy_re, _light_re = _load_all_keywords()


# ── 自动学习 ──

# 内存中的学习计数器：{normalized_pattern: {"tier": str, "count": int}}
_learn_counter: dict[str, dict] = defaultdict(lambda: {"tier": "", "count": 0})


def _normalize_for_learning(text: str) -> str:
    """把用户文本归一化为学习 key：去标点、小写、截断。
    取前 8 个词保留足够上下文，避免 "帮我修复 typo" 和 "帮我修复安全漏洞" 归为同 key。
    """
    t = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text[:120]).strip().lower()
    words = t.split()[:8]
    return " ".join(words) if words else ""


def _record_llm_result(text: str, tier: str):
    """记录 LLM 高置信分类结果，达到阈值后自动 promote。
    安全策略：只自动学习 light（误判代价低：浪费一次弱模型调用）。
    heavy 不自动学习（误判代价高：复杂任务可能被困在弱模型上）。
    """
    if tier != "light":
        return
    key = _normalize_for_learning(text)
    if not key or len(key) < 4:
        return
    entry = _learn_counter[key]
    if entry["tier"] == tier:
        entry["count"] += 1
    else:
        entry["tier"] = tier
        entry["count"] = 1

    if entry["count"] >= _LEARN_THRESHOLD:
        _promote_keyword(key, tier)
        entry["count"] = 0  # reset，避免重复写入


def _promote_keyword(pattern: str, tier: str):
    """把一个 pattern promote 到 learned keywords 文件。"""
    learned = _load_json_safe(_LEARNED_PATH)
    tier_list = learned.get(tier, [])
    # 避免重复
    existing_patterns = {item[0] if isinstance(item, list) else item for item in tier_list}
    escaped = re.escape(pattern)
    if escaped in existing_patterns or pattern in existing_patterns:
        return
    tier_list.append([escaped, pattern])
    learned[tier] = tier_list
    _save_json_safe(_LEARNED_PATH, learned)
    _log_learn(f"promoted '{pattern}' → {tier}")
    # 触发热重载
    _maybe_reload_keywords()


def _log_learn(msg: str):
    try:
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%H:%M:%S")
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}]   LEARN    {msg}\n")
    except OSError:
        pass


# ── LLM 分类 prompt（二分类 + 置信度） ──
_CLASSIFY_SYSTEM = "You are a task classifier. Reply with exactly two words: the tier and confidence."
_CLASSIFY_USER = """Classify this coding task (may be in Chinese or English):
- LIGHT: trivial changes (typo, rename, formatting, comments, docs, simple config, one-liner fix, 改错别字, 加注释, 改文案, 排版, 重命名)
- HEAVY: anything else (new feature, refactor, debug, multi-file, architecture, security, performance, 新功能, 重构, 优化, 修复bug)

Task: {task}

Reply with LIGHT or HEAVY, followed by HIGH or LOW confidence. Example: "LIGHT HIGH" or "HEAVY LOW"."""


def _llm_classify(text: str, api_url: str, api_key: str, model: str) -> tuple[str, str] | None:
    """用 light 模型做二分类 + 置信度。返回 (tier, confidence) 或 None。"""
    if _httpx is None:
        return None
    try:
        url = api_url.rstrip("/")
        if url.endswith("/v1"):
            endpoint = f"{url}/messages"
        else:
            endpoint = f"{url}/v1/messages"
        body = {
            "model": model,
            "max_tokens": 120,
            "messages": [
                {"role": "user", "content": _CLASSIFY_USER.format(task=text[:300])},
            ],
        }
        headers = {
            "x-api-key": api_key,
            "Authorization": f"Bearer {api_key}",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        r = _httpx.post(endpoint, headers=headers, json=body, timeout=5)
        if r.status_code != 200:
            _log_llm_error(f"status={r.status_code} url={endpoint} body={r.text[:200]}")
            return None
        data = r.json()
        reply = ""
        thinking_text = ""
        content = data.get("content", [])
        if content and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "thinking" or ("thinking" in block and "text" not in block):
                    thinking_text += block.get("thinking", "")
                elif "text" in block:
                    reply = block["text"]
                    break
        if not reply:
            choices = data.get("choices", [])
            if choices and isinstance(choices, list):
                msg = choices[0].get("message", {})
                reply = msg.get("content", "") if isinstance(msg, dict) else ""
        check_text = (reply or thinking_text).strip().upper()
        tier = None
        confidence = "high"
        if "LIGHT" in check_text:
            tier = "light"
        elif "HEAVY" in check_text:
            tier = "heavy"
        if tier is None:
            _log_llm_error(f"unexpected reply: {check_text[:100]} | raw={str(data)[:500]}")
            return None
        if "LOW" in check_text:
            confidence = "low"
        return (tier, confidence)
    except Exception as exc:
        _log_llm_error(f"exception: {exc}")
        return None


def _log_llm_error(msg: str):
    try:
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%H:%M:%S")
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}]   LLM_ERR  {msg}\n")
    except OSError:
        pass


def classify_task(text: str, api_url: str = None, api_key: str = None,
                  light_model: str = None) -> tuple[str, str]:
    """四层分类：guardrail → 关键词 fast-path → LLM 分类(+置信度+自学习) → 默认 medium。

    返回 (tier, reason)，tier 为 "light" / "medium" / "heavy"。
    """
    if not text:
        return "heavy", "empty input"

    # 热重载：配置文件变化时自动刷新关键词
    _maybe_reload_keywords()

    text_lower = text.lower()

    # 1. Guardrail：提到关键文件名 → heavy
    for fname in _GUARDRAIL_FILES:
        if fname in text_lower:
            return "heavy", f"guardrail: {fname}"

    # 2. Heavy 关键词 fast-path
    for pattern, label in _heavy_re:
        if pattern.search(text):
            return "heavy", f"keyword: {label}"

    # 3. Light 关键词 fast-path
    light_hits = [label for pat, label in _light_re if pat.search(text)]
    if light_hits:
        return "light", f"keyword: {','.join(light_hits)}"

    # 4. LLM 分类 + 置信度 → 低置信归 medium + 高置信自动学习
    if api_url and api_key and light_model and len(text) < 2000:
        result = _llm_classify(text, api_url, api_key, light_model)
        if result:
            tier, confidence = result
            if confidence == "high":
                _record_llm_result(text, tier)
                return tier, f"llm:{tier}+high_confidence"
            return "medium", f"llm:{tier}+low_confidence"

    # 5. 默认 medium（安全中间档，不浪费也不冒险）
    return "medium", "default"


def log_route(level: str, reason: str, model_used: str, text_preview: str):
    """写路由日志。tail -f ~/.config/mms/lb_route.log 查看。"""
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        ts = datetime.now().strftime("%H:%M:%S")
        preview = text_preview[:60].replace("\n", " ")
        if len(text_preview) > 60:
            preview += "…"
        tags = {"light": "⬇ LIGHT", "medium": "  MEDIUM", "heavy": "⬆ HEAVY"}
        tag = tags.get(level, f"  {level}")
        line = f"[{ts}] {tag}  model={model_used}  reason={reason}  prompt={preview}\n"
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def route_model(user_message: str, heavy_model: str, light_model: str,
                medium_model: str = None) -> str:
    """light → light_model，medium → medium_model，其余 → heavy_model。"""
    level, _ = classify_task(user_message)
    if level == "light":
        return light_model
    if level == "medium" and medium_model:
        return medium_model
    return heavy_model
