# Pilot 设置与保存回归

- 时间：2026-09-12（Asia/Singapore）
- 范围：旧 MMS 用户首次使用 Pilot 时的 Pi 启动、模型取消选择保存、模型设置保存交互。
- 改动：允许 Registry-only 私有快照启动 Pi；空模型选择在 worker 和 UI 明确阻止；保存操作栏移到通道页顶部并固定；连接向导和通道设置都移除第二次浏览器原生 confirm，统一使用页面内 Dialog；新增对应回归测试；版本 bump 到 4.19.5。
- 预期：没有 legacy config.toml 但有 latest-approved bundle 时可启动；取消全部模型时不发起会失败的保存；保存入口靠近页面顶部且只出现一次应用确认。
- 风险：旧的 v4.16 静态配置页不会被本次源码变更自动替换；当前 Pilot 仍以已有 shared Dialog 为统一弹窗样式。
- 验证：`python3 -m pytest tests/test_mms_web_sessions_launch.py tests/test_mms_web_model_settings.py -q`（44 passed）；`npm run build`（tsc 与 Vite 均通过，只有 chunk size warning）；`git diff --check` 通过。
- 状态：源码修复已验证；尚未发布或替换用户本机正在运行的旧实例。
