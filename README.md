<div align="center">

[**中文版 README**](README.zh-CN.md)

# dsv4-cc-proxy

**Make DeepSeek V4 work flawlessly with Claude Code**

Anthropic API compatibility proxy with **built-in watchdog**, **upstream resilience**, and **cross-platform support**.

```
Claude Code ←→ localhost:16889 (dsv4-cc-proxy) ←→ api.deepseek.com/anthropic
```

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![CI](https://github.com/HosheaLi/dsv4-cc-proxy/actions/workflows/ci.yml/badge.svg)](https://github.com/HosheaLi/dsv4-cc-proxy/actions)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)]()
[![Docker Pulls](https://img.shields.io/docker/pulls/hosheali/dsv4-cc-proxy)](https://hub.docker.com/r/hosheali/dsv4-cc-proxy)
[![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen)](coverage.svg)

</div>

---

## What's New in v2.1.0

| Feature | Description |
|---------|-------------|
| 🔄 **Watchdog Mode** | `--watchdog` flag enables automatic crash recovery — parent process monitors and restarts the child on failure |
| 🔁 **Upstream Retry + Fallback** | Automatic retry with exponential backoff + optional fallback URL (`PROXY_UPSTREAM_FALLBACK`) when DeepSeek is unreachable |
| 🪟 **Windows Compatibility** | PID file auto-adapts to `%TEMP%`, startup errors visible via stderr + Event Log |
| 🍎 **macOS Installer** | `scripts/install_macos.sh` auto-detects Python, handles Homebrew externally-managed environments, falls back to venv |
| 🚨 **Port Conflict Detection** | Proactive port check before startup — prevents silent failure and watchdog restart loops |
| 🔍 **Startup Failure Visibility** | All platforms: fatal errors printed to stderr. Windows: also written to Event Log |
| ✨ **Prompt Character Normalization** | Unicode typographic quotes auto-converted to ASCII, date format unified (`2026/06/30` → `2026-06-30`) to prevent DeepSeek parsing errors |

## Why dsv4-cc-proxy

DeepSeek V4 implements the Anthropic API format, but has 4 critical incompatibilities that break Claude Code. This proxy fixes them transparently.

| # | Problem | Symptom | Fix |
|---|---------|---------|-----|
| 1 | `tool_use` assistant messages missing a `thinking` block | `reasoning_content` 400 error | Inject empty thinking block before each tool_use |
| 2 | DeepSeek unconditionally emits `thinking`/`signature_delta` SSE events even when thinking is disabled | `Tool result missing due to internal error` in Claude Code | Strip thinking events from the SSE response stream |
| 3 | `thinking.type=adaptive` (Claude Code default) + `reasoning_effort` not supported by DeepSeek | Stream truncation / 400 errors | Normalize to `disabled` + strip reasoning_effort |
| 4 | Unicode typographic quotes (`'` `'` `'`) and date slash format (`2026/06/30`) in system prompts cause DeepSeek to misinterpret instructions | Truncated tool call arguments, malformed JSON output | Recursively normalize to ASCII single quotes + `YYYY-MM-DD` date format |

Non-DeepSeek requests and non-`/messages` endpoints pass through with zero overhead.

## Codex Support

dsv4-cc-proxy also translates between the [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses) format and DeepSeek's Chat Completions API, enabling Codex (and other OpenAI Responses API clients) to use DeepSeek V4 models.

```
Codex (Claude Code) ──→ localhost:16889 ──→ https://api.deepseek.com/chat/completions
```

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /v1/responses` | Translate Responses API requests to Chat Completions, then translate responses back |
| `POST /v1/responses/compact` | Not supported — returns 501 |

### Environment Variables

| Env Var | Default | Description |
|---------|---------|-------------|
| `CODEX_DEFAULT_MODEL` | `deepseek-v4-pro` | Default model for Codex requests |
| `CODEX_MODEL_MAP` | `{}` | JSON map of client model names to DeepSeek model names (e.g., `{"claude-sonnet-4-6": "deepseek-v4-pro"}`) |
| `CODEX_UPSTREAM` | `https://api.deepseek.com/chat/completions` | DeepSeek Chat Completions API URL |

### Usage

Point Codex to the same proxy URL:

```json
"OPENAI_BASE_URL": "http://localhost:16889"
```

The proxy auto-detects Responses API requests (`/v1/responses`) and applies the appropriate translation. All existing Anthropic API proxy features remain unchanged.

## Quick Start

### Option 1: pip install (recommended)

```bash
pip install dsv4-cc-proxy

# Start the proxy (default port 16889)
dsv4-cc-proxy

# Stop the proxy
dsv4-cc-proxy --stop
```

### Option 2: Homebrew (macOS)

```bash
brew install hosheali/tap/dsv4-cc-proxy

# Start the proxy
dsv4-cc-proxy

# Register as a background service (auto-start on login)
brew services start hosheali/tap/dsv4-cc-proxy
```

### Option 3: pipx (isolated environment)

```bash
pipx install dsv4-cc-proxy
dsv4-cc-proxy
```

### Option 4: Docker

```bash
docker run -d -p 16889:16889 --name dsv4-cc-proxy hosheali/dsv4-cc-proxy:latest
```

Or via docker compose:

```bash
docker compose up -d
```

### Configure Claude Code

Point Claude Code to the proxy by adding to your `settings.local.json`:

```json
"ANTHROPIC_BASE_URL": "http://localhost:16889"
```

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `PROXY_UPSTREAM` | `https://api.deepseek.com/anthropic` | DeepSeek API base URL |
| `PROXY_UPSTREAM_FALLBACK` | *(empty=off)* | Fallback upstream URL when primary is unreachable. Must be Anthropic API compatible |
| `PROXY_UPSTREAM_RETRY_COUNT` | `2` | Retry attempts per upstream target |
| `PROXY_UPSTREAM_RETRY_BASE_DELAY` | `1.0` | Base delay (seconds) for exponential backoff: `delay = base × 2^attempt` |
| `PROXY_HOST` | `127.0.0.1` | Bind address |
| `PROXY_PORT` | `16889` | Bind port |
| `PROXY_LOG_LEVEL` | `warning` | Log level (`info` for debugging) |
| `PROXY_DUMP_DIR` | *(empty=off)* | Debug traffic dump directory. ⚠ Contains conversation data |
| `PROXY_WATCHDOG_MAX_RESTARTS` | `5` | Max child process restarts before watchdog gives up |
| `PROXY_WATCHDOG_RESTART_DELAY` | `2` | Seconds between restart attempts |
| `PROXY_WATCHDOG_POLL_INTERVAL` | `0.5` | Seconds between child process liveness checks |

> For Codex usage, see the [Codex Support](#codex-support) section above.

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

**Recommended: Use the installer script:**

```bash
# Auto-detects Python, creates venv if needed, installs as LaunchAgent
bash scripts/install_macos.sh

# Or specify Python path manually
bash scripts/install_macos.sh /path/to/python3
```

**Manual setup:**

```bash
# Edit paths in the plist template, then:
cp scripts/com.deepseek.thinking-proxy.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist
```

> **Note:** To stop a launchd-managed proxy, unload first: `launchctl unload ~/Library/LaunchAgents/com.deepseek.thinking-proxy.plist`. Using `--stop` alone won't work because `KeepAlive` restarts it.

### Windows (Scheduled Task)

```batch
:: One-time setup (auto-start at logon, restart on crash)
powershell -ExecutionPolicy RemoteSigned -File scripts\install_windows_service.ps1 -Install

:: Start manually in terminal
scripts\start.bat

:: Or with PowerShell
powershell -ExecutionPolicy RemoteSigned -File scripts\start.ps1
```

> **Note:** `--stop` relies on POSIX signals and is **not supported on Windows**. Use `Ctrl+C` in the terminal or `taskkill` instead.

### Watchdog Mode (all platforms)

For bare-process deployments without a platform supervisor:

```bash
dsv4-cc-proxy --watchdog
# Child crashes → auto-restart (up to PROXY_WATCHDOG_MAX_RESTARTS times)
```

> **Note:** `--watchdog` is not needed when using launchd (macOS), Scheduled Task (Windows), or Docker restart policies — the platform supervisor already handles process recovery.

### Linux (systemd)

Create `/etc/systemd/system/dsv4-cc-proxy.service`:

```ini
[Unit]
Description=dsv4-cc-proxy — DeepSeek Anthropic API proxy
After=network.target

[Service]
Type=simple
User=your-user
ExecStart=/usr/local/bin/dsv4-cc-proxy
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dsv4-cc-proxy
```

## Docker (manual build)

```bash
docker build -t dsv4-cc-proxy .
docker run -d -p 16889:16889 --name dsv4-cc-proxy dsv4-cc-proxy
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
pip install dsv4-cc-proxy[test]
pytest tests/ -v
```

### Health Check

```bash
curl http://localhost:16889/health
# → {"status":"ok","version":"2.1.0","upstream":"https://api.deepseek.com/anthropic","upstream_fallback":null}
```

## Project Structure

```
.
├── dsv4_cc_proxy/
│   ├── __init__.py                  # Package entry, exports VERSION + create_app
│   ├── __main__.py                  # CLI entry — dsv4-cc-proxy command
│   ├── _version.py                  # VERSION = "2.0.0" (single source of truth)
│   ├── proxy.py                     # Core proxy logic (factory pattern)
│   └── codex/                       # Codex (Responses API) protocol translation
│       ├── __init__.py
│       ├── config.py
│       ├── translate.py
│       ├── tools.py
│       └── sse.py
├── tests/
│   ├── test_proxy.py                # 22 unit tests
│   ├── test_codex.py                # Codex config tests
│   ├── test_translate.py            # Request translation tests
│   ├── test_tools.py                # Tool format conversion tests
│   ├── test_sse.py                  # SSE streaming tests
│   ├── test_main.py                 # CLI tests
│   └── test_responses.py            # Codex HTTP route tests
├── scripts/
│   ├── start.bat                    # Windows batch startup
│   ├── start.ps1                    # PowerShell startup
│   ├── install_windows_service.ps1  # Windows Task Scheduler setup
│   ├── install_macos.sh             # macOS LaunchAgent installer
│   └── com.deepseek.thinking-proxy.plist  # macOS launchd template
├── Dockerfile                       # Docker multi-stage build
├── docker-compose.yml               # Docker Compose
├── pyproject.toml                   # Build config, entry point
├── MANIFEST.in                      # Package extras
├── .github/workflows/ci.yml         # GitHub Actions CI
├── LICENSE                          # MIT License
└── CONTRIBUTING.md                  # Contributor guidelines
```

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
