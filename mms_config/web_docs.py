# -*- coding: utf-8 -*-
"""Static setup docs and Markdown builders for the MMS config WebUI."""

from __future__ import annotations

from typing import Any


def build_config_snippets() -> dict[str, str]:
    """Manual snippets shown in WebUI; callers choose whether to apply."""
    vision = """# config.toml: vision sidecar
[vision_sidecar]
enabled = true
provider_id = "mimo-direct-anthropic"
model = "mimo-v2.5"

[[vision_sidecar.candidates]]
provider_id = "mimo-direct-anthropic"
model = "mimo-v2.5"

[[vision_sidecar.candidates]]
provider_id = "direct-kimi"
model = "K2.6"

[[vision_sidecar.candidates]]
provider_id = "direct-qwen"
model = "qwen3.6-plus"
""".strip()
    rescue = """# config.toml: rescue fallback
[rescue]
fallback_model = "deepseek-v4-flash"
fallback_cli = "codex"
hot_fallback_enabled = false
""".strip()
    opencode = """# OpenCode launch examples
mms opencode --profile agent
mms opencode --profile omo
mms opencode-smoke --profile agent --health-summary
""".strip()
    policy = """// model-policy.json: visibility and capability overrides
{
  "models": {
    "qwen3.6-plus": {
      "visible": true,
      "favorite": true,
      "capabilities": {
        "text": true,
        "vision": true,
        "tool_use": true,
        "reasoning": true,
        "thinking": true,
        "supports_thinking": true,
        "one_m_context": true,
        "context_window_tokens": 1000000,
        "cache_sensitive_transport": true
      }
    },
    "retired-or-noisy-model": {
      "visible": false,
      "hide_in": ["mms", "hive", "pilot", "ant", "mobius"]
    }
  },
  "projects": {
    "mms": {
      "default_visible": true,
      "hidden_models": ["retired-or-noisy-model"],
      "favorite_models": ["qwen3.6-plus"]
    }
  }
}
""".strip()
    preferred_cli = """# config.toml: practical WebUI target
[presets.coding]
cli = "opencode"
model = "gpt-5.5"

[opencode]
default_profile = "agent"

[opencode.agent_models.mobius-explore-glm]
provider_id = "domestic"
model = "glm-5-turbo"
""".strip()
    return {
        "vision_sidecar": vision,
        "rescue": rescue,
        "opencode": opencode,
        "model_policy": policy,
        "preferred_cli": preferred_cli,
    }


def build_setup_flow() -> list[dict[str, Any]]:
    """Product IA for the visual setup flow; kept in snapshot for WebUI/Markdown."""
    return [
        {
            "id": "channel",
            "title": "1. 通道配置",
            "summary": "配置通道名称、URL、Key、协议和模型列表接口，然后拉取模型。",
            "fields": ["provider_id", "display_name", "openai_base_url", "anthropic_base_url", "api_key", "models_endpoint", "protocols"],
            "actions": ["fetch_models", "test_models_endpoint", "save_credentials_with_audit"],
        },
        {
            "id": "model_inventory",
            "title": "2. 模型列表",
            "summary": "查看当前通道拉取结果，隐藏噪音模型，像 NewAPI 一样手动补充当前通道模型。",
            "fields": ["visible", "favorite", "hidden_models", "manual_models", "model_aliases"],
            "actions": ["hide_selected", "add_manual_model", "copy_selected"],
        },
        {
            "id": "capability",
            "title": "3. 能力标记",
            "summary": "手动标记 text、vision/multimodal、tool use、reasoning、long context 和 cache-sensitive。",
            "fields": ["text", "vision", "long_context", "tool_use", "reasoning", "cache_sensitive"],
            "actions": ["apply_known_defaults", "save_model_policy"],
        },
        {
            "id": "validation",
            "title": "4. 模型测试",
            "summary": "测试拉取、指定模型 ping/pong、可选 simple chat，并记录 request path evidence。",
            "fields": ["stream", "protocol", "request_url", "request_path", "latency", "error"],
            "actions": ["test_list", "test_selected_model", "test_chat"],
        },
        {
            "id": "fallbacks",
            "title": "5. Fallback 设置",
            "summary": "设置 rescue fallback、vision sidecar/fallback 模型和 hot fallback 开关。",
            "fields": ["fallback_model", "fallback_cli", "vision_model", "vision_candidates", "hot_fallback_enabled"],
            "actions": ["preview_config_diff", "run_non_live_smoke"],
        },
        {
            "id": "runtime",
            "title": "6. 运行默认值",
            "summary": "设置 首选 CLI、coding preset 和 OpenCode Multi-Agent profile。",
            "fields": ["preferred_cli", "opencode_profile", "executor", "reviewer", "explore", "vision_agents"],
            "actions": ["preview_launch", "save_audited"],
        },
        {
            "id": "session_assets",
            "title": "7. Session 能力面板",
            "summary": "区分 MMS dynamic 与 Global/inherited 的 skills、MCP、hooks，并可单独保存 preferences.toml 偏好。",
            "fields": ["cli", "kind", "origin", "path", "disable_key", "default_state"],
            "actions": ["filter_by_cli", "filter_by_origin", "save_preferences", "copy_preferences_snippet"],
        },
    ]


