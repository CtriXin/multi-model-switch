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

import hashlib
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

try:
    import httpx as _httpx
except ImportError:
    _httpx = None

from mms_state_io import resolve_mms_config_dir
from mms_provider_profiles import (
    apply_profile_auth_headers,
    apply_profile_body_patches,
    profile_context_window,
    profile_model_alias,
    resolve_provider_profile,
)

# ── 路径 ──
_CONFIG_DIR = resolve_mms_config_dir()
_LOG_PATH = os.path.join(_CONFIG_DIR, "lb_route.log")
_KEYWORDS_PATH = os.path.join(_CONFIG_DIR, "route_keywords.json")
_LEARNED_PATH = os.path.join(_CONFIG_DIR, "route_learned.json")

# Sticky escalation 默认衰减轮数
STICKY_DECAY_TURNS = 5

# 自动学习：LLM 连续 N 次高置信分类相同 → promote 为关键词
_LEARN_THRESHOLD = 3

# ── 内置默认关键词 ──

_BUILTIN_GUARDRAIL_FILES = {
    "mms_core", "mms_launchers", "mms_bridge", "mms_router", "mms_tui",
    "mms_adapter_registry", "mms_account_state",
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
    (r"^你好[啊呀吗]?$", "greeting"),
    (r"^hi[! ]?$", "greeting"),
    (r"^hello[! ]?$", "greeting"),
    (r"^hey[! ]?$", "greeting"),
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


def _retry_after_delay_seconds(value, *, max_delay=2.0):
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        delay = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if delay <= 0:
        return 0.0
    return min(delay, max_delay)


def _post_with_retry_after(url, *, headers, json_body, timeout=5, max_attempts=2):
    attempts = 0
    response = None
    while attempts < max_attempts:
        attempts += 1
        response = _httpx.post(url, headers=headers, json=json_body, timeout=timeout)
        if response.status_code != 429:
            return response
        delay = _retry_after_delay_seconds(response.headers.get("Retry-After"))
        if delay <= 0 or attempts >= max_attempts:
            return response
        time.sleep(delay)
    return response


def _llm_classify(
    text: str,
    api_url: str,
    api_key: str,
    model: str,
    provider_id: str = "",
    provider_profile: str = "",
) -> tuple[str, str] | None:
    """用 light 模型做二分类 + 置信度。返回 (tier, confidence) 或 None。

    优化：max_tokens=16（只需 2 个词），禁用 thinking/reasoning 避免 token 浪费。
    """
    if _httpx is None:
        return None
    import time as _time
    t0 = _time.time()
    try:
        url = api_url.rstrip("/")
        if url.endswith("/v1"):
            base_v1 = url
        else:
            base_v1 = f"{url}/v1"
        classify_content = _CLASSIFY_USER.format(task=text[:300])
        # Anthropic 协议：不发 thinking 参数（发 thinking+temperature:0 会 400）
        body = {
            "model": model,
            "max_tokens": 16,
            "temperature": 0,
            "system": "Reply with exactly two words. No explanation.",
            "messages": [
                {"role": "user", "content": classify_content},
            ],
        }
        headers = {
            "x-api-key": api_key,
            "Authorization": f"Bearer {api_key}",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        apply_profile_body_patches(
            body,
            protocol="anthropic_messages",
            provider_id=provider_id,
            profile_id=provider_profile,
            base_url=base_v1,
            model_name=model,
            thinking_enabled=False,
            purpose="classify",
        )
        apply_profile_auth_headers(
            headers,
            protocol="anthropic_messages",
            api_key=api_key,
            provider_id=provider_id,
            profile_id=provider_profile,
            base_url=base_v1,
            model_name=model,
        )
        # 尝试 Anthropic messages → fallback OpenAI chat/completions
        r = _post_with_retry_after(f"{base_v1}/messages", headers=headers, json_body=body, timeout=5)
        protocol = "anthropic"
        if r.status_code in (404, 405, 400):
            # 400 可能是不支持 thinking 参数，去掉重试
            oai_body = {
                "model": model,
                "max_tokens": 16,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": "Reply with exactly two words. No explanation."},
                    {"role": "user", "content": classify_content},
                ],
            }
            apply_profile_body_patches(
                oai_body,
                protocol="openai_chat",
                provider_id=provider_id,
                profile_id=provider_profile,
                base_url=base_v1,
                model_name=model,
                thinking_enabled=False,
                purpose="classify",
            )
            apply_profile_auth_headers(
                headers,
                protocol="openai_chat",
                api_key=api_key,
                provider_id=provider_id,
                profile_id=provider_profile,
                base_url=base_v1,
                model_name=model,
            )
            r = _post_with_retry_after(
                f"{base_v1}/chat/completions",
                headers=headers,
                json_body=oai_body,
                timeout=5,
            )
            protocol = "openai"
        elapsed_ms = int((_time.time() - t0) * 1000)
        if r.status_code != 200:
            _log_llm_error(f"status={r.status_code} model={model} url={r.url} "
                           f"elapsed={elapsed_ms}ms body={r.text[:200]}")
            return None
        try:
            data = r.json()
        except Exception:
            _log_llm_error(f"invalid JSON model={model} url={r.url} elapsed={elapsed_ms}ms: {r.text[:200]}")
            return None
        # 解析 token 用量（诊断）
        usage = data.get("usage", {})
        in_tok = usage.get("input_tokens") or usage.get("prompt_tokens", "?")
        out_tok = usage.get("output_tokens") or usage.get("completion_tokens", "?")
        cache_tok = usage.get("cache_read_input_tokens") or usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)

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
        # 优先用 text reply；fallback 到 thinking 最后 80 字符
        if reply:
            check_text = reply.strip().upper()
        elif thinking_text:
            check_text = thinking_text.strip()[-80:].upper()
        else:
            check_text = ""
        tier = None
        confidence = "high"
        if "LIGHT" in check_text or "轻量" in check_text or "简单" in check_text:
            tier = "light"
        elif "HEAVY" in check_text or "复杂" in check_text or "重度" in check_text:
            tier = "heavy"
        if tier is None:
            _log_llm_error(f"unexpected reply model={model} elapsed={elapsed_ms}ms "
                           f"tokens(in={in_tok},cache={cache_tok},out={out_tok}): "
                           f"{check_text[:100]} | raw={str(data)[:300]}")
            return None
        if "LOW" in check_text:
            confidence = "low"
        # 记录 token 异常（input > 500 说明有 thinking 浪费）
        if isinstance(in_tok, int) and in_tok > 500:
            _log_llm_error(f"token_waste model={model} protocol={protocol} "
                           f"tokens(in={in_tok},cache={cache_tok},out={out_tok}) "
                           f"elapsed={elapsed_ms}ms — consider disabling thinking for this model")
        return (tier, confidence)
    except Exception as exc:
        elapsed_ms = int((_time.time() - t0) * 1000)
        _log_llm_error(f"exception: {exc} model={model} url={api_url} elapsed={elapsed_ms}ms")
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
                  light_model: str = None, provider_id: str = "",
                  provider_profile: str = "") -> tuple[str, str]:
    """四层分类：guardrail → 关键词 fast-path → LLM 异步分类 → 默认 medium。

    返回 (tier, reason)，tier 为 "light" / "medium" / "heavy"。
    LLM 分类改为非阻塞：关键词无法决定时，用上次 LLM 结果做 hint，后台发起新分类。
    """
    if not text:
        return "heavy", "empty input"

    # 0. 系统自动请求 fast-path（Claude Code suggestion 等内部 prompt）
    if text.startswith("[SUGGESTION MODE") or text.startswith("[SYSTEM"):
        return "light", "system_prompt"

    # 热重载：配置文件变化时自动刷新关键词
    _maybe_reload_keywords()

    text_lower = text.lower()

    # 1. Guardrail：提到关键文件名 → heavy（用 \b 避免 "auth" 误匹配 "authentication"）
    for fname in _GUARDRAIL_FILES:
        if re.search(r'\b' + re.escape(fname) + r'\b', text_lower):
            return "heavy", f"guardrail: {fname}"

    # 2. Heavy 关键词 fast-path
    for pattern, label in _heavy_re:
        if pattern.search(text):
            return "heavy", f"keyword: {label}"

    # 3. Light 关键词 fast-path
    light_hits = [label for pat, label in _light_re if pat.search(text)]
    if light_hits:
        return "light", f"keyword: {','.join(light_hits)}"

    # 4. LLM 异步分类：非阻塞，不等结果
    #    - 如果上次 LLM 结果可用且未过期 → 用作 hint
    #    - 后台启动新分类（下次请求生效）
    #    - 无 hint 时 fallback 到 medium
    if api_url and api_key and light_model and len(text) < 2000:
        # 检查异步分类结果（只匹配相同文本的缓存）
        cached = _get_async_llm_result(text)
        # 启动后台分类（不阻塞当前请求）
        _submit_async_llm_classify(text, api_url, api_key, light_model, provider_id, provider_profile)
        if cached:
            tier, confidence = cached
            if confidence == "high":
                _record_llm_result(text, tier)
                return tier, f"llm_async:{tier}+high_confidence"
            return "medium", f"llm_async:{tier}+low_confidence"

    # 5. 无关键词命中 + 无异步结果 → 安全中间档
    return "medium", "no_match→medium"


