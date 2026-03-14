"""MMS 负载路由：LLM 快速分类 + 关键词 fast-path + 路由日志。

策略：
1. Guardrail：提到关键文件/关键词 → 直接 heavy（零延迟）
2. 关键词 fast-path：明确 light 关键词命中 → 直接 light（零延迟）
3. LLM 分类：用 light 模型做 <50 token 的二分类（~300ms），准确率高
4. 默认 heavy（安全，不降级）
"""

import json
import os
import re
from datetime import datetime

try:
    import httpx as _httpx
except ImportError:
    _httpx = None

# ── Guardrail：提到这些文件名 → 直接 heavy ──
_GUARDRAIL_FILES = {
    "ccs_core", "ccs_launchers", "ccs_bridge", "ccs_router", "ccs_tui",
    "ccs_adapter_registry", "ccs_account_state",
    "auth", "schema", "migration", "security", "config.toml",
}

# ── Heavy 关键词 fast-path ──
_HEAVY_KEYWORDS = [
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
    # 中文
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

# ── Light 关键词 fast-path ──
_LIGHT_KEYWORDS = [
    (r"\bfix\s+typo\b", "fix typo"),
    (r"\btypo\b", "typo"),
    (r"\blint\b", "lint"),
    (r"\bformat(?:ting)?\b", "format"),
    (r"\bdocstring\b", "docstring"),
    (r"\bnit\b", "nit"),
    (r"\bimport\s+sort\b", "import sort"),
    # 中文
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

_heavy_re = [(re.compile(p, re.IGNORECASE), label) for p, label in _HEAVY_KEYWORDS]
_light_re = [(re.compile(p, re.IGNORECASE), label) for p, label in _LIGHT_KEYWORDS]

_LOG_PATH = os.path.expanduser("~/.config/mms/lb_route.log")

# ── LLM 分类 prompt ──
_CLASSIFY_SYSTEM = "You are a task classifier. Reply ONLY with one word: LIGHT or HEAVY."
_CLASSIFY_USER = """Classify this coding task (may be in Chinese or English):
- LIGHT: trivial changes (typo, rename, formatting, comments, docs, simple config, one-liner fix, 改错别字, 加注释, 改文案, 排版, 重命名)
- HEAVY: anything else (new feature, refactor, debug, multi-file, architecture, security, performance, 新功能, 重构, 优化, 修复bug)

Task: {task}

Reply LIGHT or HEAVY:"""


def _llm_classify(text: str, api_url: str, api_key: str, model: str) -> str | None:
    """用 light 模型做快速二分类。失败返回 None。"""
    if _httpx is None:
        return None
    try:
        # 确保 URL 以 /v1/messages 结尾，不重复追加
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
        # 兼容 Anthropic 和 OpenAI 两种响应格式，跳过 thinking blocks
        reply = ""
        thinking_text = ""
        # Anthropic: {"content": [{"type":"thinking",...}, {"type":"text","text":"LIGHT"}]}
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
        # OpenAI: {"choices": [{"message": {"content": "LIGHT"}}]}
        if not reply:
            choices = data.get("choices", [])
            if choices and isinstance(choices, list):
                msg = choices[0].get("message", {})
                reply = msg.get("content", "") if isinstance(msg, dict) else ""
        # Fallback: 如果 text 为空但 thinking 里有结论，也提取
        check_text = (reply or thinking_text).strip().upper()
        if "LIGHT" in check_text:
            return "light"
        if "HEAVY" in check_text:
            return "heavy"
        _log_llm_error(f"unexpected reply: {check_text[:100]} | raw={str(data)[:500]}")
        return None
    except Exception as exc:
        _log_llm_error(f"exception: {exc}")
        return None


def _log_llm_error(msg: str):
    try:
        log_path = os.path.expanduser("~/.config/mms/lb_route.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        ts = datetime.now().strftime("%H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}]   LLM_ERR  {msg}\n")
    except OSError:
        pass


def classify_task(text: str, api_url: str = None, api_key: str = None,
                  light_model: str = None) -> tuple[str, str]:
    """三层分类：guardrail → 关键词 fast-path → LLM 分类 → 默认 heavy。

    api_url / api_key / light_model: 传入时启用 LLM 分类（用 light 模型判断）。
    """
    if not text:
        return "heavy", "empty input"

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

    # 4. LLM 分类（仅首次用户消息，后续轮次文本太长/系统消息多，跳过）
    if api_url and api_key and light_model and len(text) < 2000:
        result = _llm_classify(text, api_url, api_key, light_model)
        if result:
            return result, "llm"

    # 5. 默认 heavy（安全，不降级）
    return "heavy", "default"


def log_route(level: str, reason: str, model_used: str, text_preview: str):
    """写路由日志。tail -f ~/.config/mms/lb_route.log 查看。"""
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        ts = datetime.now().strftime("%H:%M:%S")
        preview = text_preview[:60].replace("\n", " ")
        if len(text_preview) > 60:
            preview += "…"
        tag = "⬇ LIGHT" if level == "light" else "  heavy"
        line = f"[{ts}] {tag}  model={model_used}  reason={reason}  prompt={preview}\n"
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def route_model(user_message: str, heavy_model: str, light_model: str) -> str:
    """light → light_model，其余 → heavy_model。"""
    level, _ = classify_task(user_message)
    if level == "light":
        return light_model
    return heavy_model
