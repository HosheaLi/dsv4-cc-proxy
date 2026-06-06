# Roadmap: dsv4-cc-proxy Codex 支持

## Overview

为现有 dsv4-cc-proxy 增加 OpenAI Responses API 兼容层，让 Codex CLI 能通过 DeepSeek V4 模型运行。从零搭建 `codex/` 子包（vendor isolation 模式），实现输入翻译、工具转换、SSE 状态机、路由集成，最终发布 v1.9.0。不影响现有 Anthropic 代理功能。

## Phases

- [x] **Phase 1: Foundation & Config** - codex/ 子包骨架、模型映射配置、测试基础设施 (2026-06-05)
- [ ] **Phase 2: Request Translation** - Responses API input 翻译为 Chat Completions messages
- [ ] **Phase 3: Tool Support** - 工具格式转换与 Schema 自动修复
- [ ] **Phase 4: SSE State Machine** - 流式事件翻译（文本/推理/工具调用/类型转换）
- [ ] **Phase 5: Route Integration** - HTTP handler、认证透传、压缩端点
- [ ] **Phase 6: Testing & Release** - 全面测试、文档更新、版本发布

## Phase Details

### Phase 1: Foundation & Config (✅ Complete — 2026-06-05)
**Goal**: Codex 子包可用，模型映射可配置且确定
**Depends on**: Nothing (first phase)
**Requirements**: CODX-16, CODX-17, CODX-18
**Success Criteria** (what must be TRUE):
  1. ✅ Developer can set `CODEX_DEFAULT_MODEL` env var to control default DeepSeek target model
  2. ✅ Developer can set `CODEX_MODEL_MAP` JSON env var for custom model name-to-model mappings
  3. ✅ Any model name sent by Codex (including unmapped ones) resolves to a valid DeepSeek model string — no 404 errors
  4. ✅ `dsv4_cc_proxy.codex` is importable and `config.py` exposes clean resolution API
**Plans**: 1 plan (1/1 complete)
**Verification**: 28 tests passed, coverage ≥80%, code review with 5 findings (0 critical)

Plans:
- [x] 01-01-PLAN.md — 搭建 codex/ 子包骨架，实现模型映射配置系统和测试基础设施

### Phase 2: Request Translation
**Goal**: Responses API 输入正确翻译为 Chat Completions messages 格式
**Depends on**: Phase 1
**Requirements**: CODX-03, CODX-04, CODX-11, CODX-14
**Success Criteria** (what must be TRUE):
  1. Responses API `input` array (message / function_call / function_call_output items) translates to correct Chat messages sequence
  2. `instructions` field merges with developer role messages into a single system message at the top
  3. `function_call` items attach tool_calls to the preceding assistant message (creating synthetic assistant if needed)
  4. `function_call_output` items translate to tool role messages
  5. Reasoning content is maintained across turns: assistant messages with tool_calls always include `reasoning_content: ""` to satisfy DeepSeek validation
**Plans**: 2 plans (0/2 complete)

Plans:
- [x] 02-01-PLAN.md — 创建 translate.py，实现完整的 Responses → Chat 请求翻译逻辑
- [x] 02-02-PLAN.md — 创建 test_translate.py，覆盖所有翻译行为的综合测试套件

### Phase 3: Tool Support
**Goal**: 工具定义正确转换并自动修复以满足 DeepSeek 严格 Schema 校验
**Depends on**: Phase 2
**Requirements**: CODX-07, CODX-10
**Success Criteria** (what must be TRUE):
  1. Codex flat tool format `{type, name, description, parameters}` converts to Chat nested format `{type, function: {name, description, parameters}}`
  2. Tool schema auto-repair strips unsupported fields: `default`, `readOnly`, `writeOnly`, `examples`
  3. Schema repair handles nested `$defs` or `properties` recursively — all levels are cleaned
  4. Empty `enum` arrays in schemas are removed before sending to DeepSeek
**Plans**: TBD

### Phase 4: SSE State Machine
**Goal**: DeepSeek Chat 流式事件翻译为 Responses API 标准 SSE 事件序列
**Depends on**: Phase 2, Phase 3
**Requirements**: CODX-05, CODX-06, CODX-08, CODX-09, CODX-12, CODX-13, CODX-15
**Success Criteria** (what must be TRUE):
  1. Chat `delta.content` translates to SSE `response.output_text.delta` events with correct text content
  2. Chat `delta.reasoning_content` translates to SSE `response.reasoning_text.delta` events
  3. Chat `delta.tool_calls` translates to SSE `response.function_call_arguments.delta` events with correct index tracking
  4. Full SSE event lifecycle fires in order: `response.created` → `response.in_progress` → (output_item.added / delta events) → `response.output_item.done` → `response.completed`
  5. Multiple parallel tool calls (different indices) produce independent, correctly-ordered event streams — no index collision
  6. Type transitions (reasoning → text → tool_calls) fire proper `output_item.done` + new `output_item.added` events
**Plans**: TBD

### Phase 5: Route Integration
**Goal**: `/v1/responses` HTTP 端点正常工作，不影响现有路由
**Depends on**: Phase 4
**Requirements**: CODX-01, CODX-02, CODX-19, CODX-20, CODX-21
**Success Criteria** (what must be TRUE):
  1. `POST /v1/responses` with `stream: true` returns text/event-stream SSE with correct event types
  2. `POST /v1/responses` with `stream: false` returns complete JSON response in Responses API format
  3. `POST /v1/responses/compact` returns HTTP 501 with valid error JSON body
  4. Existing `POST /v1/messages` routes continue to work — all 22 existing proxy tests pass
  5. `Authorization` header from Codex request passes through to DeepSeek API unchanged
**Plans**: TBD

### Phase 6: Testing & Release
**Goal**: 所有 codex 模块测试通过，文档完整，版本发布
**Depends on**: Phase 5
**Requirements**: (All codex requirements implicitly covered by test verification)
**Success Criteria** (what must be TRUE):
  1. All codex modules (config, translate, tools) have >=80% test line coverage
  2. All 22 existing proxy tests still pass — zero regressions
  3. New environment variables (`CODEX_DEFAULT_MODEL`, `CODEX_MODEL_MAP`, `CODEX_UPSTREAM`) documented in README
  4. Version is bumped to 1.9.0 and tagged
  5. New `/v1/responses` endpoints documented in relevant docs
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Config | 1/1 | Complete | 2026-06-05 |
| 2. Request Translation | 0/2 | Planning | - |
| 3. Tool Support | 0/0 | Not started | - |
| 4. SSE State Machine | 0/0 | Not started | - |
| 5. Route Integration | 0/0 | Not started | - |
| 6. Testing & Release | 0/0 | Not started | - |
