"""cron-ops wrap — wrap any command and check its result afterwards.

Console entry point for `cron-ops-wrap`. The shell script
`cli/cron-ops-wrap.sh` is a thin wrapper around this for crontab use;
installing via pip gives you both commands.
"""
import json
import os
import subprocess
import sys
import time


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: cron-ops-wrap <job_name> -- <command...>", file=sys.stderr)
        return 2

    job_name = argv[0]
    rest = argv[1:]
    if rest and rest[0] == "--":
        rest = rest[1:]
    if not rest:
        print("usage: cron-ops-wrap <job_name> -- <command...>", file=sys.stderr)
        return 2

    status_dir = os.environ.get("CRON_OPS_STATUS_DIR", os.path.join(os.path.expanduser("~"), ".cron-ops", "status"))
    os.makedirs(status_dir, exist_ok=True)
    safe_name = job_name.replace(" ", "-").replace("/", "_")
    status_file = os.path.join(status_dir, f"{safe_name}.json")

    fired_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    start = time.monotonic()
    proc = subprocess.run(rest)
    rc = proc.returncode
    duration = int(time.monotonic() - start)

    status = {
        "job_id": safe_name,
        "job_name": job_name,
        "success": rc == 0,
        "error": None if rc == 0 else f"exit code {rc}",
        "delivery_error": None,
        "duration_seconds": duration,
        "fired_at": fired_at,
    }
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    if rc != 0:
        from .cli import check_one
        try:
            check_one(status)
        except Exception as exc:
            print(f"⚠️ cron-ops check failed: {exc}", file=sys.stderr)

    return rc


if __name__ == "__main__":
    sys.exit(main())
