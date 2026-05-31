# dsv4-cc-proxy

**DeepSeek Anthropic API 兼容性代理** — 让 Claude Code 在 DeepSeek V4 模型上稳定运行。

## 架构概要

```
proxy/dsv4_cc_proxy/           # 包源码
proxy/tests/                   # 测试
scripts/                       # 各平台启动脚本
Dockerfile                     # Docker 多阶段构建
```

三层处理（`POST /v1/messages`）:
1. **thinking 注入**: assistant tool_use 前补空 thinking 块
2. **请求标准化**: adaptive → disabled，移除 reasoning_effort
3. **SSE 过滤**: 剥离 DeepSeek 无条件返回的 thinking/thinking_delta/signature_delta

## 重要索引

| 内容 | 位置 |
|------|------|
| 发布历史 | `CHANGELOG.md` |
| 发布文档 | `docs/dev/RELEASE.md` |
| 设计文档 | `docs/dev/deepseek-thinking-proxy.md` |
| 推广文案 | `docs/promotional/` |
| 贡献指南 | `CONTRIBUTING.md` |

## 维护

- 版本号唯一来源: `dsv4_cc_proxy/_version.py`
- 测试: `pip install .[test] && pytest tests/ -v`
- 构建: `python -m build`
