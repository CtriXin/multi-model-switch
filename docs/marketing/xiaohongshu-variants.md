# MMS 小红书推广文案 - 5 版变体

---

## 版本 1：技术极简风

**标题：** 一行命令管理所有 AI CLI，再也不用改环境变量了

**正文：**
电脑里装了 Claude、Codex、Kimi、Qwen 的看过来

每次换模型要改一堆 ANTHROPIC_API_KEY、OPENAI_BASE_URL？

我写了个工具 MMS，核心就一句话：

一个入口，统一管理所有 AI 编程 CLI

✅ `mms` 进 TUI，方向键选模型，回车启动
✅ `mms claude --provider xxx` 临时切换 provider
✅ `mms env preset --apply` 导出环境变量给脚本用
✅ `mms doctor` 一键诊断 provider 健康度

最爽的是**不污染 .zshrc**，环境变量只在本次注入

MIT 开源，curl 一键安装 👇

**标签：** #程序员 #开源 #CLI #AI编程 #效率工具 #Claude #Codex #生产力

---

## 版本 2：痛点解决风

**标题：** 改环境变量改到崩溃？这个工具拯救了我

**正文：**
有没有跟我一样，每天要在不同 AI 模型之间切来切去的？

Claude 用完想用 GPT，GPT 用完想用 Kimi...
每次都要：
- 改 ANTHROPIC_API_KEY
- 改 OPENAI_BASE_URL
- 改完发现忘改回去，下一个命令报错 😭

直到我写了 MMS（Multi-Model Switch）

现在：
- `mms` → 进界面选模型 → 启动
- `mms codex --account work` → 临时切工作号
- 用完即走，shell 干干净净

还支持多账号隔离，公司和个人的 OAuth 账号互不串

安装就一行命令，MIT 协议完全免费

**标签：** #打工人 #程序员日常 #开发工具 #AI工具 #开源项目 #效率神器

---

## 版本 3：效率工具风

**标题：** 程序员效率神器 | 3 秒切换 AI 模型

**正文：**
分享一个我每天都在用的本地工具 MMS

**它能做什么：**
🔹 统一启动 Claude / Codex / Qwen / Kimi
🔹 TUI 界面，方向键选模型，比记命令快 10 倍
🔹 多 Provider 管理，一键切换不冲突
🔹 内置诊断 `mms doctor`，provider 挂了秒知道

**设计理念：**
- 单次注入，不写全局 shell 配置
- 凭据隔离，config 只存元数据
- 本地 override，团队共享配置不污染仓库

**安装：**
```bash
curl -fsSL mms.dev/install.sh | bash
```

已经开源，GitHub 搜 multi-model-switch

**标签：** #程序员 #效率工具 #命令行 #开源 #AI编程 #生产力 #开发工具

---

## 版本 4：对比展示风

**标题：** Before vs After | 管理 AI CLI 的正确方式

**正文：**
**Before（以前）：**
```bash
export ANTHROPIC_API_KEY=sk-xxx
export ANTHROPIC_BASE_URL=https://...
claude
# 用完忘了 unset，下个项目报错
```

**After（现在）：**
```bash
mms
# 方向键选模型 → 回车 → 启动
# 环境变量自动注入，退出自动清理
```

**还有更多：**
- `mms --preset coding` 预设一键启动
- `mms --trace` 查看选择链路
- `mms doctor` 诊断所有 provider
- `mms chat` 多模型并排对话

**支持：** Claude · Codex · Qwen · Kimi · Gemini

MIT 开源，个人项目，欢迎 Star ⭐

**标签：** #编程 #开源项目 #AI工具 #程序员 #效率提升 #开发日常 #技术分享

---

## 版本 5：情感共鸣风

**标题：** 多账号多模型的痛，谁懂？

**正文：**
电脑里五个 AI 账号：
- Claude 个人号
- Claude 工作号
- OpenAI 个人号
- OpenAI 公司号
- 还有各种国产模型...

以前每次切账号都要：
改环境变量 → 启动 → 用完 → 改回来
一步错了就崩，心态也崩 💔

现在用 MMS，一切简单了：

`mms` 进界面，看到所有模型
`←/→` 切换 CLI 类型
`↑/↓` 选模型
`Enter` 启动

账号隔离、Provider 切换、环境导出，全部一站式

自己写的工具，开源了，希望帮到有同样困扰的人

**标签：** #程序员 #开源 #AI编程 #多账号管理 #生产力工具 #代码人生 #打工人自救

---

## 通用标签建议

#开源 #AI工具 #程序员 #命令行 #效率工具 #Claude #Codex #生产力 #开发工具 #技术分享 #GitHub #编程日常

## 封面图建议

1. 终端截图 + 大标题 "MMS - 一行命令管理所有 AI CLI"
2. 对比图：左边乱糟糟的环境变量 vs 右边干净的 mms 界面
3. 动图：实际演示 mms 启动过程
4. 架构图：手绘风格展示统一入口概念
5. 文字卡片：痛点 + 解决方案 + 安装命令

## 发布时间建议

- 技术向：周二/周四 12:00-14:00 或 20:00-22:00
- 职场向：工作日 早 8-9 点，晚 20-22 点
