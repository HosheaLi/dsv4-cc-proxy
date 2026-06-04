# dsv4-cc-proxy

## What This Is

DeepSeek V4 ↔ 编程 AI CLI 兼容性代理。双向协议翻译，让 Claude Code（Anthropic Messages API）和 Codex（OpenAI Responses API）能通过 DeepSeek V4 模型运行。Starlette + httpx 异步代理，目前 434 行代码，22 个单元测试。

## Core Value

让开发者能用任意编程 AI 工具（Claude Code / Codex）+ DeepSeek V4 模型组合，无需等待官方兼容支持。

## Requirements

### Validated

- ✓ Anthropic Messages API 翻译 — 现有功能（thinking 注入/标准化/SSE 剥离，3 层修复）
- ✓ DeepSeek V4 Pro/Flash 双模型支持
- ✓ SSE 流式响应处理
- ✓ 环境变量配置

### Active

- [ ] **CODX-01**: Codex CLI 可通过代理使用 DeepSeek V4 模型进行对话
- [ ] **CODX-02**: Codex 工具调用（shell、文件操作等）正常工作，包括并行工具调用
- [ ] **CODX-03**: DeepSeek 推理/思考能力在 Codex 中可用（reasoning→thinking 映射）
- [ ] **CODX-04**: Codex 多轮对话正常，reasoning 状态在多轮间正确维护
- [ ] **CODX-05**: 灵活的模型映射（Codex 模型名 → DeepSeek 模型，可配置）
- [ ] **CODX-06**: 工具定义自动修复（适配 DeepSeek 严格的 Schema 校验）
- [ ] **CODX-07**: 压缩端点正确处理（返回 501 触发 Codex 内联压缩）

### Out of Scope

- WebSocket 支持 — Codex v0.128+ 需要，先 SSE 降级（后续可加）
- 内置工具模拟（web_search、code_interpreter）— DeepSeek 不支持
- Anthropic 端点作为 Plan B — 后续迭代
- 多提供商路由（同时支持多个上游）— 后续迭代
- 桌面 GUI / Web 管理面板 — 非核心需求

## Context

**现有架构**：Starlette 异步代理，Anthropic Messages API ↔ DeepSeek Anthropic 端点的双向翻译。env var 配置。纯字典操作，无 Pydantic 模型。

**Codex CLI 使用 OpenAI Responses API**（`POST /v1/responses`），与 DeepSeek 的 Chat Completions API 不同。需要增加 `/v1/responses` 路由，将 Responses 格式翻译为 Chat Completions 格式。

**已调研 15+ 个同类项目**：
- 最佳参考：codex-relay（Rust，模型映射+配置生成）、ai-adapter（Rust，vendor isolation 模式）
- 参考借鉴：CoDeepSeedeX（Python，工具自动修复）、responses-proxy（Rust，流水线架构）

**技术决策已在方案文档中确定**：`/Users/lihaoxuan/.claude/plans/codex-deepseek-v4-responses-api-deepsee-cryptic-phoenix.md`

## Constraints

- **技术栈**：Python 3.10+、Starlette、httpx、零额外依赖
- **兼容性**：不影响现有 Anthropic Messages API 代理功能
- **测试**：纯函数测试模式（参考 `tests/test_proxy.py`），覆盖率 ≥80%

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 子包分离（`codex/` 目录） | vendor isolation 模式，便于后续加 Anthropic Plan B | — Pending |
| Chat Completions 为上游 | 与 Responses API 语义更近 | — Pending |
| 两层模型映射 | 兼顾快速设置和灵活配置 | — Pending |
| 压缩返回 501 | Codex 自动降级到内联压缩 | — Pending |
| 空字符串 reasoning 修复 | 满足 DeepSeek 校验，无需 SQLite 缓存 | — Pending |

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
*Last updated: 2026-06-04 after initialization*
