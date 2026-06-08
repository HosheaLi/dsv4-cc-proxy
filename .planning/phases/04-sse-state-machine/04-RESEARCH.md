# Phase 4: SSE State Machine - Research

**Researched:** 2026-06-06
**Domain:** SSE stream translation (DeepSeek Chat Completions delta → OpenAI Responses API events)
**Confidence:** HIGH

## Summary

This phase delivers `dsv4_cc_proxy/codex/sse.py` — an async generator that consumes a DeepSeek Chat Completions SSE chunk stream and yields OpenAI Responses API SSE event lines. The core challenge is an implicit state machine that tracks the current output item type (`reasoning` / `text` / `tool_call`) and manages type transitions, parallel tool call indices, and the complete `response.created` → `response.completed` lifecycle.

The design is heavily constrained by context decisions (D-01 through D-15), with Claude's discretion on implementation details of line buffering, event building, and error handling. The implementation must follow established codex/ patterns: pure functions, no classes, async generator from proxy.py's `filtered_stream()`, `_` prefix for internal helpers, `[CODEX]` logger prefix.

**Primary recommendation:** Build the state machine as a single async generator function with 3–4 well-factored internal helper functions, all pure logic with no side effects. Use local variables for implicit state tracking (per D-06). The translation of the first Chat delta chunk triggers `response.created` + `response.in_progress`; each type transition triggers `output_item.done` + new `output_item.added` + content_part.added as appropriate.

## User Constraints (from CONTEXT.md)

### Locked Decisions

#### 模块文件组织
- **D-01:** 新建 `dsv4_cc_proxy/codex/sse.py`，与 Phase 2 D-01 决策一致（"Phase 4 再加 sse.py"）。职责分离：`translate.py`=请求翻译，`sse.py`=流翻译。proxy.py 已有 SSE 过滤独立于请求处理的先例
- **D-02:** `__init__.py` 导出 `translate_sse_stream`，与 `resolve_model`、`translate_request`、`convert_tools` 并列

#### 函数架构
- **D-03:** 主函数 `translate_sse_stream(async generator) -> async generator` — 异步生成器模式，接收上游 Chat SSE chunk 流，yield Responses API SSE 事件。与 `proxy.py` 的 `filtered_stream()` 异步生成器模式一致
- **D-04:** 内部辅助函数使用 `_` 前缀，遵循现有约定（`_filter_sse_line`、`_inject_thinking_blocks`、`_extract_content_text` 等）
- **D-05:** 保持纯函数 + 无类模式 — 整个 codex/ 子包无 class 定义，sse.py 保持一致

#### 状态机设计
- **D-06:** 隐式状态追踪 — 用局部变量追踪 `current_output_type`（None / "reasoning" / "text" / "tool_call"）+ `active_tool_indices: set[int]`。每次收到 delta 比较新旧类型决定是否触发 `done` + `added` 事件。与 `proxy.py` 的 `thinking_indices: set` 模式一致，简单直接

#### 多工具并行调用
- **D-07:** Set 追踪活跃 tool_call indices — 维护 `active_tool_indices: set[int]`。新 index → 发送 `response.output_item.added`(function_call) + `response.function_call_arguments.delta`。已知 index → 只发送 `response.function_call_arguments.delta`。finish_reason 时遍历所有活跃 indices 发送各自的 `output_item.done`

#### SSE 事件生命周期
- **D-08:** 基于 chunk 内容推断事件触发时机：
  - 首个 chunk（含 `role: "assistant"`）→ `response.created` + `response.in_progress`
  - 首个 `delta.reasoning_content` → 当前无活跃 output_item 时发送 `response.output_item.added`(reasoning) + `response.reasoning_text.delta`
  - 首个 `delta.content` → 若当前活跃 reasoning item，先发送 reasoning `output_item.done`；再发送 `response.output_item.added`(message) + `response.content_part.added` + `response.output_text.delta`
  - 首个 `delta.tool_calls[新 index]` → 若当前活跃 text item，先发送 text `output_item.done`；再发送 `response.output_item.added`(function_call) + `response.function_call_arguments.delta`
  - `finish_reason` → 所有活跃 output_item 发送 `output_item.done` + `response.completed`

