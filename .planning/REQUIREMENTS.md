# Requirements: dsv4-cc-proxy Codex 支持

**Defined:** 2026-06-04
**Core Value:** 让 Codex CLI 能通过 DeepSeek V4 模型运行，无协议兼容性障碍

## v1 Requirements

Requirements for adding Codex (OpenAI Responses API) support.

### 协议翻译

- [ ] **CODX-01**: 代理接受 `POST /v1/responses` 请求并返回 SSE 流式响应（stream: true）
- [ ] **CODX-02**: 代理接受 `POST /v1/responses` 请求并返回完整 JSON 响应（stream: false）
- [ ] **CODX-03**: Responses API 的 `input` 数组正确翻译为 Chat Completions 的 `messages` 数组
- [ ] **CODX-04**: `instructions` 字段翻译为 system 消息（与 developer role 消息合并）
- [ ] **CODX-05**: SSE 流式事件翻译正确：Chat `delta.content` → Responses `response.output_text.delta`
- [ ] **CODX-06**: SSE 事件序列完整：`response.created` → `response.in_progress` → ... → `response.completed`

### 工具调用

- [ ] **CODX-07**: Codex 扁平工具格式 → Chat 嵌套格式转换正确
- [ ] **CODX-08**: SSE 工具调用增量翻译正确：`delta.tool_calls` → `response.function_call_arguments.delta`
- [ ] **CODX-09**: 多工具并行调用（不同 index）各自独立事件流
- [ ] **CODX-10**: 工具参数 Schema 自动修复（剥离 DeepSeek 不支持的字段：default/readOnly/writeOnly）
- [ ] **CODX-11**: 工具调用输入项（function_call/function_call_output）正确翻译

### 推理/思考

- [ ] **CODX-12**: `reasoning.effort` → DeepSeek `thinking` 参数映射（low/medium/high → type: enabled）
- [ ] **CODX-13**: SSE 推理增量翻译正确：`delta.reasoning_content` → `response.reasoning_text.delta`
- [ ] **CODX-14**: 推理内容在多轮间正确维护（assistant+tool_calls 消息注入 `reasoning_content: ""`）
- [ ] **CODX-15**: 推理→文本→工具的类型转换正确处理（output_item.done + 新 output_item.added）

### 模型映射

- [ ] **CODX-16**: `CODEX_DEFAULT_MODEL` 环境变量设置默认目标模型
- [ ] **CODX-17**: `CODEX_MODEL_MAP` JSON 映射支持精确匹配 + 前缀匹配
- [ ] **CODX-18**: Codex 发送的任意模型名都有确定的映射结果（不报 404）

### 压缩

- [ ] **CODX-19**: `POST /v1/responses/compact` 返回 501

### 集成

- [ ] **CODX-20**: 代理现有 Anthropic 路由不受影响（`/v1/messages` 正常工作）
- [ ] **CODX-21**: 认证信息透传（Authorization header 原样转发到 DeepSeek）

## v2 Requirements

Deferred to future release.

### 高级功能

- **CODX-22**: WebSocket 支持（Codex v0.128+ 默认使用 WS）
- **CODX-23**: Anthropic 端点 Plan B（推理密集型场景的备选方案）
- **CODX-24**: 内置工具模拟（web_search 通过自定义 function calling 实现）
- **CODX-25**: Codex 配置自动生成（类似 codex-relay `--print-config`）
- **CODX-26**: 磁盘会话存储（调试和崩溃恢复）

## Out of Scope

| Feature | Reason |
|---------|--------|
| WebSocket stream upgrade | 复杂度较高，Codex 可 SSE 降级，后续迭代 |
| 多提供商路由 | 不是当前核心需求，保持单一 DeepSeek 上游 |
| Admin Web UI / Dashboard | 非核心需求，控制台日志已足够 |
| code_interpreter 工具模拟 | DeepSeek 无此能力，且 Codex 本地执行可替代 |
| 桌面应用 / Tray app | 非核心需求 |
| 端到端加密 reasoning 回放 | DeepSeek 不支持，用空字符串方案替代 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CODX-01 | Phase 5 - Route Integration | Pending |
| CODX-02 | Phase 5 - Route Integration | Pending |
| CODX-03 | Phase 2 - Request Translation | Pending |
| CODX-04 | Phase 2 - Request Translation | Pending |
| CODX-05 | Phase 4 - SSE State Machine | Pending |
| CODX-06 | Phase 4 - SSE State Machine | Pending |
| CODX-07 | Phase 3 - Tool Support | Pending |
| CODX-08 | Phase 4 - SSE State Machine | Pending |
| CODX-09 | Phase 4 - SSE State Machine | Pending |
| CODX-10 | Phase 3 - Tool Support | Pending |
| CODX-11 | Phase 2 - Request Translation | Pending |
| CODX-12 | Phase 4 - SSE State Machine | Pending |
| CODX-13 | Phase 4 - SSE State Machine | Pending |
| CODX-14 | Phase 2 - Request Translation | Pending |
| CODX-15 | Phase 4 - SSE State Machine | Pending |
| CODX-16 | Phase 1 - Foundation & Config | Pending |
| CODX-17 | Phase 1 - Foundation & Config | Pending |
| CODX-18 | Phase 1 - Foundation & Config | Pending |
| CODX-19 | Phase 5 - Route Integration | Pending |
| CODX-20 | Phase 5 - Route Integration | Pending |
| CODX-21 | Phase 5 - Route Integration | Pending |

**Coverage:**
- v1 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-04*
*Last updated: 2026-06-04 — phases mapped in roadmap creation*
