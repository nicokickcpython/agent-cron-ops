"""cron-ops CLI — check / check-all / analyze commands."""
import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime, timezone

from . import __version__
from .analyzer import analyze_error
from .alerts import send_alert

_COOLDOWN = float(os.environ.get("CRON_ALERT_COOLDOWN", "3600"))
_DEFAULT_LAST_ALERT_FILE = os.path.join(
    os.path.expanduser("~"), ".cron-ops", ".last_alert.json"
)


def _last_alert_file():
    """Path to the persistent last-alert timestamp store."""
    return os.environ.get("CRON_OPS_LAST_ALERT_FILE", _DEFAULT_LAST_ALERT_FILE)


def _load_last_alerts():
    """Load {key: last_alert_timestamp} from disk; missing/corrupt -> {}."""
    try:
        with open(_last_alert_file(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_last_alerts(alerts):
    """Persist the last-alert store atomically; never raise on failure."""
    try:
        path = _last_alert_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(alerts, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass


def check_one(status: dict, alert: bool = True) -> int:
    """Check a single job status record; alert on failure. Returns exit code."""
    success = status.get("success", True)
    delivery_error = status.get("delivery_error")
    error = status.get("error")
    stderr_tail = status.get("stderr_tail")
    job_name = status.get("job_name", status.get("job_id", "?"))
    job_id = status.get("job_id", "?")

    if success and not delivery_error:
        return 0  # healthy — silent

    combined = " ".join(x for x in (error, delivery_error, stderr_tail) if x).strip()
    analysis = analyze_error(combined)
    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if analysis:
        diagnosis, fix = analysis
        pattern_class = diagnosis
        title = f"🔧 Cron 失败诊断: {job_name}"
        body = (
            f"**任务**: {job_name}\n**Job ID**: `{job_id}`\n**时间**: {now_str}\n"
            f"**诊断**: {diagnosis}\n\n**建议修复**: {fix}\n\n"
            f"**原始错误**: {(combined or '无')[:300]}"
        )
    else:
        pattern_class = "unclassified"
        title = f"🔴 Cron 任务失败: {job_name}"
        body = (
            f"**任务**: {job_name}\n**Job ID**: `{job_id}`\n**时间**: {now_str}\n"
            f"**错误**: {(combined or '无')[:500]}"
        )

    if not alert:
        print(title)
        print(body)
        return 1

    last_alerts = _load_last_alerts()
    key = f"{job_id}|{pattern_class}"
    now = time.time()
    if now - last_alerts.get(key, 0.0) < _COOLDOWN:
        return 1  # same failure already alerted recently
    last_alerts[key] = now
    _save_last_alerts(last_alerts)

    results = send_alert(title, body)
    ok = any(r[0] for r in results)
    print(f"{'✅' if ok else '⚠️'} {title}")
    if not ok:
        print(f"   告警发送失败: {[r[1] for r in results]}")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="cron-ops", description="Universal cron job health checker"
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="cmd")

    p1 = sub.add_parser("check", help="check one job status file")
    p1.add_argument("file", help="path to status.json")

    p2 = sub.add_parser("check-all", help="check all *.json in a directory")
    p2.add_argument("dir", help="directory containing status files")
    p2.add_argument(
        "--allow-empty",
        action="store_true",
        help="exit 0 when no status files are found",
    )

    p3 = sub.add_parser("analyze", help="diagnose an error string")
    p3.add_argument("text", help="error text to diagnose")

    args = parser.parse_args(argv)

    if args.cmd == "check":
        try:
            with open(args.file, encoding="utf-8") as f:
                status = json.load(f)
        except FileNotFoundError:
            print(f"错误: 状态文件不存在: {args.file}", file=sys.stderr)
            return 1
        except json.JSONDecodeError as exc:
            print(f"错误: 状态文件不是有效 JSON: {args.file} ({exc})", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"错误: 无法读取状态文件: {args.file} ({exc})", file=sys.stderr)
            return 1
        if not isinstance(status, dict):
            print(f"错误: 状态文件格式无效（应为 JSON 对象）: {args.file}", file=sys.stderr)
            return 1
        return check_one(status)

    if args.cmd == "check-all":
        files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
        if not files:
            if args.allow_empty:
                print("没有找到状态文件")
                return 0
            print("错误: 没有找到状态文件", file=sys.stderr)
            return 1
        failures = 0
        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    status = json.load(f)
                if not isinstance(status, dict):
                    raise ValueError("status file is not a JSON object")
                if check_one(status) != 0:
                    failures += 1
            except Exception as exc:
                print(f"⚠️ {path}: 解析失败 {exc}")
                failures += 1
        return 1 if failures else 0

    if args.cmd == "analyze":
        diag = analyze_error(args.text)
        if diag:
            print(f"诊断: {diag[0]}")
            print(f"建议: {diag[1]}")
        else:
            print("未匹配到已知错误模式")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
