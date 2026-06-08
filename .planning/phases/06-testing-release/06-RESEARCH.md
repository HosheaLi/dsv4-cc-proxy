# Phase 6: Testing & Release - Research

**Researched:** 2026-06-07
**Domain:** Testing, Documentation, CI/CD, Release Engineering
**Confidence:** HIGH

## Summary

Phase 6 is the project's final delivery phase: solidify test coverage, document the Codex protocol support, and execute a multi-channel release (v2.0.0). The codex subpackage tests are already at 91-98% coverage; the main gaps are `proxy.py` (61%, 141 missed lines) and `__main__.py` (0%, 74 missed lines). The CI already supports Docker semver tagging and GitHub Releases via tag push; the main CI upgrade is switching PyPI publish from API tokens to OIDC Trusted Publishing (one-time PyPI project config required).

**Primary recommendation:** Focus test effort on the uncovered paths in `proxy.py` (error handling, streaming pipeline, edge cases) and add unit tests for `__main__.py` CLI entry points. Use `coverage-badge` or `genbadge` for the coverage badge SVG in README. Follow the existing test patterns: AAA structure, pure function testing, and Starlette `TestClient` + `httpx` mocks for async handler tests.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Implementation Decisions

#### Test Scope & Strategy
- **D-01:** 全面提测，整体覆盖率目标 >=85%。proxy.py（当前 61%）和 __main__.py（当前 0%）为主要补充目标。codex 子包模块已 >=91%，保持即可
- **D-02:** 需要 E2E 测试。新建 `tests/test_e2e.py`，启动 Starlette TestClient 或真实 httpx mock 上游，验证完整请求→翻译→响应链路
- **D-03:** 覆盖率仅作参考，不在 CI 中做门控阻断（`--cov-fail-under` 不加）。CI 中运行覆盖率报告供审阅
- **D-04:** 审阅全部 111 个现有测试，必要时重构以消除冗余、改善组织。不改变测试覆盖的行为语义，纯结构优化
- **D-05:** test_responses.py 维持现有文件结构，仅在原文件中补充 proxy.py 的 filtered_stream、build_request 等缺失路径的测试
- **D-06:** 回归验证：CI 跑 `pytest tests/ -v` 单次全量运行确认全部通过。不分组、不做分层运行

#### Documentation Scope
- **D-07:** README.md + README.zh-CN.md 新增 "Codex Support" 章节，描述：三个环境变量（`CODEX_DEFAULT_MODEL`、`CODEX_MODEL_MAP`、`CODEX_UPSTREAM`）、后端 URL 配置方式、支持的端点（`/v1/responses`、`/v1/responses/compact`）。与现有 Anthropic 用法章节并列
- **D-08:** CHANGELOG.md 新增 `[2.0.0]` 条目，按模块归类：Added: codex/ 子包（config.py / translate.py / tools.py / sse.py） / proxy Codex handler / test suites。Changed: 版本升 2.0.0 / README 增加 Codex 章节 / CI 改进
- **D-09:** 新增 `docs/dev/codex-integration.md` — 技术深度文档：架构概览（三层处理流程）、翻译流程（请求 + 流式响应）、SSE 生命周期事件序列、模块依赖图。为后续维护者编写
- **D-10:** 中文 README 与英文 README 内容同步更新，中英双版均增加 Codex 使用章节

#### Version & Release
- **D-11:** 版本号升至 **2.0.0**。Codex 双协议支持是重大里程碑，按语义化版本规范应递增 MAJOR
- **D-12:** 发布渠道：全部渠道 — GitHub Release（tag 触发）+ Docker Hub（CI 自动）+ PyPI（CI OIDC Trusted Publishing）。三个渠道在一次 tag push 中全部触发
- **D-13:** 发布流程：手动打 `git tag v2.0.0` → `git push origin v2.0.0` → CI 自动构建 Docker（semver 标签）+ 发布 PyPI（OIDC）+ 生成 GitHub Release

#### CI Improvements
- **D-14:** 添加 PyPI OIDC Trusted Publishing — 在 CI 中新增 tag push 触发的 PyPI 发布 job。使用 `pypa/gh-action-pypi-publish` + `id-token: write` 权限。与 Docker job 并列，互不阻塞
- **D-15:** CI 生成覆盖率徽章（coverage badge），显示在 README。使用 `coverage-badge` 或类似工具生成 badge SVG
- **D-16:** 不需要多 Python 版本测试矩阵 — 代理服务非库，部署环境固定。单版本（Python 3.11+）够用
- **D-17:** Docker 标签策略改为 semver 标签：tag push v2.0.0 时生成 `hosheali/dsv4-cc-proxy:2.0.0`、`:2.0`、`:latest`、`:sha-xxxxx`

