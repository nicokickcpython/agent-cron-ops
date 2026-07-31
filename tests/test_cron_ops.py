"""agent-cron-ops automated test suite.

Run:  python3 -m pytest tests/ -v
Or:   python3 tests/run_all.py
"""
import json
import os
import subprocess
import sys
import tempfile

# Ensure the package is importable from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cron_ops.analyzer import analyze_error  # noqa: E402
from cron_ops.alerts import send_alert  # noqa: E402
from cron_ops import cli  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Analyzer tests
# ---------------------------------------------------------------------------
def test_analyze_rate_limit():
    diag, fix = analyze_error("HTTP 429 Too Many Requests")
    assert "限流" in diag


def test_analyze_timeout():
    diag, fix = analyze_error("connection timed out after 30s")
    assert "超时" in diag


def test_analyze_feishu_validation():
    diag, fix = analyze_error("[99992402] field validation failed")
    assert "飞书" in diag


def test_analyze_permission():
    diag, fix = analyze_error("99991672 Access denied, scope required")
    assert "权限" in diag


def test_analyze_api_key():
    diag, fix = analyze_error("invalid_api_key provided")
    assert "API Key" in diag


def test_analyze_context_length():
    diag, fix = analyze_error("context_length_exceeded")
    assert "Token" in diag or "上下文" in diag


def test_analyze_script_not_found():
    diag, fix = analyze_error("Script not found: /nonexistent/foo.py")
    assert "脚本" in diag


def test_analyze_empty_response():
    diag, fix = analyze_error("Agent produced empty response")
    assert "空响应" in diag


def test_analyze_import_error():
    diag, fix = analyze_error("ModuleNotFoundError: No module named 'requests'")
    assert "依赖" in diag


def test_analyze_oom():
    diag, fix = analyze_error("Killed by OOM killer")
    assert "内存" in diag


def test_analyze_unknown_error_returns_none():
    assert analyze_error("some completely unknown gibberish") is None


# ---------------------------------------------------------------------------
# 2. CLI check tests
# ---------------------------------------------------------------------------
def _write_status(tmpdir, data):
    path = os.path.join(tmpdir, "status.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return path


def test_check_success_silent(tmp_path):
    path = _write_status(tmp_path, {
        "job_id": "ok", "job_name": "ok-job",
        "success": True, "error": None, "delivery_error": None,
    })
    rc = cli.check_one(json.load(open(path)), alert=False)
    assert rc == 0


def test_check_failure_returns_1(tmp_path):
    path = _write_status(tmp_path, {
        "job_id": "fail", "job_name": "fail-job",
        "success": False, "error": "timeout", "delivery_error": None,
    })
    rc = cli.check_one(json.load(open(path)), alert=False)
    assert rc == 1


def test_check_delivery_error_returns_1(tmp_path):
    path = _write_status(tmp_path, {
        "job_id": "deliv", "job_name": "deliv-job",
        "success": True, "error": None,
        "delivery_error": "[99992402] field validation failed",
    })
    rc = cli.check_one(json.load(open(path)), alert=False)
    assert rc == 1


def test_check_all_counts_failures(tmp_path):
    ok = _write_status(tmp_path, {
        "job_id": "ok", "job_name": "ok", "success": True,
        "error": None, "delivery_error": None,
    })
    fail = os.path.join(tmp_path, "fail.json")
    with open(fail, "w", encoding="utf-8") as f:
        json.dump({"job_id": "fail", "job_name": "fail", "success": False,
                   "error": "boom", "delivery_error": None}, f, ensure_ascii=False)
    rc = cli.main(["check-all", str(tmp_path)])
    assert rc == 1  # at least one failure


# ---------------------------------------------------------------------------
# 3. CLI entry-point tests (subprocess, end-to-end)
# ---------------------------------------------------------------------------
def test_cli_analyze_end_to_end():
    result = subprocess.run(
        [sys.executable, "-m", "cron_ops.cli", "analyze", "429 Too Many Requests"],
        capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    assert result.returncode == 0
    assert "限流" in result.stdout


def test_cli_unknown_error():
    result = subprocess.run(
        [sys.executable, "-m", "cron_ops.cli", "analyze", "xyzzy weird"],
        capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    assert result.returncode == 0
    assert "未匹配" in result.stdout


# ---------------------------------------------------------------------------
# 4. Alert delivery tests (no network — config validation only)
# ---------------------------------------------------------------------------
def test_alert_no_config_returns_no_webhook(monkeypatch):
    monkeypatch.delenv("CRON_ALERT_WEBHOOK", raising=False)
    monkeypatch.delenv("CRON_ALERT_CHAT_ID", raising=False)
    monkeypatch.delenv("FEISHU_HOME_CHANNEL", raising=False)
    results = send_alert("t", "b")
    # At least the webhook channel reports "no webhook" without crashing
    assert any("webhook" in str(detail) for ok, detail in results)


# ---------------------------------------------------------------------------
# 5. Wrapper tests
# ---------------------------------------------------------------------------
def test_wrap_success(tmp_path, monkeypatch):
    monkeypatch.setenv("CRON_OPS_STATUS_DIR", str(tmp_path))
    rc = cli_wrap_run(["wrap-job", "--", "echo", "hello"])
    assert rc == 0
    files = os.listdir(tmp_path)
    assert any("wrap-job" in f for f in files)


def test_wrap_failure_returns_rc(tmp_path, monkeypatch):
    monkeypatch.setenv("CRON_OPS_STATUS_DIR", str(tmp_path))
    rc = cli_wrap_run(["fail-job", "--", "sh", "-c", "exit 7"])
    assert rc == 7


def cli_wrap_run(args):
    """Run cron_ops.wrap.main with args, returning exit code."""
    from cron_ops import wrap
    old = sys.argv
    sys.argv = ["cron-ops-wrap"] + args
    try:
        return wrap.main()
    finally:
        sys.argv = old


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
            failed += 1
    print(f"\n结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 用例")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
