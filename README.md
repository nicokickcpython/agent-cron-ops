# CronWatch — 定时任务不沉默

> **English** | [中文](README.zh-CN.md)

<div align="center">

[![GitHub stars](https://img.shields.io/github/stars/nicokickcpython/cronwatch?style=for-the-badge&logo=github&color=black)](https://github.com/nicokickcpython/cronwatch)
[![GitHub forks](https://img.shields.io/github/forks/nicokickcpython/cronwatch?style=for-the-badge&logo=github&color=black)](https://github.com/nicokickcpython/cronwatch)
[![GitHub license](https://img.shields.io/github/license/nicokickcpython/cronwatch?style=for-the-badge&color=blue)](LICENSE)
[![PyPI version](https://img.shields.io/pypi/v/cronwatch?style=for-the-badge&logo=pypi&logoColor=white&color=3776AB)](https://pypi.org/project/cronwatch/)
[![Python versions](https://img.shields.io/pypi/pyversions/cronwatch?style=for-the-badge&logo=python&logoColor=white&color=3776AB)](https://pypi.org/project/cronwatch/)
[![CI](https://img.shields.io/github/actions/workflow/status/nicokickcpython/cronwatch/ci.yml?style=for-the-badge&logo=githubactions&logoColor=white&label=CI&color=green)](https://github.com/nicokickcpython/cronwatch/actions)
[![Tests](https://img.shields.io/badge/tests-20%20passed-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](tests/)
[![Last commit](https://img.shields.io/github/last-commit/nicokickcpython/cronwatch?style=for-the-badge&color=orange)](https://github.com/nicokickcpython/cronwatch/commits)
[![skills.sh](https://skills.sh/b/nicokickcpython/cronwatch)](https://skills.sh/nicokickcpython/cronwatch)

</div>

**Cron 任务失败总是悄悄发生？CronWatch 让每个定时任务失败可知、原因可查、异常可警。** 轻量、零配置、安装即用，支持 Hermes / Claude Code / OpenCode / Codex 和任意 CLI 命令——无需额外监控任务，不增加轮询负担。

```
任务失败 → 秒级告警（飞书/钉钉/企业微信/任意 Webhook）
任务变慢 → 自适应基线检测，超常即报
失败原因 → 内置 10 类错误诊断，附修复建议
```

## Why / 为什么用

Scheduled job failures (execution error or delivery error) are usually **silent** — no notification, discovered days later. The traditional fix — a separate "health-check cron job" that polls job status — is fragile: the monitor itself can fail, detection lags behind the check interval, and it adds another scheduling layer.

CronWatch hooks the **post-run choke points** of the job lifecycle, so failures are detected the moment they happen.

## 快速开始 / Quick Start

```bash
# 方式一：pip 安装（推荐）
pip install cronwatch
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

## Components / 组件

| Component | Answers | Integration | Status |
|:----------|:--------|:------------|:------:|
| [cron-health-hook](cron-health-hook/) | Did the job fail? | Hermes plugin | ✅ |
| [cron-latency-watch](cron-latency-watch/) | Is the job getting slow? | Hermes plugin | ✅ |
| [cron-error-analyzer](cron-error-analyzer/) | Why did it fail? How to fix? | Hermes plugin | ✅ |
| `cron-ops` CLI | check / diagnose / alert | all agents | ✅ |
| `cron-ops-wrap` | universal command wrapper | Claude Code/OpenCode/Codex/any | ✅ |
| cron-dupe-detector | Was the job fired twice? | Hermes plugin | 🚧 |

## CLI Usage / CLI 用法

```bash
# diagnose an error string / 诊断错误
cron-ops analyze "429 Too Many Requests"
# → diagnosis: API rate limit / quota exhausted

# check one job status file / 检查任务状态
cron-ops check /path/to/status.json

# check all status files / 批量检查
cron-ops check-all ~/.cron-ops/status/
```

## Alert Configuration / 告警配置

| Var | Description | Default |
|-----|:------------|:--------|
| `CRON_ALERT_CHAT_ID` | Feishu chat_id for alerts | `FEISHU_HOME_CHANNEL` |
| `CRON_ALERT_WEBHOOK` | Generic webhook URL (DingTalk/WeCom/Slack...) | none |
| `CRON_ALERT_COOLDOWN` | Cooldown between same-failure alerts (s) | `3600` |
| `CRON_LATENCY_FACTOR` | Alert when duration > factor × rolling avg | `3.0` |
| `CRON_LATENCY_CEILING` | Absolute ceiling seconds | `3600` |
| `CRON_DUPE_WINDOW` | Duplicate-fire window (s) | `120` |
| `CRON_OPS_STATUS_DIR` | Status file dir for wrapper | `~/.cron-ops/status/` |

## Diagnosis Knowledge Base / 诊断知识库

| Error signature | Diagnosis |
|:----------------|:----------|
| `429 / rate limit` | API rate limited |
| `timeout` | network/API timeout |
| `99992402 field validation` | Feishu msg validation failed |
| `access denied / 99991672` | missing permission scope |
| `401 / invalid_api_key` | API key invalid |
| `context length / token` | context/token exceeded |
| `script not found` | script path wrong |
| `empty response` | model empty response |
| `ImportError` | missing dependency |
| `OOM / killed` | out of memory |

## Roadmap

- [x] Hermes plugins ×3 (health-hook / latency-watch / error-analyzer)
- [x] Universal CLI (check / check-all / analyze)
- [x] Universal wrapper
- [x] pip package
- [x] 20 automated test cases
- [ ] cron-dupe-detector
- [ ] Daily execution digest
- [ ] Claude Code hooks native adapter
- [ ] OpenCode plugin native adapter

## License

MIT