# ── LLM 异步分类 ──
import threading as _threading

_async_llm_result = None  # (text_key, tier, confidence, timestamp)
_async_llm_lock = _threading.Lock()  # 模块级初始化，避免 TOCTOU 竞争


def _text_cache_key(text: str) -> str:
    """取前 100 字符作为缓存 key（足够区分不同请求）。"""
    return text[:100].strip().lower()


def _get_async_llm_result(text: str):
    """获取异步 LLM 分类结果（5 分钟内有效，且必须与当前文本匹配）。"""
    global _async_llm_result
    if _async_llm_result is None:
        return None
    cached_key, tier, confidence, ts = _async_llm_result
    # 只返回与当前请求文本匹配的缓存（避免上次请求的结果错误应用到不同文本）
    if cached_key != _text_cache_key(text):
        return None
    import time
    if time.time() - ts > 300:  # 5 分钟过期
        _async_llm_result = None
        return None
    return (tier, confidence)


def _submit_async_llm_classify(text, api_url, api_key, light_model, provider_id="", provider_profile=""):
    """在后台线程中执行 LLM 分类，结果存入 _async_llm_result。"""
    # 避免并发提交多个分类请求
    if not _async_llm_lock.acquire(blocking=False):
        return
    text_key = _text_cache_key(text)
    def _run():
        global _async_llm_result
        try:
            result = _llm_classify(text, api_url, api_key, light_model, provider_id, provider_profile)
            if result:
                import time
                tier, confidence = result[0], result[1]
                _async_llm_result = (
                    text_key,
                    tier,
                    confidence,
                    time.time(),
                )
        finally:
            _async_llm_lock.release()
    t = _threading.Thread(target=_run, daemon=True)
    t.start()


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


