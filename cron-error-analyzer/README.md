# cron-error-analyzer

**Cron 任务失败诊断** — 自动识别失败原因并给出修复建议。

## 解决的问题

定时任务失败时，告警只告诉你"失败了 + 错误文本"，但常见错误的修复方法用户还得自己查。这个插件把**常见失败模式的知识库**内置到告警里：

```
任务失败 → mark_job_run() → 插件匹配错误模式 → 告警附上"诊断 + 建议修复"
```

## 内置诊断知识库

| 错误特征 | 诊断 | 建议 |
|:---------|:-----|:-----|
| `429 / rate limit / quota` | API 限流 | 查用量面板，降频或升级配额 |
| `timeout / ETIMEDOUT` | 网络/API 超时 | 目标不可达，重试或加超时 |
| `99992402 field validation` | 飞书消息校验失败 | 内容超长/特殊字符，装 text-fallback |
| `99991672 access denied` | 飞书权限不足 | 到开放平台补权限 scope |
| `401 / invalid_api_key` | API Key 无效 | 检查 .env，重新生成 |
| `context length / token` | 上下文超限 | 压缩 prompt，减少注入 |
| `script not found` | 脚本路径错误 | 检查 jobs.json script 字段 |
| `empty response` | 模型空响应 | 重试，查 API 状态 |
| `ImportError` | 依赖缺失 | 安装对应 Python 包 |
| `OOM / killed` | 内存不足 | 减少数据量，查容器限制 |

未匹配到已知模式时，告警会提示查看日志。

## 安装

```bash
hermes plugins install <owner>/<repo>/cron-error-analyzer
hermes plugins enable cron-error-analyzer
```

## 告警示例

```
🔧 Cron 失败诊断: 每日数据备份
  任务: 每日数据备份
  Job ID: abc123def456
  诊断: 飞书消息校验失败
  建议修复: 消息内容被飞书 API 拒绝（常见于超长/特殊字符）。
  原始错误: [99992402] field validation failed ...
```

## License

MIT