#### Reasoning → Text 转换
- **D-09:** `delta.content` 首次出现时关闭 reasoning item — 如果当前有活跃的 reasoning item，先发 `response.output_item.done`(reasoning)，再发 text `output_item.added` + `content_part.added`。不在 finish_reason 时才关闭（不符合 Responses API 规范，reasoning 和 text 应该是两个不同的 output_item）

#### thinking 参数映射
- **D-10:** `reasoning.effort` → `thinking` 参数映射在 `translate_request()` 中补充（Phase 2 D-12 推迟到本 Phase）。从 `request_body` 提取 `reasoning.effort`（low/medium/high 任一值），设置 `body["thinking"] = {"type": "enabled"}`。DeepSeek V4 不支持 effort 分级，统一启用即可
- **D-11:** `reasoning` 顶级字段在 mapping 后从 body 中移除（不发送给 DeepSeek，Chat API 不认此字段）

#### SSE 事件格式
- **D-12:** Output Events 格式含 `event:` 前缀行，与 OpenAI Responses API SSE 标准一致

#### 测试
- **D-13:** 独立测试文件 `tests/test_sse.py`
- **D-14:** 纯函数/异步生成器测试，覆盖率 >=90%
- **D-15:** 测试覆盖 8 个场景（基础文本流、推理流、推理→文本转换、工具调用流、多工具并行、文本→工具转换、完整生命周期、边界情况）

### Claude's Discretion
- SSE 行解析和缓冲的具体实现细节
- `response.created` 和 `response.in_progress` 事件中携带的具体元数据字段
- 内部辅助函数的具体拆分
- 日志记录的详细级别
- 异常处理策略：上游流中断时如何优雅关闭

### Deferred Ideas (OUT OF SCOPE)
无

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CODX-05 | SSE 流式事件翻译正确：Chat `delta.content` → Responses `response.output_text.delta` | DeepSeek `delta.content` 片段直接映射为 Responses `response.output_text.delta`，content_index=0, output_index 追踪当前输出项位置 |
| CODX-06 | SSE 事件序列完整：`response.created` → ... → `response.completed` | 首个 chunk 触发 created+in_progress；中间经历 output_item.added/delta 序列；finish_reason 时 close all active items + completed |
| CODX-08 | SSE 工具调用增量翻译正确：`delta.tool_calls` → `response.function_call_arguments.delta` | DeepSeek `delta.tool_calls[index].function.arguments` 片段映射为 `function_call_arguments.delta`，首次出现该 index 时先发 output_item.added |
| CODX-09 | 多工具并行调用各自独立事件流 | `active_tool_indices: set[int]` 追踪 todo：新 index → added+delta；已知 index → 仅 delta；finish_reason 遍历所有 index 发各自的 done |
| CODX-12 | `reasoning.effort` → DeepSeek `thinking` 参数映射 | 在 `translate_request()` 中提取 `reasoning.effort`(low/medium/high) → `body["thinking"] = {"type": "enabled"}`，移除 `reasoning` 字段 |
| CODX-13 | SSE 推理增量翻译正确：`delta.reasoning_content` → `response.reasoning_text.delta` | DeepSeek `delta.reasoning_content` 片段映射为 Responses `reasoning_text.delta`，首个 reasoning_content 触发 output_item.added(reasoning) |
| CODX-15 | 推理→文本→工具的类型转换正确处理 output_item.done + 新 output_item.added | 状态机通过 `current_output_type` 局部变量追踪：reasoning→text 时先 done reasoning 再 added text；text→tool_call 时先 done text 再 added function_call |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SSE chunk 解析 | Proxy / Middleware | — | sse.py 接收已解码的 Chat SSE 行（上游已传输解码），需进一步解析为结构化 delta |
| 状态机翻译 | Proxy / Middleware | — | `translate_sse_stream()` 是纯函数翻译层，无网络/IO 依赖，运行在代理进程内 |
| thinking 参数映射 | API Request Translation | — | `translate_request()` 已处理请求翻译（Phase 2），本 Phase 在其基础上增补 reasoning.effort 处理 |
| 事件标识符生成 | Proxy / Middleware | — | `response.created` 中的 response id 由 sse.py 内部生成，无外部依赖 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `json` | 3.10+ | JSON 序列化/反序列化 | 项目约束"零额外依赖"，已用于全项目 |
| Python stdlib `logging` | 3.10+ | 日志记录 | 全项目统一使用 `logging.getLogger("deepseek-proxy")` |
| Python stdlib `copy` | 3.10+ | 深拷贝保护（用于 translate.py reasoning.effort 映射） | translate.py 已有 deepcopy 模式 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 隐式状态跟踪（局部变量） | 显式状态机类（enum StateMachine） | 5 种状态用局部变量足矣；隐式跟踪遵循 D-06 且与 proxy.py 的 thinking_indices:set 一致 |
| 手动行缓冲 | aiter_lines 或其他第三方解析 | 零额外依赖约束；proxy.py 已有成熟的 buffer + `\n` 分割模式复用 |

