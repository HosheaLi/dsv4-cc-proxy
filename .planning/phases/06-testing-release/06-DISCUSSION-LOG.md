# Phase 6: Testing & Release - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-07
**Phase:** 06-testing-release
**Areas discussed:** 测试范围与策略, 文档更新范围, 版本发布方式, CI 改进

---

## 测试范围与策略

| Option | Description | Selected |
|--------|-------------|----------|
| 仅补 codex 模块 + proxy.py 关键路径 | codex/ 子包已全部 ≥91%，只需补 proxy.py 关键 handler 路径到 ~80%。__main__.py 跳过 | |
| 全面提测到 85% | proxy.py + __main__.py 也测。整体覆盖率目标 ≥85% | ✓ |
| 达标即可（80%） | 补充 proxy.py 中 responses_handler 路径的测试，整体覆盖 ≥80% | |

**User's choice:** 全面提测到 85%
**Notes:** 不设 CI 门控阻断，覆盖率仅作参考。proxy.py（61%）和 __main__.py（0%）为主要补充目标

### E2E 测试

| Option | Description | Selected |
|--------|-------------|----------|
| 需要 E2E 测试 | 新建 test_e2e.py，Starlette TestClient 或 httpx mock，验证完整请求→翻译→响应流程 | ✓ |
| 不需要，单元+集成够用 | 现有单元测试 + Phase 5 HTTP 集成测试已覆盖完整路径 | |

**User's choice:** 需要 E2E 测试

### 覆盖率强制执行

| Option | Description | Selected |
|--------|-------------|----------|
| CI 中强制门控 | CI 添加 --cov-fail-under=85，不达标 CI 不通过 | |
| 仅参考不阻断 | 运行覆盖率报告供审查，CI 不阻断 | ✓ |
| 本次达标后不做门控 | 本 Phase 提到 85%，CI 不做强制检查 | |

**User's choice:** 仅参考不阻断

### 现有测试处理

| Option | Description | Selected |
|--------|-------------|----------|
| 不动，仅新增 codex 相关测试 | 22 个 proxy 测试保持原样不变 | |
| 审阅并补充，不改现有 | 现有的保留不动，审阅后针对性补充缺失的测试 | |
| 全部审阅，必要时重构 | 审阅所有 111 个测试，必要时重构使测试组织更合理 | ✓ |

**User's choice:** 全部审阅，必要时重构

### 测试文件组织

| Option | Description | Selected |
|--------|-------------|----------|
| 维持现有 test_responses.py，仅补充缺失路径 | 不动现有文件，在原文件中追加测试 | ✓ |
| 拆分：新建 test_handler.py 覆盖纯函数 | 纯函数测试独立文件，test_responses.py 保留集成测试 | |
| 全部合并到 test_responses.py | 所有 proxy.py 测试放在一个文件 | |

**User's choice:** 维持现有 test_responses.py，仅补充缺失路径

### 回归验证

| Option | Description | Selected |
|--------|-------------|----------|
| 完整测试套件单次运行 | CI 跑 pytest tests/ -v 一次确认全部通过 | ✓ |
| 分组运行 + 对比报告 | proxy 测试 + codex 测试分别跑，生成对比报告 | |
| 添加 pre-commit hook | 每次提交自动跑全量测试 | |

**User's choice:** 完整测试套件单次运行

---

## 文档更新范围

| Option | Description | Selected |
|--------|-------------|----------|
| 新增 Codex 使用章节 | README 中增加 "Codex Support" 章节，与 Anthropic 用法并列 | ✓ |
| README 顶部双场景展示 | 开头展示两种使用场景：Claude Code 和 Codex | |
| 最小化新增，环境变量表 | 仅在环境变量表中追加 CODEX_* 三个变量 | |

**User's choice:** 新增 Codex 使用章节

### CHANGELOG 组织

| Option | Description | Selected |
|--------|-------------|----------|
| 按模块归类 | Added: codex/ 子包 / translate.py / tools.py / sse.py / proxy Codex handler | ✓ |
| 按功能归类 | Added: Codex 完整支持 / 请求翻译 / 流式翻译 / 工具转换 | |
| 简洁摘要 + 详细链接 | 简短摘要，详细内容链接到独立文档 | |