def build_test_contracts() -> list[dict[str, str]]:
    return [
        {
            "id": "models_endpoint",
            "title": "模型列表测试",
            "method": "GET /models 或配置的 models_endpoint",
            "result": "模型 ID、endpoint 状态、协议提示和脱敏 transport evidence",
        },
        {
            "id": "model_ping",
            "title": "指定模型 smoke",
            "method": "通过选定 protocol 发送最小非流式 prompt",
            "result": "ok/fail、latency、response shape、request_url/request_path",
        },
        {
            "id": "simple_chat",
            "title": "简单 chat 测试",
            "method": "一条 user message，限制短回答",
            "result": "回复预览 + cache_transport_evidence.v1",
        },
        {
            "id": "vision_probe",
            "title": "Vision probe",
            "method": "仅当模型标记 vision-capable 时发小图片/OCR 请求",
            "result": "确认直接 vision 支持，或建议启用 sidecar fallback",
        },
    ]


def build_reference_cards() -> list[dict[str, str]]:
    return [
        {
            "title": "模型配置契约",
            "path": "docs/MODEL_CONFIG_CONTRACT.md",
            "summary": "Router / Lineup / Profile / Policy 四份配置的职责边界。",
        },
        {
            "title": "用户偏好 allowlist",
            "path": "docs/MMS_USER_PREFERENCES.md",
            "summary": "哪些日常偏好适合 preferences.toml，哪些真实配置必须 人工确认。",
        },
        {
            "title": "OpenCode Lite Pro",
            "path": "docs/OPENCODE_LITE_LAUNCHER.md",
            "summary": "OpenSpec Multi、GPT executor、国产只读 explore/bug-hunt 的当前策略。",
        },
        {
            "title": "Session assets / preferences",
            "path": "docs/MMS_USER_PREFERENCES.md",
            "summary": "解释 MMS dynamic skills/MCP/hooks、global config 边界和 preferences.toml allowlist。",
        },
        {
            "title": "能力校准快照",
            "path": "docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.md",
            "summary": "当前模型能力证据输入，WebUI 默认能力标记会参考这些本地事实。",
        },
    ]


def build_setup_markdown(snapshot: dict[str, Any]) -> str:
    providers = snapshot.get("providers") or []
    lines = [
        "# MMS Setup Configuration",
        "",
        f"- mode: `{snapshot.get('mode')}`",
        f"- config: `{snapshot.get('paths', {}).get('config') or '-'}`",
        f"- model_policy: `{snapshot.get('paths', {}).get('model_policy') or '-'}`",
        f"- preferences: `{snapshot.get('paths', {}).get('preferences') or '-'}`",
        "",
        "## Providers",
    ]
    if providers:
        for item in providers:
            lines.append(
                "- `{id}` enabled={enabled} protocols={protocols} clis={clis} models={models} key={key}".format(
                    id=item.get("id") or "-",
                    enabled=item.get("enabled"),
                    protocols=",".join(item.get("protocols") or []) or "-",
                    clis=",".join(item.get("supported_clis") or []) or "-",
                    models=item.get("model_count", 0),
                    key="set" if item.get("has_api_key") else "missing",
                )
            )
    else:
        lines.append("- No providers found.")
    flow = snapshot.get("setup_flow") or []
    if flow:
        lines.extend(["", "## Visual Setup Flow"])
        for item in flow:
            lines.append(f"- **{item.get('title')}**: {item.get('summary')}")
            actions = ", ".join(item.get("actions") or [])
            if actions:
                lines.append(f"  - actions: `{actions}`")
    tests = snapshot.get("test_contracts") or []
    if tests:
        lines.extend(["", "## Model Test Contracts"])
        for item in tests:
            lines.append(f"- **{item.get('title')}**: {item.get('method')} -> {item.get('result')}")
    snippets = snapshot.get("snippets") or {}
    lines.extend(["", "## Vision Sidecar", "", "```toml", snippets.get("vision_sidecar", ""), "```"])
    lines.extend(["", "## Rescue Fallback", "", "```toml", snippets.get("rescue", ""), "```"])
    lines.extend(["", "## Model Visibility And Capability Policy", "", "```json", snippets.get("model_policy", ""), "```"])
    lines.extend(["", "## 首选 CLI", "", "```toml", snippets.get("preferred_cli", ""), "```"])
    lines.extend(["", "## OpenCode", "", "```bash", snippets.get("opencode", ""), "```"])
    recommendations = snapshot.get("recommendations") or []
    if recommendations:
        lines.extend(["", "## Recommendations"])
        lines.extend(f"- {item}" for item in recommendations)
    lines.extend(
        [
            "",
            "## Safety",
            "- WebUI writes are interactive only: preview diff, check confirmation, then save.",
            "- Saves use MMS config lock, backup, and config audit log.",
            "- API keys are accepted only in POST bodies and are never echoed back.",
        ]
    )
    return "\n".join(lines).strip() + "\n"
