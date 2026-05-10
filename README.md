<div align="center">

[**中文版 README**](README.zh-CN.md)

# dsv4-cc-proxy

**Make DeepSeek V4 work flawlessly with Claude Code**

Anthropic API compatibility proxy that fixes 3 DeepSeek V4 incompatibilities.

```
Claude Code ←→ localhost:16889 (dsv4-cc-proxy) ←→ api.deepseek.com/anthropic
```

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![CI](https://github.com/HosheaLi/dsv4-cc-proxy/actions/workflows/ci.yml/badge.svg)](https://github.com/HosheaLi/dsv4-cc-proxy/actions)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)]()
[![Docker Pulls](https://img.shields.io/docker/pulls/hosheali/dsv4-cc-proxy)](https://hub.docker.com/r/hosheali/dsv4-cc-proxy)

</div>

---

## Why dsv4-cc-proxy

DeepSeek V4 implements the Anthropic API format, but has 3 critical incompatibilities that break Claude Code. This proxy fixes them transparently.

| # | Problem | Symptom | Fix |
|---|---------|---------|-----|
| 1 | `tool_use` assistant messages missing a `thinking` block | `reasoning_content` 400 error | Inject empty thinking block before each tool_use |
| 2 | DeepSeek unconditionally emits `thinking`/`signature_delta` SSE events even when thinking is disabled | `Tool result missing due to internal error` in Claude Code | Strip thinking events from the SSE response stream |
| 3 | `thinking.type=adaptive` (Claude Code default) + `reasoning_effort` not supported by DeepSeek | Stream truncation / 400 errors | Normalize to `disabled` + strip reasoning_effort |

Non-DeepSeek requests and non-`/messages` endpoints pass through with zero overhead.

## Quick Start

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r proxy/requirements.txt

# 3. Start the proxy (default port 16889)
python3 proxy/deepseek-thinking-proxy.py

# 4. Point Claude Code to the proxy
# Set in your Claude Code settings.local.json:
#   "ANTHROPIC_BASE_URL": "http://localhost:16889"
```

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `PROXY_UPSTREAM` | `https://api.deepseek.com/anthropic` | DeepSeek API base URL |
| `PROXY_HOST` | `127.0.0.1` | Bind address |
| `PROXY_PORT` | `16889` | Bind port |
| `PROXY_LOG_LEVEL` | `warning` | Log level (`info` for debugging) |
| `PROXY_DUMP_DIR` | *(empty=off)* | Debug traffic dump directory. ⚠ Contains conversation data |

## Comparison

| Scenario | Without Proxy | With Proxy |
|----------|--------------|------------|
| tool_use msg without thinking | 400 error | Auto-injected empty thinking |
| Claude Code sends `thinking.type=adaptive` | Stream truncation / 400 | Normalized to `disabled` |
| DeepSeek SSE thinking events | Tool result missing error | Silently stripped from stream |
| Non-messages endpoints | — | Zero-overhead passthrough |
| Non-DeepSeek models | — | Zero-overhead passthrough |

## Platform Guides

### macOS (launchd auto-start)

```bash
# Copy and edit paths in the plist file first!
cp scripts/com.deepseek.thinking-proxy.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist
```

**Note:** Edit the plist file to update paths like `/Users/yourname/.claude/proxy/` to match your setup.

### Windows (Scheduled Task)

```batch
:: One-time setup (auto-start at logon, restart on crash)
scripts\install_windows_service.ps1 -Install

:: Start manually in terminal
scripts\start.bat

:: Or with PowerShell
scripts\start.ps1
```

### Linux (systemd)

Create `/etc/systemd/system/dsv4-cc-proxy.service`:

```ini
[Unit]
Description=dsv4-cc-proxy — DeepSeek Anthropic API proxy
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/dsv4-cc-proxy
ExecStart=/path/to/.venv/bin/python3 proxy/deepseek-thinking-proxy.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dsv4-cc-proxy
```

## Docker

```bash
# Build and run
docker build -t dsv4-cc-proxy .
docker run -d -p 16889:16889 --name dsv4-cc-proxy dsv4-cc-proxy

# Or use docker compose
docker compose up -d
```

## How It Works

```
┌─────────────┐     ┌──────────────────┐     ┌────────────────────┐
│ Claude Code │ ──→ │  dsv4-cc-proxy   │ ──→ │  api.deepseek.com  │
│             │     │  localhost:16889  │     │  /anthropic        │
└─────────────┘     └──────────────────┘     └────────────────────┘
                           │
                   ┌───────┴────────┐
                   │  Fixes applied  │
                   │  1. Thinking     │
                   │     injection   │
                   │  2. Thinking     │
                   │     normalize   │
                   │  3. SSE events   │
                   │     strip       │
                   └────────────────┘
```

The proxy intercepts `POST /v1/messages` and applies three fixes for `deepseek-v4*` models. All other requests pass through transparently.

## Testing

```bash
cd proxy
python3 -m pytest test_proxy.py -v
```

### Health Check

```bash
curl http://localhost:16889/health
# → {"status":"ok","version":"1.8","upstream":"https://api.deepseek.com/anthropic"}
```

## Project Structure

```
.
├── proxy/
│   ├── deepseek-thinking-proxy.py   # Proxy core (v1.8)
│   ├── test_proxy.py                # 22 unit tests
│   └── requirements.txt             # Python dependencies
├── scripts/
│   ├── start.bat                    # Windows batch startup
│   ├── start.ps1                    # PowerShell startup
│   ├── install_windows_service.ps1  # Windows Task Scheduler setup
│   └── com.deepseek.thinking-proxy.plist  # macOS launchd (optional)
├── Dockerfile                       # Docker multi-stage build
├── docker-compose.yml               # Docker Compose
├── .github/workflows/ci.yml         # GitHub Actions CI
├── LICENSE                          # MIT License
├── CONTRIBUTING.md                  # Contributor guidelines
└── README.md
```

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
