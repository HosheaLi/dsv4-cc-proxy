# Phase 4: SSE State Machine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-06
**Phase:** 04-sse-state-machine
**Areas discussed:** 模块文件组织, 状态机设计, 多工具并行调用处理, SSE 事件生命周期
**Mode:** discuss

---

## 模块文件组织

| Option | Description | Selected |
|--------|-------------|----------|
| 独立 sse.py | 新建 `dsv4_cc_proxy/codex/sse.py`，暴露 `translate_sse_stream()` 主函数。职责清晰，与 Phase 2 D-01 决策一致 | ✓ |
| 合并到 translate.py | 在现有 translate.py 中添加 SSE 状态机函数。但 translate.py 已达 291 行 | |

**User's choice:** 独立 `sse.py`（推荐选项）
**Notes:** 与 Phase 2 决策一致，proxy.py 已有 SSE 过滤独立于请求处理的先例

## 函数拆分粒度

| Option | Description | Selected |
|--------|-------------|----------|
| 异步生成器 + `_` 内部辅助函数 | `translate_sse_stream(async generator) -> async generator`，与 proxy.py 的 `filtered_stream()` 模式一致 | ✓ |
| 类封装状态机 | 用 class 封装状态，破坏纯函数无类模式 | |
| 回调函数注册 | 灵活但增加复杂度，现有代码无此模式 | |

**User's choice:** 异步生成器 + `_` 内部辅助函数（推荐选项）

---

## 状态机设计

| Option | Description | Selected |
|--------|-------------|----------|
| 隐式状态追踪 | 局部变量 `current_output_type` + `active_tool_indices: set`，与 proxy.py `thinking_indices: set` 一致 | ✓ |
| 显式状态枚举 | enum State + 转换表，引入类定义破坏模式 | |
| 无状态追踪 | 每个 chunk 独立处理，容易遗漏类型转换事件 | |

**User's choice:** 隐式状态追踪（推荐选项）
**Notes:** 当前 ≤5 种状态，局部变量足矣，不需要增加抽象层

---

## 多工具并行调用处理

| Option | Description | Selected |
|--------|-------------|----------|
| Set 追踪活跃 indices | 维护 `active_tool_indices: set[int]`，新 index → item.added，已知 index → delta，finish_reason 遍历关闭 | ✓ |
| Dict 映射 per-index 状态 | 更丰富但当前不需要，Responses API function_call_arguments.delta 只输出 delta 文本 | |
| 假设单工具调用 | Codex 经常并行调用多个 shell 命令，不适用 | |

**User's choice:** Set 追踪活跃 indices（推荐选项）

---

## SSE 事件生命周期

| Option | Description | Selected |
|--------|-------------|----------|
| 基于 chunk 内容推断 | 首 chunk → created+in_progress，首个 delta.content → text item.added，首个 delta.tool_calls → function_call item.added，finish_reason → done+completed | ✓ |
| 基于 DeepSeek 事件类型 | 依赖 finish_reason='tool_calls' vs 'stop' 区分，DeepSeek 事件类型不稳定 | |
| 双阶段收集 | 先收集全部再生成，失去流式优势 | |

**User's choice:** 基于 chunk 内容推断（推荐选项）

---

## Reasoning → Text 转换

| Option | Description | Selected |
|--------|-------------|----------|
| delta.content 首次出现时关闭 reasoning | 收到首个 delta.content 时，若当前有活跃 reasoning item，先发 reasoning done，再发 text added | ✓ |
| finish_reason 时统一关闭 | 不符合 Responses API 规范（reasoning 和 text 应该是两个不同的 output_item） | |

**User's choice:** delta.content 首次出现时关闭 reasoning（推荐选项）

---

## thinking 参数映射

| Option | Description | Selected |
|--------|-------------|----------|
| translate_request 中补充映射 | 在 translate_request() 中添加 `reasoning.effort` → `thinking: {type: enabled}` 映射。Phase 2 D-12 推迟到本 Phase | ✓ |
| sse.py 流翻译时处理 | 流阶段不应关心请求参数，应在请求阶段就确定 | |
| 不做映射 | 会导致 DeepSeek 不返回 reasoning_content，推理能力丢失 | |

**User's choice:** translate_request 中补充映射（推荐选项）

---

## Claude's Discretion

- SSE 行解析和缓冲的具体实现细节
- `response.created` 和 `response.in_progress` 事件中的元数据字段
- 内部辅助函数的具体拆分
- 日志记录的详细级别
- 上游流中断时的优雅关闭策略
