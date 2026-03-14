# TUI Interaction Findings

本文件记录当前 `TUI -> core -> launcher` 链路里的交互问题。只做 review，不包含代码修改。

## Summary Table

| 灯色 | 优先级 | 问题 | 位置 | 影响 |
|---|---|---|---|---|
| 🔴 | P1 | TUI 确认页不支持“保存为预设”，但 core 仍保留 `s` 分支，TUI 和 fallback 行为不一致 | `ccs_tui.py:971`, `ccs_core.py:3282` | 用户在不同入口下得到不同结果 |
| 🔴 | P1 | TUI 路径会继续选 source/runtime，但直达 CLI、`--custom`、fallback 路径没有等价流程，入口语义不一致 | `ccs_core.py:3206`, `ccs_core.py:4477`, `ccs_core.py:4543` | 容易再次出现“选的是 A，启动成 B” |
| 🟡 | P2 | 主场景列表会重复展示同一场景，上次使用、正常场景、启动排行可能同时出现 | `ccs_tui.py:368` | 导航噪音大，误选概率上升 |
| 🟡 | P2 | 主 TUI 没有滚动窗口，列表长时会出现“看不见但还能选到”的盲选状态 | `ccs_tui.py:277`, `ccs_tui.py:427` | 小终端下可用性明显下降 |
| 🟡 | P2 | source 列表为空时仍可确认，随后静默回退到默认 runtime | `ccs_tui.py:528`, `ccs_core.py:3253` | 用户以为自己在做来源选择，实际上系统代选 |
| 🟡 | P2 | 负载模式自定义会展示当前来源未必可承载的模型组合 | `ccs_tui.py:806` | 错误被推迟到启动阶段才暴露 |
| 🟢 | P3 | `confirm_tui` 注释写“bypass 仅 codex 有效”，但 UI 和 launcher 对 `claude` 也生效 | `ccs_tui.py:877`, `ccs_launchers.py:368` | 文案和真实行为不一致 |

## Notes

- 这轮 review 只覆盖 `ccs_tui.py` 及其在 `ccs_core.py` / `ccs_launchers.py` 的直接调用链。
- 结论基于当前 worktree 的静态代码阅读，没有跑交互自动化测试。
- 当前工作树里还有未提交的 `ccs_*` 改动，以上 findings 针对的是“现在这份代码”的状态。
