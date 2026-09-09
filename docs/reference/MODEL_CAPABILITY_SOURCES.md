# 模型能力官方来源

更新 `config/provider-profiles.json` 里的上下文长度、最大输出和识图能力时，从这里的链接查，不要从模型卡站、聚合站或搜索摘要抄。

每条记录三件事:链接、这一页真的能查到什么、最后一次核对的日期。核对过就把日期改掉;发现链接失效就换掉并写明新链接。

## 怎么用

1. 在下表找到厂商,打开「查得到」那列点名的页面。
2. 只改官方页面明确写了的值。页面没写的字段保持原样,不要从别处推断。
3. 改完在本文件把该行的日期更新为核对日期。
4. 改动理由写进提交信息,一条改动对应一个来源。

计划分级要特别小心。有些模型的上下文取决于订阅档位而不是模型本身,profile 里记的是保守档。见下面的 Kimi 说明。

## 厂商

| 厂商 | 官方页面 | 查得到 | 最后核对 |
| --- | --- | --- | --- |
| Anthropic | https://platform.claude.com/docs/en/about-claude/models/overview | 全系列上下文、最大输出、默认 effort;单个模型页有 `Input → output` 行说明是否收图 | 2026-09-09 |
| Anthropic 单模型 | https://platform.claude.com/docs/en/models/opus-4-6/overview<br>https://platform.claude.com/docs/en/models/sonnet-4-6/overview | 旧版模型的完整规格 | 2026-09-09 |
| OpenAI | https://developers.openai.com/api/docs/models | 上下文、最大输出、是否收图。注意 `platform.openai.com/docs/models` 会 301 到这里 | 2026-09-09 |
| Google Gemini | 单模型页，把末段换成模型名：<br>https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview<br>https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash<br>https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash | input/output token limit 与输入模态。总览页 `docs/models` 不带数字 | 2026-09-09 |
| xAI Grok | https://docs.x.ai/docs/models | 各模型上下文。不写最大输出 | 2026-09-09 |
| DeepSeek | https://api-docs.deepseek.com/quick_start/pricing/ | 上下文、最大输出、哪个变体收图 | 2026-09-09 |
| Moonshot Kimi 平台 | https://platform.kimi.ai/docs/models<br>https://platform.kimi.ai/docs/guide/kimi-k3-quickstart | 前者是全模型列表，后者给 k3 的上下文与 `max_completion_tokens` | 2026-09-09 |
| Kimi Code | https://www.kimi.com/code/docs/en/kimi-code/models.html | 编码套餐里各模型 id、上下文,以及按档位的限制 | 2026-09-09 |
| Z.ai GLM | https://docs.z.ai/guides/llm/glm-5.3.md<br>https://docs.z.ai/guides/llm/glm-5.2.md<br>https://docs.z.ai/guides/vlm/glm-5.3-flash.md | 单模型上下文、最大输出、输入模态。注意 `guides/llm/` 是纯文本模型，`guides/vlm/` 是收图的。索引在 https://docs.z.ai/llms.txt | 2026-09-09 |
| 智谱 BigModel | https://docs.bigmodel.cn/cn/guide/models/text/glm-5.3 | GLM-5.3 中文规格。索引在 https://docs.bigmodel.cn/llms.txt | 2026-09-09 |
| 阿里云百炼 Qwen | https://help.aliyun.com/en/model-studio/qwen3-8-max | 单模型上下文、最大输入、最大输出、输入模态。每个模型一页，把 url 末段换成模型名，例如 `qwen3-8-flash`、`qwen3-7-max` | 2026-09-09 |
| MiniMax | https://platform.minimaxi.com/docs/api-reference/api-overview<br>https://platform.minimaxi.com/docs/api-reference/text-openai-api | 前者给各模型上下文，后者写明只有 MiniMax-M3 收图。都不写最大输出 | 2026-09-09 |
| 小米 MiMo | https://mimo.mi.com/docs/zh-CN/quick-start/summary/welcome<br>https://mimo.mi.com/models/zh-CN/mimo-v2.5<br>https://mimo.mi.com/models/zh-CN/mimo-v2.5-pro | 在售模型与下线公告；单模型页有上下文、最大输出、输入模态 | 2026-09-09 |
| StepFun | https://platform.stepfun.com/docs/zh/guides/models | 全部模型的上下文与是否收图。不写最大输出 | 2026-09-09 |

