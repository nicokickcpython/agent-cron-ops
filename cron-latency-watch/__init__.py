"""Cron latency watch — alert when a scheduled job runs abnormally long.

Wraps ``cron.scheduler.run_one_job`` (the shared firing body for BOTH the
built-in ticker and external providers) to measure each job's wall-clock
duration. When a job takes longer than its own historical average by a
configurable factor (or exceeds an absolute ceiling), an alert is sent.

Why not a separate cron job? Because the check must happen *at the moment*
the job finishes — a polling job can only detect it after the fact, with
lag equal to its own schedule. A hook is immediate.

Config (.env):
  CRON_LATENCY_FACTOR   — alert when duration > factor × rolling average (default 3.0)
  CRON_LATENCY_MIN_SEC  — only evaluate jobs that historically take ≥ this (default 10)
  CRON_LATENCY_CEILING  — absolute ceiling in seconds; alert above it regardless (default 3600)
"""
import json
import logging
import os
import time
import urllib.request
from collections import deque

logger = logging.getLogger(__name__)

_FACTOR = float(os.environ.get("CRON_LATENCY_FACTOR", "3.0"))
_MIN_SEC = float(os.environ.get("CRON_LATENCY_MIN_SEC", "10"))
_CEILING = float(os.environ.get("CRON_LATENCY_CEILING", "3600"))
_HISTORY = {}  # job_id -> deque of recent durations (seconds)
_MAX_HISTORY = 10

_HOME_CHANNEL = None
_APP_ID = None
_APP_SECRET = None
_DOMAIN = "feishu"
_ALERT_CHAT = None


def _load_env():
    global _HOME_CHANNEL, _APP_ID, _APP_SECRET, _DOMAIN, _ALERT_CHAT
    env_path = os.path.join(os.environ.get("HERMES_HOME", os.path.expanduser("~")), ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                if k == "FEISHU_APP_ID":
                    _APP_ID = v
                elif k == "FEISHU_APP_SECRET":
                    _APP_SECRET = v
                elif k == "FEISHU_DOMAIN":
                    _DOMAIN = v
                elif k == "FEISHU_HOME_CHANNEL":
                    _HOME_CHANNEL = v
                elif k == "CRON_ALERT_CHAT_ID":
                    _ALERT_CHAT = v
    except Exception as exc:
        logger.warning("[cron-latency-watch] Failed to read .env: %s", exc)


def _get_tenant_token():
    base = "https://open.larksuite.com" if _DOMAIN == "lark" else "https://open.feishu.cn"
    url = f"{base}/open-apis/auth/v3/tenant_access_token/internal"
    body = json.dumps({"app_id": _APP_ID, "app_secret": _APP_SECRET}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    token = data.get("tenant_access_token")
    if not token:
        raise RuntimeError(f"Token fetch failed: {data.get('msg')}")
    return token


def _send_alert(title: str, body: str, chat_id: str):
    token = _get_tenant_token()
    base = "https://open.larksuite.com" if _DOMAIN == "lark" else "https://open.feishu.cn"
    url = f"{base}/open-apis/im/v1/messages?receive_id_type=chat_id"
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": title[:100]},
        },
        "elements": [{"tag": "markdown", "content": body}],
    }
    payload = json.dumps(
        {"receive_id": chat_id, "msg_type": "interactive", "content": json.dumps(card, ensure_ascii=False)},
        ensure_ascii=False,
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _get_job_name(job_id: str) -> str:
    try:
        jobs_path = os.path.join(os.environ.get("HERMES_HOME", os.path.expanduser("~")), "cron", "jobs.json")
        with open(jobs_path, encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("jobs", data) if isinstance(data, dict) else data
        for job in items if isinstance(items, list) else []:
            if job.get("id") == job_id:
                return job.get("name", job_id)
    except Exception:
        pass
    return job_id


def _evaluate(job_id: str, job_name: str, duration: float):
    """Record duration and alert if abnormally slow."""
    hist = _HISTORY.setdefault(job_id, deque(maxlen=_MAX_HISTORY))
    hist.append(duration)

    # Need a baseline before judging
    if len(hist) < 2:
        return

    avg = sum(list(hist)[:-1]) / (len(hist) - 1)  # exclude the current run
    threshold = max(avg * _FACTOR, _MIN_SEC)
    is_abnormal = duration > threshold or duration > _CEILING

    if not is_abnormal:
        return

    _load_env()
    chat_id = _ALERT_CHAT or _HOME_CHANNEL
    if not chat_id or not (_APP_ID and _APP_SECRET):
        logger.warning("[cron-latency-watch] No chat/creds; skipping alert")
        return

    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    title = f"🐌 Cron 任务执行异常缓慢: {job_name}"
    body = (
        f"**任务**: {job_name}\n"
        f"**Job ID**: `{job_id}`\n"
        f"**时间**: {now_str}\n"
        f"**本次耗时**: {duration:.0f}s\n"
        f"**历史平均**: {avg:.0f}s\n"
        f"**触发阈值**: {threshold:.0f}s\n\n"
        f"可能原因：模型 API 变慢、外部数据源超时、循环未收敛。"
    )
    try:
        _send_alert(title, body, chat_id)
        logger.info("[cron-latency-watch] Alert sent for %s (%.0fs)", job_id, duration)
    except Exception as exc:
        logger.error("[cron-latency-watch] Alert send failed: %s", exc)


def _install_hook():
    try:
        from cron import scheduler as cron_sched
        original = cron_sched.run_one_job
        if getattr(original, "__cron_latency_hooked", False):
            return True

        def _hooked(job, *, adapters=None, loop=None, verbose=False):
            job_id = job.get("id", "?")
            job_name = job.get("name", job_id)
            start = time.monotonic()
            try:
                return original(job, adapters=adapters, loop=loop, verbose=verbose)
            finally:
                duration = time.monotonic() - start
                try:
                    _evaluate(job_id, job_name, duration)
                except Exception as exc:
                    logger.error("[cron-latency-watch] evaluate failed: %s", exc)

        _hooked.__cron_latency_hooked = True
        cron_sched.run_one_job = _hooked
        logger.info("[cron-latency-watch] run_one_job wrapped — durations tracked")
        return True
    except Exception as exc:
        logger.warning("[cron-latency-watch] Hook install failed (may load later): %s", exc)
        return False


def register(ctx):
    logger.info("[cron-latency-watch] Plugin loaded")
    _install_hook()
    try:
        ctx.register_hook("on_session_start", lambda *a, **kw: _install_hook())
    except Exception:
        pass
    logger.info("[cron-latency-watch] Plugin registered")
