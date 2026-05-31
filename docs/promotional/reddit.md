# Reddit 帖子

## Subreddits

r/ClaudeAI, r/LocalLLaMA, r/selfhosted

## Title

dsv4-cc-proxy: an open-source proxy that makes Claude Code work on DeepSeek V4

## Body

If you've tried using Claude Code with DeepSeek V4 you've probably run into:

- `reasoning_content` 400 errors
- `Tool result missing due to internal error`
- Stream truncation

I traced these to three specific incompatibilities between DeepSeek V4's Anthropic API implementation and what Claude Code expects. Built a minimal proxy (~300 lines Python) that fixes all three.

**Repository:** https://github.com/HosheaLi/dsv4-cc-proxy

**Key features:**
- Fixes thinking injection, thinking mode normalization, and SSE event stripping
- 22 unit tests
- pip install, Homebrew, Docker – all supported
- 100% transparent pass-through for non-messages endpoints

```bash
pip install dsv4-cc-proxy
dsv4-cc-proxy
```

Set `ANTHROPIC_BASE_URL` to `http://localhost:16889` in Claude Code and you're good to go.

Happy to answer questions or take suggestions.