**User's choice:** 按模块归类

### 新文档

| Option | Description | Selected |
|--------|-------------|----------|
| 新增 codex-usage.md | 使用指南：Codex 配置、环境变量、端点说明 | |
| 不需要独立文档 | README + 内联注释已足够 | |
| 新增 docs/dev/codex-integration.md | 技术深度文档：架构概览、翻译流程、SSE 生命周期、模块依赖图 | ✓ |

**User's choice:** 新增 docs/dev/codex-integration.md

### 中文 README

| Option | Description | Selected |
|--------|-------------|----------|
| 同步更新 | 中英双版都增加 Codex 使用章节 | ✓ |
| 仅更新英文 README | README.zh-CN.md 保持现状 | |

**User's choice:** 同步更新

---

## 版本发布方式

| Option | Description | Selected |
|--------|-------------|----------|
| 1.9.0 | 与 ROADMAP 一致，MINOR 新增功能 | |
| 2.0.0 | Codex 双协议支持是重大里程碑，MAJOR 版本升级 | ✓ |

**User's choice:** 2.0.0 — Codex 支持被视为重大里程碑

### 发布渠道

| Option | Description | Selected |
|--------|-------------|----------|
| 全部渠道 | GitHub Release + Docker Hub + PyPI | ✓ |
| GitHub + Docker，PyPI 暂缓 | PyPI 需要 OIDC 配置，先做其他 | |
| 仅 GitHub Release | 只打 tag + 发 GitHub Release | |

**User's choice:** 全部渠道发布

### 发布触发方式

| Option | Description | Selected |
|--------|-------------|----------|
| 手动打 tag → CI 自动发布 | git tag v2.0.0 → push → CI 自动构建 Docker + 发布 PyPI | ✓ |
| 手动逐步发布 | 手动构建、上传 PyPI、推送 Docker | |
| CI 配置在 Phase 6 做好，发布留以后 | 本 Phase 配好 CI，实际操作留给以后 | |

**User's choice:** 手动打 tag → CI 自动发布

---

## CI 改进

| Option | Description | Selected |
|--------|-------------|----------|
| 添加 PyPI OIDC 发布 | tag push 触发 PyPI 发布 job，OIDC Trusted Publishing | ✓ |
| PyPI 手动发布 | CI 不处理 PyPI，本地手动 python -m build && twine upload | |

**User's choice:** 添加 PyPI OIDC 发布

### 覆盖率报告

| Option | Description | Selected |
|--------|-------------|----------|
| CI 输出覆盖率报告 | 在 test job 中运行 pytest --cov，CI 日志中可见 | |
| CI 生成覆盖率徽章 | 额外生成覆盖率 badge 显示在 README | ✓ |
| 不处理，本地看 | CI 不做覆盖率相关 | |

**User's choice:** CI 生成覆盖率徽章

### Python 版本矩阵

| Option | Description | Selected |
|--------|-------------|----------|
| 不需要矩阵 | 单个版本够用，代理服务非库 | ✓ |
| 添加 3.11 + 3.12 + 3.13 | 多版本矩阵确保兼容性 | |

**User's choice:** 不需要矩阵

### Docker 标签策略

| Option | Description | Selected |
|--------|-------------|----------|
| 改为 semver 标签 | v2.0.0, v2.0, latest, sha — 精确版本回溯 | ✓ |
| 保持现有 latest + sha | 简单方案 | |

**User's choice:** 改为 semver 标签

---

## Claude's Discretion

- 测试重构的具体方式（合并、拆分、重命名）
- E2E 测试的具体场景设计
- coverage badge 工具选择
- CI job 组织结构
- codex-integration.md 的结构和深度
- CHANGELOG 条目的措辞
- Git tag 和 GitHub Release 的创建方式

## Deferred Ideas

- Homebrew Tap 发布 — 待 tap 仓库创建和 Formula 编写
- WebSocket 支持（CODX-22）
- Codex 配置自动生成（CODX-25）
