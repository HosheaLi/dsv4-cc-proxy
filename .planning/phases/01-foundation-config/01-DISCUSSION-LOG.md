# Phase 1: Foundation & Config - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-05
**Phase:** 01-foundation-config
**Areas discussed:** 子包结构, 配置 API 设计, 环境变量命名, 测试策略

---

## 子包结构

| Option | Description | Selected |
|--------|-------------|----------|
| 最小化 | Phase 1 只创建 codex/__init__.py + config.py，后续按需加文件 | ✓ |
| 预规划骨架 | Phase 1 创建所有模块文件（config/translate/tools/sse），放占位 | |
| 单模块文件 | codex.py 一个文件，不分目录 | |

**User's choice:** 最小化 — 符合 YAGNI，与现有 proxy.py 单文件风格一致

### 暴露方式

| Option | Description | Selected |
|--------|-------------|----------|
| 扁平导入 | from dsv4_cc_proxy.codex import resolve_model | ✓ |
| 显式子模块 | from dsv4_cc_proxy.codex.config import resolve_model | |

**User's choice:** 扁平导入 — 与现有 __init__.py 风格一致

---

## 配置 API 设计

### 映射精度

| Option | Description | Selected |
|--------|-------------|----------|
| 两层映射 | 精确匹配 + 前缀匹配 | ✓ |
| 精确 + 通配符 | 精确匹配 + 通配符匹配 | |
| 三层映射 | 精确 + 前缀 + 正则 | |

**User's choice:** 两层映射 — 足以覆盖所有实际场景

### JSON 格式

| Option | Description | Selected |
|--------|-------------|----------|
| 扁平键值对 | {"claude-sonnet-4-6": "deepseek-v4-pro"} | ✓ |
| 结构化数组 | [{source, target, priority}] | |

**User's choice:** 扁平键值对 — 简单直观

### 配置方式

| Option | Description | Selected |
|--------|-------------|----------|
| os.getenv 纯函数 | 与 proxy.py 完全一致 | ✓ |
| dataclass + 工厂 | create_config() 返回配置对象 | |

**User's choice:** os.getenv 纯函数 — 保持现有风格

### 未匹配处理

| Option | Description | Selected |
|--------|-------------|----------|
| 回退默认模型 | 未匹配时用 CODEX_DEFAULT_MODEL | ✓ |
| 透传原始名称 | 直接发给 DeepSeek | |
| 警告 + 透传 | 记录日志但透传 | |

**User's choice:** 回退默认模型 — 最可预测，参考 codex-relay

### 前缀匹配

| Option | Description | Selected |
|--------|-------------|----------|
| 最长前缀优先 | claude-sonnet- 优先于 claude- | ✓ |
| 禁止重叠前缀 | 不允许重叠，配置时检测冲突 | |
| 先匹配先生效 | 按 JSON key 顺序 | |

**User's choice:** 最长前缀优先 — 最直观

### 上游端点

| Option | Description | Selected |
|--------|-------------|----------|
| 独立 CODEX_UPSTREAM | 默认 https://api.deepseek.com/v1 | ✓ |
| 复用 PROXY_UPSTREAM | 但 Anthropic 和 Chat 端点 URL 不同 | |
| 自动推导 | 从 PROXY_UPSTREAM 替换路径 | |

**User's choice:** 独立 CODEX_UPSTREAM

---

## 环境变量命名

| Option | Description | Selected |
|--------|-------------|----------|
| CODEX_ 前缀 | CODEX_DEFAULT_MODEL, CODEX_MODEL_MAP, CODEX_UPSTREAM | ✓ |
| PROXY_CODEX_ 前缀 | 统一但冗长 | |

**User's choice:** CODEX_ 前缀 — 与 PROXY_ 平行，简洁

---

## 测试策略

### 测试组织

| Option | Description | Selected |
|--------|-------------|----------|
| 并列单文件 | tests/test_codex.py | ✓ |
| 子目录组织 | tests/codex/test_config.py | |
| 内联测试 | doctest 或内嵌 | |

**User's choice:** 并列单文件 — 符合现有结构

### 覆盖率目标

| Option | Description | Selected |
|--------|-------------|----------|
| 高覆盖 ≥90% | 纯函数全覆盖边界条件 | ✓ |
| 标准 ≥80% | 项目最低要求 | |

**User's choice:** 高覆盖 ≥90% — 纯配置逻辑容易达到

---

## Claude's Discretion

- `config.py` 内部函数拆分粒度
- 日志记录策略
- 具体测试用例设计

## Deferred Ideas

无 — 讨论全程在 Phase 1 范围内