#### Claude's Discretion
- 测试重构的具体方式：哪些测试需要合并、拆分、重命名
- E2E 测试的具体场景设计（覆盖哪些完整路径）
- coverage badge 工具选择（coverage-badge vs shields.io vs 其他）
- CI job 的具体组织结构和依赖关系（publish job 的 needs 链）
- codex-integration.md 的具体结构和深度
- CHANGELOG 条目的具体措辞
- Git tag 和 GitHub Release 的具体创建方式

#### Deferred Ideas (OUT OF SCOPE)
- Homebrew Tap 发布 — 待 tap 仓库创建和 Formula 编写，后续迭代
- WebSocket 支持（CODX-22）— v2 需求
- Codex 配置自动生成（CODX-25）— 后续迭代
- 桌面 GUI / Web 管理面板 — 非核心需求

</user_constraints>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Unit testing | CI/Dev Environment | — | Tests run in CI via pytest; all code executes locally |
| E2E testing | CI/Dev Environment | — | Starlette TestClient + mock upstream; no external service dependency |
| Coverage reporting | CI (pytest-cov) | — | Coverage data generated in CI, badge added to static README |
| Coverage badge | CI (custom step) | README (static SVG) | Badge SVG generated from CI coverage data, committed or stored |
| Documentation | Repo (docs/) | README (static) | Master docs in `docs/dev/`, user-facing docs in README |
| Changelog | Repo (CHANGELOG.md) | GitHub Release (auto) | CHANGELOG is manual; GitHub Release auto-generated from tag |
| PyPI publishing | CI (GitHub Actions) | PyPI.org | CI uses OIDC trusted publishing to push sdist/wheel |
| Docker publishing | CI (GitHub Actions) | Docker Hub | CI builds multi-arch image and pushes with semver tags |
| GitHub Release | CI (GitHub Actions) | github.com | CI auto-creates release notes from tag push |
| Version management | Repo (_version.py) | git tag | Version in `_version.py`, tag `v2.0.0` must match |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 9.0.3 | Test runner and assertions | Existing project standard; zero-config with pyproject.toml |
| pytest-cov | 7.1.0 | Coverage reporting and badge generation | Already installed; `--cov=dsv4_cc_proxy` gives module-level report |
| Starlette TestClient | 1.0.0 | HTTP integration testing for ASGI apps | Already introduced in Phase 5 for testing `/v1/responses` handlers |
| coverage | 7.13.5 | Low-level coverage data collection | Backend for pytest-cov; used for badge generation |
| httpx | 0.28.1 | Async HTTP client mocking | `AsyncMock` + `_MockStreamResponse` pattern already established |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| ruff | 0.4.0+ | Linting (E, F, I, W) | CI lint job + pre-commit |
| coverage-badge | 0.2.0+ | Generate shields.io-style coverage SVG badge | Simple static badge; maintenance mode, recommended alternative genbadge |
| genbadge | 1.0+ | Coverage badge generation (actively maintained) | Replacement for coverage-badge; supports multiple badge types |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| coverage-badge / genbadge | shields.io dynamic endpoint + JSON gist | Dynamic badge avoids committing SVG; requires Gist token and extra CI step. Not worth complexity for this project |
| Single Python version CI matrix | Multi-version matrix (3.11/3.12/3.13) | D-16 explicitly drops multi-version; deployment environment is fixed |
| PyPI OIDC | API token (current) | OIDC is more secure, no secret management. One-time PyPI project setup required |

**Version verification:**
```bash
# All verified as available in the project environment (2026-06-07):
pytest 9.0.3, starlette 1.0.0, httpx 0.28.1, coverage 7.13.5
```

## Architecture Patterns

### System Architecture Diagram

```
Testing Pipeline (CI):
                    
  git push main/tag ──► CI (GitHub Actions)
                           │
                    ┌──────┼──────────┐
                    │      │          │
                    ▼      ▼          ▼
                lint   test       pages (main only)
                    │      │
                    │      └── cov report
                    │         └── coverage.svg badge
                    │
                publish (tag only)
                    │
          ┌─────────┼──────────┐
          │         │          │
          ▼         ▼          ▼
    GitHub     Docker      PyPI (OIDC)
    Release    Hub         Trusted Publishing
               (semver     (id-token: write)
               tags)
          
Documentation Pipeline:
          
  docs/dev/           ──► README.md/.zh-CN.md
    codex-integration.md     (Codex Support section)
    deepseek-thinking-proxy.md
    RELEASE.md
    
  CHANGELOG.md        ──► GitHub Release notes (auto-generated)
  
  coverage.svg        ──► README coverage badge
```

