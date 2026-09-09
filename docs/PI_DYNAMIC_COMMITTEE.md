# Pi Dynamic Committee

For role-aware design/product/development/testing deliberation, use the opt-in [Pi Court](PI_COURT.md). For writable delegation, use the separate [Pi Executor](PI_EXECUTOR.md). This committee remains read-only by design.

## 结论

MMS 提供一个独立、opt-in 的 Pi committee sidecar。它不经过 OpenCode，不注册到 `mms` 默认 launcher，也不读写默认全局配置。Codex、Claude 或普通脚本都可以把它当作同一个 JSON-in/JSON-out worker pool 使用。

成员没有固定模型身份。每次 mission 创建 `member-01`、`member-02` 等临时成员，再从显式选定的 MMS latest-approved bundle 中动态绑定 model、provider、URL 和 API key。

默认 `balanced` profile 面向普通 review：它从非 Gemini 的可用 family 中用 mission seed 可复现地选择不同 family，并在每个 family 的 primary / cost-aware secondary 之间选择；未选中的同家族模型会作为失败后的 model backup。当前 cost-aware secondary 偏好为 `qwen3.6-plus`、`glm-5.1`、`kimi-for-coding`，明确不使用 `kimi-for-coding-highspeed`。高风险 review 可显式传 `--selection-profile frontier`，从 `MiniMax / GPT / Kimi / Qwen / DeepSeek / GLM` 各选择当前 champion。`model-policy` 的 visible/hide 规则仍然是硬约束。

## 安全边界

- 必须显式传入 `--config-root`；不会 fallback 到 `~/.config/mms`。
- 先校验 latest-approved manifest 和所有 bundle file hashes，再读取 Router。
- 不读取 SQLite、legacy route files 或 global OAuth/account state。
- 每个 worker 使用临时 `HOME`、`XDG_*`、Pi agent/session 目录；任务结束自动删除。
- API key 通过临时 environment variable 交给 Pi，`models.json` 只保存 `$ENV_NAME` 引用。
- Pi transport 只从 runtime 显式声明的 `protocols` 导出；填写 OpenAI URL 不会虚构 `Responses` 能力。GPT 在声明 `responses` 时才使用 `openai-responses`，否则优先已声明的 `openai_chat_completions`。
- 默认工具只有 `read,grep,find,ls`，并关闭 session、context files、extensions、skills、prompt templates 和 themes。
- Pi 通过仓库已有的 `scripts/pi-cli-wrapper.sh` 启动；首次运行只会把 npm package cache 放到本仓库 `.ai/cache/pi-npx`，不会做 global install。冷缓存下 wrapper 会先用 repo-local install lock 做一次轻量 prewarm，避免多 worker 同时让 `npx` 填充同一个 shared cache。
- 非 GPT member 只接受 provider id 含 `tokyo` 的 route；缺少可用 Tokyo route 或 Tokyo route 被 Pi runtime 拦截时 fail closed，不会改走 Tencent 或 direct。GPT 保留 bundle 中的 OpenAI route chain，frontier 默认固定为 `gpt-5.5`。
- effort 不再统一关闭。committee 从 Pi 生成的 `thinkingLevelMap` 选择最高 source-backed level：`max > xhigh > high > medium > low > minimal`；例如 `k3` 使用 `max`、`gpt-5.5` 使用 `xhigh`。没有 map 时省略 `--thinking`，不伪造 level，也不传 `off`。

## Worker watchdog

Pi worker 是 agentic session，不是一次短 completion。实测中，读取 diff 和多个文件后再输出结构化评审，单个正常调用可以超过 110s；因此不能把短暂无 stdout 当成 provider 故障，也不能因为一批 `anthropic_messages` route 同时命中旧的 180s 上限，就把协议本身判坏。

当前默认值按“慢但健康”校准：

- member wall timeout：`900s`；同一 member 的 route fallback 共享这段预算。这个值来自重型 agentic review 的实测校准，不代表每个模型都能在 900s 内完成。
- Kimi route-attempt timeout：默认每条 Tokyo route 最多 `300s`，并按剩余 attempt 数公平收窄；Tokyo 超时后只会尝试 bundle 中另一条 Tokyo route，不会切到 Tencent/direct。`--kimi-attempt-timeout 0` 可在明确的历史复现实验中关闭该 cap。
- no-output idle timeout：`300s`。Pi JSON event 或 stderr 任意新字节都会刷新 activity；短于这个阈值的静默 provider call 不会被误杀。
- retained stream tail / single event：`2 MiB`。累计的正常 newline-delimited Pi events 可以超过此值，runtime 只保留 bounded tail；只有单个无法分帧的 event/line 超限才返回 `output_limit`。这避免 `message_update` 的增长快照把健康 worker 误判为输出洪水。
- exact consecutive repeated events：`32`；达到后返回 `repetition_limit`。
- committee timeout：默认 `0=auto`，实际值为 `member wall × concurrency waves + 60s`。默认 7 member、并发 4 时是 `1860s`，确保第二波仍有完整 member budget。
- quorum：默认 `0=disabled`。只有调用方显式设置 `--quorum-successes N` 时，达到 N 个成功并经过 `--quorum-grace` 后才取消剩余 worker；默认不会把一个成功意见当作委员会结论。

