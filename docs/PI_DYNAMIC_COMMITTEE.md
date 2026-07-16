# Pi Dynamic Committee

## 结论

MMS 提供一个独立、opt-in 的 Pi committee sidecar。它不经过 OpenCode，不注册到 `mms` 默认 launcher，也不读写默认全局配置。Codex、Claude 或普通脚本都可以把它当作同一个 JSON-in/JSON-out worker pool 使用。

成员没有固定模型身份。每次 mission 创建 `member-01`、`member-02` 等临时成员，再从显式选定的 MMS latest-approved bundle 中动态绑定 model、provider、URL 和 API key。

默认 `frontier` profile 会在每次 mission 启动时，从当前 bundle 为以下家族各选一个 champion：`MiniMax / GPT / Kimi / Gemini / Qwen / DeepSeek / GLM`。它保存的是选择规则，不是七个命名 agent；bundle 中出现更新版本后会重新计算。`model-policy` 的 visible/hide 规则仍然是硬约束。

## 安全边界

- 必须显式传入 `--config-root`；不会 fallback 到 `~/.config/mms`。
- 先校验 latest-approved manifest 和所有 bundle file hashes，再读取 Router。
- 不读取 SQLite、legacy route files 或 global OAuth/account state。
- 每个 worker 使用临时 `HOME`、`XDG_*`、Pi agent/session 目录；任务结束自动删除。
- API key 通过临时 environment variable 交给 Pi，`models.json` 只保存 `$ENV_NAME` 引用。
- 默认工具只有 `read,grep,find,ls`，并关闭 session、context files、extensions、skills、prompt templates 和 themes。
- Pi 通过仓库已有的 `scripts/pi-cli-wrapper.sh` 启动；首次运行只会把 npm package cache 放到本仓库 `.ai/cache/pi-npx`，不会做 global install。

## 使用方式

先用 dry-run 查看本次动态成员和 route binding，不发起模型请求：

```bash
python3 scripts/pi_committee.py \
  --config-root /explicit/path/to/mms-config-root \
  --task "评估当前实现的架构风险并给出证据" \
  --cwd /path/to/target-repo \
  --dry-run
```

不传 `--count` 时，默认执行七个 frontier family champions：

```bash
python3 scripts/pi_committee.py \
  --config-root /explicit/path/to/mms-config-root \
  --task-file /path/to/mission.md \
  --cwd /path/to/target-repo \
  --output /path/to/pi-committee-result.json
```

当前 frontier 家族顺序可以替换，也可以只给这一次临时加家族或模型：

```bash
python3 scripts/pi_committee.py \
  --config-root /explicit/path/to/mms-config-root \
  --task "增加 Claude，并额外复核 Qwen Plus" \
  --cwd /path/to/target-repo \
  --add-family Claude \
  --add-model qwen3.7-plus
```

`--add-family` 追加该家族的当前 champion；`--add-model` 追加一个 exact model。两者都只影响本次 mission。若想改成通用的能力/家族多样性选择，可用 `--selection-profile balanced --count 4 --min-families 3`。

如需人工指定本次 lineup，可以重复传 `--model`。这只是 mission-level binding，不会创建或保存 `committee-glm` 一类永久 agent：

```bash
python3 scripts/pi_committee.py \
  --config-root /explicit/path/to/mms-config-root \
  --task "独立复核这份方案" \
  --cwd /path/to/target-repo \
  --model qwen3.7-plus \
  --model claude-sonnet-4-6
```

`--model` 是完整 lineup override，不能和 `--add-model` 混用。

## Frontier 选择规则

- MiniMax、GPT、Qwen、DeepSeek、GLM：先比较可识别的 model version，再比较同版本 variant。Qwen 默认 `max > plus > flash`；DeepSeek 默认 `flash > pro`。
- Kimi：优先滚动的 `kimi-for-coding` channel；Gemini 优先滚动的 `flash-agent(high)` channel。
- 同级时再参考 policy favorite/tier、context window、可用 route 数量。
- unavailable、policy-hidden、非对话模型或无法生成 Pi route 的模型会 fail closed，不会偷用 global OAuth/default account。

这套顺序来自一次真实同任务 A/B 基线，只用于设置初始默认值。单次任务中的漏检或 JSON 格式错误不会永久降级某个模型；长期自适应需要累计多任务 health evidence 后再做。

## Parent 集成

Parent 只需要完成两件事：

1. 生成 mission text 并调用 sidecar。
2. 读取 `mms.pi_committee.result.v1`，根据各成员的 `verdict/findings/evidence` 做最终 synthesis。

Sidecar 本身不绑定 Codex 或 Claude，也不负责替 parent 做最终决策。这样可以随时更换 parent，worker runtime 不需要改名或重配。

每个成功结果都包含 `cache_transport_evidence.v1`；发生 route fallback 时，每次 attempt 也保留独立 evidence。结果不会包含 API key。