**Installation:**
```bash
pip install -e ".[test]"
```
（无新依赖，仅安装开发依赖的 pytest）

## Architecture Patterns

### System Architecture Diagram

```
DeepSeek Chat Completions API
         │
         │ SSE stream: data: {delta chunk}\n
         ▼
┌──────────────────────────────────┐
│  translate_sse_stream()          │
│  (async generator)               │
│                                  │
│  State:                          │
│    current_output_type: None     │
│    │  "reasoning"                │
│    │  "text"                     │
│    │  "tool_call"                │
│    active_tool_indices: set[int] │
│    item_id counter: int          │
│    output_index counter: int     │
│                                  │
│  For each delta chunk:           │
│    │                             │
│    ├─ 1st chunk (role) ──────────┤── response.created + in_progress
│    │                             │
│    ├─ reasoning_content ─────────┤── type transition? 
│    │                             │    → done prev item + added reasoning
│    │                             │    → reasoning_text.delta
│    ├─ content ───────────────────┤── type transition?
│    │                             │    → done reasoning + added message
│    │                             │    → content_part.added + output_text.delta
│    ├─ tool_calls ───────────────┤── new index?
│    │                             │    → done text + added function_call
│    │    Yes                      │    → function_call_arguments.delta
│    │    No (known index)         │    → function_call_arguments.delta only
│    │                             │
│    └─ finish_reason ─────────────┤── output_item.done × N
│                                  │  → response.completed
│                                  │
│         yield: "event: type\ndata: {json}\n\n"
│                                  │
└──────────────────────────────────┘
         │
         │ Responses API SSE event lines
         ▼
    Phase 5 HTTP StreamingResponse
```

### Recommended Project Structure

```
dsv4_cc_proxy/codex/
├── __init__.py          # 导出 translate_sse_stream (新增导出)
├── config.py            # 不变
├── translate.py         # 修改: 添加 reasoning.effort → thinking 映射
├── tools.py             # 不变
└── sse.py               # 新建: SSE 状态机翻译

tests/
├── test_codex.py        # 不变
├── test_translate.py    # 修改: 添加 reasoning.effort 映射测试
├── test_tools.py        # 不变
└── test_sse.py          # 新建: SSE 状态机测试 (新建)
```

### Pattern 1: Async Generator + State Tracked via Locals

**What:** The core pattern used throughout this codebase. An `async for` loop consumes upstream bytes/chunks, maintains state in local variables, and yields translated output. No class, no global state, no external side effects beyond logging.

**When to use:** This is the mandatory pattern for sse.py (D-03, D-05). Every stream processing function in the project uses this pattern.

**Example (from proxy.py L357-383):**
```python
# Source: dsv4_cc_proxy/proxy.py filtered_stream()
async def filtered_stream():
    thinking_indices = set()
    event_types = []
    all_filtered = []
    buffer = ""

    try:
        async for chunk in upstream_resp.aiter_bytes():
            text = chunk.decode("utf-8", errors="replace")
            buffer += text

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                filtered, thinking_indices = _filter_sse_line(line, thinking_indices)
                if filtered is not None:
                    yield (filtered + "\n").encode("utf-8")
        # flush remaining buffer
        if buffer.strip():
            filtered, thinking_indices = _filter_sse_line(buffer, thinking_indices)
            if filtered is not None:
                yield (filtered + "\n").encode("utf-8")
    except Exception:
        logger.exception("upstream stream read error")
```

### Pattern 2: Implicit State Transition via `_` Internal Helpers

**What:** Internal functions prefixed with `_` handle each type of state transition, returning `(event_lines, new_state)` tuples. The main generator function orchestrates the state machine, calling helpers when delta content types change.

