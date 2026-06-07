# Phase 6: Testing & Release - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning

<domain>
## Phase Boundary

全面测试验证（覆盖率提升至 ≥85%）、文档更新（README/CHANGELOG/codex-integration.md）、版本发布 v2.0.0（全部渠道：GitHub Release + Docker Hub + PyPI）、CI 改进（PyPI OIDC 发布 + 覆盖率徽章 + semver Docker 标签）。

此阶段不新增代码功能。测试、文档、CI 配置、发布操作为主要交付物。

Success Criteria（来自 ROADMAP.md）:
1. 所有 codex 模块（config、translate、tools、sse）测试覆盖率 ≥80% — 已完成（91-98%），需保底
2. 所有现有 proxy 测试仍通过 — 零回归（完整测试套件单次运行验证）
3. 新环境变量记录在文档中
4. 版本号升至 2.0.0 并打 tag
5. 新 `/v1/responses` 端点记录在相关文档中

</domain>

<decisions>
## Implementation Decisions

### 测试范围与策略
- **D-01:** 全面提测，整体覆盖率目标 ≥85%。proxy.py（当前 61%）和 __main__.py（当前 0%）为主要补充目标。codex 子包模块已 ≥91%，保持即可
- **D-02:** 需要 E2E 测试。新建 `tests/test_e2e.py`，启动 Starlette TestClient 或真实 httpx mock 上游，验证完整请求→翻译→响应链路
- **D-03:** 覆盖率仅作参考，不在 CI 中做门控阻断（`--cov-fail-under` 不加）。CI 中运行覆盖率报告供审阅
- **D-04:** 审阅全部 111 个现有测试，必要时重构以消除冗余、改善组织。不改变测试覆盖的行为语义，纯结构优化
- **D-05:** test_responses.py 维持现有文件结构，仅在原文件中补充 proxy.py 的 filtered_stream、build_request 等缺失路径的测试
- **D-06:** 回归验证：CI 跑 `pytest tests/ -v` 单次全量运行确认全部通过。不分组、不做分层运行

### 文档更新范围
- **D-07:** README.md + README.zh-CN.md 新增 "Codex Support" 章节，描述：三个环境变量（`CODEX_DEFAULT_MODEL`、`CODEX_MODEL_MAP`、`CODEX_UPSTREAM`）、后端 URL 配置方式、支持的端点（`/v1/responses`、`/v1/responses/compact`）。与现有 Anthropic 用法章节并列
- **D-08:** CHANGELOG.md 新增 `[2.0.0]` 条目，按模块归类：Added: codex/ 子包（config.py / translate.py / tools.py / sse.py） / proxy Codex handler / test suites。Changed: 版本升 2.0.0 / README 增加 Codex 章节 / CI 改进
- **D-09:** 新增 `docs/dev/codex-integration.md` — 技术深度文档：架构概览（三层处理流程）、翻译流程（请求 + 流式响应）、SSE 生命周期事件序列、模块依赖图。为后续维护者编写
- **D-10:** 中文 README 与英文 README 内容同步更新，中英双版均增加 Codex 使用章节

### 版本发布方式
- **D-11:** 版本号升至 **2.0.0**。Codex 双协议支持是重大里程碑，按语义化版本规范应递增 MAJOR
- **D-12:** 发布渠道：全部渠道 — GitHub Release（tag 触发）+ Docker Hub（CI 自动）+ PyPI（CI OIDC Trusted Publishing）。三个渠道在一次 tag push 中全部触发
- **D-13:** 发布流程：手动打 `git tag v2.0.0` → `git push origin v2.0.0` → CI 自动构建 Docker（semver 标签）+ 发布 PyPI（OIDC）+ 生成 GitHub Release

### CI 改进
- **D-14:** 添加 PyPI OIDC Trusted Publishing — 在 CI 中新增 tag push 触发的 PyPI 发布 job。使用 `pypa/gh-action-pypi-publish` + `id-token: write` 权限。与 Docker job 并列，互不阻塞
- **D-15:** CI 生成覆盖率徽章（coverage badge），显示在 README。使用 `coverage-badge` 或类似工具生成 badge SVG
- **D-16:** 不需要多 Python 版本测试矩阵 — 代理服务非库，部署环境固定。单版本（Python 3.11+）够用
- **D-17:** Docker 标签策略改为 semver 标签：tag push v2.0.0 时生成 `hosheali/dsv4-cc-proxy:2.0.0`、`:2.0`、`:latest`、`:sha-xxxxx`

### Claude's Discretion
- 测试重构的具体方式：哪些测试需要合并、拆分、重命名
- E2E 测试的具体场景设计（覆盖哪些完整路径）
- coverage badge 工具选择（coverage-badge vs shields.io vs 其他）
- CI job 的具体组织结构和依赖关系（publish job 的 needs 链）
- codex-integration.md 的具体结构和深度
- CHANGELOG 条目的具体措辞
- Git tag 和 GitHub Release 的具体创建方式

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 发布流程
- `docs/dev/RELEASE.md` — 完整发布管线文档：PyPI 配置、Docker 标签策略、CI job 设计、版本号规范
- `CHANGELOG.md` — 现有 changelog，1.8.0/1.8.1 条目格式参考

