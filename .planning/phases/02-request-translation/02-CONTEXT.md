# Phase 2: Request Translation - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

将 Responses API 的 `input` 数组翻译为 Chat Completions 的 `messages` 数组。此阶段交付纯转换函数（`translate.py`），接收完整的 Responses API 请求体，返回 Chat Completions 请求体。不涉及 HTTP 路由、流处理或工具格式转换。

成功标准（来自 ROADMAP.md）：
1. `input` 数组（message / function_call / function_call_output items）→ 正确的 Chat messages 序列
2. `instructions` 字段与 developer role 消息合并为一个 system 消息置顶
3. `function_call` items 追加 tool_calls 到前一条 assistant 消息（无前一条时创建合成 assistant）
4. `function_call_output` items → tool role 消息
5. 含 tool_calls 的 assistant 消息确保有 `reasoning_content: ""` 满足 DeepSeek 校验

</domain>

<decisions>
## Implementation Decisions

### 模块文件组织
- **D-01:** 新建 `dsv4_cc_proxy/codex/translate.py`，与技术方案一致。Phase 2 只包含请求翻译逻辑，Phase 4 再加 `sse.py`
- **D-02:** translate.py 只在 `dsv4_cc_proxy/codex/__init__.py` 中导出主翻译函数，与现有 `config.py` 导出 `resolve_model` 风格一致

### 函数架构
- **D-03:** 单一主入口函数 `translate_request(request_body: dict) -> dict` — 纯函数，输入不改动，返回全新字典
- **D-04:** 内部辅助函数全部使用 `_` 前缀（如 `_translate_input_items`、`_merge_system_messages`、`_attach_tool_calls`），只导出 `translate_request`。与 `proxy.py` 中的 `_filter_sse_line`、`_inject_thinking_blocks` 风格一致

### System 消息合并
- **D-05:** `instructions` 顶级字段 + developer role 消息用 `\n\n` 换行符合并为一个 system 消息，放在 messages 数组最前面。如果都为空，不生成 system 消息

### function_call 边界情况
- **D-06:** function_call 前无 assistant 消息时，创建合成 assistant 消息：`{"role": "assistant", "content": None, "tool_calls": [...]}`

### 内容提取
- **D-07:** message 的 content 为数组格式时，提取所有 `input_text` type 的 `text` 字段用 `\n` 拼接；content 为纯字符串时直接使用

### 未知类型处理
- **D-08:** 遇到未知 input item 类型，记录 WARNING 日志并跳过该 item，不中断翻译流程

### Reasoning 多轮维护
- **D-09:** Reasoning 项折叠到后续第一个 assistant 消息的 `reasoning_content` 字段。多个 reasoning 项拼接。后续无 assistant 消息时不注入 reasoning
- **D-10:** Reasoning 项内容提取：从 `content` 数组中提取 `type: "reasoning_text"` 的 `text` 字段拼接；同时保留 `summary` 文本
- **D-11:** 翻译时检查每个 assistant 消息：如果有 `tool_calls` 但没有 `reasoning_content` 字段，注入 `reasoning_content: ""` 满足 DeepSeek 校验
- **D-12:** Reasoning → thinking 参数映射**不在 Phase 2 实现**，留给 Phase 4（SSE 流处理阶段）
- **D-13:** 异常序列（如 reasoning → user 而非 reasoning → assistant）只发 WARNING 跳过 reasoning，不做结构性修复

### Claude's Discretion
- 内部辅助函数的具体拆分粒度（如 `_extract_content_text`、`_merge_system_messages`、`_translate_input_item` 等）
- 日志记录的详细级别
- 函数参数校验的严格程度
- Docstring 风格

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 架构与设计
- `/Users/lihaoxuan/.claude/plans/codex-deepseek-v4-responses-api-deepsee-cryptic-phoenix.md` §输入翻译 — Responses → Chat 字段映射表、边界情况处理、两层防御策略
- `docs/dev/deepseek-thinking-proxy.md` — 现有 thinking 注入/标准化/SSE 剥离三层处理，理解旧代码模式

### 现有代码
- `dsv4_cc_proxy/codex/config.py` — 已有模型映射实现，理解纯函数模式和模块级 env var 风格
- `dsv4_cc_proxy/codex/__init__.py` — 子包导出模式，translate.py 需保持一致
- `dsv4_cc_proxy/proxy.py` — 现有代理实现（434 行），理解纯函数+无类模式、`_` 前缀约定、日志记录风格
- `dsv4_cc_proxy/_version.py` — 版本号来源（当前 1.8.0）

### 测试
- `tests/test_proxy.py` — 现有测试模式：AAA 模式、monkeypatch env var、reload 模块、纯函数直接导入
- `tests/test_codex.py` — Phase 1 测试（6 个），理解 codex 模块测试约定

### 需求
- `.planning/REQUIREMENTS.md` — CODX-03, CODX-04, CODX-11, CODX-14（本 Phase 的需求条目）
- `.planning/ROADMAP.md` — Phase 2 成功标准

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `dsv4_cc_proxy/codex/config.py` 的 `resolve_model()` — 翻译后的请求体中 model 字段需要调用此函数解析
- `dsv4_cc_proxy/proxy.py` 的 `_get_client()` — 后续 Phase 5 路由集成时可直接复用

### Established Patterns
- **纯函数 + 无类**：整个 proxy.py 和 config.py 无 class 定义，translate.py 保持一致
- **模块级配置**：`os.getenv` 模块级取值 + 默认值，如 `CODEX_UPSTREAM`
- **日志**：`logging.getLogger("deepseek-proxy")`，统一 logger 名称
- **下划线前缀**：内部函数用 `_` 前缀（`_filter_sse_line`、`_inject_thinking_blocks`、`_parse_model_map`），公共 API 不加前缀
- **JSON 序列化**：`json.dumps/loads` + `ensure_ascii=False`

### Integration Points
- `translate_request()` 将由 Phase 5 的 HTTP handler 调用，在发送到 DeepSeek Chat Completions API 之前转换请求体
- `translate.py` 需要导入 `dsv4_cc_proxy.codex.config` 中的 `CODEX_UPSTREAM`（构建完整请求 URL）
- 后续 Phase 3 `tools.py` 的工具格式转换在翻译流程中调用（工具定义转换与消息翻译分离）

</code_context>

<specifics>
## Specific Ideas

- 技术方案中已明确定义了输入翻译映射表（Responses → Chat），讨论确认了更细的边界策略
- 推理的两层防御策略：Phase 2 实现第一层（输入翻译层折叠 reasoning + 空字符串注入），Phase 4 实现第二层（SSE 流翻译）
- 与现有 Anthropic 代理的 thinking 注入逻辑保持对称：都为满足 DeepSeek 校验而做预处理

</specifics>

<deferred>
## Deferred Ideas

无 — 讨论全程在 Phase 2 范围内

</deferred>

---

*Phase: 02-request-translation*
*Context gathered: 2026-06-05*