## 核对覆盖率

不是每个值都核对过。下表记录 2026-09-09 这一轮的实际情况，**没查到的字段一律保持原样，不做推断**。判断某个值可不可信，先看这里。

| 厂商 | 核对到什么程度 | 没查到的 |
| --- | --- | --- |
| Anthropic | 全部。4.6 两个 legacy 加当前四个：Opus 5、Sonnet 5、Fable 5.1、Haiku 4.5 | 无 |
| OpenAI | 只有官方页面还在列的四个：gpt-6-astra、gpt-5.6 的 sol / terra / luna | gpt-5、gpt-5-pro、gpt-5.4、gpt-5.4-mini、gpt-5.5 已从官方页下架，值沿用旧记录 |
| Google Gemini | 3.1、3.5-flash、3.8-flash、2.5-pro、2.5-flash、裸 gemini-3（即已下线的 3-pro-preview） | gemini-3.5、3.1-flash-image |
| xAI Grok | 全部七个的上下文 | 官方页面不写各模型是否收图，因此一律不记 vision |
| DeepSeek | V4 三个：flash、pro、flash-vision-exp | deepseek-chat、deepseek-reasoner 已不在官方页 |
| Moonshot Kimi | k3 全系、k2.6、k2.7-code 及 highspeed、kimi-for-coding 两个 | kimi-k2.5、k2.6-code-preview、kimi-for-code |
| Z.ai / 智谱 GLM | glm-5.2、glm-5.3、glm-5.3-flash | glm-4.5 / 4.5-air / 4.6 / 4.7 / 5 / 5-turbo / 5.1，官方现已路由到 5.3 系 |
| 阿里 Qwen | qwen3.8-max、qwen3.8-flash、qwen3.7-max | qwen3.8-max-preview |
| MiniMax | 全部八个的上下文，以及只有 M3 收图这一条 | 官方不写各模型最大输出 |
| 小米 MiMo | mimo-v2.5、mimo-v2.5-pro | mimo-v2 全系（2026-06-30 已下线） |
| StepFun | step-3.7-flash、step-3.5-flash、step-1o-turbo-vision | step-router-v1 不在官方文档里 |

覆盖面有意做得比任何单个中转通道宽：把厂商当前在售的整条产品线都写进来，新模型出现在通道里时就已经有数据，不用等下一轮补。

## 官方文档查不到时，按这个顺序找

**一、厂商自己的机器可读接口。** 和文档同源，而且是活的，还能覆盖文档已经下架的旧模型。需要该通道的 key。

| 厂商 | 接口 | 直接给出 |
| --- | --- | --- |
| Anthropic | `GET https://api.anthropic.com/v1/models` | `max_input_tokens`、`max_tokens`、`capabilities.image_input.supported`、`capabilities.effort` 的 low/medium/high/max/xhigh、`capabilities.thinking.types` |
| Google | `GET https://generativelanguage.googleapis.com/v1beta/models` | `inputTokenLimit`、`outputTokenLimit`、`supportedGenerationMethods` |
| OpenAI | `GET /v1/models` | 只有 id，没有限额，这条路走不通 |

Anthropic 那个接口的字段和我们需要的字段几乎一一对应，是所有来源里最好的一个。

**二、实测这条通道。** 对中转来说这是唯一真正准确的答案，因为**生效的上限是中转的上限，不是厂商的**。厂商说 1M，中转可能只给你 200K，文档永远看不出来。两个探测：

- 上下文与最大输出：故意把 `max_tokens` 设到明显超限，或送一段超长输入，读错误里报出来的数字。多数网关会把真实上限写进错误消息。
- 识图：发一张 1×1 的图，收不收一次就知道。

这也是套餐分档唯一能被发现的方式。

**三、承认查不到。** 留空、走保守值，比填一个来源不明的数字好。留空时 `conservative_fallback` 会接手，含义是「没有任何来源声明过」，不是「不支持」。