**When to use:** For each type transition (reasoning→text, text→tool_call, finish_reason) and event building (response.created payload, output_item.added payload, delta payloads).

**Example (conceptual for sse.py):**
```python
def _build_output_item_added(output_index: int, item_type: str, **kwargs) -> str:
    """Build a response.output_item.added SSE event string."""
    item = {"id": f"item_{output_index}", "type": item_type, "status": "in_progress"}
    if item_type == "function_call":
        item.update({"name": kwargs["name"], "call_id": kwargs["call_id"], "arguments": ""})
    elif item_type == "message":
        item["role"] = "assistant"
        item["content"] = []
    # ...
    data = {"type": "response.output_item.added", "item": item, "output_index": output_index}
    return f"event: response.output_item.added\ndata: {json.dumps(data)}\n\n"
```

### Anti-Patterns to Avoid
- **Single massive function:** The state machine logic must be split into `_` helpers. A single 300-line function doing everything is hard to test and violates existing patterns.
- **Mutable state in closures or classes:** D-05 requires no class definitions. Keep state in local variables of the async generator.
- **Assuming reasoning and text never coexist:** Though rare, DeepSeek could emit `reasoning_content` and `content` in the same chunk. Handle gracefully by processing reasoning first, then content.
- **Forgetting to emit `content_part.added`:** After reasoning→text transition, the text output_item needs both `output_item.added` and `content_part.added` before `output_text.delta`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON serialization | Custom SSE event string builder | `json.dumps(data)` + f-string | stdlib json 已用于全项目，处理 Unicode/escaping 正确性 |
| Async generator infrastructure | Custom async iterator protocols | `async for` + `yield` | Python 原生，proxy.py 已验证模式 |
| Logging | print() statements | `logger = logging.getLogger("deepseek-proxy")` | 全项目统一日志系统，支持级别控制、文件输出 |

**Key insight:** This phase adds zero new dependencies. Every capability needed (JSON parsing, async iteration, logging) is already in the project's Python stdlib + async generator toolkit.

## Common Pitfalls

### Pitfall 1: Missing `event:` Prefix Lines

**What goes wrong:** Responses API SSE events require BOTH an `event:` prefix line AND a `data:` line. Forgetting the `event:` line causes Codex CLI to misinterpret the event type, silently dropping deltas.

**Why it happens:** Chat Completions SSE uses only `data:` lines with a `type` field in the JSON. The Responses API uses `event:` + `data:` dual-line format. Developers familiar with Chat SSE naturally forget the `event:` line.

**How to avoid:** Always emit events in this exact format:
```
event: response.output_text.delta
data: {"type":"response.output_text.delta","delta":"text","item_id":"msg_1","output_index":0,"content_index":0}

```
Note the blank line (double `\n\n`) terminating each event.

**Warning signs:** Codex shows no visible output but no error either; SSE events appear correct in curl but Codex ignores them.

### Pitfall 2: Index Collision with Parallel Tool Calls

**What goes wrong:** Multiple parallel tool calls have different indices. When the `submit_output` round sends back tool results, the new response's tool calls start at index 0 again. Tracking `active_tool_indices` with a set that persists across responses would cause stale indices to interfere.

**Why it happens:** `active_tool_indices` is per-response state. A new response starts fresh with no active items. If the set is not re-initialized per call to `translate_sse_stream()`, old indices leak.

**How to avoid:** `active_tool_indices` is a local variable in the async generator function. Each invocation of `translate_sse_stream()` gets its own fresh set. No persistence across calls.

**Warning signs:** Function call arguments from a previous response appear in the current response's deltas.

### Pitfall 3: Reasoning → Text Transition Misses content_part.added

**What goes wrong:** The reasoning→text transition emits `output_item.done(reasoning)` then `output_item.added(message)` but forgets `content_part.added`, causing Codex to not display any text content for the message item.

**Why it happens:** The transition logic for reasoning→text requires 3 events in sequence: done reasoning, added message, added content_part. The content_part step is easy to overlook.

**How to avoid:** The state transition helper for `reasoning → text` must emit in order:
1. `response.output_item.done` (reasoning item)
2. `response.output_item.added` (message item with empty content[])
3. `response.content_part.added` (output_text content part)
4. `response.output_text.delta` (first text delta)

### Pitfall 4: finish_reason Emitted Multiple Times

