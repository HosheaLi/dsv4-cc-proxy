# Phase 4: SSE State Machine - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning

<domain>
## Phase Boundary

将 DeepSeek Chat Completions 的 SSE 流式 chunk 翻译为 OpenAI Responses API 标准 SSE 事件序列。此阶段交付 `sse.py`（异步生成器 + 内部辅助函数），接收 Chat Completions SSE 流，输出 Responses API 格式的 SSE 事件流。不涉及 HTTP 路由注册（Phase 5）或请求翻译（Phase 2 已完成）。

成功标准（来自 ROADMAP.md）：
1. Chat `delta.content` → SSE `response.output_text.delta` 事件，文本内容正确
2. Chat `delta.reasoning_content` → SSE `response.reasoning_text.delta` 事件
3. Chat `delta.tool_calls` → SSE `response.function_call_arguments.delta` 事件，index 追踪正确
4. 完整 SSE 事件生命周期按序触发：`response.created` → `response.in_progress` → (output_item.added / delta events) → `response.output_item.done` → `response.completed`
5. 多工具并行调用（不同 index）各自独立事件流，无 index 冲突
6. 类型转换（reasoning → text → tool_calls）正确触发 `output_item.done` + 新 `output_item.added`

</domain>

<decisions>
## Implementation Decisions

### 模块文件组织
- **D-01:** 新建 `dsv4_cc_proxy/codex/sse.py`，与 Phase 2 D-01 决策一致（"Phase 4 再加 sse.py"）。职责分离：`translate.py`=请求翻译，`sse.py`=流翻译。proxy.py 已有 SSE 过滤独立于请求处理的先例
- **D-02:** `__init__.py` 导出 `translate_sse_stream`，与 `resolve_model`、`translate_request`、`convert_tools` 并列

### 函数架构
- **D-03:** 主函数 `translate_sse_stream(async generator) -> async generator` — 异步生成器模式，接收上游 Chat SSE chunk 流，yield Responses API SSE 事件。与 `proxy.py` 的 `filtered_stream()` 异步生成器模式一致
- **D-04:** 内部辅助函数使用 `_` 前缀，遵循现有约定（`_filter_sse_line`、`_inject_thinking_blocks`、`_extract_content_text` 等）
- **D-05:** 保持纯函数 + 无类模式 — 整个 codex/ 子包无 class 定义，sse.py 保持一致

### 状态机设计
- **D-06:** 隐式状态追踪 — 用局部变量追踪 `current_output_type`（None / "reasoning" / "text" / "tool_call"）+ `active_tool_indices: set[int]`。每次收到 delta 比较新旧类型决定是否触发 `done` + `added` 事件。与 `proxy.py` 的 `thinking_indices: set` 模式一致，简单直接

### 多工具并行调用
- **D-07:** Set 追踪活跃 tool_call indices — 维护 `active_tool_indices: set[int]`。新 index → 发送 `response.output_item.added`(function_call) + `response.function_call_arguments.delta`。已知 index → 只发送 `response.function_call_arguments.delta`。finish_reason 时遍历所有活跃 indices 发送各自的 `output_item.done`

### SSE 事件生命周期
- **D-08:** 基于 chunk 内容推断事件触发时机：
  - 首个 chunk（含 `role: "assistant"`）→ `response.created` + `response.in_progress`
  - 首个 `delta.reasoning_content` → 当前无活跃 output_item 时发送 `response.output_item.added`(reasoning) + `response.reasoning_text.delta`
  - 首个 `delta.content` → 若当前活跃 reasoning item，先发送 reasoning `output_item.done`；再发送 `response.output_item.added`(message) + `response.content_part.added` + `response.output_text.delta`
  - 首个 `delta.tool_calls[新 index]` → 若当前活跃 text item，先发送 text `output_item.done`；再发送 `response.output_item.added`(function_call) + `response.function_call_arguments.delta`
  - `finish_reason` → 所有活跃 output_item 发送 `output_item.done` + `response.completed`

