# P14_dsv4ToCC

**DeepSeek Anthropic API 兼容性代理** — 让 Claude Code 在 DeepSeek V4 模型上稳定运行。

## 项目架构

```
proxy/deepseek-thinking-proxy.py   # 代理核心 (v1.8)
proxy/test_proxy.py                # 22 个单元测试
proxy/requirements.txt             # Python 依赖
```

## 核心技术栈

- Python + Flask（轻量 HTTP 代理）
- SSE 流式处理（事件重写/过滤/剥离）
- `.plist` macOS launchd 自启

## 关键设计

代理在 `POST /v1/messages` 三层处理：
1. **请求端注入**: assistant tool_use 无 thinking 时插入空 thinking 块
2. **请求标准化**: `thinking.type=adaptive` → `disabled`，移除 `reasoning_effort`
3. **响应过滤**: SSE 流中剥离 DeepSeek 无条件返回的 thinking/thinking_delta/signature_delta

## 开发

```bash
cd proxy
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest test_proxy.py -v
```

## 命令

- `python3 proxy/deepseek-thinking-proxy.py` — 启动代理
- `python3 -m pytest proxy/test_proxy.py -v` — 运行测试
