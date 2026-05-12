# Contributing to dsv4-cc-proxy

感谢你考虑为 dsv4-cc-proxy 贡献代码！这是一个小而专注的项目，你的每份贡献都很重要。

## 行为准则

本项目采用 [Contributor Covenant 2.1](https://www.contributor-covenant.org/)。参与即表示你同意遵守该准则。

## 如何贡献

### 报告 Bug

1. 先搜索 [Issues](https://github.com/<user>/dsv4-cc-proxy/issues)，确认没有重复
2. 使用 Bug Report 模板，提供：
   - 复现步骤
   - 代理日志（设置 `PROXY_LOG_LEVEL=info`）
   - 操作系统和 Python 版本
   - Claude Code 版本（如适用）

### 提交功能请求

1. 先搜索 Issues 和 Discussions 确认没有重复
2. 使用 Feature Request 模板，说明：
   - 解决了什么问题
   - 期望的行为
   - 备选方案

### 提交 Pull Request

1. Fork 仓库
2. 创建分支：`git checkout -b feat/your-feature` 或 `fix/your-fix`
3. 遵循代码规范
4. 确保所有测试通过
5. 提交 PR，填写 PR 描述模板

## 开发环境

```bash
# 克隆后
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖和开发工具
pip install -e ".[dev]"

# 运行测试
python3 -m pytest tests/ -v

# 代码检查
ruff check dsv4_cc_proxy/ tests/
```

## 代码规范

- **PEP 8** — 遵循 Python 官方风格指南
- **类型注解** — 所有函数参数和返回值需要类型注解
- **文档字符串** — 公共函数需要 docstring（Args/Returns/Raises）
- **函数 < 50 行** — 保持函数小而专注
- **测试覆盖** — 新功能必须包含测试

## 提交信息规范

使用 Conventional Commits：

```
feat: 添加 Windows 服务安装支持
fix: 修复 SSE 流式处理中的空指针异常
docs: 更新 README 配置表格
test: 添加 thinking 注入的边界测试
chore: 更新依赖版本
```

## 测试要求

- 所有现有测试必须通过：`python3 -m pytest tests/ -v`
- 新功能的测试覆盖率 ≥ 80%
- 测试命名：`test_函数_场景_预期`

## 分支策略

- `main` — 稳定版本
- `feat/*` — 新功能分支
- `fix/*` — Bug 修复分支
- 所有合并到 `main` 的 PR 需通过 CI

## 疑问

如有任何问题，开 Issue 或 Discussion 即可。

再次感谢你的贡献！
