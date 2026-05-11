# V2EX 帖子

## 标题

做了个让 Claude Code 在 DeepSeek V4 上稳定跑的代理，免费 + 开源

## 正文

Claude Code 很强大，但官方只走 Anthropic API。DeepSeek V4 实现了 Anthropic 兼容接口，但有 3 个不兼容坑：

1. tool_use 消息缺 thinking 块 → 400 错误
2. Claude Code 默认发 `thinking.type=adaptive` → DeepSeek 不支持，流式截断
3. DeepSeek 无条件返回 thinking SSE 事件 → 导致 Tool result missing

一个一个排查出来，写了个轻量代理在中间透明修复，让 Claude Code 在 DeepSeek V4 上稳定跑。

**dsv4-cc-proxy**：https://github.com/HosheaLi/dsv4-cc-proxy

特点：
- 纯 Python，Starlette + httpx，无外部服务依赖
- 22 个单元测试覆盖各种边界情况
- pip 安装、Homebrew、Docker 三种安装方式
- macOS launchd 自启、Windows 计划任务、Linux systemd
- GitHub Actions CI 全自动测试 + PyPI + Docker Hub + Homebrew 自动发布

Quick Start：

```bash
pip install dsv4-cc-proxy
dsv4-cc-proxy
```

Homebrew 用户：

```bash
brew install hosheali/tap/dsv4-cc-proxy
brew services start hosheali/tap/dsv4-cc-proxy
```

然后把 Claude Code 的 `ANTHROPIC_BASE_URL` 设成 `http://localhost:16889` 就行。

欢迎 star、提 issue、PR。
