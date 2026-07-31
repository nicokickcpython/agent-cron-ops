---
name: cron-ops
description: "Cron job reliability toolkit: failure alerts + latency watch + error diagnosis. Integrate into any agent's (Claude Code/OpenCode/Codex/Hermes) scheduled tasks — alert immediately on failure with diagnosis and fix suggestions."
---

# Cron Ops — Scheduled Task Reliability

## What This Is

When your agent (Claude Code / OpenCode / Codex / Hermes) runs scheduled jobs, failures are often **silent** — no notification, discovered days later. cron-ops checks right after the job finishes: failure → alert (with diagnosis and fix), success → silent.

## When to Use

- User mentions "scheduled jobs fail silently", "cron didn't run", "job execution is abnormal"
- User wants failure notifications/monitoring for cron jobs
- User needs to diagnose an error string from a failed cron job

## Integration (pick one)

### Path A: System crontab wrapper (most universal)

Wrap any command with `cron-ops-wrap`:

```bash
# crontab example
0 2 * * * cron-ops-wrap "daily-backup" -- /path/to/backup.sh
0 3 * * * cron-ops-wrap "code-review" -- claude -p "review the repo"
```

How it works: command finishes → wrapper writes a status file → `cron-ops check` inspects it → failure triggers alert.

### Path B: Claude Code hooks (native)

Configure `~/.claude/settings.json` to run the check after each session stops:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "cron-ops check ~/.cron-ops/status/last-run.json"
          }
        ]
      }
    ]
  }
}
```

### Path C: OpenCode plugin (native)

OpenCode supports plugin events (`event:session.idle` / `event:session.error`) — call `cron-ops check` from the plugin.

### Path D: Hermes plugins

Hermes has a native cron scheduler; use `cron-health-hook` / `cron-latency-watch` / `cron-error-analyzer` directly (see repo subdirectories).

## Commands

```bash
# diagnose an error string
cron-ops analyze "429 Too Many Requests"
# → diagnosis: API rate limit / quota exhausted
# → fix: check API usage dashboard; lower frequency or upgrade quota

# check a job status file
cron-ops check /path/to/status.json

# batch check
cron-ops check-all ~/.cron-ops/status/
```

## Alert Config (env vars, all paths)

| Var | Description |
|-----|-------------|
| `CRON_ALERT_CHAT_ID` | Feishu chat_id (if using Feishu) |
| `CRON_ALERT_WEBHOOK` | Any webhook URL (universal) |
| `CRON_ALERT_COOLDOWN` | Cooldown between alerts for same failure, default 3600 |

No Feishu? Point `CRON_ALERT_WEBHOOK` at any webhook (DingTalk / WeCom / Slack bot URL).

## FAQ

- **Just want to test the alert**: `cron-ops check` a status file with `success:false`
- **Don't want spam**: same failure alerts once per hour by default
- **Hermes user**: use the plugin directories directly, no wrapper needed
