# Hacker News 帖子

## Title

Show HN: dsv4-cc-proxy – Run Claude Code on DeepSeek V4 without errors

## URL

https://github.com/HosheaLi/dsv4-cc-proxy

## Text

Hi HN,

DeepSeek V4 implements the Anthropic API format, but Claude Code expects a few things that DeepSeek doesn't support:

1. `tool_use` messages need a `thinking` block before them, or Claude Code gets a 400 error
2. Claude Code sends `thinking.type=adaptive` with `reasoning_effort`, which DeepSeek only handles as `enabled`/`disabled`
3. DeepSeek unconditionally emits SSE `thinking` events that confuse Claude Code's parser

I built a lightweight proxy that fixes all three transparently: https://github.com/HosheaLi/dsv4-cc-proxy

- Python/Starlette/httpx, ~300 lines, zero external dependencies beyond those three
- 22 unit tests
- macOS launchd, Windows scheduled task, Linux systemd, Docker – pick your platform
- Non-DeepSeek requests pass through with zero overhead

```
pip install -r proxy/requirements.txt
python3 proxy/deepseek-thinking-proxy.py
# Point Claude Code to http://localhost:16889
```

Took me a while to figure out the exact incompatibilities from the error logs, so hopefully this saves others the same debugging time.
