# dsv4-cc-proxy

## What This Is

DeepSeek V4 ↔ 编程 AI CLI 兼容性代理。双向协议翻译，让 Claude Code（Anthropic Messages API）和 Codex（OpenAI Responses API）能通过 DeepSeek V4 模型运行。Starlette + httpx 异步代理，v2.0.0 发布。

已发布 v2.0.0：Anthropic Messages API 代理 + OpenAI Responses API 代理，148 个测试，91% 覆盖率。

## Core Value

让开发者能用任意编程 AI 工具（Claude Code / Codex）+ DeepSeek V4 模型组合，无需等待官方兼容支持。

## Requirements

### Validated — Phase 6 (v2.0.0 Release)

全部 codex 需求已在各阶段验证完成：

- ✅ **CODX-01 ~ CODX-21**: 全部 21 个 Codex 需求已通过测试验证（Phases 1-5）
- ✅ **Phase 6 成功标准**：所有 7 项成功标准已达成
  1. ✓ codex 模块测试覆盖率 ≥80%（config 91%, translate 98%, tools 93%, sse 93%）
  2. ✓ proxy.py 87% + __main__.py 86% 覆盖率
  3. ✓ 148 个测试全部通过，零回归
  4. ✓ 环境变量文档已更新（README EN + ZH）
  5. ✓ 版本升至 2.0.0 并提交（_version.py）
  6. ✓ /v1/responses 端点文档已完成（README + codex-integration.md）
  7. ✓ CI 配置 PyPI OIDC Trusted Publishing + Docker semver 标签 + 覆盖率徽章

### Out of Scope

- WebSocket 支持 — Codex v0.128+ 需要，先 SSE 降级（后续可加）
- 内置工具模拟（web_search、code_interpreter）— DeepSeek 不支持
- Anthropic 端点作为 Plan B — 后续迭代
- 多提供商路由（同时支持多个上游）— 后续迭代
- 桌面 GUI / Web 管理面板 — 非核心需求
- Homebrew Tap 发布 — 后续迭代

## Context

**现有架构**：Starlette 异步代理，双协议支持（Anthropic Messages API + OpenAI Responses API）。env var 配置。纯字典操作，无 Pydantic 模型。

**Codex 支持**：`codex/` 子包（vendor isolation 模式），六个模块：config.py（模型映射）、translate.py（请求翻译）、tools.py（工具转换）、sse.py（SSE 状态机）、__init__.py（公共 API）。

**已发布 v2.0.0**：Docker Hub + PyPI + GitHub Release 三渠道。

## Constraints

- **技术栈**：Python 3.10+、Starlette、httpx、零额外依赖
- **兼容性**：不影响现有 Anthropic Messages API 代理功能
- **测试**：纯函数测试模式，覆盖率 ≥80%（当前 91%）

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 子包分离（`codex/` 目录） | vendor isolation 模式 | ✅ 已实现 |
| Chat Completions 为上游 | 与 Responses API 语义更近 | ✅ 已实现 |
| 两层模型映射 | 兼顾快速设置和灵活配置 | ✅ 已实现 |
| 压缩返回 501 | Codex 自动降级到内联压缩 | ✅ 已实现 |
| 空字符串 reasoning 修复 | 满足 DeepSeek 校验 | ✅ 已实现 |
| 版本升至 2.0.0 | Codex 双协议支持是重大里程碑 | ✅ 已实现 |
| PyPI OIDC Trusted Publishing | 安全发布，免 API Token | ⚠ CI 配置已完成，需用户配置 pypi.org |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-07 — v2.0.0 release (Phase 6 testing-release complete, project milestone reached)*