# ── Model Routes Legacy Export（generated bundle / compatibility） ───────────

import stat

MODEL_ROUTES_VERSION = 1
MODEL_ROUTES_LINEUP_VERSION = 1
MODEL_POLICY_VERSION = 1
MODEL_ROUTES_PATH = os.path.join(_CONFIG_DIR, "model-routes.json")
MODEL_ROUTES_LINEUP_PATH = os.path.join(_CONFIG_DIR, "model-routes.lineup.json")
MODEL_POLICY_PATH = os.path.join(_CONFIG_DIR, "model-policy.json")
MODEL_CONFIG_AUDIT_PATH = os.path.join(_CONFIG_DIR, "model-config.audit.ndjson")
MODEL_ROUTES_SNAPSHOTS_DIR = os.path.join(_CONFIG_DIR, "model-routes.snapshots")
MODEL_ROUTES_LINEUP_SNAPSHOTS_DIR = os.path.join(_CONFIG_DIR, "model-routes.lineup.snapshots")
_BUILTIN_PROVIDER_PROFILE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "config",
    "provider-profiles.json",
)
_USER_PROVIDER_PROFILE_BASENAMES = ("provider-profiles.json", "model-profiles.json")

_SENSITIVE_LINEUP_KEYS = {"api_key", "anthropic_base_url", "openai_base_url"}
_LINEUP_PRESERVE_ROUTE_KEYS = {
    "display_name", "label", "description", "tags", "capabilities", "tier",
    "priority", "pricing", "notes", "owner", "source", "reference_notes",
}
_LINEUP_PRESERVE_LEAF_KEYS = {
    "display_name", "label", "notes", "source", "pricing",
}


def _clean_str(value):
    return str(value or "").strip()


def _route_protocol(route_entry):
    route = route_entry or {}
    if _clean_str(route.get("anthropic_base_url")):
        return "anthropic_messages"
    return "openai_chat"


def _route_base_url_for_profile(route_entry):
    route = route_entry or {}
    return _clean_str(route.get("anthropic_base_url")) or _clean_str(route.get("openai_base_url"))


def _wire_model_id(model_name, route_entry):
    route = route_entry or {}
    explicit = _clean_str(route.get("model_id"))
    if explicit:
        return explicit
    protocol = _route_protocol(route)
    alias = profile_model_alias(
        model_name,
        protocol=protocol,
        provider_id=_clean_str(route.get("provider_id")),
        base_url=_route_base_url_for_profile(route),
    )
    return alias or _clean_str(model_name)


def _profile_reference_urls(model_name, route_entry):
    route = route_entry or {}
    _, profile = resolve_provider_profile(
        provider_id=_clean_str(route.get("provider_id")),
        base_url=_route_base_url_for_profile(route),
        model_name=model_name,
    )
    refs = profile.get("references") if isinstance(profile.get("references"), list) else []
    return [str(item).strip() for item in refs if str(item or "").strip()]


def _route_context_window(model_name, route_entry):
    route = route_entry or {}
    return profile_context_window(
        model_name,
        provider_id=_clean_str(route.get("provider_id")),
        base_url=_route_base_url_for_profile(route),
    )


def _route_endpoint_payload(route_entry, model_name=""):
    route = route_entry or {}
    payload = {
        "provider_id": _clean_str(route.get("provider_id")),
        "anthropic_base_url": _clean_str(route.get("anthropic_base_url")),
        "openai_base_url": _clean_str(route.get("openai_base_url")),
        "api_key": str(route.get("api_key") or ""),
    }
    if model_name:
        payload["model_id"] = _wire_model_id(model_name, route)
    return payload


def _canonical_routes_payload(routes):
    ordered_routes = {}
    for model_name in sorted(routes):
        info = routes.get(model_name) or {}
        ordered_routes[model_name] = {
            "primary": _route_endpoint_payload(info.get("primary"), model_name),
            "fallbacks": [
                _route_endpoint_payload(item, model_name)
                for item in (info.get("fallbacks") or [])
            ],
        }
    return {
        "version": MODEL_ROUTES_VERSION,
        "routes": ordered_routes,
    }


