"""Alert delivery: Feishu interactive card + generic webhook."""
import json
import os
import urllib.request


def _feishu_send(title: str, body: str, chat_id: str):
    """Send an interactive-card alert via Feishu Open API."""
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    domain = os.environ.get("FEISHU_DOMAIN", "feishu")
    if not (app_id and app_secret):
        return False, "no feishu creds"

    base = "https://open.larksuite.com" if domain == "lark" else "https://open.feishu.cn"
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
