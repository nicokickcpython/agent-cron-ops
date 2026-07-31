# CronWatch — 定时任务不沉默

> [English](README.md) | **中文**

<div align="center">

[![GitHub stars](https://img.shields.io/github/stars/nicokickcpython/cronwatch?style=for-the-badge&logo=github&color=black)](https://github.com/nicokickcpython/cronwatch)
[![GitHub forks](https://img.shields.io/github/forks/nicokickcpython/cronwatch?style=for-the-badge&logo=github&color=black)](https://github.com/nicokickcpython/cronwatch)
[![GitHub license](https://img.shields.io/github/license/nicokickcpython/cronwatch?style=for-the-badge&color=blue)](LICENSE)
[![PyPI version](https://img.shields.io/pypi/v/cron-ops?style=for-the-badge&logo=pypi&logoColor=white&color=3776AB)](https://pypi.org/project/cron-ops/)
[![Python versions](https://img.shields.io/pypi/pyversions/cron-ops?style=for-the-badge&logo=python&logoColor=white&color=3776AB)](https://pypi.org/project/cron-ops/)
[![CI](https://img.shields.io/github/actions/workflow/status/nicokickcpython/cronwatch/ci.yml?style=for-the-badge&logo=githubactions&logoColor=white&label=CI&color=green)](https://github.com/nicokickcpython/cronwatch/actions)
[![Tests](https://img.shields.io/badge/tests-20%20passed-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](tests/)
[![Last commit](https://img.shields.io/github/last-commit/nicokickcpython/cronwatch?style=for-the-badge&color=orange)](https://github.com/nicokickcpython/cronwatch/commits)

</div>

**Cron 任务失败总是悄悄发生？CronWatch 让每个定时任务失败可知、原因可查、异常可警。** 轻量、零配置、安装即用，支持 Hermes / Claude Code / OpenCode / Codex 和任意 CLI 命令——无需额外监控任务，不增加轮询负担。

```
任务失败 → 秒级告警（飞书/钉钉/企业微信/任意 Webhook）
任务变慢 → 自适应基线检测，超常即报
失败原因 → 内置 10 类错误诊断，附修复建议
```

## 为什么用

定时任务失败（执行错误或推送失败）往往是**静默**的。传统解法是开一个"监控定时任务"定期轮询，但监控任务本身也可能失败、检测滞后、多一层调度复杂度。

CronWatch 挂钩任务生命周期的**收尾点**，失败即时感知。

## 快速开始

```bash
# 方式一：pip 安装（推荐）
pip install cron-ops
cron-ops-wrap "daily-backup" -- /path/to/backup.sh

# 方式二：Hermes 插件
hermes plugins install nicokickcpython/cronwatch/cron-health-hook

# 方式三：无依赖 wrapper（零安装）
/path/to/cron-ops-wrap.sh "daily-backup" -- /path/to/backup.sh
```

系统 crontab 用法：

```bash
0 2 * * * cron-ops-wrap "daily-backup" -- /path/to/backup.sh
0 3 * * * cron-ops-wrap "code-review" -- claude -p "review the repo"
0 4 * * * cron-ops-wrap "data-job" -- opencode run "process today's data"
```

## 系列成员

| 组件 | 回答的问题 | 集成方式 | 状态 |
|:-----|:-----------|:--------|:----:|
| [cron-health-hook](cron-health-hook/) | 任务失败了吗？ | Hermes 插件 | ✅ |
| [cron-latency-watch](cron-latency-watch/) | 任务变慢了吗？ | Hermes 插件 | ✅ |
| [cron-error-analyzer](cron-error-analyzer/) | 为什么失败？怎么修？ | Hermes 插件 | ✅ |
| `cron-ops` CLI | 检查/诊断/告警 | 所有 agent | ✅ |
| `cron-ops-wrap` | 通用命令 wrapper | Claude Code/OpenCode/Codex/任意 | ✅ |
| cron-dupe-detector | 任务被重复触发？ | Hermes 插件 | 🚧 |

## CLI 用法

```bash
# 诊断错误
cron-ops analyze "429 Too Many Requests"
# → 诊断: API 限流 / 配额耗尽

# 检查任务状态
cron-ops check /path/to/status.json

# 批量检查
cron-ops check-all ~/.cron-ops/status/
```

## 告警配置

| 变量 | 说明 | 默认 |
|------|:-----|:----:|
| `CRON_ALERT_CHAT_ID` | 飞书告警 chat_id | `FEISHU_HOME_CHANNEL` |
| `CRON_ALERT_WEBHOOK` | 通用 webhook（钉钉/企业微信/Slack） | 无 |
| `CRON_ALERT_COOLDOWN` | 同一失败告警冷却（秒） | `3600` |
| `CRON_LATENCY_FACTOR` | 超过历史均值几倍告警 | `3.0` |
| `CRON_LATENCY_CEILING` | 绝对超时上限（秒） | `3600` |
| `CRON_DUPE_WINDOW` | 重复判定窗口（秒） | `120` |
| `CRON_OPS_STATUS_DIR` | wrapper 状态文件目录 | `~/.cron-ops/status/` |

## 诊断知识库（内置 10 类错误模式）

| 错误特征 | 诊断 |
|:---------|:-----|
| `429 / rate limit` | API 限流 |
| `timeout` | 网络/API 超时 |
| `99992402 field validation` | 飞书消息校验失败 |
| `access denied / 99991672` | 权限不足 |
| `401 / invalid_api_key` | API Key 无效 |
| `context length / token` | 上下文超限 |
| `script not found` | 脚本路径错误 |
| `empty response` | 模型空响应 |
| `ImportError` | 依赖缺失 |
| `OOM / killed` | 内存不足 |

## Roadmap

- [x] Hermes 插件 ×3（health-hook / latency-watch / error-analyzer）
- [x] 通用 CLI + wrapper
- [x] pip 包
- [x] 20 个自动化测试用例
- [ ] cron-dupe-detector
- [ ] 每日执行摘要
- [ ] Claude Code hooks 原生适配
- [ ] OpenCode plugin 原生适配

## License

MIT
