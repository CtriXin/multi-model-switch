# OpenRouter 模型名合同

给往 New API / Oracle 加模型的人。Pilot 从 v5.1.12（稳定线 v4.23.9）起，拉取通道模型时用这份名字去对 OpenRouter，对上才填识图、context、默认 effort。

对外模型名一律写 OpenRouter 的 **model id**，原样，带厂商前缀。

## 这次

页面：<https://openrouter.ai/openai/gpt-6-sol>

模型名写：

```text
openai/gpt-6-sol
```

不要写成 `gpt-6-sol`、`GPT-6 Sol`、`openai/gpt-6-sol-20260922`、`openai/gpt-6-sol:batch`、`openai/gpt-6-sol-pro`。

`:batch` 是另一条路由，`gpt-6-sol-pro` 是另一个模型。带日期的 canonical slug 不是对外 id。

## 规则

1. 从 OpenRouter 模型页或 `https://openrouter.ai/api/v1/models` 的 `id` 字段抄，不要用页面标题。
2. 保留大小写以外的每一个字符：斜杠、连字符、点、冒号。比对时忽略大小写。
3. 末尾的 `[1m]` 这类方括号后缀会被去掉后再比。不要靠这个后缀表达上下文。
4. 完整 id 一定要能对上。只写斜杠后面那段（如 `gpt-6-sol`）有时也能对上，但同名尾巴会被目录里先出现的那条占住。对外名字不要用短名。
5. 不做模糊匹配。`gpt6sol` 对不上 `gpt-6-sol`。

New API 的 `/models` 列表里返回的名字，就是 Pilot 用来比对的名字。上游如果要另一个调用字符串，在通道里做映射，不要改这个对外名字。请求打通只说明上游认调用名，不说明 Pilot 能对上 OpenRouter。

## 启动时怎么显示

分组仍是 MMS 的 family（`grok` 进 Grok，`gpt-` 进 GPT），不是 `x-ai`、`openai` 这种前缀。

启动列表里，`厂商/模型` 一律只显示斜杠后面的名字：`openai/gpt-6-luna` 显示为 `gpt-6-luna`。厂商前缀用来对上已有 family：`openai` 进 GPT，`x-ai` 进 Grok，不会新开一组叫 `openai`。没有斜杠的名字仍走原来的关键词规则。发给上游的 id 仍是完整字符串。

## 拉取后会填什么

对上之后，Pilot 把这三项填进同一次待保存修改。还要点保存才写入。

| 字段 | 来源 | 不写的情况 |
|---|---|---|
| 识图 | `architecture.input_modalities` 里有 `image`、`vision` 或 `multimodal` | 目录没给模态列表 |
| context | `context_length` | 没有这个数字 |
| 默认 effort | `reasoning.default_effort` | 不是 `low` / `medium` / `high` / `xhigh` / `max`（`none`、`minimal` 不写） |

MMS 官方 profile 里已经有的字段，用官方的，不用 OpenRouter 盖掉。这个模型以前手设过的识图、context、effort 也不盖。

`openai/gpt-6-sol` 在 2026-09-23 的目录值：可识图（模态含 `image`），context `1050000`，默认 effort `medium`。目录会变，以拉取当时的 OpenRouter 为准。
