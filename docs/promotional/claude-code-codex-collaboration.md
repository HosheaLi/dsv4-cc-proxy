
# Claude Code + Codex 双 AI 协作实战：让两个顶级编程 Agent 接力写代码

在日常开发中，我同时使用 Claude Code 和 OpenAI Codex 两个编程 Agent。一个负责规划调度，一个负责执行编码，理论上效率应该翻倍。但实际跑起来后，遇到了**文件写不进去、任务中途卡死、完成后没通知、线程残留反复弹窗**等一系列问题。

经过逐步排查，最终定位到根因是 **DeepSeek V4 代理的 Responses API 兼容性问题**——Codex CLI 通过代理调用 DeepSeek 时，API 响应格式不匹配导致文件写入等操作在协议层就失败了，表象上像是沙箱或权限问题。

这篇文章记录我从踩坑到填坑的完整过程，根因定位，以及最终稳定的协作方案。


## 协作模型

核心思路：Claude Code 作为**编排者**（规划、拆分任务、审查结果），Codex 作为**执行者**（大批量编码、修复实现），通过 Codex Plugin 桥接。

```
┌──────────────────────────────────────────────────┐
│              Claude Code (编排者)                  │
│                                                    │
│  1. 分析需求 → 拆分 Phase                          │
│  2. 每个 Phase 生成 Task Envelope                  │
│  3. 委托 Codex 执行编码 ─────────────────┐         │
│  4. 审查 Codex 产出 → 判定通过/修改       │         │
│  5. 提交代码 (Claude Code 负责)           │         │
│                                                    │
├──────────────────────────────────────────────────┤
│        codex:codex-rescue (调度层)                 │
│                                                    │
│  codex exec -C <worktree> --json                  │
│       ↓                                            │
│  stdin/stdout 直连 (无中间守护进程)                 │
│       ↓                                            │
│  ┌──────────────────────────┐                     │
│  │   Codex CLI v0.141.0     │                     │
│  │   (DeepSeek V4 via 代理)  │                     │
│  │                          │                     │
│  │  • 读取代码库             │                     │
│  │  • 执行命令/写文件         │                     │
│  │  • 运行测试验证            │                     │
│  └──────────────────────────┘                     │
└──────────────────────────────────────────────────┘
```

实际使用示例：

```bash
# Phase 3: 对话引擎 + 决策引擎
/codex:rescue --background "实现 Phase 3: conversation/engine.py (FSM状态机) 
  + decision/engine.py (决策引擎)，包含完整测试，删除旧 loop.py"

# Phase 6: 认证流程 + 事件系统
/codex:rescue "实现 Phase 6: auth/session.py (登录态管理) 
  + events/dispatcher.py (事件总线)，覆盖所有单元测试"
```

## 遇到的问题

两头 AI 协作听上去美好，实际跑起来遇到了 **5 个核心问题**：

| # | 问题 | 现象 | 严重程度 |
|---|------|------|---------|
| 1 | **文件写不进去** | Codex 报告完成，`git status` 显示 clean | 🔴 致命 |
| 2 | **无进度反馈** | 执行中完全静默，不知道卡死还是在跑 | 🟠 严重 |
| 3 | **完成后没通知** | 任务结束无任何提示，需手动检查才知完成 | 🟠 严重 |
| 4 | **10分钟超时太短** | 复杂任务被 Claude Code Bash 超时强杀 | 🟡 中等 |
| 5 | **线程残留反复弹窗** | 每次新任务提示 "存在已完成线程，如何处理？" | 🟡 中等 |


## 问题分析与解决

### 根因定位：代理 API 兼容性问题

在逐项解决表层问题之前，关键的排查过程如下：

**现象**：Codex 任务报告"完成"，实际文件未落盘，`git status` 显示 clean。同时伴随间歇性任务中断、部分命令执行失败等异常。

**初步排查**：初看像是 macOS Sandbox/Seatbelt 的 `workspace-write` 模式 bug——Codex 在受限沙箱中执行，文件写入被系统拦截。这也是 GitHub 上 openai/codex 已知 issue 提到的问题。

但进一步验证发现：**通过 `codex exec` 直接调用，即使使用相同的沙箱参数，文件也能正常写入**。真正的问题出在 Claude Code Plugin 通过 App Server (JSON-RPC) 调用时，Codex CLI 与 DeepSeek V4 代理之间的 **Responses API 协议兼容性**——代理未正确处理部分 API 响应格式，导致 Codex 在 App Server 模式下执行文件操作时出现协议层错误。

**最终解决**：更新 DeepSeek V4 代理的 Responses API 翻译层，修复协议兼容性后，两条路径（`codex exec` 和 App Server）均恢复正常。表层的 sandbox/heartbeat/ephemeral 修复仍然是必要的防御性改进。

### 问题 1：文件写不进去 — 代理协议兼容性

