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


def _llm_classify(text: str, api_url: str, api_key: str, model: str) -> tuple[str, str] | None:
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
        # 尝试 Anthropic messages → fallback OpenAI chat/completions
        r = _httpx.post(f"{base_v1}/messages", headers=headers, json=body, timeout=5)
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
                # 各家禁用 thinking 的通用兼容参数：
                "enable_thinking": False,       # Qwen 系列
                "reasoning_effort": "low",      # OpenAI 兼容（"none" 非标准值）
                "use_thinking": False,          # Kimi 系列
            }
            r = _httpx.post(f"{base_v1}/chat/completions", headers=headers, json=oai_body, timeout=5)
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
                  light_model: str = None) -> tuple[str, str]:
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
        _submit_async_llm_classify(text, api_url, api_key, light_model)
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


def _submit_async_llm_classify(text, api_url, api_key, light_model):
    """在后台线程中执行 LLM 分类，结果存入 _async_llm_result。"""
    # 避免并发提交多个分类请求
    if not _async_llm_lock.acquire(blocking=False):
        return
    text_key = _text_cache_key(text)
    def _run():
        global _async_llm_result
        try:
            result = _llm_classify(text, api_url, api_key, light_model)
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


# ── Model Routes Export（供 Hive MCP / 外部消费） ──────────────────

import stat
import time as _time

MODEL_ROUTES_PATH = os.path.join(_CONFIG_DIR, "model-routes.json")
_MMS_CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.toml")

# role 权重复用 mms_core 的定义
_EXPORT_ROLE_WEIGHTS = {"primary": 0, "auto": 1, "fallback": 2}