### Reasoning → Text 转换
- **D-09:** `delta.content` 首次出现时关闭 reasoning item — 如果当前有活跃的 reasoning item，先发 `response.output_item.done`(reasoning)，再发 text `output_item.added` + `content_part.added`。不在 finish_reason 时才关闭（不符合 Responses API 规范，reasoning 和 text 应该是两个不同的 output_item）

### thinking 参数映射
- **D-10:** `reasoning.effort` → `thinking` 参数映射在 `translate_request()` 中补充（Phase 2 D-12 推迟到本 Phase）。从 `request_body` 提取 `reasoning.effort`（low/medium/high 任一值），设置 `body["thinking"] = {"type": "enabled"}`。DeepSeek V4 不支持 effort 分级，统一启用即可
- **D-11:** `reasoning` 顶级字段在 mapping 后从 body 中移除（不发送给 DeepSeek，Chat API 不认此字段）

### SSE 事件格式
- **D-12:** Output Events 格式含 `event:` 前缀行，与 OpenAI Responses API SSE 标准一致：
  ```
  event: response.created
  data: {"type": "response.created", ...}

  event: response.output_item.added
  data: {"type": "response.output_item.added", ...}
  ```

### 测试
- **D-13:** 独立测试文件 `tests/test_sse.py`，与 `test_translate.py`、`test_tools.py`、`test_codex.py` 并列
- **D-14:** 纯函数/异步生成器测试，覆盖率 ≥90%
- **D-15:** 测试覆盖场景：
  1. 基础文本流：纯 delta.content → output_text.delta 事件
  2. 推理流：delta.reasoning_content → reasoning_text.delta 事件
  3. 推理 → 文本转换：reasoning 结束 → output_item.done + text item.added
  4. 工具调用流：delta.tool_calls → function_call_arguments.delta 事件
  5. 多工具并行：多个不同 index 的工具调用各自独立事件流
  6. 文本 → 工具转换：text item done + function_call item.added
  7. 完整生命周期：created → in_progress → output_item.added → delta × N → output_item.done → completed
  8. 边界：空流、仅 finish_reason（无内容）、重复 finish_reason

### Claude's Discretion
- SSE 行解析和缓冲的具体实现细节（参考 proxy.py 的 `\n` 分割 + buffer 模式）
- `response.created` 和 `response.in_progress` 事件中携带的具体元数据字段（response id 生成策略、model 名称等）
- 内部辅助函数的具体拆分（如 `_build_sse_event`、`_handle_delta`、`_close_active_items` 等）
- 日志记录的详细级别
- 异常处理策略：上游流中断时如何优雅关闭

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 架构与设计
- `/Users/lihaoxuan/.claude/plans/codex-deepseek-v4-responses-api-deepsee-cryptic-phoenix.md` §流式输出翻译 — Chat delta → Responses 事件映射表、SSE 事件生命周期、type transition 规则
- `docs/dev/deepseek-thinking-proxy.md` — 现有 Anthropic 代理 SSE 过滤实现（`filtered_stream()`、行缓冲、thinking_indices 追踪），sse.py 需对齐异步生成器模式

### 现有代码
- `dsv4_cc_proxy/codex/translate.py` — 请求翻译实现（291 行），理解 translate_request() 调用链、`_` 前缀约定、`[CODEX]` 日志风格。本 Phase 需在此补充 reasoning.effort → thinking 映射
- `dsv4_cc_proxy/codex/tools.py` — 工具格式转换（160 行），理解嵌套工具格式 `{type, function: {name, ...}}`、纯函数 + deepcopy 模式
- `dsv4_cc_proxy/codex/config.py` — 配置模块（84 行），理解纯函数 + 模块级 env var 风格
- `dsv4_cc_proxy/codex/__init__.py` — 子包导出模式（当前导出 resolve_model/convert_tools/translate_request），sse.py 需一致
- `dsv4_cc_proxy/proxy.py` — 核心代理 SSE 过滤实现（`filtered_stream()` 异步生成器、行缓冲 `\n` 分割 + buffer、`thinking_indices: set` 追踪、`_filter_sse_line()` 行过滤、`_build_response_headers()`），sse.py 的异步生成器和 Set 追踪直接复用此模式