**排查过程**：

第一反应是 Codex 没在做事。查了日志发现不是——Codex 确实跑了，命令都执行了，但最终文件在磁盘上看不到。

进一步对比发现两条 Codex 调用路径表现不同：

- **GSD Bridge 路径**：`codex exec --json` → 正常，文件落盘
- **Plugin App Server 路径**：JSON-RPC thread/start → 异常，文件不落盘

怀疑过是 macOS Seatbelt 沙箱问题，但 `codex exec` 在相同机器上正常排除了这个可能。最终沿协议链路逐层排查，定位到 **dsv4-cc-proxy 代理的 Responses API → Chat Completions 翻译层存在兼容性缺陷**——部分 tool call 响应未被正确解析，导致 Codex App Server 模式下的文件写入在协议层中断。表象上很容易误判为 sandbox 权限问题。

**解决方案**：

修复代理的 Responses API 翻译层（`dsv4-cc-proxy/codex/translate.py`），补全 SSE 事件状态机和 tool call 响应格式兼容性。修复后所有 Codex 调用路径（`codex exec`、App Server JSON-RPC、`/codex:rescue` 插件命令）均正常落盘。

同时保留了防御性配置——将 App Server 沙箱级别从 `workspace-write` 提升到 `danger-full-access`，避免 macOS 下潜在的 Seatbelt 拦截（沙箱行为在不同 OS 版本间不稳定）。

### 问题 2+3：无心跳 + 无完成通知

Codex App Server 的 turn 捕获逻辑只等待完成信号，中间没有任何定期输出。导致两个体验问题：
- 执行中：LLM 思考期间完全静默，用户不知道 Codex 是否卡死
- 完成后：没有明确的通知，直到手动检查才知道结束

**解决方案**：

在 `captureTurn` 函数（App Server turn 等待的统一入口）中增加三层机制：

```javascript
// 心跳：每 30 秒报告进度
heartbeatInterval = setInterval(() => {
  emitProgress(onProgress,
    `Codex 运行中... ${mins}m${secs}s | ${commands} 命令 | ${files} 文件变更`,
    "running");
}, 30000);

// 超时保护：默认 25 分钟
timeoutTimer = setTimeout(() => {
  emitProgress(onProgress,
    `Codex 超时，返回部分结果。`, "finalizing");
  completeTurn(state, null, { timedOut: true });
}, timeoutMs);

// 完成通知：Turn 结束后输出摘要
emitProgress(onProgress,
  `Codex 完成: ${fileCount} 文件变更, ${cmdCount} 命令。`, "finalizing");
emitProgress(onProgress,
  `变更文件: ${touchedFiles.join(", ")}`, "finalizing");
```

现在的输出效果：

```
[codex] Codex 运行中... 2m30s | 5 命令 | 0 文件变更    ← 心跳
[codex] Codex 运行中... 5m0s | 12 命令 | 3 文件变更     ← 心跳
[codex] Codex 运行中... 7m30s | 18 命令 | 6 文件变更    ← 心跳
[codex] Codex 完成: 8 文件变更, 22 命令。               ← 完成通知
[codex] 变更文件: auth/__init__.py, auth/session.py,    ← 文件清单
         events/dispatcher.py, tests/test_auth/...
```

### 问题 4：10 分钟超时

Claude Code 的 Bash 工具硬上限是 10 分钟（600000ms），无法调整。而 Codex 单轮最长可跑 30 分钟、复杂任务从探索到写入需要 5-15 分钟。

**解决方案**：

在 `codex-companion.mjs` 中添加 `--timeout` 参数，默认 25 分钟（匹配 GSD Bridge），内部通过 `setTimeout` + Promise 竞态实现：

```bash
# 默认 25 分钟超时
codex-companion.mjs task --write "复杂实现任务"

# 自定义超时（分钟）
codex-companion.mjs task --write --timeout 15 "中等复杂度任务"
```

超时后返回部分结果（已写入的文件不丢失），同时输出超时提示便于用户决定是否 `--resume` 续接。

### 问题 5：线程残留弹窗

原来的设计是 `persistThread: true`（持久化线程），每次任务结束后线程残留。下次新任务时，Plugin 会自动检查可续接线程并弹出 "存在之前的 Codex 已完成线程。如何处理？" 的提示。

**解决方案**：

改为 ephemeral（一次性）模式：

```diff
- persistThread: true,
+ // resume 时持久化线程以便后续继续续接；普通任务自动清理
+ persistThread: Boolean(resumeThreadId),
```

逻辑：普通任务 → `ephemeral: true` → 完成自动清理。`--resume` 续接任务 → `ephemeral: false` → 保留线程以便再次续接。

同时移除 `rescue.md` 命令中的自动 `task-resume-candidate` 检查，只有用户显式指定 `--resume` 时才检查可续接线程。


## 修复脚本与持久化

