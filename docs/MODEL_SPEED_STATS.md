# MMS Model Speed Stats

## 存储位置

MMS 自己把测速结果写到：

```text
~/.config/mms/speed-stats.json
```

外部工具如果要消费这份数据，应该读取这份文件，而不是要求 MMS 反向写入别的项目目录。

## 当前记录内容

每个 model 维护一条滚动统计：

```json
{
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

## 已知限制

- 这是 bridge 层 best-effort 统计，不保证覆盖所有 CLI 直连路径
- `TPS` 只在 bridge 能拿到可靠 output tokens 时更新；拿不到时只更新 `TTFB`
- `last_updated` 超过 7 天的记录可视为 stale；当前由读取侧决定是否忽略
