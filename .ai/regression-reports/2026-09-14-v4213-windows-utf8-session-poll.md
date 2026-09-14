# Windows Native Preview session polling UTF-8 fix

- 时间：2026-09-14（Asia/Singapore）
- 范围：Windows Pilot 在 Pi 工具执行后，页面只显示半截回复并提示本地服务状态异常
- 证据：Windows 使用中文 codepage；Pi 的 `conversation.jsonl` 是 UTF-8。`backfill_history()` 原先未指定 encoding，页面轮询会在中文或 emoji 回复后触发 `UnicodeDecodeError`，接口返回 500。
- 修改文件：`mms_web/session_actions.py`、`tests/test_mms_web_sessions_service.py`
- 修改：读取 native Pi history 时显式使用 `encoding="utf-8"`，保持 POSIX 行为不变；新增中文与 emoji 回归覆盖。
- 测试：`PYTHONPATH=. uv run pytest -q tests/test_mms_web_sessions_service.py tests/test_mms_web_sessions_launch.py` → 35 passed
- 风险：仅影响会话历史读取编码；不修改模型路由、Bot、配置、OAuth 或工具执行逻辑。
- 状态：代码修复完成；需要发布新 hotfix 后由 Windows 用户复测完整回复链。