### 版本与构建
- `dsv4_cc_proxy/_version.py` — 当前版本 `VERSION = "1.8.0"`，唯一版本来源。需改为 `2.0.0`
- `pyproject.toml` — 包元数据和构建配置，`project.scripts` entry point

### CI
- `.github/workflows/ci.yml` — 现有 CI：test job + docker job。需添加 PyPI publish job、覆盖率报告、semver 标签

### 现有文档
- `README.md` — 英文 README，需新增 Codex Support 章节
- `README.zh-CN.md` — 中文 README，同步更新
- `docs/dev/deepseek-thinking-proxy.md` — 现有 Anthropic 代理设计文档，codex-integration.md 应与之一致

### 测试
- `tests/test_proxy.py` — 现有 22 个 proxy 测试，需审阅重构
- `tests/test_responses.py` — 21 个 HTTP 集成测试，需补充缺失路径
- `tests/test_codex.py` / `test_translate.py` / `test_tools.py` / `test_sse.py` — codex 子包测试，覆盖率 91-98%

### 需求
- `.planning/REQUIREMENTS.md` — CODX-01 ~ CODX-21 完整需求列表
- `.planning/ROADMAP.md` — Phase 6 成功标准和依赖关系

### 设计参考
- `/Users/lihaoxuan/.claude/plans/codex-deepseek-v4-responses-api-deepsee-cryptic-phoenix.md` — 原始技术方案文档
- `.planning/phases/05-route-integration/05-CONTEXT.md` — Phase 5 handler 架构决策，测试文件组织约定
- `.planning/phases/04-sse-state-machine/04-CONTEXT.md` — SSE 状态机决策，测试覆盖场景列表

### 外部参考
- [OpenAI Responses API SSE 格式](https://platform.openai.com/docs/api-reference/responses) — 事件类型和字段结构
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion) — delta chunk 格式
- [PyPI Trusted Publishing (OIDC)](https://docs.pypi.org/trusted-publishers/) — OIDC 配置指南
- [Docker Metadata Action](https://github.com/docker/metadata-action) — semver 标签生成
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `pytest --cov=dsv4_cc_proxy --cov-report=term` — 现有覆盖率报告命令，直接复用
- `starlette.testclient.TestClient` — Phase 5 已引入的 HTTP 测试工具，E2E 测试可复用
- `.github/workflows/ci.yml` — 现有 CI 配置，PyPI job 和 semver 标签在其中追加

### Established Patterns
- **纯函数测试 + AAA 模式**：所有 test_*.py 遵循 Arrange-Act-Assert 模式
- **单文件对应测试**：test_translate.py ↔ translate.py, test_tools.py ↔ tools.py, test_sse.py ↔ sse.py
- **覆盖率策略**：模块级 `--cov=module` 逐一检查，汇总 `--cov=dsv4_cc_proxy`
- **CI 触发**：push main / PR → test + lint + docker（现有模式，PyPI job 需增加 tag push 触发）

### Integration Points
- `dsv4_cc_proxy/_version.py` → 修改 `VERSION = "2.0.0"`，发布 tag 需与此一致
- `pyproject.toml` → `project.version` 动态从 `_version.py` 读取，无需手动修改
- `.github/workflows/ci.yml` → 新增加：publish-pypi job（tag 触发）、覆盖率 badge step、semver docker 标签
- `README.md` / `README.zh-CN.md` → 新增 Codex Support 章节
- `CHANGELOG.md` → 追加 `## [2.0.0]` 条目
</code_context>

<specifics>
## Specific Ideas

- E2E 测试应覆盖至少以下场景：
  1. 非流式 Codex 请求 → DeepSeek → Responses API JSON 响应
  2. 流式 Codex 请求 → DeepSeek → Responses API SSE 事件流
  3. Compact 端点 → 501 响应
  4. Authorization header 透传验证
- 测试重构原则：保持行为等价，仅改结构。不在此阶段引入新测试逻辑
- 覆盖率徽章工具推荐 `coverage-badge`（Python 生态），或 CI 中用 `shields.io` 动态 URL 生成
- PyPI OIDC 需要在 pypi.org 项目页面预先配置 Trusted Publisher（GitHub 仓库 + workflow 文件名），这是 Phase 6 实施时的一次性操作
- 发布 tag 后验证：`pip install dsv4-cc-proxy==2.0.0`、`docker pull hosheali/dsv4-cc-proxy:2.0.0`、`curl -I https://github.com/HosheaLi/dsv4-cc-proxy/releases/tag/v2.0.0`
</specifics>

<deferred>
## Deferred Ideas

- Homebrew Tap 发布 — 待 tap 仓库创建和 Formula 编写，后续迭代
- WebSocket 支持（CODX-22）— v2 需求
- Codex 配置自动生成（CODX-25）— 后续迭代
- 桌面 GUI / Web 管理面板 — 非核心需求

### Reviewed Todos (not folded)
None — no matching todos found.

</deferred>

---

*Phase: 06-testing-release*
*Context gathered: 2026-06-07*