**What goes wrong:** DeepSeek may emit only one `finish_reason` but the state machine could process it twice if the termination detection is not idempotent. Duplicate `response.completed` events cause Codex to error or behave unpredictably.

**Why it happens:** The state machine needs to detect that `finish_reason` was already processed and skip subsequent occurrences.

**How to avoid:** Use a boolean flag `_completed = False` that is set to True after emitting `response.completed`. Check this flag before processing any subsequent `finish_reason` or delta content.

### Pitfall 5: Empty response with only finish_reason

**What goes wrong:** DeepSeek may return only a finish_reason chunk with no prior deltas (e.g., when content filter blocks output). The state machine must emit `response.created` + `response.in_progress` + `response.completed` without crashing.

**How to avoid:** Initialize `_is_first_chunk = True`. The first chunk (even if finish_reason-only) triggers created+in_progress. If there are no output items to close, skip output_item.done and go directly to completed.

## Code Examples

### DeepSeek Chat Delta Chunk Format (Input)

```json
// First chunk: role + optional content/reasoning
// Source: api-docs.deepseek.com verified from web search
{"id":"...","choices":[{"index":0,"delta":{"content":"","role":"assistant"},"finish_reason":null}],"created":...,"model":"deepseek-v4-pro","object":"chat.completion.chunk"}

// Reasoning content delta
{"choices":[{"index":0,"delta":{"reasoning_content":"Let me think..."},"finish_reason":null}]}

// Text content delta
{"choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

// Tool call first delta (with id + name)
{"choices":[{"index":0,"delta":{"role":"assistant","content":null,"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"get_weather","arguments":""}}]},"finish_reason":null}]}

// Tool call arguments delta
{"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"loc"}}}]}}]}

// Multiple parallel tool calls
{"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"ation\": \"SF\"}"}},{"index":1,"function":{"arguments":"{\"cit"}}}]}}]}

// Final chunk with finish_reason
{"choices":[{"index":0,"delta":{},"finish_reason":"stop","usage":{...}}]}

// Tool call finish
{"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}
```

### OpenAI Responses API SSE Events (Output)

```json
// Source: developers.openai.com/api/docs/guides/streaming-responses

event: response.created
data: {"type":"response.created","response":{"id":"resp_123","object":"response","created":...,"model":"deepseek-v4-pro","status":"in_progress","usage":null}}

event: response.in_progress
data: {"type":"response.in_progress","response":{"id":"resp_123","object":"response","status":"in_progress"}}

event: response.output_item.added
data: {"type":"response.output_item.added","item":{"id":"item_0","type":"reasoning","status":"in_progress","summary":[]},"output_index":0}

event: response.reasoning_text.delta
data: {"type":"response.reasoning_text.delta","item_id":"item_0","output_index":0,"content_index":0,"delta":"Let me think...","sequence_number":1}

event: response.output_item.done
data: {"type":"response.output_item.done","item":{"id":"item_0","type":"reasoning","status":"completed"},"output_index":0}

event: response.output_item.added
data: {"type":"response.output_item.added","item":{"id":"item_1","type":"message","role":"assistant","content":[],"status":"in_progress"},"output_index":1}

event: response.content_part.added
data: {"type":"response.content_part.added","item_id":"item_1","output_index":1,"content_index":0,"part":{"type":"output_text","text":""}}

event: response.output_text.delta
data: {"type":"response.output_text.delta","item_id":"item_1","output_index":1,"content_index":0,"delta":"Hello world","sequence_number":2}

event: response.output_item.done
data: {"type":"response.output_item.done","item":{"id":"item_1","type":"message","status":"completed","content":[{"type":"output_text","text":"Hello world"}]},"output_index":1}

event: response.completed
data: {"type":"response.completed","response":{"id":"resp_123","object":"response","status":"completed","usage":{"input_tokens":100,"output_tokens":50,"output_tokens_details":{"reasoning_tokens":30},"total_tokens":150}}}

// Tool call variant

event: response.output_item.added
data: {"type":"response.output_item.added","item":{"id":"fc_0","type":"function_call","name":"get_weather","call_id":"call_1","arguments":"","status":"in_progress"},"output_index":2}

event: response.function_call_arguments.delta
data: {"type":"response.function_call_arguments.delta","item_id":"fc_0","call_id":"call_1","output_index":2,"delta":"{\"location\": \"San Francisco\"","sequence_number":5}

event: response.function_call_arguments.done
data: {"type":"response.function_call_arguments.done","item_id":"fc_0","call_id":"call_1","output_index":2,"delta":"{\"location\": \"San Francisco\"}"}

event: response.output_item.done
data: {"type":"response.output_item.done","item":{"id":"fc_0","type":"function_call","name":"get_weather","call_id":"call_1","arguments":"{\"location\": \"San Francisco\"}","status":"completed"},"output_index":2}
```