### Recommended Project Structure (testing additions)

```
tests/
├── test_proxy.py           # 22 existing tests + additions for proxy.py gaps
├── test_responses.py       # 21 existing tests + additions for filtered_stream/build_request paths
├── test_codex.py           # 6 existing tests (config) — keep as-is
├── test_translate.py       # translate.py tests — keep as-is
├── test_tools.py           # tools.py tests — keep as-is
├── test_sse.py             # sse.py tests — keep as-is
├── test_e2e.py             # NEW: E2E integration tests (Starlette TestClient)
├── test_main.py            # NEW: __main__.py CLI tests
```

### Pattern 1: Pure Function Unit Testing (AAA)
**What:** Test pure functions with Arrange-Act-Assert pattern, no mocks needed.
**When to use:** For all functions that transform data without side effects (e.g., `_inject_thinking_blocks`, `_normalize_thinking`, `_filter_sse_line`, `_translate_chat_to_responses`).
**Example:**
```python
# Source: tests/test_proxy.py (existing project pattern)
def test_inject_thinking_adds_block():
    data = {
        "model": "deepseek-v4-pro",
        "thinking": {"type": "enabled"},
        "messages": [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "call_1", "name": "Bash", "input": {"cmd": "ls"}}
            ]}
        ]
    }
    assert _inject_thinking_blocks(data)
    content = data["messages"][0]["content"]
    assert content[0]["type"] == "thinking"
    assert content[0]["thinking"] == ""
    assert content[1]["type"] == "tool_use"
```

### Pattern 2: Async Handler Testing (TestClient + httpx mock)
**What:** Test async route handlers using Starlette TestClient, mocking httpx responses.
**When to use:** For all route handler testing (`responses_handler`, `proxy`, `compact_handler`, `health`).
**Source:** tests/test_responses.py (existing project pattern — lines 9-16 for fixture, 65-70 for mock helper)
```python
# Fixture
@pytest.fixture
def client():
    return TestClient(create_app())

# Mock helper
class _MockJSONResponse:
    def __init__(self, status_code=200, json_data=None, content=None):
        self.status_code = status_code
        self._json = json_data
        self.content = content or json.dumps(json_data or {}).encode("utf-8")
        self.headers = httpx.Headers({"content-type": "application/json"})
    def json(self):
        return self._json
    async def aclose(self):
        pass

# Test
def test_something(client):
    mock_resp = _MockJSONResponse(status_code=200, json_data={...})
    with patch("dsv4_cc_proxy.proxy._get_client") as mock_get_client:
        mock_get_client.return_value = _make_mock_client(mock_resp)
        resp = client.post("/v1/responses", json={...})
    assert resp.status_code == 200
```

### Pattern 3: CLI Entry Point Testing (monkeypatch sys.argv)
**What:** Test `__main__.py` by manipulating `sys.argv` and calling `main()`.
**When to use:** For testing `--stop`, PID file handling, and normal startup paths.
```python
def test_main_stop_not_running(monkeypatch, tmp_path):
    pidfile = tmp_path / "test.pid"  # file doesn't exist
    monkeypatch.setattr("sys.argv", ["dsv4-cc-proxy", "--stop", f"--pidfile={pidfile}"])
    from dsv4_cc_proxy.__main__ import main
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
```

### Anti-Patterns to Avoid
- **Testing implementation details:** Don't test private helpers through the public API if their behavior is already covered by pure-function tests. Keep tests focused on contract.
- **Flaky E2E tests with real upstream:** Always mock the upstream httpx client. Never connect to real DeepSeek API in tests.
- **Coverage-gaming:** Adding tests solely to bump coverage numbers without verifying behavior. Every new test should assert meaningful behavior.
- **Splitting the `proxy` function too much:** The `proxy()` function is long by necessity (ASGI handler). Test it through the TestClient, not by unit-testing internal async generators directly.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Coverage badge SVG | Custom badge generation script | `coverage-badge` or `genbadge` | Proven color thresholds, shields.io-compatible SVG output |
| OIDC auth flow | Custom PyPI publish script | `pypa/gh-action-pypi-publish@release/v1` | Handles OIDC token exchange, attestations, retry logic |
| Docker semver tagging | Manual tag computation | `docker/metadata-action@v5` | Automatically generates {{version}}, {{major}}.{{minor}}, latest, sha tags |