def _lineup_leaf_payload(model_name, route_entry, generated_at):
    route = route_entry or {}
    refs = _profile_reference_urls(model_name, route)
    context_window = _route_context_window(model_name, route)
    payload = {
        "provider_id": _clean_str(route.get("provider_id")),
        "model_id": _wire_model_id(model_name, route),
    }
    if context_window is not None:
        payload["max_context_tokens"] = int(context_window)
        payload["context_source"] = "provider-profiles.json"
    if refs:
        payload["context_reference_url"] = refs[0]
        payload["context_references"] = refs
        payload["context_reference_checked_at"] = generated_at
    return payload


def _sanitize_lineup_leaf(value):
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if key not in _SENSITIVE_LINEUP_KEYS and key in _LINEUP_PRESERVE_LEAF_KEYS
    }


def _merge_lineup_leaf(existing, generated):
    merged = _sanitize_lineup_leaf(existing)
    for key, value in generated.items():
        merged[key] = value
    return merged


def _merge_lineup_entry(existing, generated):
    existing = existing if isinstance(existing, dict) else {}
    merged = {
        str(key): value
        for key, value in existing.items()
        if key in _LINEUP_PRESERVE_ROUTE_KEYS
    }
    merged.update({key: value for key, value in generated.items() if key not in {"primary", "fallbacks"}})
    merged["primary"] = _merge_lineup_leaf(existing.get("primary"), generated.get("primary") or {})

    existing_fallbacks = existing.get("fallbacks") if isinstance(existing.get("fallbacks"), list) else []
    existing_by_provider = {
        _clean_str(item.get("provider_id")): item
        for item in existing_fallbacks
        if isinstance(item, dict) and _clean_str(item.get("provider_id"))
    }
    merged["fallbacks"] = [
        _merge_lineup_leaf(existing_by_provider.get(_clean_str(item.get("provider_id"))), item)
        for item in (generated.get("fallbacks") or [])
        if isinstance(item, dict)
    ]
    return merged


def _read_existing_lineup_routes():
    try:
        payload = _read_json_file(MODEL_ROUTES_LINEUP_PATH)
    except (OSError, json.JSONDecodeError):
        return {}
    routes = payload.get("routes") if isinstance(payload, dict) else {}
    return routes if isinstance(routes, dict) else {}


def _canonical_lineup_payload(routes, *, generated_at, source_routes_hash):
    existing_routes = _read_existing_lineup_routes()
    ordered_routes = {}
    for model_name in sorted(routes):
        info = routes.get(model_name) or {}
        generated = {
            "primary": _lineup_leaf_payload(model_name, info.get("primary"), generated_at),
            "fallbacks": [
                _lineup_leaf_payload(model_name, item, generated_at)
                for item in (info.get("fallbacks") or [])
            ],
        }
        ordered_routes[model_name] = _merge_lineup_entry(existing_routes.get(model_name), generated)
    return {
        "version": MODEL_ROUTES_LINEUP_VERSION,
        "generated_at": generated_at,
        "source_routes_hash": source_routes_hash,
        "routes": ordered_routes,
    }


def _empty_model_policy_payload(generated_at=None):
    return {
        "version": MODEL_POLICY_VERSION,
        "updated_at": generated_at or _routes_generated_at(),
        "description": "User-maintained model visibility and preference policy. MMS never stores provider secrets here.",
        "models": {},
        "projects": {},
    }


def _canonical_json_bytes(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
    ).encode("utf-8")


def _pretty_json_text(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=False,
    ) + "\n"


def _routes_generated_at():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read_json_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_text_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_secure_text_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp-{os.getpid()}-{time.time_ns()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp_path, path)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _write_snapshot_if_missing(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "x", encoding="utf-8") as f:
            f.write(text)
    except FileExistsError:
        return False
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return True


def _routes_dependency_paths():
    from mms_core import CONFIG_PATH, CREDENTIALS_PATH, OVERRIDE_PATHS

    return [
        CONFIG_PATH,
        CREDENTIALS_PATH,
        *OVERRIDE_PATHS,
        *_provider_profile_dependency_paths(),
    ]


def _provider_profile_dependency_paths():
    return [
        _BUILTIN_PROVIDER_PROFILE_PATH,
        *(os.path.join(_CONFIG_DIR, basename) for basename in _USER_PROVIDER_PROFILE_BASENAMES),
    ]


def _latest_routes_is_fresh():
    if not os.path.exists(MODEL_ROUTES_PATH) or not os.path.exists(MODEL_ROUTES_LINEUP_PATH):
        return False
    try:
        latest_mtime = min(os.path.getmtime(MODEL_ROUTES_PATH), os.path.getmtime(MODEL_ROUTES_LINEUP_PATH))
        dependency_mtime = max(
            (
                os.path.getmtime(path)
                for path in _routes_dependency_paths()
                if path and os.path.exists(path)
            ),
            default=0,
        )
    except OSError:
        return False
    if latest_mtime < dependency_mtime:
        return False
    payload = _read_json_file_or_empty(MODEL_ROUTES_PATH)
    lineup = _read_json_file_or_empty(MODEL_ROUTES_LINEUP_PATH)
    if lineup.get("source_routes_hash") != _content_hash({"version": MODEL_ROUTES_VERSION, "routes": payload.get("routes") or {}}):
        return False
    return not any(issue.get("level") == "error" for issue in validate_model_config_bundle(payload, lineup, _read_json_file_or_empty(MODEL_POLICY_PATH)))