每个 Pi 子进程都在独立 POSIX process group 中运行。watchdog 先向整个 group 发 `SIGTERM`，grace 结束后仍在原 group 的 descendant 会收到 `SIGKILL`；Pi 自身的 SIGTERM handler 也会清理它登记的 detached children。主动 `setsid()` 逃离原 group 的任意第三方进程不属于 OS process-group 保证范围。stream reader 与 supervisor 之间使用 bounded queue，极端输出会 backpressure 到 pipe，不会形成 unbounded Python queue。结果和 Parent packet 会保留 `terminal_reason`、elapsed、stdout/stderr bytes、repeat peak、是否 terminate/force-kill，以及 committee stop reason。即使 global deadline 或 opt-in quorum 触发，也会返回所有已完成结果和被取消 member 的明确状态。

同一 member 的多个 route attempt 共享 wall budget，但不再用 `max(1, remaining)` 强行制造一秒 fallback。Kimi 的每个 Tokyo attempt 还受独立 cap 约束，第一条 route 的 `wall_timeout` 不再等同于 member budget 耗尽。剩余预算不足一秒时，未启动的 route 会记录为 `status=skipped`、`terminal_reason=no_budget_remaining`、`started=false`、`budget_seconds=0`；它不会被标成 provider `wall_timeout`，也不会进入 `fallback_members`。真正启动的 attempt 会记录 `started=true` 和实际分配的 `budget_seconds`。

timestamped latest-approved bundle 默认必须在 `30` 天 freshness window 内。校验顺序是 hash verification → bundle age gate → model selection；旧 root 中 hash 正确但已经漂移的 `kimi-k2.x` 不会再进入 provider dispatch。`--max-bundle-age-days 0` 只用于调用方明确要求的历史 replay。public plan 会保留 resolved `config_root`、manifest path、revision、age 和 freshness status，方便区分 Host 选错 root 与 provider/model 故障。

可按单次 mission 调整，而不写任何全局配置：

```bash
python3 scripts/pi_committee_parent.py \
  --config-root /explicit/path/to/mms-config-root \
  --task-file /path/to/mission.md \
  --cwd /path/to/target-repo \
  --timeout 900 \
  --kimi-attempt-timeout 300 \
  --max-bundle-age-days 30 \
  --idle-timeout 300 \
  --max-output-bytes 2097152 \
  --max-repeated-events 32 \
  --committee-timeout 0
```

不建议仅因某个 protocol 较慢就缩短它的 timeout。应先看 member `watchdog` 和 attempt `cache_transport_evidence`，区分 `request_error`、真实 idle、wall budget 不足和输出异常。

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

- GPT 固定选择 `gpt-5.5`；缺少该 model 时 frontier fail closed，不会静默升级到其他 GPT 版本。MiniMax、Qwen、DeepSeek、GLM：先比较可识别的 model version，再比较同版本 variant。Qwen 默认 `max > plus > flash`；DeepSeek 默认 `flash > pro`。
- Kimi：优先 fresh bundle 中最新版本，例如真实模型 id `k3` 会排在 `kimi-k2.8-code` / `kimi-k2.7-code` 前；同版本再优先 coding/code 系列，不把旧 `kimi-for-coding` alias 固定成永久 champion。所有非 GPT family 的 route chain 只保留 Tokyo route，并限制 Kimi 单 route 不能吞完整个 member budget。Gemini 优先滚动的 `flash-agent(high)` channel。
- 同级时再参考 policy favorite/tier、context window、可用 route 数量。
- unavailable、policy-hidden、非对话模型或无法生成 Pi route 的模型会 fail closed，不会偷用 global OAuth/default account。

这套顺序来自一次真实同任务 A/B 基线，只用于设置初始默认值。单次任务中的漏检或 JSON 格式错误不会永久降级某个模型；长期自适应需要累计多任务 health evidence 后再做。

## Parent 集成

Codex 或 Claude 可以显式调用 shared `$pi-committee` skill source；仓库内 `assets/session-assets/skills/pi-committee/` 保留可发布镜像，Codex/Claude discovery entry 使用 symlink 指向 canonical shared skill。`allow_implicit_invocation` 仍为 `false`，Parent 必须显式触发。该安装方式不修改 preferences、launcher、OpenCode 或真实 MMS config。

Parent adapter 可以直接派发任务并输出 `mms.pi_committee.parent_packet.v1`：

```bash
python3 scripts/pi_committee_parent.py \
  --config-root /explicit/path/to/mms-config-root \
  --task-file /path/to/mission.md \
  --cwd /path/to/target-repo \
  --output /path/to/parent-packet.json
```

也可以把已有 raw result 转成 parent packet，不发起 provider call：

```bash
python3 scripts/pi_committee_parent.py \
  --result /path/to/pi-committee-result.json \
  --output /path/to/parent-packet.json
```

Parent packet 保留完整 public plan、所有原始 member response、flattened evidence index、route health、failure/raw/fallback 状态和 synthesis contract。`ready_for_synthesis` 不是“有一个成功就算 ready”：默认要求成功数达到 planned member 的 `50%`（向上取整），且多成员委员会至少需要两个成功；因此 `7` 人委员会至少 `4` 人成功，`1/7` 会明确返回 `insufficient_coverage`。Parent 需要完成三件事：

1. 生成 mission text 并调用 sidecar。
2. 完整读取 parent packet，包括失败和 raw response。
3. 仅在 `ready_for_synthesis=true` 时，根据 `synthesis_contract` 输出 committee health、共识、分歧、独立发现、风险、建议和 confidence；否则只报告覆盖不足与失败证据。

Adapter 不用 string similarity 假装推断 semantic consensus，也不会调用第八个 synthesis model。最终判断始终属于当前 Codex/Claude parent，因此可以随时更换 parent，worker runtime 不需要改名或重配。

每个成功结果都包含 `cache_transport_evidence.v1`；发生 route fallback 时，每次 attempt 也保留独立 evidence。结果不会包含 API key。
