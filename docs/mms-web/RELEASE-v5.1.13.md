# v5.1.13 Preview · 启动列表按模型名显示

OpenRouter 形式的模型 id，例如 `openai/gpt-5.6-sol`，启动列表只显示斜杠后面的名字，并归入已有 family：`openai` 进 GPT，`x-ai` 进 Grok。没有斜杠的名字仍走原来的关键词规则。

短名和 `厂商/模型` 显示成同一个名字时，左边只留一行。右边按通道分开，每条通道启动时仍发送自己的 id。

## 升级须知

更新会重启 Pilot。请先完成或停止正在执行、等待确认及排队的任务。不需要迁移模型、通道或 API Key。

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel dev
```
