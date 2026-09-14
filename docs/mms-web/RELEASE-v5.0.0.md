# v5.0.0 · Bot 工作台进入主线，合流 4.21.x Windows 修复

## 升级须知

5.0 是 Bot 工作台的版本边界：Bot 相关能力只在 5.x 出现，4.21.z 维护线不含任何 Bot 代码。本说明随 `dev` 一起演进，正式 tag 打出前内容仍会补充。

从 4.21.z 升级不需要迁移配置：配置根仍是 `~/.config/mms-next`，Bot 的定义、任务、记忆和通知都放在 Pilot 的 state root 下，不写真实 `~/.config/mms*`。

## Bot 工作台

- Pilot 新增 `#page=bots`：每个 Bot 是长期存在的协作者，用户用聊天交代目标，Bot 在自己的 Pi 会话里执行，成果以文件卡片回到对话。
- 运行时：任务状态机、`requestId` 幂等、最多五层分发、Bot 之间的邮箱、按 Bot 隔离的记忆、`runAt` 定时与自动唤醒、并发上限与优先级排队。
- Coordinator：由 Bot 自己的模型产出 JSON 计划并由运行时执行，支持 `direct-first` / `plan-approve` / `off`，计划可批准、驳回、替换，30 秒内可撤销。普通 direct-first 任务直接使用持久会话，不再额外启动 planner。
- 韧性与送达：基础设施错误按 30 秒 / 2 分钟 / 8 分钟重试三次；事件日志、桌面通知与带 `X-MMS-Signature` 的 webhook。
- 协作回执：同事回报带一行摘要和成果引用，系统失败以 `system` 类消息送达。
- 视觉：Bot 页面完全走 Pilot 主题 token，浅色、深色与强调色一致；几何头像十种形状六种颜色，表情按 Bot 身份稳定生成。
- 隔离：Bot 会话持久化 `owner=bot`，不再出现在 Pilot 的会话列表里。

## Pilot

- 设置新增运行环境标签；帮助面板的版本更新列表读取随安装附带的真实发布说明。

## 合流的 4.21.z Windows 修复

包含 v4.21.0 到 v4.21.12 的全部 Windows 修复：GBK 系统下 `mms web` 生命周期与对话链路的编码问题、Pi RPC 管道与启动握手、UTF-8 历史读取、PowerShell 回退、工作区文件夹选择器、Pilot doctor 自检、会话守护 pid 的 Win32 查询。细节见各 `RELEASE-v4.21.z.md`。