def _content_hash(payload):
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _read_json_file_or_empty(path):
    try:
        payload = _read_json_file(path)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _latest_approved_model_config_bundle():
    config_dir = resolve_mms_config_dir()
    manifest_path = os.path.join(config_dir, "generated", "model-registry.latest-approved.json")
    try:
        import mms_registry

        bundle = mms_registry.load_latest_approved_bundle(config_dir=config_dir, include_secret=True)
    except Exception as exc:
        if os.path.exists(manifest_path):
            return {
                "invalid_latest_approved": True,
                "error": f"{type(exc).__name__}: {exc}",
                "routes_payload": {},
                "lineup_payload": {},
                "policy_payload": {},
                "manifest_path": manifest_path,
                "verified_files": {},
            }
        return {}
    payloads = bundle.get("payloads") if isinstance(bundle.get("payloads"), dict) else {}
    routes_payload = payloads.get("router")
    lineup_payload = payloads.get("lineup")
    policy_payload = payloads.get("policy")
    if not isinstance(routes_payload, dict) or not isinstance(lineup_payload, dict):
        return {}
    if not isinstance(policy_payload, dict):
        policy_payload = {}
    return {
        "routes_payload": routes_payload,
        "lineup_payload": lineup_payload,
        "policy_payload": policy_payload,
        "manifest_path": bundle.get("manifest_path") or "",
        "verified_files": bundle.get("verified_files") or {},
    }


def _current_model_config_payloads():
    approved = _latest_approved_model_config_bundle()
    if approved:
        return approved
    return {
        "routes_payload": _read_json_file_or_empty(MODEL_ROUTES_PATH),
        "lineup_payload": _read_json_file_or_empty(MODEL_ROUTES_LINEUP_PATH),
        "policy_payload": _read_json_file_or_empty(MODEL_POLICY_PATH),
        "manifest_path": "",
        "verified_files": {},
    }


def _ensure_model_policy_file(generated_at):
    if os.path.exists(MODEL_POLICY_PATH):
        return _read_json_file_or_empty(MODEL_POLICY_PATH)
    payload = _empty_model_policy_payload(generated_at)
    _write_secure_text_file(MODEL_POLICY_PATH, _pretty_json_text(payload))
    return payload


