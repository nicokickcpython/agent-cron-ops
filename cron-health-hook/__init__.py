"""Cron job result hook — auto-alert on any cron job failure.

Monkey-patches ``cron.jobs.mark_job_run`` (the single choke point every
scheduled job goes through after execution) so that ANY job — agent job or
script job, live-adapter or standalone delivery — is checked the moment it
finishes. On failure (execution error OR delivery error) it immediately
sends an alert to the configured chat with the error details, instead of
waiting for a separate health-check cron job.

Silent when all jobs succeed (no spam).

Config (in .env or plugin.yaml ``env`` block):
  CRON_ALERT_CHAT_ID   — chat to receive alerts (default: FEISHU_HOME_CHANNEL)
  CRON_ALERT_COOLDOWN  — seconds between alerts for the same failure (default 3600)
"""
import json
import logging
import os
import time
import urllib.request

logger = logging.getLogger(__name__)

_ALERT_COOLDOWN_SECONDS = int(os.environ.get("CRON_ALERT_COOLDOWN", "3600"))
_last_alert = {}  # signature -> monotonic timestamp

_HOME_CHANNEL = None
_APP_ID = None
_APP_SECRET = None
_DOMAIN = "feishu"
_ALERT_CHAT = None


def _load_env():
    """Load Feishu creds from .env once."""
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
        logger.warning("[cron-health-hook] Failed to read .env: %s", exc)


def _get_tenant_token():
    """Fetch a Feishu tenant_access_token."""
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
    """Send a plain-text alert to the chat.

    NOTE(2026-08-03 fix): previously sent an interactive card, but cards with
    markdown content fail Feishu validation (99992402 field validation failed)
    — the same failure that cron report deliveries hit. Plain text always sends.
    """
    token = _get_tenant_token()
    base = "https://open.larksuite.com" if _DOMAIN == "lark" else "https://open.feishu.cn"
    url = f"{base}/open-apis/im/v1/messages?receive_id_type=chat_id"
    text = f"{title}\n{body}"
    payload = json.dumps(
        {"receive_id": chat_id, "msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)},
        ensure_ascii=False,
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _get_job_name(job_id: str) -> str:
    """Look up a job's display name from jobs.json."""
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


def _check_and_alert(job_id: str, success: bool, error=None, delivery_error=None):
    """Post-run check: alert immediately if the job failed in any way."""
    if success and not delivery_error:
        return

    _load_env()
    chat_id = _ALERT_CHAT or _HOME_CHANNEL
    if not chat_id:
        logger.warning("[cron-health-hook] No alert chat configured (set CRON_ALERT_CHAT_ID)")
        return
    if not (_APP_ID and _APP_SECRET):
        logger.warning("[cron-health-hook] Missing Feishu creds; skipping alert")
        return

    job_name = _get_job_name(job_id)
    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    # Cooldown: don't spam the same failure every run
    sig = f"{job_id}|{success}|{error}|{delivery_error}"
    last = _last_alert.get(sig, 0)
    if time.monotonic() - last < _ALERT_COOLDOWN_SECONDS:
        return
    _last_alert[sig] = time.monotonic()

    # Determine failure type
    if not success and delivery_error:
        title = f"🔴 Cron 任务执行+推送失败: {job_name}"
        body = (
            f"**任务**: {job_name}\n"
            f"**Job ID**: `{job_id}`\n"
            f"**时间**: {now_str}\n"
            f"**执行错误**: {(error or '无')[:500]}\n"
            f"**推送错误**: {delivery_error[:500]}\n\n"
            f"请检查日志: `{os.path.join(os.environ.get('HERMES_HOME', ''), 'logs', 'agent.log')}`"
        )
    elif not success:
        title = f"🔴 Cron 任务执行失败: {job_name}"
        body = (
            f"**任务**: {job_name}\n"
            f"**Job ID**: `{job_id}`\n"
            f"**时间**: {now_str}\n"
            f"**错误**: {(error or '无')[:500]}\n\n"
            f"请检查日志: `{os.path.join(os.environ.get('HERMES_HOME', ''), 'logs', 'agent.log')}`"
        )
    else:
        title = f"🟠 Cron 任务推送失败: {job_name}"
        body = (
            f"**任务**: {job_name}\n"
            f"**Job ID**: `{job_id}`\n"
            f"**时间**: {now_str}\n"
            f"**推送错误**: {delivery_error[:500]}\n\n"
            f"执行本身成功，但结果未能送达。"
        )

    try:
        _send_alert(title, body, chat_id)
        logger.info("[cron-health-hook] Alert sent for job %s (%s)", job_id, job_name)
    except Exception as exc:
        logger.error("[cron-health-hook] Alert send failed: %s", exc)


def _install_hook():
    """Wrap cron.jobs.mark_job_run with a post-run health check."""
    try:
        from cron import jobs as cron_jobs
        original = cron_jobs.mark_job_run
        if getattr(original, "__cron_health_hooked", False):
            return True

        def _hooked(job_id, success, error=None, delivery_error=None):
            result = original(job_id, success, error=error, delivery_error=delivery_error)
            try:
                _check_and_alert(job_id, success, error=error, delivery_error=delivery_error)
            except Exception as exc:
                logger.error("[cron-health-hook] _check_and_alert failed: %s", exc)
            return result

        _hooked.__cron_health_hooked = True
        cron_jobs.mark_job_run = _hooked
        logger.info("[cron-health-hook] mark_job_run wrapped — every cron job result is now checked")
        return True
    except Exception as exc:
        logger.warning("[cron-health-hook] Hook install failed (may load later): %s", exc)
        return False


def register(ctx):
    """Register the cron health hook plugin."""
    logger.info("[cron-health-hook] Plugin loaded")
    _install_hook()
    try:
        ctx.register_hook("on_session_start", lambda *a, **kw: _install_hook())
    except Exception:
        pass
    logger.info("[cron-health-hook] Plugin registered")
