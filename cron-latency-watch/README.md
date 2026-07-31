# cron-latency-watch

**Cron 任务耗时监控** — 任务执行异常缓慢时自动告警，无需独立监控任务。

## 解决的问题

定时任务执行变慢（模型 API 变慢、外部数据源超时、脚本死循环）往往被忽略——任务"跑完了"，只是慢，不会报错。用户直到几天后才发现每天的备份任务从 2 分钟涨到了 2 小时。

## 方案

这个插件包装 `cron.scheduler.run_one_job` —— 每个定时任务（agent 任务和 script 任务）的**统一执行入口**。记录每次执行的墙钟耗时，与任务自身的历史均值对比：

```
任务执行 → run_one_job() → 插件记录耗时 → 超过历史均值 × 3 → 立即告警
                                        → 正常 → 静默
```

**自适应基线**：每个任务用自己的历史均值做基线，不看全局——5 秒的任务和 5 分钟的任务用同一套逻辑，互不干扰。

## 安装

```bash
hermes plugins install <owner>/<repo>/cron-latency-watch
hermes plugins enable cron-latency-watch
```

## 配置（.env）

| 变量 | 说明 | 默认 |
|------|------|------|
| `CRON_LATENCY_FACTOR` | 超过历史均值几倍时告警 | `3.0` |
| `CRON_LATENCY_MIN_SEC` | 只评估历史均值 ≥ 此秒数的任务 | `10` |
| `CRON_LATENCY_CEILING` | 绝对上限秒数，超过必告警 | `3600` |

## 告警示例

```
🐌 Cron 任务执行异常缓慢: 每日数据备份
  任务: 每日数据备份
  Job ID: abc123def456
  本次耗时: 5400s
  历史平均: 120s
  触发阈值: 360s
  可能原因：模型 API 变慢、外部数据源超时、循环未收敛。
```

## License

MIT
