"""Cron error analyzer — classify cron failures and suggest fixes.

Wraps ``cron.jobs.mark_job_run`` (the single post-run choke point) and, on
failure, matches the error text against a knowledge base of common Hermes
cron failure signatures (API rate limits, timeouts, token limits, platform
permission errors, missing scripts, empty responses...). The alert includes
a **diagnosis** and **concrete fix**, so the user doesn't have to grep logs
manually.

Designed to be the third member of the cron-ops plugin family:
  - cron-health-hook    → "it failed, here's the error"
  - cron-latency-watch  → "it's running too slowly"
  - cron-error-analyzer → "here's WHY it failed and how to fix it"
"""
import json
import logging
import os
import re
import time
import urllib.request

logger = logging.getLogger(__name__)

# (regex, diagnosis, fix) tuples — checked in order on the combined error text
ERROR_PATTERNS = [
    (
        re.compile(r"429|rate.?limit|Too Many Requests|quota", re.I),
        "API 限流 / 配额耗尽",
        "检查对应 API 的用量面板；降低调用频率或升级配额；DeepSeek 可查余额 (user/balance)。",
    ),
    (
        re.compile(r"timed? ?out|timeout|Timeout|ETIMEDOUT", re.I),
        "网络或 API 超时",
        "目标服务可能不可达（被墙/宕机/变慢）；重试或增加超时；检查日志确认哪个请求超时。",
    ),
    (
        re.compile(r"99992402|field validation failed", re.I),
        "飞书消息校验失败",
        "消息内容被飞书 API 拒绝（常见于超长/特殊字符）。安装 cron-health-hook 的 text-fallback 或缩短报告长度。",
    ),
    (
        re.compile(r"99991672|access denied|permission|scope required", re.I),
        "飞书权限不足",
        "应用缺少权限 scope：到飞书开放平台给应用添加所需权限（如 im:chat:readonly / im:message）。",
    ),
    (
        re.compile(r"invalid_api_key|authentication|401|Unauthorized", re.I),
        "API Key 无效或过期",
        "检查 .env / config 中的 API key；重新生成并更新。",
    ),
    (
        re.compile(r"context.?length|token.*exceed|maximum.*token|1000000|overflow", re.I),
        "上下文/Token 超限",
        "任务提示词或输入过大；压缩 skill 内容、减少注入的上下文、分片处理。",
    ),
    (
        re.compile(r"script not found|No such file|not found.*script", re.I),
        "脚本路径错误",
        "cron 脚本不在预期目录；检查 jobs.json 中 script 字段的相对路径是否正确。",
    ),
    (
        re.compile(r"empty response|produced nothing|no response", re.I),
        "模型返回空响应",
        "模型 API 故障或超时；重试；检查 API 状态页。",
    ),
    (
        re.compile(r"module.*not found|ImportError|No module", re.I),
        "Python 依赖缺失",
        "任务运行环境缺少依赖；在 venv 中 pip install 对应包。",
    ),
    (
        re.compile(r"memory|OOM|killed", re.I),
        "内存不足（OOM）",
        "任务占用内存过大；减少单批数据量；检查容器内存限制。",
    ),
]

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
        logger.warning("[cron-error-analyzer] Failed to read .env: %s", exc)


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
            "template": "red",
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


def _analyze(error_text: str):
    """Return (diagnosis, fix) for the error text, or None if unknown."""
    for pattern, diagnosis, fix in ERROR_PATTERNS:
        if pattern.search(error_text or ""):
            return diagnosis, fix
    return None


def _check_and_alert(job_id: str, success: bool, error=None, delivery_error=None):
    if success and not delivery_error:
        return

    combined = f"{error or ''} {delivery_error or ''}".strip()
    analysis = _analyze(combined)

    _load_env()
    chat_id = _ALERT_CHAT or _HOME_CHANNEL
    if not chat_id or not (_APP_ID and _APP_SECRET):
        logger.warning("[cron-error-analyzer] No chat/creds; skipping alert")
        return

    job_name = _get_job_name(job_id)
    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if analysis:
        diagnosis, fix = analysis
        title = f"🔧 Cron 失败诊断: {job_name}"
        body = (
            f"**任务**: {job_name}\n"
            f"**Job ID**: `{job_id}`\n"
            f"**时间**: {now_str}\n"
            f"**诊断**: {diagnosis}\n\n"
            f"**建议修复**: {fix}\n\n"
            f"**原始错误**: {(combined or '无')[:300]}"
        )
    else:
        title = f"🔴 Cron 任务失败: {job_name}"
        body = (
            f"**任务**: {job_name}\n"
            f"**Job ID**: `{job_id}`\n"
            f"**时间**: {now_str}\n"
            f"**错误**: {(combined or '无')[:500]}\n\n"
            f"未匹配到已知错误模式，请查看日志: `~/.hermes/logs/agent.log`"
        )

    try:
        _send_alert(title, body, chat_id)
        logger.info("[cron-error-analyzer] Alert sent for %s (%s)", job_id, job_name)
    except Exception as exc:
        logger.error("[cron-error-analyzer] Alert send failed: %s", exc)


def _install_hook():
    try:
        from cron import jobs as cron_jobs
        original = cron_jobs.mark_job_run
        if getattr(original, "__cron_error_analyzer_hooked", False):
            return True

        def _hooked(job_id, success, error=None, delivery_error=None):
            result = original(job_id, success, error=error, delivery_error=delivery_error)
            try:
                _check_and_alert(job_id, success, error=error, delivery_error=delivery_error)
            except Exception as exc:
                logger.error("[cron-error-analyzer] check failed: %s", exc)
            return result

        _hooked.__cron_error_analyzer_hooked = True
        cron_jobs.mark_job_run = _hooked
        logger.info("[cron-error-analyzer] mark_job_run wrapped — failures now diagnosed")
        return True
    except Exception as exc:
        logger.warning("[cron-error-analyzer] Hook install failed (may load later): %s", exc)
        return False


def register(ctx):
    logger.info("[cron-error-analyzer] Plugin loaded")
    _install_hook()
    try:
        ctx.register_hook("on_session_start", lambda *a, **kw: _install_hook())
    except Exception:
        pass
    logger.info("[cron-error-analyzer] Plugin registered")
