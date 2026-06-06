# Phase 3: Tool Support - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning

<domain>
## Phase Boundary

工具定义格式转换与 Schema 自动修复。将 Codex 的扁平工具格式转换为 DeepSeek Chat 嵌套格式，并自动剥离 DeepSeek 严格 Schema 校验不兼容的字段。此阶段交付 `tools.py`（纯转换函数），不涉及 SSE 流中的工具调用增量翻译（Phase 4）或 HTTP 路由（Phase 5）。

成功标准（来自 ROADMAP.md）：
1. Codex 扁平格式 `{type, name, description, parameters}` → Chat 嵌套格式 `{type, function: {name, description, parameters}}`
2. Schema 自动修复剥离不兼容字段：`default`、`readOnly`、`writeOnly`、`examples`
3. Schema 修复递归处理所有嵌套层级（`$defs`、`properties`、`items`、`anyOf`）
4. 空 `enum` 数组在发送给 DeepSeek 前移除

</domain>

<decisions>
## Implementation Decisions

### 模块边界与集成
- **D-01:** 新建 `dsv4_cc_proxy/codex/tools.py`，暴露单一主函数 `convert_tools(tools: list[dict]) -> list[dict]`
- **D-02:** `translate_request()` 调用 `convert_tools()` 处理 tools 字段，一条翻译链完成请求转换。调用位置在 messages 翻译之后、最终输出之前（Claude's Discretion）
- **D-03:** `__init__.py` 只导出 `convert_tools`，与 `resolve_model`、`translate_request` 并列

### Schema 修复策略
- **D-04:** 只剥离不兼容字段，不自动补全 `required`/`additionalProperties`。原因：Codex 不一定开启 strict 模式，自动补全可能引入不符合用户预期的约束
- **D-05:** 剥离字段清单（全量清理）：
  - `default`（所有类型上剥离，不区分 number/integer）
  - `readOnly` / `writeOnly`
  - `examples`
  - `minLength` / `maxLength`（DeepSeek strict 模式不支持）
  - `minItems` / `maxItems`（同上）
  - 空 `enum: []` 数组

### Schema 修复粒度
- **D-06:** 递归清理所有嵌套层级，不限深度。遍历路径：`properties` 的子属性、`$defs` 内的引用、`anyOf` 的各分支、嵌套 `object` 的 properties、`array` 的 `items`
- **D-07:** 遇到无法安全修复的 schema（不符合 JSON Schema 规范、非字典类型 parameters），抛出明确异常，不静默吞掉

### Codex 工具格式处理
- **D-08:** 处理标准 OpenAI function 格式 `{type: "function", name, description, parameters}`。未知 type 字段记录 WARNING + 原样透传（与 translate.py D-08 风格一致）
- **D-09:** 已知 type=function 但缺少 `parameters` 字段时，不做 schema 修复但正常保持格式转换

### 函数内部设计
- **D-10:** `convert_tools()` 主函数内部拆分两个私有辅助函数（Claude's Discretion）：
  - `_convert_tool_format()` — 处理 CODX-07：扁平 → 嵌套格式转换
  - `_clean_schema()` — 处理 CODX-10：递归剥离不兼容字段 + 清理空 enum
  - 内部函数使用 `_` 前缀，与 translate.py 风格一致

### 测试
- **D-11:** 独立测试文件 `tests/test_tools.py`，与 `test_codex.py`、`test_translate.py` 并列
- **D-12:** 纯函数测试，覆盖率 ≥90%
- **D-13:** 测试覆盖场景：
  1. 格式转换：扁平→嵌套、已嵌套保持、多工具数组
  2. Schema 修复：剥离各字段（default/readOnly/writeOnly/examples/minLength/maxLength/minItems/maxItems）、空 enum 清理
  3. 递归清理：`$defs` 引用、`anyOf` 分支、嵌套 object properties、array items
  4. 边界：空 tools 列表、无 parameters 字段、未知 type 透传
  5. 错误：无效 schema（非字典 parameters）抛异常