**明确不采信**：模型卡站、API 聚合站、第三方目录、评测榜、搜索结果摘要、以及任何转述官方而不是官方本身的页面。它们经常把预览版和正式版、把套餐档位和模型上限混在一起，而且不会随厂商更新。（`web.archive.org` 上的官方页面快照在原则上可信，但当前环境取不到。）

## OpenRouter：备选，不是真值

OpenRouter 的 `https://openrouter.ai/api/v1/models` 一次返回全部模型的上下文、最大输出和输入模态，是查新模型最快的入口。但它不能当主来源，2026-09-09 实测：

| | 数量 |
| --- | --- |
| 我们 profile 里的模型 id | 67 |
| OpenRouter 上能对上的 | 40 |
| 完全找不到的 | 27 |
| 对上了但上下文数字不一致的 | 26 |

找不到的那 27 个不是冷门模型，而是**恰好最需要配置的那批**：Kimi Code 的 `k3`、`kimi-for-coding` 全系，MiniMax 的 `-highspeed` 变体，我们自己的 `[1m]` 别名，Gemini 的裸 id，以及 Claude 4.6。这些模型只在各家自己的通道或中转上存在，OpenRouter 根本不路由它们。

对上了也常常不一致，因为 OpenRouter 报的是**它当前选中的上游供应商**的限额，不是厂商口径：

| 模型 | 官方 / 我们 | OpenRouter |
| --- | --- | --- |
| glm-5.3 | 1000000 | 1310720 |
| gpt-5 | 1000000 | 400000 |
| deepseek-chat | 1000000 | 163840 |
| minimax-m3 | 1000000 | 1048576 |
| glm-4.5 | 200000 | 131072 |

还有一件 OpenRouter 看不到的事：**套餐分档**。Kimi 的 k3 上下文取决于订阅等级，任何目录都表达不了这个。

所以顺序是：先查官方文档，官方查不到再用 OpenRouter 当参考，并且在页面上明确标注来源是 provider catalog。这也是「从 OpenRouter catalog 快速匹配」这个入口存在的理由，它是兜底，不是默认。

拉最新 20 条看有没有该补的模型：

```bash
python3 scripts/openrouter_recent_models.py            # 最新 20 条
python3 scripts/openrouter_recent_models.py --limit 50
python3 scripts/openrouter_recent_models.py --missing   # 只看 profile 里还没有的
```

## 已知的坑

**Kimi Code 的 k3 按套餐分档。** 官方写的是 Moderato 限 256K,Allegretto 及以上到 1M。`kimi-code` profile 里 `k3` 记 262144 是保守档,`k3[1m]` 记 1048576 是显式的 1M 入口,`tests/test_provider_profiles.py` 钉住了这两个值。**不要把 `k3` 改成 1M。** 套餐够的用户在页面上自己设成 1M,那是 `model_policy` 层,优先级高于 profile。官方另有一个固定 256K 的 id 叫 `k3-256k`。

**OpenAI 已经下架的模型仍在 profile 里。** `gpt-5`、`gpt-5-pro`、`gpt-5.4`、`gpt-5.4-mini` 不在官方当前列表上了,但很多中转通道还在提供。它们的值保持原样,不要因为官方页面查不到就删。

**Anthropic 的 4.6 系列已是 legacy。** 当前是 Opus 5 / Sonnet 5 / Fable 5.1 / Haiku 4.5。旧模型页仍在,规格照样能查。

**MiMo V2 全系列 2026-06-30 下线。** profile 里的 `mimo-v2-*` 是历史条目。

**「1M」的字面值有两种。** 有的厂商指 1000000,有的指 1048576。以页面上的数字为准;只写了「1M」而没有数字时,沿用该 profile 已有的写法,不要来回改。

**MiniMax 的快照说 M2.7 能读图，官方说不能。** 官方 OpenAI 兼容接口文档写明只有 MiniMax-M3 支持图片输入，其余文本模型都不支持。现在 profile 把这七个显式记为不收图，免得批量对比反复把「能读图」当成待修正项提出来。

**Grok 不记 vision。** x.ai 的模型表只给上下文，没有逐模型写是否收图，所以一个都不记，让它保持未声明。

**上下文写多大不是免费的。** 它参与上下文核算。写成模型的物理上限,对套餐受限的用户会偏乐观;写成保守档,对高档用户会偏小。有分档时记保守档,让用户自己在页面上调高。
