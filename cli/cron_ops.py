#!/usr/bin/env python3
"""cron-ops check — universal cron job health checker for ANY agent.

Works with any agent tool (Hermes, Claude Code, OpenCode, Codex...) by
reading a generic JSON status file that each agent's cron adapter writes
after every job run.

Status file format (written by agent adapters):
    {"job_id": "...", "job_name": "...", "success": true/false,
     "error": "..." or null, "delivery_error": "..." or null,
     "duration_seconds": 123, "fired_at": "2026-01-01T08:00:00"}

Usage:
    cron-ops check <status.json>            # check one job result
    cron-ops check-all <dir>                # check all *.json in dir
    cron-ops analyze <error-text>           # diagnose an error string

The CLI itself is agent-agnostic: any wrapper (Hermes plugin, shell wrapper
for Claude Code/OpenCode, CI step) can call it after a job finishes.
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.request

# ---------------------------------------------------------------------------
# Error knowledge base (shared with Hermes cron-error-analyzer plugin)
# ---------------------------------------------------------------------------
ERROR_PATTERNS = [
    (
        re.compile(r"429|rate.?limit|Too Many Requests|quota", re.I),
        "API 限流 / 配额耗尽",
        "检查对应 API 的用量面板；降低调用频率或升级配额。",
    ),
    (
        re.compile(r"timed? ?out|timeout|Timeout|ETIMEDOUT", re.I),
        "网络或 API 超时",
        "目标服务可能不可达（被墙/宕机/变慢）；重试或增加超时。",
    ),
    (
        re.compile(r"99992402|field validation failed", re.I),
        "飞书消息校验失败",
        "消息内容被飞书 API 拒绝（常见于超长/特殊字符）。",
    ),
    (
        re.compile(r"99991672|access denied|permission|scope required", re.I),
        "权限不足",
        "应用缺少权限 scope；到开放平台补权限。",
    ),
    (
        re.compile(r"invalid_api_key|authentication|401|Unauthorized", re.I),
        "API Key 无效或过期",
        "检查 .env / config 中的 API key；重新生成并更新。",
    ),
    (
        re.compile(r"context.?length|token.*exceed|maximum.*token", re.I),
        "上下文/Token 超限",
        "压缩 prompt、减少注入的上下文、分片处理。",
    ),
    (
        re.compile(r"script not found|No such file|not found.*script", re.I),
        "脚本路径错误",
        "检查 cron 任务中 script 字段的相对路径是否正确。",
    ),
    (
        re.compile(r"empty response|produced nothing|no response", re.I),
        "模型返回空响应",
        "模型 API 故障或超时；重试；检查 API 状态页。",
    ),
    (
        re.compile(r"module.*not found|ImportError|No module", re.I),
        "Python 依赖缺失",
        "任务运行环境缺少依赖；安装对应包。",
    ),
    (
        re.compile(r"memory|OOM|killed", re.I),
        "内存不足（OOM）",
        "任务占用内存过大；减少数据量；检查容器限制。",
    ),
]

# ---------------------------------------------------------------------------
# Alert delivery — generic webhook + Feishu built-in
# ---------------------------------------------------------------------------
_LAST_ALERT = {}
_COOLDOWN = float(os.environ.get("CRON_ALERT_COOLDOWN", "3600"))


def _feishu_send(title: str, body: str, chat_id: str):
    """Send an interactive-card alert via Feishu Open API."""
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    domain = os.environ.get("FEISHU_DOMAIN", "feishu")
    if not (app_id and app_secret):
        return False, "no feishu creds"

    base = "https://open.larksuite.com" if domain == "lark" else "https://open.feishu.cn"
    # tenant token
    req = urllib.request.Request(
        f"{base}/open-apis/auth/v3/tenant_access_token/internal",
        data=json.dumps({"app_id": app_id, "app_secret": app_secret}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        token = json.loads(resp.read().decode()).get("tenant_access_token")
    if not token:
        return False, "token fetch failed"

    card = {
        "config": {"wide_screen_mode": True},
        "header": {"template": "red", "title": {"tag": "plain_text", "content": title[:100]}},
        "elements": [{"tag": "markdown", "content": body}],
    }
    payload = json.dumps(
        {"receive_id": chat_id, "msg_type": "interactive",
         "content": json.dumps(card, ensure_ascii=False)},
        ensure_ascii=False,
    ).encode()
    req = urllib.request.Request(
        f"{base}/open-apis/im/v1/messages?receive_id_type=chat_id",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return True, json.loads(resp.read().decode())


def _webhook_send(title: str, body: str):
    """Send via generic webhook URL (CRON_ALERT_WEBHOOK)."""
    url = os.environ.get("CRON_ALERT_WEBHOOK", "")
    if not url:
        return False, "no webhook"
    payload = json.dumps({"title": title, "body": body, "text": f"{title}\n{body}"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return True, resp.read().decode()[:100]


def send_alert(title: str, body: str):
    """Route alert to configured channel(s). Returns list of (ok, detail)."""
    results = []
    chat_id = os.environ.get("CRON_ALERT_CHAT_ID") or os.environ.get("FEISHU_HOME_CHANNEL")
    if chat_id:
        results.append(_feishu_send(title, body, chat_id))
    results.append(_webhook_send(title, body))
    return results


def analyze_error(text: str):
    """Return (diagnosis, fix) or None."""
    for pattern, diagnosis, fix in ERROR_PATTERNS:
        if pattern.search(text or ""):
            return diagnosis, fix
    return None


def check_one(status: dict, alert: bool = True):
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

    # Cooldown
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


def main():
    parser = argparse.ArgumentParser(description="Universal cron job health checker")
    sub = parser.add_subparsers(dest="cmd")

    p1 = sub.add_parser("check", help="check one job status file")
    p1.add_argument("file", help="path to status.json")

    p2 = sub.add_parser("check-all", help="check all *.json in a directory")
    p2.add_argument("dir", help="directory containing status files")

    p3 = sub.add_parser("analyze", help="diagnose an error string")
    p3.add_argument("text", help="error text to diagnose")

    args = parser.parse_args()

    if args.cmd == "check":
        with open(args.file, encoding="utf-8") as f:
            status = json.load(f)
        return check_one(status)

    elif args.cmd == "check-all":
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

    elif args.cmd == "analyze":
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