### 测试
- `tests/test_translate.py` — Phase 2 测试（562 行，23 用例），理解 AAA 模式、异步生成器测试模式
- `tests/test_tools.py` — Phase 3 测试（305 行，21 用例），理解 codex 模块测试约定

### 需求
- `.planning/REQUIREMENTS.md` — CODX-05, CODX-06, CODX-08, CODX-09, CODX-12, CODX-13, CODX-15（本 Phase 的需求条目）
- `.planning/ROADMAP.md` — Phase 4 成功标准

### 外部参考
- OpenAI Responses API SSE 事件格式参考 — 理解标准事件类型和字段结构
- DeepSeek Chat Completions API 文档 — 理解 delta chunk 格式（delta.content/delta.reasoning_content/delta.tool_calls）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `proxy.py` 的 `filtered_stream()` 异步生成器 — 行缓冲（`\n` 分割 + buffer 累积）、Set 追踪模式（`thinking_indices`）、`data: ` 前缀解析、JSON 事件类型分发。sse.py 的 `translate_sse_stream()` 直接复用这些模式
- `proxy.py` 的 `_build_response_headers()` — 了解 SSE 响应头构建，Phase 5 路由集成时参考
- `codex/tools.py` 的 `convert_tools()` — 工具格式已在请求翻译阶段处理为嵌套格式，sse.py 不需要关心工具定义格式

### Established Patterns
- **异步生成器 + 行缓冲**：`proxy.py` L357-405 `filtered_stream()` — `async for chunk in upstream.aiter_bytes()` → decode → buffer 累积 → `\n` 分割 → 逐行处理 → yield。sse.py 输入已是 SSE chunk（Chat 格式），输出 yield Responses 格式 SSE 行
- **Set 追踪模式**：`proxy.py` 用 `thinking_indices: set` 追踪 thinking blocks。sse.py 用 `active_tool_indices: set` 追踪活跃工具调用 — 模式完全相同
- **`_` 前缀内部函数**：整个代码库统一约定
- **`[CODEX]` 日志前缀**：`logger = logging.getLogger("deepseek-proxy")`，`%s` 风格格式化
- **纯函数 + 无类**：整个 codex/ 子包保持此约束

### Integration Points
- `translate_sse_stream()` 由 Phase 5 的 HTTP handler 调用，消费 Chat Completions SSE 流 → 输出 Responses API SSE 流
- sse.py 被 translate.py 单向依赖（translate.py 调用 convert_tools 处理工具定义，sse.py 独立于 translate.py）
- 后续 Phase 5 需要 `__init__.py` 导出 `translate_sse_stream` 供路由 handler 使用

</code_context>

<specifics>
## Specific Ideas

- 设计文档中的 SSE 事件映射表是明确的实现参考，讨论确认了所有关键转换时机
- 与现有 Anthropic 代理的 SSE 过滤逻辑保持对称：都是异步生成器 + Set 追踪 + 行缓冲模式
- 状态机"隐式追踪"而非显式状态枚举 — 当前 ≤5 种状态，局部变量足矣
- `reasoning.effort` 映射统一启用 thinking（DeepSeek V4 不支持 effort 分级），与 Phase 2 的"空字符串 reasoning 注入"形成完整的推理支持两层防御

</specifics>

<deferred>
## Deferred Ideas

无 — 讨论全程在 Phase 4 范围内

</deferred>

---

*Phase: 04-sse-state-machine*
*Context gathered: 2026-06-06*