def export_model_routes(cfg=None, force=False):
    """遍历 role=primary/auto/fallback 的 provider，按优先级生成 model→endpoint 映射。

    只收录支持 anthropic_messages 协议且有 anthropic_base_url 的 provider。
    写入 ~/.config/mms/model-routes.json（权限 0o600）。

    Returns:
        dict: {model_name: {anthropic_base_url, api_key, provider_id, priority, role}}
    """
    from mms_core import (
        load_config, apply_local_overrides, resolve_provider_context,
        _provider_label, _probe_models, _normalize_priority, _normalize_role,
        _provider_effective_models, _runtime_priority_for_model,
        ROLE_WEIGHTS, DEFAULT_PRIORITY, _model_capability_tags,
        _native_clis_for_model, _bridge_clis_for_model, _model_cli_modes,
        _load_usage_stats, _active_usage_path,
    )

    if cfg is None:
        cfg = load_config()
        if cfg is None:
            return {}
        cfg = apply_local_overrides(cfg)

    # mtime 检查：config / usage 未变且 routes 已存在 → 直接返回缓存
    if not force and os.path.exists(MODEL_ROUTES_PATH) and os.path.exists(_MMS_CONFIG_PATH):
        try:
            config_mtime = os.path.getmtime(_MMS_CONFIG_PATH)
            routes_mtime = os.path.getmtime(MODEL_ROUTES_PATH)
            usage_path = _active_usage_path()
            usage_mtime = os.path.getmtime(usage_path) if os.path.exists(usage_path) else 0
            if routes_mtime >= config_mtime and routes_mtime >= usage_mtime:
                with open(MODEL_ROUTES_PATH, "r", encoding="utf-8") as f:
                    return json.load(f).get("routes", {})
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

        # 获取模型列表（probe + extra_models + fallback_models，与 TUI 一致）
        cached_models = _probe_models(ctx, emit_output=False).get("models")
        models = list(_provider_effective_models(provider_def, cached_models, cfg))

        openai_url = openai_url_early
        pname = _provider_label(ctx)
        supported_clis = provider_def.get("supported_clis", [])
        providers_info.append({
            "provider_id": pid,
            "provider_name": pname,
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
        "claude-opus-4-6", "claude-sonnet-4-6",
        "claude-opus-4-5-20251101", "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
    }
    # Aggregate use_count from usage.json for fuzzy-resolve ranking
    _use_counts = {}
    try:
        _usage_stats = _load_usage_stats()
        for _src in _usage_stats.get("sources", {}).values():
            for _mname, _cnt in (_src.get("models") or {}).items():
                _use_counts[_mname] = _use_counts.get(_mname, 0) + _cnt
    except Exception:
        pass

    # Model-CLI compatibility: GPT/Gemini/O-series need codex-capable provider,
    # Claude needs claude-capable. Matches MMS TUI's supported_clis filtering.
    def _model_cli_compatible(model_name, supported_clis):
        if not supported_clis:
            return True  # no restriction
        lower = model_name.lower()
        if lower.startswith(("gpt-", "gemini-", "o1-", "o3-", "o4-")):
            return "codex" in supported_clis
        if lower.startswith("claude-"):
            return "claude" in supported_clis
        # Domestic models: usually work with any CLI
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
                "api_key": pinfo["api_key"],
                "provider_id": pinfo["provider_id"],
                "provider_name": pinfo["provider_name"],
                "priority": effective_priority,
                "role": pinfo["role"],
                "sort_key": (
                    ROLE_WEIGHTS.get(pinfo["role"], 1),
                    0 if pinfo.get("is_default") else 1,
                    -effective_priority,
                    pinfo["provider_name"],
                    pinfo["provider_id"],
                ),
            }
            if pinfo.get("openai_base_url"):
                candidate["openai_base_url"] = pinfo["openai_base_url"]
            candidates_by_model[normalized].append(candidate)

    routes = {}
    for normalized, candidates in candidates_by_model.items():
        ordered = sorted(candidates, key=lambda item: item["sort_key"])
        if not ordered:
            continue
        primary = dict(ordered[0])
        primary.pop("provider_name", None)
        primary.pop("sort_key", None)
        primary.update({
            "capabilities": _model_capability_tags(normalized),
            "native_clis": _native_clis_for_model(normalized),
            "bridge_clis": _bridge_clis_for_model(normalized),
            "cli_modes": _model_cli_modes(normalized),
            "use_count": _use_counts.get(normalized, 0),
        })
        fallback_routes = []
        for item in ordered[1:1 + _MAX_FALLBACKS]:
            fallback_entry = dict(item)
            fallback_entry.pop("provider_name", None)
            fallback_entry.pop("sort_key", None)
            fallback_routes.append(fallback_entry)
        if fallback_routes:
            primary["fallback_routes"] = fallback_routes
        routes[normalized] = primary

    # 写入文件
    output = {
        "_meta": {
            "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            "generator": "mms",
        },
        "routes": routes,
    }

    os.makedirs(os.path.dirname(MODEL_ROUTES_PATH), exist_ok=True)
    with open(MODEL_ROUTES_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    os.chmod(MODEL_ROUTES_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    return routes


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
        msg = f"✓ 已生成 {MODEL_ROUTES_PATH}（{len(routes)} 条路由）"
        if _console:
            _console.print(f"[green]{msg}[/green]")
        else:
            print(msg)
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
            table.add_column("Role", style="magenta")
            table.add_column("Priority", style="yellow", justify="right")
            table.add_column("Capabilities", style="white")
            table.add_column("CLI", style="dim")
            table.add_column("Anthropic Base URL", style="dim")

            for model_name, info in sorted(routes.items()):
                cli_modes = info.get("cli_modes", {})
                cli_summary = ", ".join(
                    f"{cli}:{mode}"
                    for cli, mode in cli_modes.items()
                    if mode in {"native", "bridge"}
                ) or "-"
                table.add_row(
                    model_name,
                    info.get("provider_id", ""),
                    info.get("role", "auto"),
                    str(info.get("priority", "")),
                    ", ".join(info.get("capabilities", [])) or "-",
                    cli_summary,
                    (info.get("anthropic_base_url") or "")[:50],
                )
            _console.print(table)
            _console.print(f"\n[dim]文件: {MODEL_ROUTES_PATH}[/dim]")
        else:
            print(json.dumps(routes, indent=2, ensure_ascii=False))
        return

    if sub in ("-h", "--help", "help"):
        msg = "用法: mms routes [show|export]\n  show   — 显示当前路由表（默认）\n  export — 强制重新生成 model-routes.json"
        if _console:
            _console.print(msg)
        else:
            print(msg)
        return

    if _console:
        _console.print(f"[red]未知子命令: {sub}[/red]")
        _console.print("用法: mms routes [show|export]")
