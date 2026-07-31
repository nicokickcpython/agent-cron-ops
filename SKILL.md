---
name: cron-ops
description: "Cron 任务可靠性工具：失败告警 + 耗时检测 + 错误诊断。集成到任何 agent（Claude Code/OpenCode/Codex/Hermes）的定时任务，任务失败立即告警并给出修复建议。"
---

# Cron Ops — 定时任务可靠性

## 这是什么

你的 agent（Claude Code / OpenCode / Codex / Hermes）跑定时任务时，任务失败往往是**静默的**——没有通知，几天后才发现。cron-ops 在任务执行完后立即检查，失败就告警（含错误诊断和修复建议），成功则静默。

## 何时使用

- 用户提到"定时任务失败了没人知道"、"cron 没跑"、"任务执行异常"
- 用户要求给定时任务加失败通知/监控
- 用户需要诊断一个 cron 失败的错误信息

## 集成方式（选一种）

### 方式 A：系统 crontab wrapper（最通用）

用 `cli/cron-ops-wrap.sh` 包裹任意命令：

```bash
# crontab 示例
0 2 * * * /path/to/cron-ops-wrap.sh "每日备份" -- /path/to/backup.sh
0 3 * * * /path/to/cron-ops-wrap.sh "代码审查" -- claude -p "review the repo"
```

原理：命令跑完 → wrapper 写状态文件 → `cron_ops.py check` 检查 → 失败即告警。

### 方式 B：Claude Code hooks（原生集成）

在 `~/.claude/settings.json` 配置 hooks，任务结束后自动检查：

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "cron_ops.py check ~/.cron-ops/status/last-run.json"
          }
        ]
      }
    ]
  }
}
```

### 方式 C：OpenCode plugin（原生集成）

OpenCode 支持 plugin 事件（`event:session.idle` / `event:session.error`），在 plugin 中调用 `cron_ops.py check`。

### 方式 D：Hermes 插件

Hermes 有原生 cron 调度器，直接用 `cron-health-hook` / `cron-latency-watch` / `cron-error-analyzer` 插件（见仓库对应目录）。

## 常用命令

```bash
# 诊断一段错误文本
cron_ops.py analyze "429 Too Many Requests"
# → 诊断: API 限流 / 配额耗尽
# → 建议: 检查对应 API 的用量面板；降低调用频率或升级配额。

# 检查任务状态文件
cron_ops.py check /path/to/status.json

# 批量检查
cron_ops.py check-all ~/.cron-ops/status/
```

## 告警配置

环境变量（所有方式通用）：

| 变量 | 说明 |
|------|------|
| `CRON_ALERT_CHAT_ID` | 飞书 chat_id（有飞书时） |
| `CRON_ALERT_WEBHOOK` | 任意 webhook URL（通用） |
| `CRON_ALERT_COOLDOWN` | 同一失败告警冷却秒数，默认 3600 |

没有飞书就用 `CRON_ALERT_WEBHOOK` 指向任意 webhook（钉钉/企业微信/Slack 机器人地址）。

## 常见问题

- **只想测试告警**：`cron_ops.py check` 一个 `success:false` 的状态文件
- **不想被刷屏**：同一种失败默认 1 小时只告警一次
- **Hermes 用户**：直接用插件目录，无需 wrapper
