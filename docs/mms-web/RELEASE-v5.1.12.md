# v5.1.12 Preview · 拉取模型时填入能力

在 Pilot 里拉取通道模型时，模型 id 若与 OpenRouter 斜杠后面的名字一致，识图、上下文长度和默认 effort 会填进这次待保存的修改。官方 profile 已有的字段优先；已经手设过的值不会被覆盖。`glm-5.4` 可以对上 `z-ai/glm-5.4`，`glm5.4` 不会。

拉取本身不改已发布配置。确认保存后，之后启动的会话才会读到。

## 升级须知

更新会重启 Pilot。请先完成或停止正在执行、等待确认及排队的任务。不需要迁移模型、通道或 API Key。

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel dev
```
