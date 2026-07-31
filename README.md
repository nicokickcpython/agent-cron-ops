# cron-health-hook

**Cron 任务健康钩子** — 每个定时任务执行完自动检查结果，失败立即告警到飞书。

## 解决的问题

Hermes 默认**没有**"定时任务执行后"的钩子。任务失败（执行错误或推送失败）只会默默写进 jobs.json，没有通知——用户经常是几天后才发现任务一直没跑。

传统解法是再开一个"监控定时任务"定期检查所有任务状态，但这是治标不治本：
- 监控任务本身也可能失败
- 发现问题滞后（取决于检查频率）
- 多一层调度，多一层复杂度

## 方案

这个插件 monkey-patch `cron.jobs.mark_job_run` —— 这是**每个**定时任务执行完毕后的统一收尾函数（agent 任务和 script 任务、live 投递和 standalone 投递都会经过它）。包装它之后：

```
任务执行完 → mark_job_run() → 插件检查 success/delivery_error
                              → 失败 → 立即发飞书告警（含任务名/错误/时间）
                              → 成功 → 静默
```

**零额外定时任务，零轮询，失败即时感知。**

## 安装

```bash
# 从 Git 仓库安装
hermes plugins install <owner>/<repo>

# 启用
hermes plugins enable cron-health-hook
```

## 配置

在 `.env` 中设置（可选，默认已用飞书现有配置）：

| 变量 | 说明 | 默认 |
|------|------|------|
| `CRON_ALERT_CHAT_ID` | 接收告警的飞书 chat_id | `FEISHU_HOME_CHANNEL` |
| `CRON_ALERT_COOLDOWN` | 同一失败重复告警的冷却秒数 | `3600` |

需要 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`（通常已配置）。

## 告警示例

失败时发送红色卡片到飞书：

```
🔴 Cron 任务执行失败: 海外产品调研每日报告
  任务: 海外产品调研每日报告
  Job ID: da318b987a7e
  时间: 2026-07-31 12:27:37
  错误: ...
  请检查日志: /opt/data/logs/agent.log
```

## 工作原理

```python
# 核心：包装 mark_job_run
original = cron_jobs.mark_job_run
def _hooked(job_id, success, error=None, delivery_error=None):
    result = original(job_id, success, error=error, delivery_error=delivery_error)
    _check_and_alert(job_id, success, error=error, delivery_error=delivery_error)
    return result
cron_jobs.mark_job_run = _hooked
```

- 失败类型自动区分：执行失败 / 推送失败 / 两者都失败
- 冷却机制防止同一错误刷屏
- 插件在 gateway 启动时加载，`on_session_start` 兜底重试

## License

MIT
