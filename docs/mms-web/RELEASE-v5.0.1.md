# v5.0.1 · 修复设置滚动条遮挡与 Bot 交互/弹窗样式

## 升级须知

本版本为 5.0.0 的紧急体验修复更新，配置根与数据保持不变（`~/.config/mms-next` 与 `state_root/bots`），无需手动迁移配置。更新后刷新网页客户端即可生效。

## 变更说明

本版本为 5.0.0 后的紧急体验修复版本，专注于修复 5.0.0 中发现的 5 处 UI/CSS 布局与交互问题：

1. **设置页与快速模型选择器滚动条遮挡修复**
   - 给设置页（`studio.css` 中的 `.settings-shell .settings-page`、`.settings-shell .channel-models`、`.general-settings`）补充右侧安全内边距（`padding-right: 14px;`），彻底解决长内容滚动时滚动条遮挡右侧控件和开关的问题。
   - 快速模型选择器列表（`quick-model-list`）补充 `padding: 5px 6px;`，防止滚动条覆盖模型条目。

2. **Bot 执行停止按钮位置优化**
   - 移除此前孤悬在输入框外部左上方的悬空操作栏。
   - 任务在队列或执行中（`queued` / `starting` / `running`）时，输入框右下角主按钮自动切换为停止按钮（红色警示色与方块图标），点击即刻中止执行，与主流对话交互一致。

3. **Bot 失败任务重试按钮内聚优化**
   - 移除输入框外部左上方的悬空重试按钮。
   - 在对话消息流的错误提示卡片（`.bot-chat-error`）内紧随错误说明提供行内胶囊按钮 `[↺ 重试]`，确保错误原因与重试操作处于同一视觉上下文。

4. **Bot 预设编辑弹窗“默认模型”选择器下拉箭头对齐修复**
   - 修复 `.model-picker-trigger` 弹性盒模型与文字换行问题，文字部分 `flex: 1 1 auto; min-width: 0;` 自动截断，右侧下拉箭头固定靠右居中，不再掉入第二行中间。

5. **Bot 创建/编辑弹窗视口自适应与头像高光防裁切**
   - 为 `.bot-create-dialog` 增加 `max-height: min(90vh, 740px); overflow-y: auto;`，适配笔记本及小屏幕视口，防止弹窗超出屏幕导致底部操作按钮被硬截断。
   - 为 `.bot-color-options` 补充上下各 6px 呼吸间距，防止选中头像圆点的高光轮廓（`outline`）被弹窗边缘截断。

---

## 验证与门禁

- `tsc --noEmit`：0 错误。
- Node 单元测试（`apps/mms-web/tests/*.test.mjs`）：114 项全绿通过。
- CSS Hex 限制门禁：严格通过。
- 前端静态包已重新打包构建至 `mms_web_static/`。