**Key insight:** All three "don't hand-roll" items are already established in the project's CI or will be added. The patterns exist in the current CI (Docker metadata action, PyPA publish action). No new libraries needed.

## Common Pitfalls

### Pitfall 1: OIDC PyPI Setup Forgot
**What goes wrong:** CI PyPI publish job fails with "403 Forbidden" because the trusted publisher was never registered on PyPI.
**Why it happens:** OIDC trusted publishing requires one-time configuration at `pypi.org/manage/account/publishing/` — it's NOT just a CI change.
**How to avoid:** Add a pre-requisite step to Phase 6: configure PyPI trusted publisher before the release tag push. Required fields: PyPI project name `dsv4-cc-proxy`, GitHub owner `HosheaLi`, repo `P14_dsv4ToCC`, workflow name `ci.yml`, environment name `pypi`.
**Warning signs:** The CI publish job will fail on the first tagged push with a 403 error.

### Pitfall 2: proxy() Handler Async Generator Not Fully Covered
**What goes wrong:** The `proxy()` function (ASGI handler) is 135 lines with two async generators (`passthrough`, `filtered_stream`). Testing all paths through TestClient is complex because it reads the full request body, makes an upstream call, then conditionally returns different StreamingResponses.
**Why it happens:** The function has branching on `is_messages`, `original_thinking_enabled`, `strip_thinking`, `is_sse`, plus error handling (`JSONDecodeError`, `Exception` on upstream).
**How to avoid:** Test the function through TestClient with carefully constructed mock responses for each branch. Use the `_MockStreamResponse` pattern from `test_responses.py`. Cover at least: non-messages path, messages with thinking enabled, messages with thinking disabled, upstream failure (502).
**Warning signs:** Coverage report shows `proxy()` function with <70% after test additions.

### Pitfall 3: __main__.py Testing Introduces Side Effects
**What goes wrong:** Testing `main()` or `_stop()` writes PID files, starts uvicorn, or sends OS signals. Tests leave state behind.
**Why it happens:** `__main__.py` is designed to manage processes (PID file, SIGTERM, uvicorn).
**How to avoid:** Use `tmp_path` fixture for PID files. Mock `uvicorn.run` entirely. Mock `os.kill` for signal testing. Use `monkeypatch.setattr("sys.argv", ...)` for CLI argument testing.
**Warning signs:** Tests fail with "Address already in use" or leave PID files in `/tmp/`.

### Pitfall 4: Coverage Badge Staleness
**What goes wrong:** The coverage badge shows an old percentage because the SVG was generated once locally and never updated in CI.
**Why it happens:** Static SVG committed to repo; CI doesn't regenerate it.
**How to avoid:** Either (a) generate badge in CI as a step after `pytest --cov`, commit it back, or (b) use shields.io dynamic endpoint with a JSON file. Option (a) is simpler. Option (b) requires a public Gist or uploading to GitHub Pages.
**Warning signs:** Badge shows 60% when actual coverage is 85+%.

### Pitfall 5: CHANGELOG Version Pinning
**What goes wrong:** CHANGELOG.md has `[2.0.0]` but `_version.py` still says `1.8.0` — or vice versa.
**Why it happens:** Version is maintained in two places (`_version.py` + git tag + CHANGELOG + pyproject.toml dynamic reference).
**How to avoid:** Single source of truth is `_version.py`. Update first, then verify consistency. The version update task should touch exactly: `_version.py`, `CHANGELOG.md`, and the git tag. pyproject.toml uses dynamic reference so it stays in sync.
**Warning signs:** Tag says `v2.0.0` but pip-installed version shows `1.8.0`.

## Code Examples

### Existing patterns from project test files:

#### Mock Stream Response (for SSE testing)
```python
# Source: tests/test_responses.py (existing project pattern)
class _MockStreamResponse:
    def __init__(self, status_code=200, chunks=None, headers=None):
        self.status_code = status_code
        self._chunks = chunks or []
        self.headers = httpx.Headers(headers or {"content-type": "text/event-stream"})

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")

    async def aclose(self):
        pass
```

