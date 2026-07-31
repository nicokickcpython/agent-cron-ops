"""Error pattern knowledge base for cron job diagnosis."""
import re

ERROR_PATTERNS = [
    (
        re.compile(r"429|rate.?limit|\bquota\b", re.I),
        "API 限流 / 配额耗尽",
        "检查对应 API 的用量面板；降低调用频率或升级配额。",
    ),
    (
        re.compile(r"timed? ?out|ETIMEDOUT", re.I),
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
        re.compile(r"invalid_api_key|authentication|401", re.I),
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
        re.compile(r"memory|OOM|\bkilled\b", re.I),
        "内存不足（OOM）",
        "任务占用内存过大；减少数据量；检查容器限制。",
    ),
]


def analyze_error(text: str):
    """Return (diagnosis, fix) for the error text, or None if unknown."""
    for pattern, diagnosis, fix in ERROR_PATTERNS:
        if pattern.search(text or ""):
            return diagnosis, fix
    return None