以上修改涉及 6 个文件（cache + marketplace 两个副本各 3 个文件）。插件更新后可能被覆盖，因此编写了一键修复脚本：

```bash
bash ~/.claude/scripts/codex-sandbox-fix.sh
```

脚本自动检测四项修复：
1. sandbox 模式 → `danger-full-access`
2. 心跳代码是否存在
3. 超时保护是否就绪
4. 市场副本自动 git commit

```bash
$ bash ~/.claude/scripts/codex-sandbox-fix.sh

Codex 修复检查 — Thu Jun 18 20:57:59 CST 2026

── sandbox 检查 ──
  ✅ sandbox 已修复: .../cache/.../codex-companion.mjs
  ✅ sandbox 已修复: .../marketplaces/.../codex-companion.mjs

── 心跳/超时检查 ──
  ✅ 心跳已就绪: .../cache/.../codex.mjs
  ✅ 心跳已就绪: .../marketplaces/.../codex.mjs

检查完毕。
```


## 最终协作流程

经过以上修复，Claude Code + Codex 的协作变得丝滑：

```
Claude Code: "实现 Phase 6 的 auth + events 模块"
  │
  ├─ spawn codex:codex-rescue agent
  │     └─ codex-companion.mjs task --write
  │           └─ App Server { sandbox: "danger-full-access", ephemeral: true }
  │                 │
  │                 ├─ [0s]    Starting Codex task thread.
  │                 ├─ [1s]    Thread ready.
  │                 ├─ [30s]   Codex 运行中... 0m30s | 3 命令 | 0 文件变更
  │                 ├─ [2m30s] Codex 运行中... 2m30s | 8 命令 | 0 文件变更
  │                 ├─ [3m]    cat > auth/session.py ... (exit 0)  ← 开始写入
  │                 ├─ [4m]    cat > events/dispatcher.py ... (exit 0)
  │                 ├─ [5m]    pytest tests/ ... 14 passed         ← 运行测试
  │                 ├─ [5m30s] Codex 完成: 6 文件变更, 24 命令。
  │                 └─         变更文件: auth/__init__.py, auth/session.py,
  │                             auth/login_flow.py, events/__init__.py,
  │                             events/dispatcher.py, tests/...
  │
  └─ Claude Code: "审查完成。6 个文件已就位，14 个测试全部通过。Phase 6 完成。"
```

## 小结

| 修复项 | 修改位置 | 改动量 |
|--------|---------|--------|
| **代理 Responses API 协议兼容性**（根因） | dsv4-cc-proxy/codex/translate.py | ~150 行 |
| sandbox `danger-full-access`（防御性） | codex-companion.mjs | 1 行 |
| 30s 心跳 + 完成通知 | codex.mjs (captureTurn + runAppServerTurn) | ~70 行 |
| 25min 超时 + `--timeout` 参数 | codex-companion.mjs + codex.mjs | ~15 行 |
| ephemeral 线程 + 移除弹窗 | codex-companion.mjs + rescue.md + agent | ~10 行 |
| 一键修复脚本 | codex-sandbox-fix.sh | 71 行 |

代理协议修复是根因，解决后 `/codex:rescue` 和 `codex exec` 两条路径均恢复正常。其余防御性改进保留了心跳、超时、ephemeral 等机制，让双 AI 协作可观测、可恢复。

核心教训：
- **AI Agent 协作的故障排查需要追到协议层**。表象可能是文件落不了盘、命令执行失败，实际根因可能在 API 代理的协议翻译层。App Server 模式与 `codex exec` 模式走的是同一条 API 链路，一条通一条不通时，问题往往在中间层
- **AI Agent 协作需要心跳**。LLM 思考期间完全静默，用户需要定期反馈才知道系统没死
- **默认 ephemeral**。子任务应该用完即弃，残留的线程和弹窗会增加认知负担
- **保留防御性修复**。即使根因已解决，sandbox 级别提升、超时保护、心跳机制这些防御性改进仍然有价值——下次遇到其他兼容性问题时，它们能让故障可观测、可恢复


**相关资源**：

- [Codex Plugin for Claude Code](https://github.com/openai/codex-plugin-cc) — OpenAI 官方插件
- [Codex CLI 文档](https://developers.openai.com/codex/cli/) — `codex exec` 和 App Server 协议参考
- [dsv4-cc-proxy](https://github.com/HosheaLi/dsv4-cc-proxy) — DeepSeek V4 → Responses API 代理（本次修复的核心）
- [Codex Permissions 文档](https://developers.openai.com/codex/permissions) — 三种沙箱模式说明
- [Codex Sandbox Issue #14068](https://github.com/openai/codex/issues/14068) — macOS Seatbelt 沙箱已知问题（最终确认非本次根因，但相关）

如果你也在用 Claude Code + Codex 的组合，或者有更好的协作方案，欢迎在评论区交流。
