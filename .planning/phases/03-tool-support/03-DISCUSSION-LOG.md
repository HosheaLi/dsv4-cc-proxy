# Phase 3: Tool Support - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-06
**Phase:** 03-tool-support
**Areas discussed:** Schema 修复策略, 模块边界, Schema 修复粒度, Codex 工具格式处理, 测试策略与边界, 函数命名与 API 设计

---

## Schema 修复策略

| Option | Description | Selected |
|--------|-------------|----------|
| 只剥离不兼容字段 | 移除 default/readOnly/writeOnly/minLength/maxLength/minItems/maxItems/examples，不修改 required/additionalProperties | ✓ |
| 剥离 + 补全 strict 约束 | 额外自动遍历 object 补全 required + additionalProperties: false | |
| 可配置模式 | 通过环境变量控制是否补全 | |

**User's choice:** 只剥离不兼容字段
**Notes:** Codex 不一定开启 strict 模式，自动补全可能引入不符合用户预期的约束。如果 DeepSeek 报错，由 Codex 侧调整。

---

## 剥离字段范围

| Option | Description | Selected |
|--------|-------------|----------|
| default + readOnly + writeOnly + examples | 核心四个字段 | |
| 以上 + minLength/maxLength/minItems/maxItems | 加上长度/数量约束 | |
| 全部以上 + 空 enum 清理 | 全量清理：default(所有类型)、readOnly、writeOnly、examples、minLength、maxLength、minItems、maxItems、空 enum[] | ✓ |

**User's choice:** 全量清理
**Notes:** ROADMAP 成功标准明确要求空 enum 也要移除。做全量清理。

---

## 模块边界

| Option | Description | Selected |
|--------|-------------|----------|
| tools.py 独立函数，translate_request() 调用 | convert_tools() 被 translate_request() 调用，一条链完成翻译 | ✓ |
| tools.py 独立函数，由 HTTP handler 调用 | Phase 5 handler 分别调用 translate_request() 和 convert_tools() | |
| tools.py 独立函数 + 可选集成 | translate_request(body, repair_tools=True) 参数控制 | |

**User's choice:** tools.py 独立函数，translate_request() 调用
**Notes:** 与现有 `config.resolve_model()` 被 `translate_request()` 调用的模式一致。

---

## translate_request() 中调用位置

| Option | Description | Selected |
|--------|-------------|----------|
| 翻译 messages 之后 | 在流程末尾处理 tools | |
| 翻译 messages 之前 | 先转换 tools 提前发现 schema 错误 | |
| Claude 决定 | — | ✓ |

**User's choice:** Claude's Discretion → messages 翻译后、最终输出前

---

## Schema 修复递归深度

| Option | Description | Selected |
|--------|-------------|----------|
| 递归清理所有嵌套层级 | 不限深度，遍历 $defs/anyOf/nested objects/array items | ✓ |
| 只清理顶层 + 一层嵌套 | 不解引用 $defs/$ref | |
| 参数控制深度 | repair_schema(schema, max_depth=10) | |

**User's choice:** 递归清理所有嵌套层级
**Notes:** 与 ROADMAP "所有层级都被清理" 一致。防御性处理。

---

## 错误处理策略

| Option | Description | Selected |
|--------|-------------|----------|
| 静默降级 — WARNING + 跳过 | 无法修复的 schema 保留原样 | |
| 严格模式 — 抛出异常 | schema 无法解析时抛出明确异常 | ✓ |

**User's choice:** 严格模式 — 验证失败时抛出异常
**Notes:** 静默通过可能导致 DeepSeek 400 错误更难调试。

---

## Codex 工具格式处理

| Option | Description | Selected |
|--------|-------------|----------|
| 仅标准 OpenAI function 格式 | 只处理 {type, name, description, parameters} | |
| 标准 + 预定义工具识别 | 识别 web_search/code_interpreter 并特殊处理 | |
| 标准 + 防御未知格式 | 处理 function 格式 + 未知 type WARNING + 透传 | ✓ |

**User's choice:** 标准格式 + 防御未知格式
**Notes:** 与 translate.py D-08 风格一致。确保未来 Codex 新增工具类型不会崩溃。

---

## 测试文件策略

| Option | Description | Selected |
|--------|-------------|----------|
| 独立文件 test_tools.py | 与 test_codex.py、test_translate.py 并列 | ✓ |
| 合并到 test_codex.py | codex 子包功能集中测试 | |
| 合并到 test_translate.py | 作为翻译流程的一部分测试 | |

**User's choice:** 独立测试文件 test_tools.py
**Notes:** tools.py 是独立模块，独立测试更清晰。

---

## 测试覆盖率目标

| Option | Description | Selected |
|--------|-------------|----------|
| ≥90%，纯函数测试 | 与 Phase 1 config.py 目标一致 | ✓ |
| ≥80%，纯函数测试 | 与项目整体要求一致 | |

**User's choice:** 覆盖率 ≥90%
**Notes:** 测试范围包括格式转换、Schema 修复（各字段剥离 + 空 enum 清理）、递归清理（$defs/anyOf/嵌套）、边界条件、错误处理。

---

## 函数命名与 API 设计

| Option | Description | Selected |
|--------|-------------|----------|
| 单一主函数 convert_tools() | 内部完成 format conversion + schema repair | |
| convert_tools + repair_schema 两个导出 | 分别处理 CODX-07 和 CODX-10 | |
| Claude 决定 | — | ✓ |

**User's choice:** Claude's Discretion → 单一主函数 `convert_tools()`，内部拆分为 `_convert_tool_format()` 和 `_clean_schema()`

---

## Claude's Discretion

- `convert_tools()` 内部 `_convert_tool_format()` 和 `_clean_schema()` 的具体拆分粒度
- `translate_request()` 中 tools 转换调用的精确位置（messages 翻译后）
- 日志记录的详细级别
- 异常类型选择
