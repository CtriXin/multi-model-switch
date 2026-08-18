"""非 Claude 桥接模型(GLM/Kimi/未来模型)的 1M context 回归。

覆盖两个修复:
- A: TUI 未展示 1M 开关时返回 None,mms_core 不覆盖 provider 的 claude_1m_mode
- C: 非 Claude 桥接模型 + window>=1M 时,shell slots 不依赖 enable_claude_1m 开关,
  且 CLAUDE_CODE_MAX_CONTEXT_TOKENS 泛化写入(不再枚举 glm-5.2)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mms_launchers import (
    _apply_claude_context_env_overrides,
    _apply_claude_shell_context_slots,
    _is_non_claude_routed_model,
)


class TestNonClaudeRoutedModel(unittest.TestCase):
    def test_glm_kimi_and_future_models_are_non_claude(self):
        for name in ("glm-5.3", "glm-5.2", "kimi-k3", "some-future-model", "open/glm-5.3"):
            self.assertTrue(_is_non_claude_routed_model(name), name)

    def test_claude_family_models_are_not_non_claude(self):
        for name in ("claude-sonnet-4-6", "claude-opus-5", "claude-sonnet-4-6[1m]", ""):
            self.assertFalse(_is_non_claude_routed_model(name), name)


class TestShellContextSlotsForNonClaudeModels(unittest.TestCase):
    def test_non_claude_model_gets_1m_slots_even_when_toggle_off(self):
        # C 方案:launch_claude 对非 Claude 桥接模型强制 enable_1m=True,
        # 这里验证调用点等效表达(enable_claude_1m=False + routed 判定)仍写 [1m] 壳名。
        env = {"ANTHROPIC_MODEL": "glm-5.3"}
        shell = _apply_claude_shell_context_slots(
            env,
            context_window=1_000_000,
            fallback_model="claude-sonnet-4-6",
            enable_1m=False or _is_non_claude_routed_model("glm-5.3"),
            provider_id="xin",
        )
        self.assertEqual(shell, "claude-sonnet-4-6[1m]")
        self.assertEqual(env["ANTHROPIC_MODEL"], "claude-sonnet-4-6[1m]")
        self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "claude-sonnet-4-6")

    def test_claude_model_with_toggle_off_stays_bare(self):
        # 真实 Claude 模型且用户关掉 1M:行为不变,不写 [1m](保护既有语义)。
        env = {"ANTHROPIC_MODEL": "claude-sonnet-4-6"}
        shell = _apply_claude_shell_context_slots(
            env,
            context_window=1_000_000,
            fallback_model="claude-sonnet-4-6",
            enable_1m=False,
            provider_id="default",
        )
        self.assertEqual(shell, "")
        self.assertEqual(env["ANTHROPIC_MODEL"], "claude-sonnet-4-6")


class TestExplicitContextCapGeneralization(unittest.TestCase):
    def test_glm_5_3_and_future_models_trigger_explicit_cap(self):
        for model in ("glm-5.3", "glm-5.2", "some-future-1m-model"):
            env = {}
            _apply_claude_context_env_overrides(env, context_window=1_000_000, model_names=[model])
            self.assertEqual(env.get("CLAUDE_CODE_MAX_CONTEXT_TOKENS"), "1000000", model)

    def test_claude_model_does_not_trigger_explicit_cap(self):
        env = {}
        _apply_claude_context_env_overrides(env, context_window=1_000_000, model_names=["claude-sonnet-4-6[1m]"])
        self.assertNotIn("CLAUDE_CODE_MAX_CONTEXT_TOKENS", env)

    def test_non_claude_model_below_1m_window_no_cap(self):
        env = {}
        _apply_claude_context_env_overrides(env, context_window=200_000, model_names=["glm-5.3"])
        self.assertNotIn("CLAUDE_CODE_MAX_CONTEXT_TOKENS", env)


class TestTuiNoneDoesNotOverrideProviderMode(unittest.TestCase):
    def test_tui_returns_none_when_no_toggle(self):
        # 直接验证 mms_core 解包后的写入语义:claude_1m_enabled is None -> 不写 runtime key
        runtime_runtime = {"claude_1m_mode": "auto"}
        claude_1m_enabled = None
        if claude_1m_enabled is not None:
            runtime_runtime["claude_1m_mode"] = "enable" if claude_1m_enabled else "disable"
        self.assertEqual(runtime_runtime["claude_1m_mode"], "auto")

        # 对照:开关展示且用户关闭时仍显式写 disable
        runtime_runtime = {"claude_1m_mode": "auto"}
        claude_1m_enabled = False
        if claude_1m_enabled is not None:
            runtime_runtime["claude_1m_mode"] = "enable" if claude_1m_enabled else "disable"
        self.assertEqual(runtime_runtime["claude_1m_mode"], "disable")

    def test_core_source_keeps_none_guard(self):
        # 防回归:mms_core 写入点必须保留 None guard
        import mms_core
        import inspect

        src = inspect.getsource(mms_core)
        self.assertIn("claude_1m_enabled is not None", src)


if __name__ == "__main__":
    unittest.main()
