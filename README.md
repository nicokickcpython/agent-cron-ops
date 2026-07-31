# Agent Cron Ops — Cron Job Reliability Toolkit (Cross-Agent)

> **English** | [中文](README.zh-CN.md)

Make scheduled tasks of **any agent tool** fail loudly, diagnose fast, and alert instantly — via execution hooks, no extra monitoring cron job, zero polling.

Supported: **Hermes Agent** · **Claude Code** · **OpenCode** · **Codex** · any shell script

## Why

Scheduled job failures (execution error or delivery error) are usually **silent**. The traditional fix — a separate "health-check cron job" that polls job status — is fragile: the monitor itself can fail, detection lags behind the check interval, and it adds another scheduling layer.

This toolkit hooks the **post-run choke points** of the job lifecycle, so failures are detected the moment they happen.

## Two Integration Paths

### Path 1: Hermes plugins (native cron scheduler)

Hermes has a built-in cron scheduler. Every job passes through two choke points; plugins monkey-patch them:

```
job runs → run_one_job() ← latency-watch / dupe-detector hook here
    ↓
completed → mark_job_run() ← health-hook / error-analyzer hook here
    ↓
  jobs.json (state persisted)
```

```bash
hermes plugins install <owner>/agent-cron-ops/cron-health-hook
hermes plugins install <owner>/agent-cron-ops/cron-latency-watch
hermes plugins install <owner>/agent-cron-ops/cron-error-analyzer
```

### Path 2: Universal CLI wrapper (Claude Code / OpenCode / Codex / anything)

Claude Code, OpenCode, etc. have **no built-in cron scheduler** — their "scheduled jobs" are system crontab / CI calling the CLI non-interactively. Wrap the command to get the same failure alerts:

```bash
# system crontab example
0 2 * * * /path/to/cron-ops-wrap.sh "daily-backup" -- /path/to/backup.sh
0 3 * * * /path/to/cron-ops-wrap.sh "code-review" -- claude -p "review the repo"
0 4 * * * /path/to/cron-ops-wrap.sh "data-job" -- opencode run "process today's data"
```

```
command runs → wrapper records exit code + duration → cron_ops.py check
                                                    → failure → alert with diagnosis + fix
                                                    → success → silent
```

Or install via pip (recommended):

```bash
pip install agent-cron-ops
cron-ops-wrap "daily-backup" -- /path/to/backup.sh
```

## Components

| Component | Answers | Integration | Status |
|:----------|:--------|:------------|:------:|
| [cron-health-hook](cron-health-hook/) | Did the job fail? | Hermes plugin | ✅ |
| [cron-latency-watch](cron-latency-watch/) | Is the job getting slow? | Hermes plugin | ✅ |
| [cron-error-analyzer](cron-error-analyzer/) | Why did it fail? How to fix? | Hermes plugin | ✅ |
| [cli/cron_ops.py](cli/cron_ops.py) | Universal check+diagnose+alert CLI | all agents | ✅ |
| [cli/cron-ops-wrap.sh](cli/cron-ops-wrap.sh) | Universal command wrapper | Claude Code/OpenCode/Codex/any | ✅ |
| cron-dupe-detector | Was the job fired twice? | Hermes plugin | 🚧 |

## CLI Usage

```bash
# diagnose an error string
cron_ops.py analyze "429 Too Many Requests"
# → diagnosis: API rate limit / quota exhausted
# → fix: check API usage dashboard; lower frequency or upgrade quota

# check one job status file
cron_ops.py check /path/to/status.json

# check all status files in a directory
cron_ops.py check-all ~/.cron-ops/status/
```

## Alert Configuration (env vars, all paths)

| Var | Description | Default |
|-----|:------------|:--------|
| `CRON_ALERT_CHAT_ID` | Feishu chat_id for alerts | `FEISHU_HOME_CHANNEL` |
| `CRON_ALERT_WEBHOOK` | Generic webhook URL (non-Feishu channels) | none |
| `CRON_ALERT_COOLDOWN` | Cooldown between alerts for same failure (s) | `3600` |
| `CRON_LATENCY_FACTOR` | Alert when duration > factor × rolling avg | `3.0` |
| `CRON_LATENCY_CEILING` | Absolute ceiling seconds | `3600` |
| `CRON_DUPE_WINDOW` | Duplicate-fire window (s) | `120` |
| `CRON_OPS_STATUS_DIR` | Status file dir for wrapper | `~/.cron-ops/status/` |

Feishu needs `FEISHU_APP_ID` / `FEISHU_APP_SECRET`; other platforms use `CRON_ALERT_WEBHOOK` pointing at any webhook (DingTalk / WeCom / Slack bot URL).

## Diagnosis Knowledge Base (10 built-in error patterns)

| Error signature | Diagnosis | Fix |
|:----------------|:----------|:----|
| `429 / rate limit` | API rate limited | check usage dashboard, lower frequency |
| `timeout` | network/API timeout | service unreachable, retry or raise timeout |
| `99992402 field validation` | Feishu msg validation failed | content too long / special chars |
| `access denied / 99991672` | missing permission scope | add scope in open platform |
| `401 / invalid_api_key` | API key invalid | check .env, regenerate |
| `context length / token` | context/token exceeded | compress prompt, reduce injection |
| `script not found` | script path wrong | check script field |
| `empty response` | model empty response | retry, check API status |
| `ImportError` | missing dependency | install package |
| `OOM / killed` | out of memory | reduce data, check container limits |

## Roadmap

- [x] Hermes plugins ×3 (health-hook / latency-watch / error-analyzer)
- [x] Universal CLI (cron_ops.py check/check-all/analyze)
- [x] Universal wrapper (cron-ops-wrap.sh)
- [x] pip package (`agent-cron-ops` wheel)
- [ ] cron-dupe-detector
- [ ] Daily execution digest
- [ ] Claude Code hooks native adapter (settings.json hooks)
- [ ] OpenCode plugin native adapter

## License

MIT
