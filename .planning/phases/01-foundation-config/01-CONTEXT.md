# Phase 1: Foundation & Config - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

搭建 `codex/` 子包骨架（vendor isolation 模式），实现模型映射配置系统，建立测试基础设施。此阶段只交付可导入的配置模块 — 不涉及 HTTP 路由或请求翻译。

</domain>

<decisions>
## Implementation Decisions

### 子包结构
- **D-01:** Phase 1 最小化创建 `dsv4_cc_proxy/codex/__init__.py` + `config.py`，后续 Phase 按需添加 `translate.py`、`tools.py`、`sse.py`
- **D-02:** 使用扁平导入暴露公共 API：`from dsv4_cc_proxy.codex import resolve_model`，与现有 `from dsv4_cc_proxy import create_app` 风格一致

### 模型映射
- **D-03:** 两层映射：精确匹配优先 → 前缀匹配（最长前缀优先）→ 回退 `CODEX_DEFAULT_MODEL`
- **D-04:** `CODEX_MODEL_MAP` 格式为扁平键值对 JSON：`{"claude-sonnet-4-6": "deepseek-v4-pro", "claude-": "deepseek-v4-flash"}`
- **D-05:** 未匹配到任何映射时，回退到 `CODEX_DEFAULT_MODEL` 的值，确保始终解析到有效模型
- **D-06:** 配置方式遵循现有模式：`os.getenv` + 纯函数（无 dataclass/类），保持与 `proxy.py` 一致

### 环境变量
- **D-07:** Codex 相关 env var 使用 `CODEX_` 前缀，与现有 `PROXY_` 前缀平行
- **D-08:** Phase 1 定义三个环境变量：
  - `CODEX_DEFAULT_MODEL` — 默认目标 DeepSeek 模型（如 `deepseek-v4-pro`）
  - `CODEX_MODEL_MAP` — JSON 格式的模型名映射表
  - `CODEX_UPSTREAM` — Chat Completions 端点地址，默认 `https://api.deepseek.com/v1`

### 测试
- **D-09:** 测试文件 `tests/test_codex.py`，与 `tests/test_proxy.py` 并列
- **D-10:** 纯函数测试，覆盖率 ≥90%，覆盖正常路径 + 边界条件 + 异常处理（JSON 解析错误、空映射表、重叠前缀等）

### Claude's Discretion
- `config.py` 内部函数拆分（如 `parse_model_map()` 是否独立导出）
- 日志记录策略（哪些映射结果需要 log）
- 精确的测试用例设计（具体边界值、异常场景选择）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 架构与设计
- `/Users/lihaoxuan/.claude/plans/codex-deepseek-v4-responses-api-deepsee-cryptic-phoenix.md` — 完整技术方案：子包结构、上游端点选择、模型映射设计、输入/输出翻译规则、工具处理策略
- `docs/dev/deepseek-thinking-proxy.md` — 现有 Anthropic 代理的设计文档，理解 thinking 注入/标准化/SSE 剥离三层处理

### 现有代码
- `dsv4_cc_proxy/proxy.py` — 现有代理实现（434 行），需要理解配置模式（os.getenv）、纯函数风格、Starlette 应用工厂
- `dsv4_cc_proxy/__init__.py` — 包暴露方式（from proxy import create_app），codex 子包需保持一致
- `tests/test_proxy.py` — 现有测试模式（纯函数导入、Arrange-Act-Assert、边界条件覆盖），codex 测试需对齐

### 项目规范
- `.planning/PROJECT.md` — 项目约束：Python 3.10+、Starlette+httpx、零额外依赖、测试覆盖率 ≥80%
- `.planning/ROADMAP.md` — Phase 1 成功标准：CODX-16/17/18

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `dsv4_cc_proxy/proxy.py` 的配置模式：模块级 `os.getenv` + 默认值 + 纯函数，codex/config.py 直接复用此模式
- `dsv4_cc_proxy/__init__.py` 的暴露模式：`from .module import public_api`，codex/__init__.py 采用相同方式

### Established Patterns
- **纯函数 + 无类**：整个 proxy.py 无 class 定义，所有逻辑是模块级函数。codex 模块保持一致
- **httpx 客户端管理**：proxy.py 已有 `_get_client()` + `_shared_client` 模式，codex 模块后续可直接复用
- **JSON 序列化**：使用 `json.dumps/loads` + `ensure_ascii=False`，与现有风格一致
- **日志**：`logging.getLogger("deepseek-proxy")` — codex 模块可共用或创建独立 logger

### Integration Points
- `dsv4_cc_proxy/codex/` 是 `dsv4_cc_proxy/` 包内的新子包，与 `proxy.py` 同级
- 后续 Phase 5 将在 `proxy.py` 的 `create_app()` 中注册 `/v1/responses` 路由，调用 codex 模块
- 无需修改现有 `__init__.py` 或 `__main__.py`（Phase 1 范围外）

</code_context>

<specifics>
## Specific Ideas

- 映射解析逻辑参考了 codex-relay（Rust）的两层映射设计
- 用户明确偏好"先精确匹配，再最长前缀匹配"的确定行为，不要模糊的优先级规则
- 环境变量命名要保持简洁，`CODEX_` 前缀而非 `PROXY_CODEX_`

</specifics>

<deferred>
## Deferred Ideas

无 — 讨论全程在 Phase 1 范围内

</deferred>

---

*Phase: 01-foundation-config*
*Context gathered: 2026-06-05*
