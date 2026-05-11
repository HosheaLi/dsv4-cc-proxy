
在使用 Claude Code 的过程中，Anthropic 官方 API 的调用成本和网络问题一直是个痛点。DeepSeek V4 提供了兼容 Anthropic 格式的 API，价格优势明显，但实际对接时存在若干协议层面的差异，直接使用的话在进行 Agent spawn 工具调用时会出现不少问题。

经过排查，定位到 **3 个核心兼容性问题**：

```
reasoning_content 返回 400 错误
Tool result missing due to internal error
SSE 流式输出中途截断
```

DeepSeek 官方文档对思考模式的行为作了明确说明：

> 思考模式不支持 temperature、top_p、presence_penalty、frequency_penalty 参数。请注意，为了兼容已有软件，设置参数不会报错，但也不会生效。
>
> 在思考模式下，思维链内容通过 `reasoning_content` 参数返回，与 `content` 同级。在后续轮次的拼接中，可以选择性地返回 `reasoning_content` 给 API：
>
> - 在两个 user 消息之间，如果模型**未进行工具调用**，则中间 assistant 的 `reasoning_content` 无需参与上下文拼接，在后续轮次中将其传入 API 会被忽略。
> - 在两个 user 消息之间，如果模型**进行了工具调用**，则中间 assistant 的 `reasoning_content` 需参与上下文拼接，在后续所有 user 交互轮次中**必须回传**给 API。

代理中间件的核心设计思路正是基于上述规则：在工具调用场景下自动补全 `reasoning_content` 的结构要求，在响应端剥离 DeepSeek 无条件返回的 thinking 事件。项目已开源：[dsv4-cc-proxy](https://github.com/HosheaLi/dsv4-cc-proxy)

---

### 问题分析与解决方案

| # | 问题 | 症状 | 解决方案 |
|---|------|------|---------|
| 1 | tool_use 消息缺少 thinking 块 | `reasoning_content` 400 错误 | 请求端自动注入空 thinking 块 |
| 2 | DeepSeek 无条件返回 thinking SSE 事件 | `Tool result missing due to internal error` | 响应端剥离 SSE 中的 thinking 事件 |
| 3 | `thinking.type=adaptive` 不被支持 | 流式截断 / 400 | 标准化为 disabled + 移除 reasoning_effort 参数 |

---

### 技术设计

**轻量实现**
基于 Starlette + httpx 构建，核心代码不到 300 行，无外部服务依赖，内存占用低。

**测试覆盖**
22 个单元测试，覆盖各修复路径的边界场景。

**代理行为**
代理仅在 `POST /v1/messages` 请求上执行修复逻辑，其余端点零开销透传，不影响正常 API 调用。

架构示意：

```
Claude Code ←→ localhost:16889 (dsv4-cc-proxy) ←→ api.deepseek.com
```

---

### 效果对比

| 场景 | 无代理直连 | 通过代理 |
|------|-----------|---------|
| tool_use 消息缺 thinking | 400 错误 | 自动注入修复 |
| Claude 发送 adaptive thinking | 流截断 / 400 | 自动标准化为 disabled |
| DeepSeek 返回 thinking 事件 | Tool result missing | 自动剥离 |
| 非 messages 端点请求 | 正常 | 零开销透传 |

---

### 部署方式

支持多种部署场景：

| 平台 | 部署方式 |
|------|---------|
| pip 安装（推荐） | `pip install dsv4-cc-proxy` + `dsv4-cc-proxy` |
| Homebrew（macOS） | `brew install hosheali/tap/dsv4-cc-proxy` |
| Docker | `docker run -d -p 16889:16889 hosheali/dsv4-cc-proxy` |
| macOS | launchd 开机自启（`brew services start`） |
| Windows | 计划任务 / 双击 `.bat` 启动 |
| Linux | systemd 服务 |

**一键安装**：

```bash
pip install dsv4-cc-proxy
dsv4-cc-proxy
```

**Homebrew（macOS）**：

```bash
brew install hosheali/tap/dsv4-cc-proxy
brew services start hosheali/tap/dsv4-cc-proxy
```

**Docker**：

```bash
docker run -d -p 16889:16889 --name dsv4-cc-proxy hosheali/dsv4-cc-proxy:latest
```

启动后配置 Claude Code 的 `ANTHROPIC_BASE_URL`：

```json
"ANTHROPIC_BASE_URL": "http://localhost:16889"
```

---

### 参考资料

- [DeepSeek Thinking Mode 官方文档](https://api-docs.deepseek.com/guides/thinking_mode)
- [Claude Code 配置指南](https://docs.anthropic.com/en/docs/claude-code/setup)
- [项目仓库 — dsv4-cc-proxy](https://github.com/HosheaLi/dsv4-cc-proxy)

如果你有在使用 DeepSeek V4 + Claude Code 的组合，这个工具可以省去排查兼容性问题的时间。欢迎在评论区交流，或在 GitHub 提交 Issue 和 PR。
