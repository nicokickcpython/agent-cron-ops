"""agent-cron-ops automated test suite.

Run:  python3 -m pytest tests/ -v
Or:   python3 tests/test_cron_ops.py
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.error

from datetime import datetime
from pathlib import Path

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


# Minimal stand-ins for pytest fixtures so the plain-Python runner below
# can also execute the fixture-based tests.
class _MiniCapsys:
    def __init__(self):
        import contextlib
        import io
        self._out, self._err = io.StringIO(), io.StringIO()
        self._ctx = contextlib.ExitStack()
        self._ctx.enter_context(contextlib.redirect_stdout(self._out))
        self._ctx.enter_context(contextlib.redirect_stderr(self._err))

    def readouterr(self):
        class Result:
            out = self._out.getvalue()
            err = self._err.getvalue()
        return Result


class _MiniMonkeyPatch:
    def __init__(self):
        self._undo = []

    def setenv(self, name, value):
        self._undo.append(("env", name, os.environ.get(name)))
        os.environ[name] = value

    def delenv(self, name, raising=True):
        if name not in os.environ:
            if raising:
                raise KeyError(name)
            return
        self._undo.append(("env", name, os.environ.get(name)))
        del os.environ[name]

    def setattr(self, target, name, value):
        self._undo.append(("attr", target, name, getattr(target, name, None)))
        setattr(target, name, value)

    def restore(self):
        for op in reversed(self._undo):
            if op[0] == "env":
                _, name, value = op
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            else:
                _, target, name, value = op
                setattr(target, name, value)
        self._undo = []


class _MiniTmpPath:
    def __init__(self, root):
        self._root = Path(root)

    def __truediv__(self, name):
        return self._root / name

    def __fspath__(self):
        return str(self._root)

    def __str__(self):
        return str(self._root)


# ---------------------------------------------------------------------------
# 6. Regression tests for review fixes
# ---------------------------------------------------------------------------
def test_check_missing_file_exit_1(tmp_path, capsys):
    rc = cli.main(["check", str(tmp_path / "nope.json")])
    err = capsys.readouterr().err
    assert rc == 1
    assert "状态文件不存在" in err


def test_check_invalid_json_exit_1(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    rc = cli.main(["check", str(bad)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "有效 JSON" in err


def test_check_non_object_json_exit_1(tmp_path, capsys):
    arr = tmp_path / "arr.json"
    arr.write_text("[1, 2]", encoding="utf-8")
    rc = cli.main(["check", str(arr)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "JSON 对象" in err


def test_check_all_empty_dir_exit_1(tmp_path):
    assert cli.main(["check-all", str(tmp_path)]) == 1


def test_check_all_empty_dir_allow_empty_exit_0(tmp_path, capsys):
    assert cli.main(["check-all", str(tmp_path), "--allow-empty"]) == 0
    assert "没有找到状态文件" in capsys.readouterr().out


def test_cli_version_flag():
    result = subprocess.run(
        [sys.executable, "-m", "cron_ops.cli", "--version"],
        capture_output=True, text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    assert result.returncode == 0
    assert "cron-ops 1.0.0" in result.stdout


def test_cooldown_persists_to_disk_and_suppresses(monkeypatch, tmp_path):
    store = tmp_path / "last_alert.json"
    monkeypatch.setenv("CRON_OPS_LAST_ALERT_FILE", str(store))
    calls = []
    monkeypatch.setattr(cli, "send_alert",
                        lambda title, body: calls.append(title) or [(True, "ok")])
    status = {"job_id": "job1", "job_name": "job1", "success": False,
              "error": "connection timed out", "delivery_error": None}
    assert cli.check_one(status) == 1
    assert cli.check_one(status) == 1  # same pattern_class -> suppressed
    assert len(calls) == 1
    data = json.loads(store.read_text(encoding="utf-8"))
    assert "job1|网络或 API 超时" in data
    # A different pattern_class for the same job alerts again
    status["error"] = "ModuleNotFoundError: No module named 'requests'"
    assert cli.check_one(status) == 1
    assert len(calls) == 2
    data = json.loads(store.read_text(encoding="utf-8"))
    assert "job1|Python 依赖缺失" in data


def test_cooldown_corrupt_store_does_not_crash(monkeypatch, tmp_path):
    store = tmp_path / "last_alert.json"
    store.write_text("garbage", encoding="utf-8")
    monkeypatch.setenv("CRON_OPS_LAST_ALERT_FILE", str(store))
    calls = []
    monkeypatch.setattr(cli, "send_alert",
                        lambda title, body: calls.append(title) or [(True, "ok")])
    status = {"job_id": "job2", "job_name": "job2", "success": False,
              "error": "boom", "delivery_error": None}
    assert cli.check_one(status) == 1
    assert len(calls) == 1


def test_analyze_quota_word_boundary():
    assert "限流" in analyze_error("API quota exceeded")[0]
    assert analyze_error("quotable remark") is None


def test_analyze_killed_word_boundary():
    assert "内存" in analyze_error("worker was killed by OOM")[0]
    assert analyze_error("skilled worker") is None


def test_wrap_captures_stderr_tail(tmp_path, monkeypatch):
    monkeypatch.setenv("CRON_OPS_STATUS_DIR", str(tmp_path))
    script = "i=0; while [ $i -lt 150 ]; do echo \"line $i\" >&2; i=$((i+1)); done; exit 1"
    rc = cli_wrap_run(["noisy-job", "--", "sh", "-c", script])
    assert rc == 1
    status = json.load(open(os.path.join(tmp_path, "noisy-job.json"), encoding="utf-8"))
    lines = status["stderr_tail"].splitlines()
    assert len(lines) == 100
    assert lines[0] == "line 50"
    assert lines[-1] == "line 149"


def test_wrap_timestamps_timezone_aware(tmp_path, monkeypatch):
    monkeypatch.setenv("CRON_OPS_STATUS_DIR", str(tmp_path))
    rc = cli_wrap_run(["tz-job", "--", "true"])
    assert rc == 0
    status = json.load(open(os.path.join(tmp_path, "tz-job.json"), encoding="utf-8"))
    fired_at = status["fired_at"]
    assert fired_at.endswith("+00:00")
    assert datetime.fromisoformat(fired_at).tzinfo is not None


def test_send_alert_webhook_http_error_caught(monkeypatch):
    from cron_ops import alerts
    def boom(title, body):
        raise urllib.error.HTTPError("http://example.invalid", 500, "boom", None, None)
    monkeypatch.setattr(alerts, "_webhook_send", boom)
    monkeypatch.delenv("CRON_ALERT_CHAT_ID", raising=False)
    monkeypatch.delenv("FEISHU_HOME_CHANNEL", raising=False)
    results = alerts.send_alert("t", "b")
    assert any("webhook http error" in str(detail) for ok, detail in results)


def test_send_alert_webhook_url_error_caught(monkeypatch):
    from cron_ops import alerts
    def boom(title, body):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(alerts, "_webhook_send", boom)
    monkeypatch.delenv("CRON_ALERT_CHAT_ID", raising=False)
    monkeypatch.delenv("FEISHU_HOME_CHANNEL", raising=False)
    results = alerts.send_alert("t", "b")
    assert any("webhook network error" in str(detail) for ok, detail in results)


def test_send_alert_feishu_http_error_caught(monkeypatch):
    from cron_ops import alerts
    def boom(title, body, chat_id):
        raise urllib.error.HTTPError("http://example.invalid", 400, "bad", None, None)
    monkeypatch.setattr(alerts, "_feishu_send", boom)
    monkeypatch.setenv("CRON_ALERT_CHAT_ID", "chat-1")
    results = alerts.send_alert("t", "b")
    assert any("feishu http error" in str(detail) for ok, detail in results)


def test_shell_wrap_valid_json_and_check_invocation(tmp_path):
    repo = os.path.join(os.path.dirname(__file__), "..")
    script = os.path.join(repo, "cli", "cron-ops-wrap.sh")
    with open(script, encoding="utf-8") as f:
        assert f.readline().strip() == "#!/usr/bin/env bash"  # keep bash shebang

    status_dir = tmp_path / "status"
    stub = tmp_path / "stub-check"
    stub.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$STUB_LOG\"\n", encoding="utf-8")
    stub.chmod(0o755)
    stub_log = tmp_path / "stub.log"
    env = dict(os.environ, CRON_OPS_STATUS_DIR=str(status_dir),
               CRON_OPS_BIN=str(stub), STUB_LOG=str(stub_log))

    result = subprocess.run(
        ["bash", script, "shell-job", "--", "sh", "-c", "exit 3"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 3
    status = json.loads((status_dir / "shell-job.json").read_text(encoding="utf-8"))
    assert status["success"] is False
    assert status["error"] == "exit code 3"  # quoted, valid JSON
    assert json.dumps(status)  # must serialize
    assert stub_log.read_text(encoding="utf-8").splitlines() == [
        "check", str(status_dir / "shell-job.json")]

    # Success: null error and no check invocation
    stub_log.unlink()
    result = subprocess.run(
        ["bash", script, "shell-ok", "--", "true"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0
    status = json.loads((status_dir / "shell-ok.json").read_text(encoding="utf-8"))
    assert status["success"] is True
    assert status["error"] is None
    assert not stub_log.exists()


def test_project_metadata_and_gitignore():
    repo = os.path.join(os.path.dirname(__file__), "..")
    pyproject = open(os.path.join(repo, "pyproject.toml"), encoding="utf-8").read()
    assert 'license = "MIT"' in pyproject  # PEP 639
    assert "[project.urls]" in pyproject
    assert "dev =" in pyproject
    gitignore = open(os.path.join(repo, ".gitignore"), encoding="utf-8").read()
    for entry in ("dist/", "*.egg-info/", ".venv/", ".pytest_cache/"):
        assert entry in gitignore


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    import inspect
    root = tempfile.mkdtemp(prefix="cron-ops-tests-")
    for t in tests:
        monkeypatch = _MiniMonkeyPatch()
        capsys = _MiniCapsys()
        args = {}
        for name in inspect.signature(t).parameters:
            if name == "tmp_path":
                args[name] = _MiniTmpPath(tempfile.mkdtemp(dir=root))
            elif name == "monkeypatch":
                args[name] = monkeypatch
            elif name == "capsys":
                args[name] = capsys
        ok = True
        try:
            t(**args)
        except Exception as e:
            ok = False
            message = f"  ❌ {t.__name__}: {e}"
        finally:
            capsys._ctx.close()
            monkeypatch.restore()
        if ok:
            passed += 1
            message = f"  ✅ {t.__name__}"
        else:
            failed += 1
        print(message)
    print(f"\n结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 用例")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