### Claude's Discretion
- `convert_tools()` 内部 `_convert_tool_format()` 和 `_clean_schema()` 的具体拆分粒度
- `translate_request()` 中 tools 转换调用的精确位置（在哪个步骤之间）
- 日志记录的详细级别
- 异常类型选择

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 架构与设计
- `/Users/lihaoxuan/.claude/plans/codex-deepseek-v4-responses-api-deepsee-cryptic-phoenix.md` §工具处理 — 工具格式转换规范、自动修复字段清单、CoDeepSeedeX 参考
- `docs/dev/deepseek-thinking-proxy.md` — 现有 Anthropic 代理设计，理解纯函数 + 无类模式

### 现有代码
- `dsv4_cc_proxy/codex/translate.py` — 翻译函数实现（286 行），理解集成模式（`translate_request()` 调用链）、`_` 前缀约定、WARNING 日志风格
- `dsv4_cc_proxy/codex/config.py` — 配置模块，理解纯函数 + 模块级 env var 风格
- `dsv4_cc_proxy/codex/__init__.py` — 子包导出模式，tools.py 需一致
- `dsv4_cc_proxy/proxy.py` — 现有代理实现（434 行），理解工具定义格式、`_has_tool_use()` 等 Anthropic 工具处理逻辑

### 测试
- `tests/test_translate.py` — Phase 2 测试（562 行，23 个用例），理解 AAA 模式、边界覆盖风格
- `tests/test_codex.py` — Phase 1 测试（6 个），理解 codex 模块测试约定

### 外部参考
- DeepSeek Function Calling 官方文档：https://api-docs.deepseek.com/guides/function_calling — strict 模式 JSON Schema 约束、支持/不支持的字段清单
- 参考实现：CoDeepSeedeX（Python，工具自动修复策略）

### 需求
- `.planning/REQUIREMENTS.md` — CODX-07, CODX-10（本 Phase 的需求条目）
- `.planning/ROADMAP.md` — Phase 3 成功标准

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `translate_request()` 中已预留注释：工具定义格式转换由 Phase 3 处理。集成位置明确
- `dsv4_cc_proxy/codex/config.py` 的 `resolve_model()` 已在 translate.py 流程中被调用 — tools.py 可参考相同调用模式
- `translate.py` 的 `_extract_content_text()` 展示了递归/深层遍历的代码风格，`_clean_schema()` 可复用类似递归模式

### Established Patterns
- **纯函数 + 无类**：整个 proxy.py 和 codex/ 子包无 class 定义，tools.py 保持一致
- **`_` 前缀内部函数**：`_filter_sse_line`、`_inject_thinking_blocks`、`_parse_model_map`、`_extract_content_text`、`_merge_system_messages` — tools.py 的 `_convert_tool_format()`、`_clean_schema()` 对齐
- **WARNING 日志**：未知/异常输入记录 `logger.warning("[CODEX] ...")` 并跳过/透传
- **单一公共导出**：`__init__.py` 中只导出模块的主函数，内部函数不暴露
- **JSON 序列化**：`json.dumps/loads` + `ensure_ascii=False`

### Integration Points
- `translate_request()` 将在翻译流程中调用 `convert_tools()`，替换 tools 字段内容
- `convert_tools()` 不导入 translate.py 的任何内容（单向依赖：translate.py → tools.py）
- 后续 Phase 5 的 HTTP handler 通过 `translate_request()` 间接触发 tools 转换

</code_context>

<specifics>
## Specific Ideas

- 参考了 CoDeepSeedeX 的 tool schema auto-repair 策略，但只做剥离不做补全（保守策略）
- 与现有 Anthropic 代理的 thinking 注入逻辑保持对称：都为满足 DeepSeek 校验而做预处理
- DeepSeek strict 模式下 `default` 仅支持 number/integer 类型，但统一所有类型剥离简化逻辑

</specifics>

<deferred>
## Deferred Ideas

- **strict 模式自动补全**（自动填充 required + additionalProperties: false）— 若后续 Codex 默认开启 strict 模式，可添加环境变量切换
- **工具定义验证器**（独立验证 schema 合法性）— 可作为额外增强但非当前需求
- **非 strict 模式兼容策略分离** — 当前单一策略适用于两种模式

</deferred>

---

*Phase: 03-tool-support*
*Context gathered: 2026-06-06*
