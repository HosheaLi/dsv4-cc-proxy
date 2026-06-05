# Phase 2: Request Translation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-05
**Phase:** 02-request-translation
**Areas discussed:** 模块文件组织, 函数架构, 边界情况处理, 推理(reasoning)多轮维护

---

## 模块文件组织

| Option | Description | Selected |
|--------|-------------|----------|
| 新建 translate.py | 所有请求翻译逻辑放 dsv4_cc_proxy/codex/translate.py，与技术方案一致 | ✓ |
| 新建 translate.py + sse.py 骨架 | 提前创建 sse.py 空文件为 Phase 4 预留 | |
| 合并到现有文件 | 翻译逻辑直接放 __init__.py 或 config.py | |

**User's choice:** 新建 translate.py — 与技术方案一致，后续 Phase 4 加 sse.py 时边界清晰

---

## 函数架构

| Option | Description | Selected |
|--------|-------------|----------|
| 单一入口，返回新字典 | `translate_request(request_body: dict) -> dict`，纯函数，输入不改动 | ✓ |
| 多步拆解，内部函数可导出 | 子函数可独立测试和导出 | |
| in-place 修改 | 直接修改传入的 request_body | |

**User's choice:** 单一入口 + 返回新字典，内部函数用 `_` 前缀，只导出主函数

**Notes:** 与 proxy.py 风格一致（`_filter_sse_line`、`_inject_thinking_blocks` 都以下划线前缀）

---

## 边界情况处理

### System 消息合并

| Option | Description | Selected |
|--------|-------------|----------|
| 换行符合并 | `\n\n` 连接 instructions + developer 消息 | ✓ |
| 空格合并 | 单个空格连接 | |
| 保留多条 system | 不合并，按顺序保留 | |

**User's choice:** `\n\n` 换行符合并

### function_call 无前导 assistant

| Option | Description | Selected |
|--------|-------------|----------|
| 创建合成 assistant | 插入 `{role: assistant, content: None, tool_calls: [...]}` | ✓ |
| 报错/跳过 | 跳过并记录警告 | |
| 追加到最近的 user | 不符合 OpenAI/DeepSeek 格式规范 | |

**User's choice:** 创建合成 assistant 消息

### 内容格式提取

| Option | Description | Selected |
|--------|-------------|----------|
| 提取 input_text 的 text | 数组提取 input_text 块 text 字段拼接，字符串直接使用 | ✓ |
| 提取 input_text + input_image | 同时提取图片 URL（DeepSeek 不支持多模态） | |
| 原样保留数组 | 不提取，原样传递 content 数组 | |

**User's choice:** 提取 input_text 的 text 字段，`\n` 拼接

### 未知 input 类型

| Option | Description | Selected |
|--------|-------------|----------|
| 警告并跳过 | WARNING 日志 + 跳过 item | ✓ |
| 抛出异常 | ValueError 中断翻译 | |
| 原样透传 | 追加到 messages 末尾 | |

**User's choice:** 警告并跳过，不中断翻译流程

---

## 推理(reasoning)多轮维护

### Reasoning 合并策略

| Option | Description | Selected |
|--------|-------------|----------|
| 合并到后续 assistant | reasoning 折叠到后续第一个 assistant 的 reasoning_content | ✓ |
| 创建独立消息 | 单独生成一条空 content 的 assistant 消息 | |
| 忽略 reasoning | 直接丢弃 | |

**User's choice:** 合并到后续 assistant 消息的 reasoning_content

### 空字符串注入

| Option | Description | Selected |
|--------|-------------|----------|
| 注入空字符串 | 有 tool_calls 但无 reasoning_content 时注入 `""` | ✓ |
| 不做处理 | 留给后续 Phase | |
| 创建推理缓存 | 跨请求缓存（技术方案已否定） | |

**User's choice:** 注入 `reasoning_content: ""`

### 异常序列处理

| Option | Description | Selected |
|--------|-------------|----------|
| 不处理 | WARNING 跳过 reasoning，假设输入格式合法 | ✓ |
| 容错处理 | 尝试修复异常序列 | |

**User's choice:** 不处理异常序列，只 WARNING 跳过

### Reasoning → thinking 参数映射

| Option | Description | Selected |
|--------|-------------|----------|
| 不需要 | Phase 2 只做消息翻译，参数映射留给 Phase 4 | ✓ |
| 需要映射 | 同时设置 thinking 参数 | |
| 自动检测 | 有 reasoning 项时自动启用 thinking | |

**User's choice:** 不在 Phase 2 实现，留给 Phase 4

### Reasoning item 字段提取

| Option | Description | Selected |
|--------|-------------|----------|
| 按方案实现 | 提取 content 中 reasoning_text 的 text 拼接 + summary | ✓ |
| 仅提取 summary | 忽略 content 细节 | |
| 保留原始结构 | 原始 JSON 作为 reasoning_content 值 | |

**User's choice:** 按 OpenAI Responses API 规范提取 reasoning_text 的 text 字段

---

## Claude's Discretion

- 内部辅助函数的具体拆分粒度
- 日志记录的详细级别
- 函数参数校验的严格程度
- Docstring 风格
