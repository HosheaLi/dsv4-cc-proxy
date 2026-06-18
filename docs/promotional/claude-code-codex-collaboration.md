
# Claude Code + Codex 双 AI 协作实战：让两个顶级编程 Agent 接力写代码

在日常开发中，我同时使用 Claude Code 和 OpenAI Codex 两个编程 Agent。一个负责规划调度，一个负责执行编码，理论上效率应该翻倍。但实际跑起来后，遇到了**文件写不进去、任务中途卡死、完成后没通知、线程残留反复弹窗**等一系列问题。

这篇文章记录我从踩坑到填坑的完整过程，以及最终的协作方案。


## 协作模型

核心思路：Claude Code 作为**编排者**（规划、拆分任务、审查结果），Codex 作为**执行者**（大批量编码、修复实现），通过 Codex Plugin 桥接。

```
┌──────────────────────────────────────────────────┐
│              Claude Code (编排者)                  │
│                                                    │
│  1. 分析需求 → 拆分 Phase                          │
│  2. 每个 Phase 生成详细实现指令                     │
│  3. 委托 Codex 执行编码 ─────────────────┐         │
│  4. 审查 Codex 产出 → 判定通过/修改       │         │
│  5. 继续下一个 Phase                      │         │
│                                                    │
├──────────────────────────────────────────────────┤
│           codex:codex-rescue (桥接层)              │
│                                                    │
│  codex-companion.mjs task --write                 │
│       ↓                                            │
│  App Server JSON-RPC                              │
│       ↓                                            │
│  ┌──────────────────────────┐                     │
│  │    Codex CLI v0.137      │                     │
│  │    (GPT-5.4 编码引擎)     │                     │
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

### 问题 1：文件写不进去 — 沙箱陷阱

**排查过程**：

第一反应是 Codex 没在做事。查了日志发现不是——Codex 确实跑了，`rm`、`cat >` 命令都执行了，但文件在磁盘上看不到。

进一步对比发现，项目里有两套 Codex 调用路径：

- **GSD Bridge 路径**：`codex exec -s workspace-write --dangerously-bypass-approvals-and-sandbox` → **文件正常写入**
- **Plugin 路径**：App Server `thread/start { sandbox: "workspace-write" }` → **文件不落盘**

关键差异在于 `--dangerously-bypass-approvals-and-sandbox` 标志。App Server 虽然也支持 `workspace-write` 沙箱模式，但 macOS Seatbelt 会拦截实际的写操作。GitHub 上有多个已确认的 bug issue（openai/codex #14068、#6667、#5824）—— 即使在 App Server 协议中指定了 `workspace-write`，工具命令仍在 read-only 沙箱中执行。

**解决方案**：

App Server 协议其实支持三种沙箱模式：

| 模式 | 文件写入 | 网络 | 插件是否使用 |
|------|---------|------|------------|
| `read-only` | 禁止 | 禁止 | ✅ 审查任务 |
| `workspace-write` | **buggy（macOS 不落盘）** | 可选 | ❌ 已弃用 |
| **`danger-full-access`** | **直接落盘** | 全开 | ✅ **修复后采用** |

修改一行代码（`codex-companion.mjs:488`）：

```diff
- sandbox: request.write ? "workspace-write" : "read-only",
+ sandbox: request.write ? "danger-full-access" : "read-only",
```

`danger-full-access` 等效于 `codex exec --dangerously-bypass-approvals-and-sandbox`，完全绕过 OS 级沙箱，文件直接写入真实文件系统。

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

| 修复项 | 修改文件 | 改动量 |
|--------|---------|--------|
| sandbox `danger-full-access` | codex-companion.mjs | 1 行 |
| 30s 心跳 + 完成通知 | codex.mjs (captureTurn + runAppServerTurn) | ~70 行 |
| 25min 超时 + `--timeout` 参数 | codex-companion.mjs + codex.mjs | ~15 行 |
| ephemeral 线程 + 移除弹窗 | codex-companion.mjs + rescue.md + agent | ~10 行 |
| 一键修复脚本 | codex-sandbox-fix.sh | 71 行 |

全部改动不到 200 行代码，解决了双 AI 协作中最影响体验的五个痛点。

核心教训：
- **App Server 的沙箱 ≠ CLI 的沙箱**。即使表面上参数相同，底层行为可能完全不同（macOS Seatbelt 下的 `workspace-write` bug）
- **AI Agent 协作需要心跳**。LLM 思考期间完全静默，用户需要定期反馈才知道系统没死
- **默认 ephemeral**。子任务应该用完即弃，残留的线程和弹窗会增加认知负担
- **写修复脚本**。Plugin 更新可能覆盖修改，自动化恢复是必要的


**相关资源**：

- [Codex Plugin for Claude Code](https://github.com/openai/codex-plugin-cc) — OpenAI 官方插件
- [Codex CLI 文档](https://developers.openai.com/codex/cli/) — App Server 协议参考
- [Codex Sandbox Issue #14068](https://github.com/openai/codex/issues/14068) — App Server sandbox bug
- [Codex Permissions 文档](https://developers.openai.com/codex/permissions) — 三种沙箱模式说明

如果你也在用 Claude Code + Codex 的组合，或者有更好的协作方案，欢迎在评论区交流。
