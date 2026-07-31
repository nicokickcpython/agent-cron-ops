# Hermes Cron Ops — 定时任务可靠性插件系列

让 Hermes 的定时任务**失败可知、原因可查、异常可警**，全部通过执行钩子实现——不增加任何额外定时任务，零轮询。

## 为什么需要这个系列

Hermes 默认**没有**"定时任务执行后"的钩子。任务失败（执行错误或推送失败）只会默默写进 jobs.json，没有通知——用户经常是几天后才发现任务一直没跑。

传统解法是再开一个"监控定时任务"定期检查所有任务状态，但这是治标不治本：
- 监控任务本身也可能失败
- 发现问题滞后（取决于检查频率）
- 多一层调度，多一层复杂度

**这个系列直接在任务执行的收尾点挂钩子，失败即时感知，零额外调度。**

## 系列成员

| 插件 | 回答的问题 | Hook 点 | 状态 |
|:-----|:-----------|:--------|:----:|
| [cron-health-hook](cron-health-hook/) | 任务失败了吗？ | `mark_job_run` | ✅ |
| [cron-latency-watch](cron-latency-watch/) | 任务是不是变慢了？ | `run_one_job` | ✅ |
| [cron-error-analyzer](cron-error-analyzer/) | 为什么失败？怎么修？ | `mark_job_run` | ✅ |
| cron-dupe-detector | 任务被重复触发了？ | `run_one_job` | 🚧 开发中 |

## 架构原理

Hermes 的 cron 系统有两个**所有任务必经**的收尾点：

```
任务执行 → run_one_job() ← latency-watch / dupe-detector 在这里挂钩
    ↓
执行完成 → mark_job_run() ← health-hook / error-analyzer 在这里挂钩
    ↓
   jobs.json（状态落盘）
```

插件通过 monkey-patch 包装这两个函数，执行后立即检查——agent 任务和 script 任务、live 投递和 standalone 投递全覆盖。

## 组合使用效果

```
任务失败 → health-hook 报"失败了"
         → error-analyzer 报"因为飞书校验失败，建议..."
任务变慢 → latency-watch 报"本次 5400s，历史平均 120s"
```

## 安装

每个插件独立安装：

```bash
hermes plugins install <owner>/<repo>/cron-health-hook
hermes plugins install <owner>/<repo>/cron-latency-watch
hermes plugins install <owner>/<repo>/cron-error-analyzer
```

## 配置

| 变量 | 所属 | 说明 | 默认 |
|------|:----:|:-----|:----:|
| `CRON_ALERT_CHAT_ID` | 全部 | 告警接收 chat | `FEISHU_HOME_CHANNEL` |
| `CRON_ALERT_COOLDOWN` | health-hook | 同一失败告警冷却（秒） | `3600` |
| `CRON_LATENCY_FACTOR` | latency-watch | 超过均值几倍告警 | `3.0` |
| `CRON_LATENCY_CEILING` | latency-watch | 绝对超时上限（秒） | `3600` |
| `CRON_DUPE_WINDOW` | dupe-detector | 重复判定窗口（秒） | `120` |

告警通过飞书发送，需要 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`（通常已配置）。

## Roadmap

- [x] cron-health-hook — 失败即告警
- [x] cron-latency-watch — 耗时异常检测
- [x] cron-error-analyzer — 错误模式诊断
- [ ] cron-dupe-detector — 重复运行检测
- [ ] 每日执行摘要（成功任务汇总，替代"今日无事"）

## License

MIT
