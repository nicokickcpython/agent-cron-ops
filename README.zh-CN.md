# Agent Cron Ops — 定时任务可靠性套件（跨 Agent）

> [English](README.md) | **中文**

让 **任何 Agent 工具** 的定时任务**失败可知、原因可查、异常可警**——全部通过执行钩子实现，不增加额外定时任务，零轮询。

支持：**Hermes Agent** · **Claude Code** · **OpenCode** · **Codex** · 任意 shell 定时任务

## 为什么需要

定时任务失败（执行错误或推送失败）往往是**静默**的。传统解法是开一个"监控定时任务"定期轮询，但监控任务本身也可能失败、检测滞后、多一层调度复杂度。

本套件挂钩任务生命周期的**收尾点**，失败即时感知。

## 两种集成方式

### 方式一：Hermes 插件（有原生 cron 调度器）

Hermes 内置 cron 调度器，所有任务必经两个收尾点，插件 monkey-patch 挂钩：

```
任务执行 → run_one_job() ← latency-watch / dupe-detector 挂钩
    ↓
执行完成 → mark_job_run() ← health-hook / error-analyzer 挂钩
    ↓
  jobs.json（状态落盘）
```

```bash
hermes plugins install <owner>/agent-cron-ops/cron-health-hook
hermes plugins install <owner>/agent-cron-ops/cron-latency-watch
hermes plugins install <owner>/agent-cron-ops/cron-error-analyzer
```

### 方式二：通用 CLI wrapper（Claude Code / OpenCode / Codex / 任意命令）

Claude Code、OpenCode 等**没有内建 cron 调度器**——它们的"定时任务"由系统 crontab / CI 调用 CLI 非交互模式完成。用 wrapper 包裹即可获得同样的失败告警：

```bash
# 系统 crontab 示例
0 2 * * * /path/to/cron-ops-wrap.sh "daily-backup" -- /path/to/backup.sh
0 3 * * * /path/to/cron-ops-wrap.sh "code-review" -- claude -p "review the repo"
0 4 * * * /path/to/cron-ops-wrap.sh "data-job" -- opencode run "process today's data"
```

```
任务命令执行 → wrapper 记录退出码+耗时 → cron_ops.py check
                                        → 失败 → 立即告警（含诊断+修复建议）
                                        → 成功 → 静默
```

推荐用 pip 安装：

```bash
pip install agent-cron-ops
cron-ops-wrap "daily-backup" -- /path/to/backup.sh
```

## 系列成员

| 组件 | 回答的问题 | 集成方式 | 状态 |
|:-----|:-----------|:--------|:----:|
| [cron-health-hook](cron-health-hook/) | 任务失败了吗？ | Hermes 插件 | ✅ |
| [cron-latency-watch](cron-latency-watch/) | 任务变慢了吗？ | Hermes 插件 | ✅ |
| [cron-error-analyzer](cron-error-analyzer/) | 为什么失败？怎么修？ | Hermes 插件 | ✅ |
| [cli/cron_ops.py](cli/cron_ops.py) | 通用检查+诊断+告警 CLI | 所有 agent | ✅ |
| [cli/cron-ops-wrap.sh](cli/cron-ops-wrap.sh) | 通用命令 wrapper | Claude Code/OpenCode/Codex/任意 | ✅ |
| cron-dupe-detector | 任务被重复触发？ | Hermes 插件 | 🚧 |

## CLI 用法

```bash
# 诊断一段错误文本
cron_ops.py analyze "429 Too Many Requests"
# → 诊断: API 限流 / 配额耗尽
# → 建议: 检查对应 API 的用量面板；降低调用频率或升级配额。

# 检查单个任务状态文件
cron_ops.py check /path/to/status.json

# 批量检查目录下所有状态文件
cron_ops.py check-all ~/.cron-ops/status/
```

## 告警配置（环境变量，所有方式通用）

| 变量 | 说明 | 默认 |
|------|:-----|:----:|
| `CRON_ALERT_CHAT_ID` | 飞书告警 chat_id | `FEISHU_HOME_CHANNEL` |
| `CRON_ALERT_WEBHOOK` | 通用 webhook URL（非飞书通道） | 无 |
| `CRON_ALERT_COOLDOWN` | 同一失败告警冷却（秒） | `3600` |
| `CRON_LATENCY_FACTOR` | 超过历史均值几倍告警 | `3.0` |
| `CRON_LATENCY_CEILING` | 绝对超时上限（秒） | `3600` |
| `CRON_DUPE_WINDOW` | 重复判定窗口（秒） | `120` |
| `CRON_OPS_STATUS_DIR` | wrapper 状态文件目录 | `~/.cron-ops/status/` |

飞书通道需要 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`；其他平台用 `CRON_ALERT_WEBHOOK` 指向任意 webhook（钉钉/企业微信/Slack 机器人地址）。

## 诊断知识库（内置 10 种常见错误模式）

| 错误特征 | 诊断 | 建议 |
|:---------|:-----|:-----|
| `429 / rate limit` | API 限流 | 查用量面板，降频或升级配额 |
| `timeout` | 网络/API 超时 | 目标不可达，重试或加超时 |
| `99992402 field validation` | 飞书消息校验失败 | 内容超长/特殊字符 |
| `access denied / 99991672` | 权限不足 | 到开放平台补 scope |
| `401 / invalid_api_key` | API Key 无效 | 检查 .env，重新生成 |
| `context length / token` | 上下文超限 | 压缩 prompt，减少注入 |
| `script not found` | 脚本路径错误 | 检查 script 字段 |
| `empty response` | 模型空响应 | 重试，查 API 状态 |
| `ImportError` | 依赖缺失 | 安装对应包 |
| `OOM / killed` | 内存不足 | 减少数据量，查容器限制 |

## Roadmap

- [x] Hermes 插件 ×3（health-hook / latency-watch / error-analyzer）
- [x] 通用 CLI（cron_ops.py check/check-all/analyze）
- [x] 通用 wrapper（cron-ops-wrap.sh）
- [x] pip 包（`agent-cron-ops` wheel）
- [ ] cron-dupe-detector
- [ ] 每日执行摘要
- [ ] Claude Code hooks 原生适配（settings.json hooks）
- [ ] OpenCode plugin 原生适配

## License

MIT