### translate_sse_stream() Async Generator Skeleton

```python
# Source: Pattern from proxy.py filtered_stream(), adapted for sse.py per D-03/D-06
async def translate_sse_stream(
    upstream: AsyncIterable[dict],
) -> AsyncGenerator[str, None]:
    """翻译 DeepSeek Chat delta chunk 流为 Responses API SSE 事件流。

    Args:
        upstream: Chat Completions delta dict 的异步迭代器。

    Yields:
        Responses API SSE 事件字符串（含 event: + data: 行）。
    """
    # 状态追踪（D-06 隐式状态）
    current_output_type: str | None = None  # None | "reasoning" | "text" | "tool_call"
    active_tool_indices: set[int] = set()   # D-07
    is_first_chunk = True
    _completed = False
    sequence = 0
    response_id = f"resp_{uuid4().hex[:12]}"
    output_counter = 0

    try:
        async for chunk in upstream:  # chunk 已解码为 dict
            choices = chunk.get("choices", [])
            if not choices:
                continue

            delta = choices[0].get("delta", {})
            finish_reason = choices[0].get("finish_reason")

            if _completed:
                continue  # Pitfall 4: idempotent finish

            # ---- 首个 chunk: created + in_progress (D-08) ----
            if is_first_chunk:
                yield _build_response_created(response_id, ...)
                yield _build_response_in_progress(response_id)
                is_first_chunk = False

            # ---- reasoning_content ----
            reasoning = delta.get("reasoning_content")
            if reasoning:
                new_type = "reasoning"
                if new_type != current_output_type and current_output_type is not None:
                    yield _build_output_item_done(current_output_type, ...)
                if current_output_type != "reasoning":
                    output_counter += _yield_item_added(output_counter, "reasoning", ...)
                    current_output_type = "reasoning"
                sequence += 1
                yield _build_reasoning_text_delta(...)

            # ---- content (text) ----
            content_text = delta.get("content")
            if content_text is not None:
                new_type = "text"
                if new_type != current_output_type and current_output_type is not None:
                    yield _build_output_item_done(current_output_type, ...)
                if current_output_type != "text":
                    # 需要 emit added + content_part.added
                    output_counter += _yield_item_added(output_counter, "message", ...)
                    yield _build_content_part_added(...)
                    current_output_type = "text"
                sequence += 1
                yield _build_output_text_delta(...)

            # ---- tool_calls ----
            tool_calls = delta.get("tool_calls")
            if tool_calls:
                new_indices = set()
                for tc in tool_calls:
                    idx = tc.get("index")
                    new_indices.add(idx)
                    # D-07: 已知 index 只发 delta，新 index 先 added
                    if idx not in active_tool_indices:
                        # 如果当前有 text item，先 close
                        if current_output_type == "text":
                            yield _build_output_item_done("text", ...)
                        output_counter += _yield_item_added(output_counter, "function_call", ...)
                        active_tool_indices.add(idx)
                        current_output_type = "tool_call"
                    sequence += 1
                    yield _build_function_call_arguments_delta(idx, ...)

            # ---- finish_reason ----
            if finish_reason:
                # D-08: close all active items
                for idx in sorted(active_tool_indices):
                    yield _build_output_item_done("function_call", ...)
                if current_output_type in ("reasoning", "text"):
                    yield _build_output_item_done(current_output_type, ...)
                yield _build_response_completed(response_id, ...)
                _completed = True

    except Exception:
        logger.exception("[CODEX] SSE stream translation error")
        # Claude's discretion: error handling strategy
```

### reasoning.effort → thinking Mapping (in translate_request())

