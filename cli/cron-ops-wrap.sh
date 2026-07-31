#!/usr/bin/env bash
# cron-ops wrap — universal wrapper for ANY agent's cron job.
#
# Wrap any command so its exit status is recorded to a status file and
# checked by cron-ops right after it finishes. Works with Claude Code
# (claude -p "..."), OpenCode (opencode run "..."), Codex, or plain scripts.
#
# Usage:
#   cron-ops-wrap.sh "job_name" -- <command...>
#
# Example (system crontab):
#   0 2 * * * /path/to/cron-ops-wrap.sh "每日备份" -- /path/to/backup.sh
#   0 3 * * * /path/to/cron-ops-wrap.sh "代码审查" -- claude -p "review the repo"
#
# Env:
#   CRON_OPS_STATUS_DIR — where status files go (default: ~/.cron-ops/status/)
#   CRON_ALERT_*        — alert config (see cron_ops.py)

set -u

JOB_NAME="${1:-unknown}"
shift
# shellcheck disable=SC2124
CMD_ARGS=("$@")
if [ "${1:-}" = "--" ]; then
    shift
    CMD_ARGS=("$@")
fi

if [ ${#CMD_ARGS[@]} -eq 0 ]; then
    echo "usage: cron-ops-wrap.sh <job_name> -- <command...>" >&2
    exit 2
fi

STATUS_DIR="${CRON_OPS_STATUS_DIR:-$HOME/.cron-ops/status}"
STATUS_FILE="$STATUS_DIR/$(echo "$JOB_NAME" | tr ' /' '__').json"
mkdir -p "$STATUS_DIR"

FIRED_AT=$(date -Is)
START=$(date +%s)

# Run the actual job
"${CMD_ARGS[@]}"
RC=$?

END=$(date +%s)
DURATION=$((END - START))

# Write status record
cat > "$STATUS_FILE" <<EOF
{
  "job_id": "$(echo "$JOB_NAME" | tr ' ' '-')",
  "job_name": "$JOB_NAME",
  "success": $([ $RC -eq 0 ] && echo true || echo false),
  "error": $([ $RC -eq 0 ] && echo null || echo "exit code $RC"),
  "delivery_error": null,
  "duration_seconds": $DURATION,
  "fired_at": "$FIRED_AT"
}
EOF

# Check + alert on failure (silent on success)
CRON_OPS_BIN="${CRON_OPS_BIN:-$(dirname "$0")/cron_ops.py}"
if [ $RC -ne 0 ]; then
    python3 "$CRON_OPS_BIN" check "$STATUS_FILE"
fi

exit $RC