def _append_model_config_audit(event):
    try:
        os.makedirs(os.path.dirname(MODEL_CONFIG_AUDIT_PATH), exist_ok=True)
        payload = {
            "ts": _routes_generated_at(),
            "actor": os.environ.get("MMS_ACTOR") or os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown",
            **event,
        }
        with open(MODEL_CONFIG_AUDIT_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        os.chmod(MODEL_CONFIG_AUDIT_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def validate_model_config_bundle(routes_payload=None, lineup_payload=None, policy_payload=None):
    bundle_error = ""
    if routes_payload is None and lineup_payload is None and policy_payload is None:
        current = _current_model_config_payloads()
        routes_payload = current["routes_payload"]
        lineup_payload = current["lineup_payload"]
        policy_payload = current["policy_payload"]
        bundle_error = str(current.get("error") or "") if current.get("invalid_latest_approved") else ""
    else:
        routes_payload = routes_payload or _read_json_file_or_empty(MODEL_ROUTES_PATH)
        lineup_payload = lineup_payload or _read_json_file_or_empty(MODEL_ROUTES_LINEUP_PATH)
        policy_payload = policy_payload or _read_json_file_or_empty(MODEL_POLICY_PATH)
    issues = []
    if bundle_error:
        issues.append({"level": "error", "code": "latest_approved_invalid", "detail": bundle_error})

    routes = routes_payload.get("routes") if isinstance(routes_payload.get("routes"), dict) else {}
    lineup_routes = lineup_payload.get("routes") if isinstance(lineup_payload.get("routes"), dict) else {}
    policy_models = policy_payload.get("models") if isinstance(policy_payload.get("models"), dict) else {}
    expected_routes_hash = _content_hash({"version": MODEL_ROUTES_VERSION, "routes": routes})
    if lineup_payload.get("source_routes_hash") and lineup_payload.get("source_routes_hash") != expected_routes_hash:
        issues.append({"level": "error", "code": "lineup_source_routes_hash_mismatch"})

    for model_name, info in routes.items():
        if model_name not in lineup_routes:
            issues.append({"level": "error", "code": "lineup_missing_model", "model": model_name})
        primary = info.get("primary") if isinstance(info, dict) else {}
        if not isinstance(primary, dict) or not primary.get("provider_id"):
            issues.append({"level": "error", "code": "route_missing_primary_provider", "model": model_name})
        if isinstance(primary, dict) and not (primary.get("anthropic_base_url") or primary.get("openai_base_url")):
            issues.append({"level": "error", "code": "route_missing_base_url", "model": model_name})
        if isinstance(primary, dict) and not primary.get("api_key"):
            issues.append({"level": "error", "code": "route_missing_api_key", "model": model_name})
        fallbacks = info.get("fallbacks") if isinstance(info, dict) and isinstance(info.get("fallbacks"), list) else []
        for index, fallback in enumerate(fallbacks):
            if not isinstance(fallback, dict) or not fallback.get("provider_id"):
                issues.append({"level": "error", "code": "fallback_missing_provider", "model": model_name, "index": index})
            if isinstance(fallback, dict) and not (fallback.get("anthropic_base_url") or fallback.get("openai_base_url")):
                issues.append({"level": "error", "code": "fallback_missing_base_url", "model": model_name, "index": index})
            if isinstance(fallback, dict) and not fallback.get("api_key"):
                issues.append({"level": "error", "code": "fallback_missing_api_key", "model": model_name, "index": index})

    for model_name in lineup_routes:
        if model_name not in routes:
            issues.append({"level": "error", "code": "lineup_extra_model", "model": model_name})
        lineup_entry = lineup_routes.get(model_name)
        if not isinstance(lineup_entry, dict):
            continue
        leaves = [lineup_entry.get("primary"), *(lineup_entry.get("fallbacks") if isinstance(lineup_entry.get("fallbacks"), list) else [])]
        for index, leaf in enumerate(leaves):
            if not isinstance(leaf, dict):
                continue
            for secret_key in _SENSITIVE_LINEUP_KEYS:
                if secret_key in leaf:
                    issues.append({"level": "error", "code": "lineup_contains_secret_field", "model": model_name, "field": secret_key, "index": index})
    for model_name in policy_models:
        if model_name not in routes and model_name not in lineup_routes:
            issues.append({"level": "warning", "code": "policy_unknown_model", "model": model_name})
    policy_projects = policy_payload.get("projects") if isinstance(policy_payload.get("projects"), dict) else {}
    for project_name, project_config in policy_projects.items():
        if not isinstance(project_config, dict):
            continue
        for field in ("allowed_models", "hidden_models", "disabled_models", "favorite_models"):
            values = project_config.get(field)
            if not isinstance(values, list):
                continue
            for model_name in values:
                if isinstance(model_name, str) and model_name not in routes and model_name not in lineup_routes:
                    if field in {"hidden_models", "disabled_models"}:
                        continue
                    issues.append({
                        "level": "warning",
                        "code": "policy_project_unknown_model",
                        "project": project_name,
                        "field": field,
                        "model": model_name,
                    })
    return issues


def _persist_payload_snapshot(payload, snapshots_dir):
    payload_hash = _content_hash(payload)
    snapshot_path = os.path.join(snapshots_dir, f"{payload_hash}.json")
    _write_snapshot_if_missing(snapshot_path, _pretty_json_text(payload))
    return payload_hash, snapshot_path


def _persist_routes_export(routes):
    canonical_payload = _canonical_routes_payload(routes)
    route_hash = _content_hash(canonical_payload)
    route_snapshot_path = os.path.join(MODEL_ROUTES_SNAPSHOTS_DIR, f"{route_hash}.json")

    generated_at = _routes_generated_at()
    if not os.path.exists(route_snapshot_path):
        route_snapshot_payload = {
            "version": MODEL_ROUTES_VERSION,
            "generated_at": generated_at,
            "routes": canonical_payload["routes"],
        }
        _write_snapshot_if_missing(route_snapshot_path, _pretty_json_text(route_snapshot_payload))
    route_payload = _read_json_file(route_snapshot_path)
    generated_at = route_payload.get("generated_at") or generated_at

    lineup_payload = _canonical_lineup_payload(routes, generated_at=generated_at, source_routes_hash=route_hash)
    lineup_hash, _ = _persist_payload_snapshot(lineup_payload, MODEL_ROUTES_LINEUP_SNAPSHOTS_DIR)
    policy_payload = _ensure_model_policy_file(generated_at)
    issues = validate_model_config_bundle(route_payload, lineup_payload, policy_payload)

    route_text = _pretty_json_text(route_payload)
    lineup_text = _pretty_json_text(lineup_payload)
    changed_files = []
    if (not os.path.exists(MODEL_ROUTES_PATH)) or _read_text_file(MODEL_ROUTES_PATH) != route_text:
        _write_secure_text_file(MODEL_ROUTES_PATH, route_text)
        changed_files.append(MODEL_ROUTES_PATH)
    if (not os.path.exists(MODEL_ROUTES_LINEUP_PATH)) or _read_text_file(MODEL_ROUTES_LINEUP_PATH) != lineup_text:
        _write_secure_text_file(MODEL_ROUTES_LINEUP_PATH, lineup_text)
        changed_files.append(MODEL_ROUTES_LINEUP_PATH)

    if changed_files:
        _append_model_config_audit({
            "action": "routes_export",
            "files": changed_files,
            "route_count": len(route_payload.get("routes") or {}),
            "route_hash": route_hash,
            "lineup_hash": lineup_hash,
            "issue_count": len(issues),
        })
    return _read_json_file(MODEL_ROUTES_PATH)


def export_model_routes(cfg=None, force=False, startup_safe=False):
    """导出 legacy route-export 兼容契约，并做 snapshot 去重。"""
    from mms_core import (
        load_config, apply_local_overrides, resolve_provider_context,
        _probe_models, _probe_models_for_startup, _normalize_priority, _normalize_role,
        _provider_effective_models, _runtime_priority_for_model,
        ROLE_WEIGHTS, DEFAULT_PRIORITY,
    )

    if cfg is None:
        cfg = load_config()
        if cfg is None:
            return {}
        cfg = apply_local_overrides(cfg)

    # Verified latest-approved bundle is the stable read-side truth. Explicit
    # force=True still regenerates legacy root aliases from current config.
    if not force:
        approved = _latest_approved_model_config_bundle()
        if approved:
            if approved.get("invalid_latest_approved"):
                return {}
            issues = validate_model_config_bundle(
                approved["routes_payload"],
                approved["lineup_payload"],
                approved["policy_payload"],
            )
            if not any(issue.get("level") == "error" for issue in issues):
                return (approved["routes_payload"].get("routes") or {})

    # latest 新于 config / override / credentials 时，直接读固定 latest 文件。
    if not force and _latest_routes_is_fresh():
        try:
            _ensure_model_policy_file(_routes_generated_at())
            return _read_json_file(MODEL_ROUTES_PATH).get("routes", {})
        except (OSError, json.JSONDecodeError):
            pass

    # 收集所有 enabled providers（只看 anthropic_messages/openai_chat_completions 协议）
    providers_info = []
    seen_ids = set()
    default_provider_id = str(cfg.get("provider", {}).get("default") or "").strip()

    for provider_def in cfg.get("providers", []):
        pid = provider_def.get("id")
        if not pid or pid in seen_ids:
            continue
        if not provider_def.get("enabled", True):
            continue

        protocols = provider_def.get("protocols", [])
        has_anthropic = "anthropic_messages" in protocols
        has_openai = "openai_chat_completions" in protocols
        if not has_anthropic and not has_openai:
            continue

        try:
            ctx = resolve_provider_context(cfg, pid)
        except (SystemExit, Exception):
            continue

        anthropic_url = (ctx.get("anthropic_base_url") or "").strip()
        openai_url_early = (ctx.get("openai_base_url") or "").strip()
        if not anthropic_url and not openai_url_early:
            continue
        if not ctx.get("api_key"):
            continue

        role = _normalize_role(provider_def.get("role", "auto"))
        priority = _normalize_priority(provider_def.get("priority", DEFAULT_PRIORITY))
        is_default = (pid == default_provider_id)

        # 启动期 routes export 优先走 startup-safe probe，避免单个坏 provider 阻塞整个 CLI。
        try:
            probe_result = (
                _probe_models_for_startup(cfg, ctx, emit_output=False)
                if startup_safe
                else _probe_models(ctx, emit_output=False)
            )
            cached_models = probe_result.get("models")
            models = list(_provider_effective_models(provider_def, cached_models, cfg))
        except Exception:
            continue

        openai_url = openai_url_early
        supported_clis = provider_def.get("supported_clis", [])
        providers_info.append({
            "provider_id": pid,
            "anthropic_base_url": anthropic_url,
            "openai_base_url": openai_url,
            "api_key": ctx["api_key"],
            "role": role,
            "priority": priority,
            "family_priority_overrides": provider_def.get("family_priority_overrides", {}),
            "models": models,
            "supported_clis": supported_clis,
            "is_default": is_default,
        })
        seen_ids.add(pid)

    # 模型 claim：按每个 model 的有效 priority 单独排序后 claim
    # 过滤上游 gateway 吐出的 claude- 前缀国产模型别名（如 claude-glm-5、claude-kimi-k2.5）
    _DOMESTIC_KEYWORDS = ("glm", "kimi", "qwen", "minimax", "deepseek", "doubao", "seed", "bailian")
    # 只保留最新一代 Claude 模型，过滤旧版（3.x、4-1、4-20250514 等）
    _CLAUDE_KEEP = {
        "claude-opus-4-6", "claude-opus-4-6-thinking", "claude-sonnet-4-6",
        "claude-opus-4-5-20251101", "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
    }
    # Model-CLI compatibility: keep the coarse family filter aligned with current
    # runtime routing, but do not expose executor metadata to route-export consumers.
    def _model_cli_compatible(model_name, supported_clis):
        if not supported_clis:
            return True  # no restriction
        normalized_clis = {
            str(item or "").strip().lower()
            for item in supported_clis
            if str(item or "").strip()
        }
        lower = model_name.lower()
        if lower.startswith(("gpt-", "o1-", "o3-", "o4-")):
            return "codex" in normalized_clis or "claude" in normalized_clis
        if lower.startswith("gemini-"):
            return (
                "gemini" in normalized_clis
                or "claude" in normalized_clis
                or "codex" in normalized_clis
            )
        if lower.startswith("claude-"):
            return "claude" in normalized_clis or "codex" in normalized_clis
        return True

    _MAX_FALLBACKS = 3
    candidates_by_model = defaultdict(list)
    for pinfo in providers_info:
        for model_name in pinfo["models"]:
            normalized = str(model_name or "").strip()
            if not normalized:
                continue
            # Skip if provider doesn't support the CLI this model family needs
            if not _model_cli_compatible(normalized, pinfo.get("supported_clis", [])):
                continue
            # claude- 前缀 + 国产关键词 → 虚拟别名，跳过
            if normalized.startswith("claude-") and any(kw in normalized.lower() for kw in _DOMESTIC_KEYWORDS):
                continue
            # 旧版 Claude 模型 → 跳过，只保留白名单
            if normalized.startswith("claude-") and normalized not in _CLAUDE_KEEP:
                continue

            effective_priority = _runtime_priority_for_model(pinfo, normalized)
            candidate = {
                "anthropic_base_url": pinfo["anthropic_base_url"],
                "openai_base_url": pinfo["openai_base_url"],
                "api_key": pinfo["api_key"],
                "provider_id": pinfo["provider_id"],
                "sort_key": (
                    ROLE_WEIGHTS.get(pinfo["role"], 1),
                    -effective_priority,
                    0 if pinfo.get("is_default") else 1,
                    pinfo["provider_id"],
                    pinfo["anthropic_base_url"],
                    pinfo["openai_base_url"],
                ),
            }
            candidates_by_model[normalized].append(candidate)

    routes = {}
    for normalized, candidates in candidates_by_model.items():
        ordered = sorted(candidates, key=lambda item: item["sort_key"])
        if not ordered:
            continue
        primary = _route_endpoint_payload(ordered[0])
        fallbacks = []
        for item in ordered[1:1 + _MAX_FALLBACKS]:
            fallbacks.append(_route_endpoint_payload(item))
        routes[normalized] = {
            "primary": primary,
            "fallbacks": fallbacks,
        }

    persisted = _persist_routes_export(routes)
    return persisted.get("routes", {})


def routes_main(cfg, args):
    """CLI 入口: mms routes [export|show]"""
    try:
        from rich.console import Console as _RC
        from rich.table import Table as _RT
        _console = _RC()
    except ImportError:
        _console = None
        _RT = None

    sub = args[0] if args else "show"

    if sub in ("export", "generate"):
        routes = export_model_routes(cfg, force=True)
        issues = validate_model_config_bundle()
        msg = f"✓ 已生成 {MODEL_ROUTES_PATH} + {MODEL_ROUTES_LINEUP_PATH}（{len(routes)} 条路由，{len(issues)} 个校验项）"
        if _console:
            _console.print(f"[green]{msg}[/green]")
        else:
            print(msg)
        return

    if sub in ("check", "validate", "doctor"):
        routes = export_model_routes(cfg, force=False)
        issues = validate_model_config_bundle()
        errors = [item for item in issues if item.get("level") == "error"]
        warnings = [item for item in issues if item.get("level") != "error"]
        if _console:
            color = "red" if errors else "green"
            _console.print(f"[{color}]Model config check: {len(errors)} errors, {len(warnings)} warnings, {len(routes)} routes[/{color}]")
            for item in issues[:50]:
                style = "red" if item.get("level") == "error" else "yellow"
                _console.print(f"[{style}]{item.get('level')} {item.get('code')} {item.get('model', '')}[/{style}]")
            _console.print(f"[dim]Router: {MODEL_ROUTES_PATH}[/dim]")
            _console.print(f"[dim]Lineup: {MODEL_ROUTES_LINEUP_PATH}[/dim]")
            _console.print(f"[dim]Policy: {MODEL_POLICY_PATH}[/dim]")
            _console.print(f"[dim]Audit: {MODEL_CONFIG_AUDIT_PATH}[/dim]")
        else:
            print(json.dumps({"errors": errors, "warnings": warnings, "route_count": len(routes)}, indent=2, ensure_ascii=False))
        if errors:
            raise SystemExit(1)
        return

    if sub in ("show", "list", "ls"):
        routes = export_model_routes(cfg, force=False)
        if not routes:
            if _console:
                _console.print("[yellow]没有路由。请先配置 provider 并运行 mms routes export[/yellow]")
            return

        if _console and _RT:
            table = _RT(title=f"Model Routes ({len(routes)} models)")
            table.add_column("Model", style="cyan")
            table.add_column("Provider", style="green")
            table.add_column("Anthropic Base URL", style="dim")
            table.add_column("OpenAI Base URL", style="dim")
            table.add_column("Fallbacks", style="white")

            for model_name, info in sorted(routes.items()):
                primary = info.get("primary") or {}
                fallback_summary = ", ".join(
                    item.get("provider_id", "")
                    for item in (info.get("fallbacks") or [])
                    if item.get("provider_id")
                ) or "-"
                table.add_row(
                    model_name,
                    primary.get("provider_id", ""),
                    (primary.get("anthropic_base_url") or "")[:50],
                    (primary.get("openai_base_url") or "")[:50],
                    fallback_summary,
                )
            _console.print(table)
            _console.print(f"\n[dim]文件: {MODEL_ROUTES_PATH}[/dim]")
        else:
            print(json.dumps(routes, indent=2, ensure_ascii=False))
        return

    if sub in ("-h", "--help", "help"):
        msg = "用法: mms routes [show|export|check]\n  show   — 显示当前路由表（默认）\n  export — 强制重新生成 Router + Lineup + Policy stub\n  check  — 校验 Router / Lineup / Policy 一致性"
        if _console:
            _console.print(msg)
        else:
            print(msg)
        return

    if _console:
        _console.print(f"[red]未知子命令: {sub}[/red]")
        _console.print("用法: mms routes [show|export]")