```python
# Source: D-10 from CONTEXT.md
# Add after body.copy() in translate_request() body processing:

# D-10: reasoning.effort → thinking mapping
reasoning = body.get("reasoning", {})
if isinstance(reasoning, dict) and reasoning.get("effort") in ("low", "medium", "high"):
    body["thinking"] = {"type": "enabled"}
# D-11: remove reasoning field after mapping
body.pop("reasoning", None)
```

### SSE Event Builder Helper

```python
# Source: Pattern inferred from OpenAI streaming docs and D-12
def _build_sse_event(event_type: str, data: dict) -> str:
    """构建完整 SSE 事件行（含 event: 前缀 + data: JSON + 空行终止）。

    Args:
        event_type: SSE 事件类型（如 "response.output_text.delta"）
        data: JSON 可序列化的事件荷载

    Returns:
        完整 SSE 事件字符串（含尾随双换行）
    """
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Chat Completions API SSE (only `data:` lines) | Responses API SSE (`event:` + `data:` dual lines) | 2025 Q1 (OpenAI Responses API launch) | SSE 格式完全不同，需要主动翻译层 |
| DeepSeek R1 streaming (reasoning_content only) | DeepSeek V4 streaming (reasoning_content + content + tool_calls) | 2025 Q4 (DeepSeek V4 release) | 推理内容可以在同一流中与文本/工具调用共存，需要状态机管理类型转换 |
| Anthropic Messages API SSE (content block events) | Chat Completions delta format (choice-based) | 项目架构决策 | 本项目已在 proxy.py 中处理 Anthropic SSE 过滤；codex/ 子包需要相反方向的翻译 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DeepSeek V4 的 delta chunk 中 `reasoning_content` 和 `content` 不会出现在同一 delta 中 | Stream Structure | 若同时出现，状态机需要按 priority 顺序处理（先 reasoning 再 content） |
| A2 | DeepSeek V4 的 `finish_reason` 值包括 `"stop"`、`"length"`、`"tool_calls"`、`"content_filter"` | Stream Structure | 若出现未知 finish_reason 值，应透传给 Responses completed event |
| A3 | OpenAI Responses API 的事件序列要求 `content_part.added` 在 `output_text.delta` 之前 | Event Lifecycle | 若 Codex 不需要 `content_part.added`，可省略简化逻辑 |
| A4 | `response.created` 中的 `response` 对象需包含 `id`、`object`、`created`、`model`、`status` 等字段 | Response Metadata | Codex 可能只依赖 `response.id`；额外字段为兼容性填充 |
| A5 | `sequence_number` 字段在 Responses API SSE 事件中是可选的 | Event Payload | 若 Codex 依赖 sequence_number 去重/排序，必须正确递增生成 |

## Open Questions

1. **response.id 的生成策略**
   - What we know: 需要唯一标识符，现有 proxy.py 不生成 response ID
   - What's unclear: Codex CLI 是否验证 response ID 格式？UUID 是否兼容？
   - Recommendation: 使用 `uuid.uuid4().hex[:12]` 生成短 ID，格式 `resp_<hex>`。这也可以作为 Claude's discretion 自行决定。

2. **output_item 的 id 生成策略**
   - What we know: Responses API 用 `msg_<hex>`、`fc_<hex>`、`rs_<hex>` 等前缀
   - What's unclear: Codex CLI 是否将这些 ID 用于后续的 submit_tool_outputs 调用？
   - Recommendation: 简单递增 `item_{n}` 格式。如果 Codex 需要特定前缀格式，后续可调整。

3. **response.completed 中的 usage 数据**
   - What we know: DeepSeek 在最后一个 chunk 的 `usage` 字段提供 token 计数
   - What's unclear: 是否需要将 DeepSeek 的 usage 映射为 Responses API 的 `output_tokens_details` 格式（含 reasoning_tokens）
   - Recommendation: DeepSeek V4 的 usage 格式与 OpenAI 基本相同，可以直接透传核心字段。reasoning_tokens 在 completion_tokens_details 中。

4. **response.in_progress 是否必须**
   - What we know: 一些 OpenAI Responses 实现跳过 in_progress 事件
   - What's unclear: Codex CLI 是否要求此事件
   - Recommendation: 按 D-08 要求实现。如果 Codex 跳过此事件，日志可验证。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.x |
| Config file | none — pyproject.toml or pytest.ini |
| Quick run command | `python3 -m pytest tests/test_sse.py -v --tb=short` |
| Full suite command | `python3 -m pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CODX-05 | Chat `delta.content` → `response.output_text.delta` | unit | `python3 -m pytest tests/test_sse.py::test_text_stream -x` | No (Wave 0) |
| CODX-06 | Full lifecycle: created → in_progress → ... → completed | unit | `python3 -m pytest tests/test_sse.py::test_full_lifecycle -x` | No (Wave 0) |
| CODX-08 | `delta.tool_calls` → `response.function_call_arguments.delta` | unit | `python3 -m pytest tests/test_sse.py::test_tool_call_stream -x` | No (Wave 0) |
| CODX-09 | Multiple parallel tool calls, independent streams | unit | `python3 -m pytest tests/test_sse.py::test_parallel_tool_calls -x` | No (Wave 0) |
| CODX-12 | `reasoning.effort` → `thinking: {"type":"enabled"}` | unit | `python3 -m pytest tests/test_translate.py::test_reasoning_effort_mapping -x` | No (Wave 0) |
| CODX-13 | `delta.reasoning_content` → `response.reasoning_text.delta` | unit | `python3 -m pytest tests/test_sse.py::test_reasoning_stream -x` | No (Wave 0) |
| CODX-15 | reasoning→text→tool_calls type transitions | unit | `python3 -m pytest tests/test_sse.py::test_type_transition_chain -x` | No (Wave 0) |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_sse.py -v --tb=short`
- **Per wave merge:** `python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_sse.py` — new file, all 8+ test scenarios (D-15)
- [ ] `tests/test_translate.py` — add `test_reasoning_effort_mapping` test (CODX-12, D-10)
- [ ] `dsv4_cc_proxy/codex/sse.py` — new file, the async generator + helper functions

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Delta chunk 解析用 try/except 保护；json.loads() 不可信输入前已由 upstream 处理 |
| V6 Cryptography | no | 无加密操作 |
| V12 File I/O | no | 无文件 I/O |

### Known Threat Patterns for SSE Translation

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed delta chunk causing crash | Denial of Service | try/except around json.loads(); continue on parse failure |
| Infinite stream denial of service | Denial of Service | Async generator pattern with proper cancellation via finally block |
| Information leak through error messages | Information Disclosure | Error logging uses `logger.exception()` with no user data in message |

## Sources

### Primary (HIGH confidence)
- dsv4_cc_proxy/proxy.py — `filtered_stream()` async generator pattern, `thinking_indices: set` tracking pattern, line buffering
- dsv4_cc_proxy/codex/translate.py — Pure function pattern, `_` prefix convention, `[CODEX]` logger, deepcopy pattern
- dsv4_cc_proxy/codex/tools.py — Deepcopy immutability pattern, `_` internal helpers
- dsv4_cc_proxy/codex/__init__.py — Export pattern for new `translate_sse_stream`
- tests/test_proxy.py — AAA test pattern, Set-based SSE filtering test pattern
- tests/test_translate.py — Async generator test patterns (23 tests), monkeypatch pattern for env vars
- design doc: /Users/lihaoxuan/.claude/plans/codex-deepseek-v4-responses-api-deepsee-cryptic-phoenix.md — SSE event mapping table, lifecycle rules

### Secondary (MEDIUM confidence)
- [CITED: developers.openai.com/api/docs/guides/streaming-responses] — Responses API SSE event types: response.created, response.in_progress, response.output_item.added, response.output_text.delta, response.reasoning_text.delta, response.function_call_arguments.delta, response.completed
- [CITED: api-docs.deepseek.com/api/create-chat-completion] — DeepSeek Chat delta format: delta.content, delta.reasoning_content, delta.tool_calls, finish_reason values

### Tertiary (LOW confidence)
- [ASSUMED] sequence_number field in Responses SSE events — verified as optional, can be omitted or sequentially incremented
- [ASSUMED] DeepSeek V4 delta format matches documented Chat Completions format — verified via multiple community implementations

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, patterns directly from existing code
- Architecture: HIGH — locked decisions (D-01 through D-15) define all structural choices; Claude's discretion areas are well-bounded
- Pitfalls: HIGH — Pitfalls 1-5 derived from known patterns in SSE translation and existing codebase issues

**Research date:** 2026-06-06
**Valid until:** 2026-07-06 (stable API surface — both OpenAI Responses API and DeepSeek Chat API are mature)
