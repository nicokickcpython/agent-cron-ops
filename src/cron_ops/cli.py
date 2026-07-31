"""cron-ops CLI — check / check-all / analyze commands."""
import argparse
import glob
import json
import os
import sys
import time

from .analyzer import analyze_error
from .alerts import send_alert

_LAST_ALERT = {}
_COOLDOWN = float(os.environ.get("CRON_ALERT_COOLDOWN", "3600"))


def check_one(status: dict, alert: bool = True) -> int:
    """Check a single job status record; alert on failure. Returns exit code."""
    success = status.get("success", True)
    delivery_error = status.get("delivery_error")
    error = status.get("error")
    job_name = status.get("job_name", status.get("job_id", "?"))
    job_id = status.get("job_id", "?")

    if success and not delivery_error:
        return 0  # healthy — silent

    combined = f"{error or ''} {delivery_error or ''}".strip()
    analysis = analyze_error(combined)
    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if analysis:
        diagnosis, fix = analysis
        title = f"🔧 Cron 失败诊断: {job_name}"
        body = (
            f"**任务**: {job_name}\n**Job ID**: `{job_id}`\n**时间**: {now_str}\n"
            f"**诊断**: {diagnosis}\n\n**建议修复**: {fix}\n\n"
            f"**原始错误**: {(combined or '无')[:300]}"
        )
    else:
        title = f"🔴 Cron 任务失败: {job_name}"
        body = (
            f"**任务**: {job_name}\n**Job ID**: `{job_id}`\n**时间**: {now_str}\n"
            f"**错误**: {(combined or '无')[:500]}"
        )

    sig = f"{job_id}|{combined}"
    if time.monotonic() - _LAST_ALERT.get(sig, 0) < _COOLDOWN:
        return 1
    _LAST_ALERT[sig] = time.monotonic()

    if alert:
        results = send_alert(title, body)
        ok = any(r[0] for r in results)
        print(f"{'✅' if ok else '⚠️'} {title}")
        if not ok:
            print(f"   告警发送失败: {[r[1] for r in results]}")
    else:
        print(title)
        print(body)
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Universal cron job health checker")
    sub = parser.add_subparsers(dest="cmd")

    p1 = sub.add_parser("check", help="check one job status file")
    p1.add_argument("file", help="path to status.json")

    p2 = sub.add_parser("check-all", help="check all *.json in a directory")
    p2.add_argument("dir", help="directory containing status files")

    p3 = sub.add_parser("analyze", help="diagnose an error string")
    p3.add_argument("text", help="error text to diagnose")

    args = parser.parse_args(argv)

    if args.cmd == "check":
        with open(args.file, encoding="utf-8") as f:
            status = json.load(f)
        return check_one(status)

    if args.cmd == "check-all":
        files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
        if not files:
            print("没有找到状态文件")
            return 0
        failures = 0
        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    status = json.load(f)
                if check_one(status) != 0:
                    failures += 1
            except Exception as exc:
                print(f"⚠️ {path}: 解析失败 {exc}")
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