#### Mock Client Factory
```python
# Source: tests/test_responses.py (existing project pattern)
def _make_mock_client(mock_response):
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.build_request.return_value = MagicMock(spec=httpx.Request)
    mock_client.send.return_value = mock_response
    return mock_client
```

#### CLI Entry Point Test (recommended pattern)
```python
import sys
import pytest
from pathlib import Path

def test_main_stop_normal(monkeypatch, tmp_path):
    pidfile = tmp_path / "dsv4-cc-proxy.pid"
    pidfile.write_text("99999")
    monkeypatch.setattr("sys.argv", ["dsv4-cc-proxy", "--stop", f"--pidfile={pidfile}"])
    # Mock os.kill so no actual signal is sent
    with patch("dsv4_cc_proxy.__main__.os.kill") as mock_kill:
        from dsv4_cc_proxy.__main__ import main
        main()
        mock_kill.assert_called_once_with(99999, signal.SIGTERM)
    assert not pidfile.exists()  # cleaned up after graceful stop
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PyPI API token in GitHub Secrets | OIDC Trusted Publishing (id-token: write) | PyPI 2024 | No secret management, automatic attestations, more secure |
| Docker tags: latest + sha only | Semver tags: {{version}}, {{major}}.{{minor}}, latest, sha | Already implemented in CI | Users can pin to exact version |

**Deprecated/outdated:**
- `coverage-badge` (PyPI): Maintenance mode since ~2024. Active fork is `genbadge`. For this project, either tool works — `coverage-badge` is simpler and the project only needs one badge.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PyPI OIDC Trusted Publisher configuration is a manual one-time step on pypi.org | Common Pitfalls — Pitfall 1 | CI publish job will fail with 403 if not configured first |
| A2 | The existing Docker semver tag configuration (`docker/metadata-action` with `type=semver`) is correct and only triggers on tag push | CI Improvements | Docker tags may generate incorrectly on branch pushes; verify CI YAML |
| A3 | `coverage-badge -o coverage.svg` generates a shields.io-compatible SVG badge | Standard Stack | SVG format may differ; verify output before adding to README |

## Open Questions (RESOLVED)

1. **[Coverage badge CI strategy]**
   - What we know: Two approaches exist: (a) generate SVG in CI and commit it, (b) use shields.io dynamic endpoint with JSON file served via GitHub Pages
   - What's unclear: Approach (a) requires CI commit back to repo (git config + push). Approach (b) requires hosting the JSON. The project already has GitHub Pages — could host the badge JSON there.
   - Recommendation: Start with approach (a) for simplicity. If the CI commit-back step proves flaky, switch to (b).
   - **Resolution:** Approach (a) chosen per Plan 03 Task 3. coverage-badge generates SVG in CI, committed back with `[skip ci]`.

2. **[proxy() function test strategy]**
   - What we know: D-05 says add to test_responses.py, don't create new files for proxy.py tests. The proxy() handler has 135+ uncovered lines.
   - What's unclear: Should we add one class per branch (TestProxyPassthrough, TestProxyFilteredStream) or one class per function being tested?
   - Recommendation: Follow the test_responses.py convention — one class per logical path. Add classes like `TestProxyPassthrough`, `TestProxyFilteredStream`, `TestProxyError` to test_responses.py.
   - **Resolution:** One class per logical path per Plan 01 Task 2. TestProxyPassthrough, TestProxyFilteredStream, TestProxyBuildRequest, TestProxyConnectionError.

3. **[E2E test specific scenarios]**
   - What we know: D-02 requires E2E tests. CONTEXT.md specifics suggest 4 scenarios.
   - What's unclear: How many scenarios beyond the 4 listed (stream+non-stream+compact+auth) should be covered?
   - Recommendation: Start with the 4 specific scenarios from CONTEXT.md. Add more only after the coverage gaps in proxy.py and __main__.py are closed.
   - **Resolution:** 4 scenarios per Plan 02 Task 1 — non-stream JSON, stream SSE, compact 501, auth passthrough.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| python3 | All | Yes | 3.14.5 | — |
| pytest | Test execution | Yes | 9.0.3 | — |
| pytest-cov | Coverage reporting | Yes | 7.1.0 | — |
| starlette | ASGI framework | Yes | 1.0.0 | — |
| httpx | Async HTTP client | Yes | 0.28.1 | — |
| uvicorn | ASGI server (__main__.py) | Yes | installed | Mock in tests |
| coverage-badge | Badge SVG generation | No (need to install) | — | genbadge (needs install) or shields.io |
| Docker | Container build (local verification) | Yes | — | CI handles remote |
| GitHub Actions | CI/CD (remote) | Yes (GitHub) | — | N/A |

**Missing dependencies with no fallback:**
- None. All core tools are available.

**Missing dependencies with fallback:**
- `coverage-badge` is not installed locally. Install via `pip install coverage-badge` or use `genbadge`.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-cov 7.1.0 |
| Config file | pyproject.toml (`[tool.pytest.ini_options]`) |
| Quick run command | `python -m pytest tests/ -x` |
| Full suite command | `python -m pytest tests/ -v` |
| Coverage command | `python -m pytest tests/ --cov=dsv4_cc_proxy --cov-report=term` |

### Phase Requirements Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-01 | proxy.py >=85% coverage | unit | `python -m pytest tests/ --cov=dsv4_cc_proxy/proxy.py --cov-report=term` | Wave 0 (test_responses.py additions) |
| D-01 | __main__.py >=85% coverage | unit | `python -m pytest tests/ --cov=dsv4_cc_proxy/__main__.py --cov-report=term` | Wave 0 (new test_main.py) |
| D-02 | E2E non-stream => JSON response | integration | `python -m pytest tests/test_e2e.py -x` | Wave 0 (new test_e2e.py) |
| D-02 | E2E stream => SSE events | integration | `python -m pytest tests/test_e2e.py -x` | Wave 0 (new test_e2e.py) |
| D-02 | E2E compact => 501 | integration | `python -m pytest tests/test_e2e.py -x` | Wave 0 (new test_e2e.py) |
| D-02 | E2E auth passthrough | integration | `python -m pytest tests/test_e2e.py -x` | Wave 0 (new test_e2e.py) |
| D-04 | Test review/refactor | manual review | `python -m pytest tests/ -v` (regression check) | Existing files |
| D-06 | Zero regression | regression | `python -m pytest tests/ -v` | All existing files |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_e2e.py tests/test_responses.py tests/test_main.py -x`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_e2e.py` — new file for E2E integration tests
- [ ] `tests/test_main.py` — new file for __main__.py CLI tests
- [ ] `tests/test_responses.py` — add classes for proxy.py missing paths (filtered_stream, build_request, etc.)
- [ ] `tests/test_proxy.py` — additional tests for error handling, edge cases

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | Authorization header passthrough; verified by E2E test |
| V5 Input Validation | Yes | JSON parse error handling (400s), upstream error translation |
| V6 Cryptography | No | Proxy does not handle crypto; auth tokens are passed through |

### Known Threat Patterns for Starlette/httpx Proxy

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Authorization header leakage in logs | Information Disclosure | D-04: test and verify no auth tokens appear in log output; DUMP_DIR is opt-in with explicit warning |
| Upstream request injection (path) | Tampering | `proxy()` handler proxies exact path via `Path:path` route; no path mutation |
| Missing auth rejection | Spoofing | If upstream rejects (401/403), proxy translates to Responses API error format; no credential validation at proxy level |

## Sources

### Primary (HIGH confidence)
- [Project test files] - `tests/test_proxy.py`, `tests/test_responses.py` — existing patterns confirmed by direct reading
- [CONTEXT.md](./06-CONTEXT.md) — all user decisions copied verbatim
- [Environment tools] - python3 3.14.5, pytest 9.0.3, starlette 1.0.0, httpx 0.28.1 — verified via command
- [ci.yml](../../../.github/workflows/ci.yml) — current CI configuration read in full

### Secondary (MEDIUM confidence)
- [PyPI Trusted Publishing docs](https://docs.pypi.org/trusted-publishers/) — OIDC trusted publishing pattern verified from official documentation
- [PyPA publish action](https://github.com/pypa/gh-action-pypi-publish) — action configuration pattern verified via WebSearch
- [coverage-badge PyPI](https://pypi.org/project/coverage-badge/) — tool existence and usage verified from PyPI

### Tertiary (LOW confidence)
- `genbadge` as coverage-badge replacement — mentioned in WebSearch results, not verified locally. Coverage-badge works for this use case, genbadge is a fallback.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — All tools verified in environment; existing project uses them
- Architecture: HIGH — Patterns derived from existing project code
- Pitfalls: HIGH — Based on experience with similar projects; OIDC setup pitfall is well-documented

**Research date:** 2026-06-07
**Valid until:** 2026-07-07 (stable tooling — pytest, starlette, coverage, etc. are mature)