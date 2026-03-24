# MMS Model Speed Stats

## 存储位置

MMS 自己把测速结果写到：

```text
~/.config/mms/speed-stats.json
```

外部工具如果要消费这份数据，应该读取这份文件，而不是要求 MMS 反向写入别的项目目录。

## 当前记录内容

当前文件同时包含两层视图：

- 顶层 `model -> stats`：兼容旧读取方的聚合视图
- `_providers` / `_scoped_models`：新的 provider 作用域视图，避免同名模型串线

推荐新接入方优先读取 `_scoped_models` 或 `_providers`。

```json
{
  "_schema_version": 2,
  "_scoped_models": {
    "provider-3f1c2a9b8d11::claude-sonnet-4-6": {
      "provider_key": "provider-3f1c2a9b8d11",
      "provider_id": "xin",
      "provider_name": "Xin",
      "model": "claude-sonnet-4-6",
      "ttfb_avg_ms": 300.0,
      "tps_avg": 110.0,
      "samples": 2,
      "tps_samples": 2,
      "warming_up": true,
      "last_updated": "2026-03-24T09:10:29.859407+00:00"
    }
  },
  "claude-sonnet-4-6": {
    "ttfb_avg_ms": 300.0,
    "tps_avg": 110.0,
    "samples": 2,
    "tps_samples": 2,
    "warming_up": true,
    "last_updated": "2026-03-24T09:10:29.859407+00:00"
  }
}
```

字段含义：

- `ttfb_avg_ms`: Time To First Byte 的滚动均值，单位毫秒
- `tps_avg`: Tokens Per Second 的滚动均值，只在拿到可靠 output tokens 时更新
- `samples`: 成功请求样本数
- `tps_samples`: 成功拿到 TPS 的样本数
- `warming_up`: 预热阶段标记，前 5 次样本内为 `true`
- `last_updated`: 最近一次成功更新的时间

新增字段含义：

- `_schema_version`: 当前文件结构版本
- `_providers`: 按 provider 作用域分组的完整统计
- `_scoped_models`: 扁平化后的 provider+model 视图，适合 Hive 这类外部消费者直接读取
- `provider_key`: provider 稳定标识，优先按 endpoint 指纹生成；只改 provider 名称时不变

## 更新策略

- 前 5 次样本使用 simple average，避免冷启动单点把 EMA 拉偏
- 第 6 次起切到 EMA，`alpha = 0.2`
- 写盘使用进程内锁 + 文件锁 + atomic rename，避免并发覆盖

## model key 语义

测速按 **实际被 bridge 发往上游的 model id** 聚合，而不是 slot 占位名。

也就是说：

- `claude-sonnet-4-6` / `claude-opus-4-6` 这种真实模型名会被直接统计
- 负载均衡模式下，会按最终落到的 `light / medium / heavy` 实际 model 分别累计
- 不使用 `claude-* slot` 这类占位值作为速度 key

## provider 作用域语义

为了解决不同 provider 下同名模型串线的问题，新结构按 provider 作用域隔离：

- 如果两个 provider 的 endpoint 不同，即使模型名相同，也会分别统计
- 如果只是把 provider 改名，但底层 endpoint 没变，会继续落到同一个 `provider_key`
- 如果 endpoint 变了，会生成新的 `provider_key`，避免把不同上游的测速混在一起

对 Hive 这类外部消费者的建议：

- 新代码优先读取 `_scoped_models`
- 如需分组展示，可再按 `provider_key` / `provider_id` 聚合
- 顶层按模型聚合的视图仅作兼容保留，不建议继续作为主数据源

## 已知限制

- 这是 bridge 层 best-effort 统计，不保证覆盖所有 CLI 直连路径
- `TPS` 只在 bridge 能拿到可靠 output tokens 时更新；拿不到时只更新 `TTFB`
- `last_updated` 超过 7 天的记录可视为 stale；当前由读取侧决定是否忽略

## 预热命令

现在可以直接用：

```bash
mms warm
```

交互流程会先选通道，再选预热方式：

- 最近使用模型（推荐）
- 手动选择模型
- 全部模型（不推荐）

说明：

- 预热是为了提前打通上游链路、连接池或 provider 冷启动，不等于测速
- 预热会发送真实请求，因此会消耗额度
- 不建议长期对所有模型做全量预热，优先预热最近常用模型即可
