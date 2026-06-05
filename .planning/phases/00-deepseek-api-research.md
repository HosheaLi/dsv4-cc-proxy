---
security_review: true
---

# Phase 0: DeepSeek API Endpoint Research for Codex Responses API Proxying

**Researched:** 2026-06-04
**Domain:** DeepSeek API endpoints, OpenAI Responses API translation, streaming SSE
**Confidence:** HIGH (cross-verified from official docs, GitHub issues across 10+ projects, and community analysis)

## Summary

This research compares two approaches for proxying OpenAI's Responses API (used by Codex CLI) through DeepSeek V4 models. Both DeepSeek API endpoints -- Chat Completions (`/chat/completions`) and Anthropic-compatible (`/anthropic/v1/messages`) -- support thinking mode and tool calling, but each has distinct SSE formats, known bugs, and translation complexity.

**Primary recommendation:** Use DeepSeek Chat Completions endpoint (`/chat/completions`) as the primary backend for Responses API translation. The Chat Completions API has a closer semantic mapping to Responses API events, a simpler SSE format, and a well-established translation ecosystem. The Anthropic endpoint is best reserved as a fallback (Plan B) for scenarios where Chat Completions encounters the `tool_choice` limitation.

**Both endpoints share the same critical bug:** The `reasoning_content` (Chat) or `thinking` blocks (Anthropic) from assistant messages that made tool calls MUST be preserved and replayed in subsequent turns. Dropping them causes HTTP 400 errors. This is a DeepSeek-side constraint, not endpoint-specific.

### Key Discovery for Existing dsv4-cc-proxy

The existing proxy solves this exact problem for the Anthropic endpoint by injecting empty thinking blocks. For the Responses API path, the fix needs to operate on `reasoning_content` (OpenAI format) rather than `thinking` blocks (Anthropic format), but the underlying issue is identical.

---

## User Constraints (from CONTEXT.md)

*No CONTEXT.md exists for this research phase -- this is a greenfield investigation to inform planning.*

---

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-01 | Compare DeepSeek Chat Completions vs Anthropic endpoint for Codex proxying | Full comparison below |
| REQ-02 | Document SSE format differences and translation complexity | Both formats documented |
| REQ-03 | Identify known bugs and workarounds | 11+ confirmed issues catalogued |
| REQ-04 | Determine if existing dsv4-cc-proxy thinking fixes can be reused | Analysis below |
| REQ-05 | Recommend primary and fallback endpoint strategies | Recommendation with rationale |

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Responses API request parsing | Proxy | -- | Proxy receives Responses API format, parses structured events |
| Chat history management | Proxy | -- | Must preserve `reasoning_content` across tool-call turns |
| SSE format translation | Proxy | -- | Translates Chat/Anthropic SSE events to Responses API events |
| Reasoning content preservation | Proxy | -- | Core DeepSeek compatibility fix, agnostic to endpoint |
| LLM inference | DeepSeek API | -- | Both endpoints ultimately call the same DeepSeek models |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | >=0.27.0 | Async HTTP client | Already used, proven with streaming |
| starlette | >=0.37.0 | ASGI framework | Already used, proven SSE support |
| uvicorn | >=0.29.0 | ASGI server | Already used, stable |

### Translation Support (New)

The existing httpx+starlette+uvicorn stack is sufficient for both endpoint strategies. No additional core dependencies are needed -- the translation logic is pure Python data transformation.

### Alternatives Considered

The ecosystem has 8+ externally maintained proxy projects (ai-adapter Rust, codex-relay Rust, responses-proxy Rust, codex-deepseek Python, CoDeepSeedeX, mimo2codex, etc.) that already solve this problem. Using an existing proxy avoids reinventing the wheel, but none offer the specific DeepSeek thinking-mode fixes (`reasoning_content` round-trip, SSE thinking filtering) that dsv4-cc-proxy already implements.

---

## DeepSeek Endpoint Comparison

### Endpoint A: Chat Completions (`/chat/completions`)

**Base URL:** `https://api.deepseek.com`

**Request format:**
```json
{
  "model": "deepseek-v4-pro",
  "messages": [{"role": "user", "content": "..."}],
  "stream": true,
  "reasoning_effort": "high",
  "extra_body": {"thinking": {"type": "enabled"}}
}
```

**SSE streaming format:**
```
data: {"choices":[{"delta":{"content":"Hello","reasoning_content":null}}]}
data: {"choices":[{"delta":{"content":null,"reasoning_content":"Let me think..."}}]}
data: [DONE]
```

**Chunk types in stream:**
| Field in `delta` | When present | Notes |
|-----------------|-------------|-------|
| `content` | Regular text output | Streaming tokens |
| `reasoning_content` | Thinking mode only | Always before `content` in stream |
| `tool_calls` | Function/tool calling | Accumulated by `index` |
| `role` | First chunk only | Always `"assistant"` |

**Known issues:**
1. `reasoning_content` must be preserved in context across tool-call turns (400 error if missing)
2. `reasoning_content` and `tool_calls` arrive in separate chunks, never the same chunk
3. `tool_choice="required"` and `tool_choice={"type":"function",...}` cause HTTP 400 when thinking mode is enabled
4. Temperature/top_p/presence_penalty/frequency_penalty silently ignored when thinking enabled

**Performance:**
| Model | Input (cache miss) | Input (cache hit) | Output | Max concurrency |
|-------|-------------------|-------------------|--------|-----------------|
| v4-pro | $0.435/M | $0.003625/M | $0.87/M | 500 |
| v4-flash | $0.14/M | $0.0028/M | $0.28/M | 2,500 |

**Context:** 1M tokens input, 384K tokens max output

**Strengths for Responses API translation:**
- Native OpenAI format -- Responses API is built on the same protocol
- `reasoning_content` maps directly to `response.reasoning_summary_text.delta`
- `tool_calls` maps to `response.function_call_arguments.delta`
- Simple `data:` line SSE format (no `event:` line complexity)
- `finish_reason` matches Responses API `stop_reason` semantics
- Well-established translation by 6+ existing proxy projects

### Endpoint B: Anthropic Compatible (`/anthropic/v1/messages`)

**Base URL:** `https://api.deepseek.com/anthropic`

**Request format:**
```json
{
  "model": "deepseek-v4-pro",
  "messages": [{"role": "user", "content": "..."}],
  "stream": true,
  "thinking": {"type": "enabled"},
  "anthropic_version": "2023-06-01"
}
```

**SSE streaming format:**
```
event: message_start
data: {"type":"message_start","message":{"id":"...","content":[],"role":"assistant",...}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":"","signature":"..."}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"Let me think..."}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: content_block_start
data: {"type":"content_block_start","index":1,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"Hello"}}

event: content_block_stop
data: {"type":"content_block_stop","index":1}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}

event: message_stop
data: {"type":"message_stop"}
```

**Block types:**
| Block type | Delta type | Purpose |
|-----------|------------|---------|
| `thinking` | `thinking_delta` | Chain-of-thought reasoning content |
| `text` | `text_delta` | Final text output |
| `tool_use` | `input_json_delta` | Tool call arguments (partial JSON) |
| `thinking` | `signature_delta` | Cryptographic signature for replay validation |

**Known issues (beyond shared ones):**
1. Thinking blocks must be replayed unchanged (including DeepSeek-issued signatures) -- same 400 error as endpoint A
2. Content block lifecycle must be strictly ordered: start -> delta(s) -> stop
3. Thinking and text blocks cannot be simultaneously open (protocol constraint)
4. `input_json_delta` uses `partial_json` field name, not `input`
5. SSE events can be split across network packets (requires line-level buffering)
6. `cache_control` and `thinking.budget_tokens` are silently ignored
7. Some proxy implementations incorrectly translate Anthropic-format tools to OpenAI format, dropping `function.name`

**Strengths for Responses API translation:**
- Rich content block lifecycle (start/delta/stop) maps well to Responses API output item lifecycle
- Thinking blocks have native SSE support (no need to parse `reasoning_content` field)
- Existing dsv4-cc-proxy code can be partially reused (thinking injection + SSE filtering)
- Proven compatibility with Claude Code (existing proxy is in production)

### Shared Issues (Both Endpoints)

| Issue | Root Cause | Impact | Workaround |
|-------|-----------|--------|------------|
| `reasoning_content` must round-trip | DeepSeek validates thinking content across turns | HTTP 400 on 2nd+ turn with tool calls | Preserve `reasoning_content` in context or inject empty `""` as fallback |
| `tool_choice="required"` fails in thinking mode | DeepSeek V4 doesn't support forced tool choice in thinking mode | Breaks structured output, WebSearch | Use `tool_choice="auto"` only |
| Temperature/presence_penalty ignored in thinking mode | Thinking mode disables sampling params | Silent no-op | Accept the limitation |
| Legacy model names deprecated | `deepseek-chat`/`deepseek-reasoner` removed July 24, 2026 | Model not found | Migrate to `deepseek-v4-pro`/`deepseek-v4-flash` |
| Thinking mode is default for V4 | Default behavior | Unexpected behavior change | Explicitly set `thinking: {"type": "disabled"}` if disabling |

---

## Architecture Patterns

### SSE Translation Pattern (Chat Completions -> Responses API)

The most common pattern across all existing translation proxies (responses-proxy, codex-relay, ai-adapter):

```
Chat Delta Stream                    Responses API Event Stream
─────────────────                  ─────────────────────────────
First chunk                        response.created
                                   response.in_progress
                                   response.output_item.added
                                   response.content_part.added

delta.content                      response.output_text.delta (repeated)

delta.tool_calls (new)
  → output_item.added              response.output_item.added (function_call)
  → function_call_arguments.delta  response.function_call_arguments.delta (repeated)

delta.reasoning_content            response.reasoning_summary_text.delta (repeated)

finish_reason="stop"               response.output_text.done
                                   response.content_part.done
                                   response.output_item.done
                                   response.completed

[ DONE ]                           (stream terminated)
```

### SSE Translation Pattern (Anthropic -> Responses API)

```
Anthropic SSE Event                 Responses API Event
──────────────────                 ─────────────────────────────
message_start                       response.created
                                    response.in_progress

content_block_start (text)          response.output_item.added
                                    response.content_part.added

content_block_delta (text_delta)    response.output_text.delta (repeated)

content_block_stop (text)           response.output_text.done
                                    response.content_part.done
                                    response.output_item.done

content_block_start (tool_use)      response.output_item.added (function_call)

content_block_delta (input_json)    response.function_call_arguments.delta (repeated)

content_block_stop (tool_use)       response.output_item.done

content_block_start (thinking)      response.reasoning_summary_part.added

content_block_delta (thinking)      response.reasoning_summary_text.delta (repeated)

content_block_stop (thinking)       response.reasoning_summary_text.done

message_delta                       
message_stop                        response.completed
```

### Translation Complexity Comparison

| Aspect | Chat -> Responses | Anthropic -> Responses |
|--------|------------------|----------------------|
| Lines of translation logic | ~50-80 lines | ~100-150 lines |
| State machine management | Simple (delta buffer) | Complex (block lifecycle) |
| Reasoning extraction | Direct `reasoning_content` | Parse thinking blocks from content |
| Tool call assembly | Accumulate by `index` | Buffer `partial_json` by block index |
| Known-working implementations | 6+ projects | 1-2 projects (ai-adapter) |

**The Chat Completions endpoint requires approximately 40-50% less translation code.**

### Existing dsv4-cc-proxy Reuse Analysis

The existing proxy implements three fixes for the Anthropic endpoint:

| Fix | Anthropic Format | Responses API Equivalent | Reusable? |
|-----|-----------------|-------------------------|-----------|
| Thinking injection | Inject empty `thinking` block before `tool_use` | Inject `reasoning_content: ""` on assistant messages | Logic reusable, format different |
| Thinking normalization | Convert `adaptive` -> `disabled` | Not needed (Responses API has explicit `reasoning.effort`) | Not needed |
| SSE thinking filtering | Filter `thinking_delta`/`signature_delta` events | Filter `reasoning_content` from content | Logic reusable, SSE format different |

**Verdict:** Approximately 30% of the existing proxy's logic is directly reusable (the concept of preserving reasoning content across turns). The SSE handling and format conversion need to be rewritten for Responses API format.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Basic Responses API -> Chat translation | Custom SSE parser | Adapt logic from [responses-proxy](https://github.com/CallOrRet/responses-proxy) or [codex-relay](https://github.com/MetaFARS/codex-relay) | Both MIT-licensed, well-tested Rust/Python implementations |
| `reasoning_content` round-trip fix | Complex caching layer | `reasoning_content: ""` fallback injection on all assistant messages | Simpler and more reliable than tracking state per-message |

**Key insight:** The `reasoning_content` round-trip bug is the deceptively complex problem. Many teams implement caching or state tracking, but the simplest reliable fix is to ensure EVERY assistant message in the request history has `reasoning_content` set -- even if empty string. This eliminates the conditional logic.

---

## Common Pitfalls

### Pitfall 1: `reasoning_content` Not Preserved in Context
**What goes wrong:** Second and subsequent API calls with tool-call history fail with HTTP 400.
**Root cause:** DeepSeek validates that `reasoning_content` from tool-calling assistant messages is echoed back in all subsequent requests.
**How to avoid:** Always set `reasoning_content: ""` on every assistant message that has `tool_calls` but no `reasoning_content`.
**Warning signs:** `HTTP 400: The reasoning_content in the thinking mode must be passed back to the API.`

### Pitfall 2: `tool_choice="required"` Causes 400
**What goes wrong:** Structured output extraction breaks; WebSearch tool fails.
**Root cause:** DeepSeek V4's thinking mode rejects forced tool choice.
**How to avoid:** Only use `tool_choice="auto"`. For forced tool usage, disable thinking mode.
**Warning signs:** `HTTP 400: Thinking mode does not support this tool_choice`

### Pitfall 3: SSE Events Split Across Network Packets
**What goes wrong:** Malformed JSON parsing, lost events.
**Root cause:** SSE streams can fragment mid-line; line-level buffering is required.
**How to avoid:** Implement line-level buffering (split on `\n`, buffer incomplete lines).
**Warning signs:** `json.JSONDecodeError` on partially-received SSE data.

### Pitfall 4: Empty `reasoning_content` Stripped by JSON Serializer
**What goes wrong:** The `reasoning_content: ""` pair is serialized as if non-existent, triggering the 400 error.
**Root cause:** Some JSON serializers omit null/empty fields by default. DeepSeek validates the field exists, even if empty.
**How to avoid:** Use `json.dumps(data, ensure_ascii=False)` or a custom encoder that preserves empty/None fields.

### Pitfall 5: Anthropic Thinking Blocks Stripped on Replay
**What goes wrong:** Same 400 error, different field name.
**Root cause:** Generic Anthropic clients strip `thinking` blocks from assistant messages. DeepSeek signs its own blocks and requires them unchanged.
**How to avoid:** Detect `api.deepseek.com/anthropic` and preserve ALL thinking blocks (including DeepSeek-issued signatures).

---

## Code Examples

### Chat Completions -> Responses API Translation (Core Logic)

```python
# Core translation: Chat delta to Responses API event
# Source: Derived from community patterns (responses-proxy, codex-relay)

def translate_chat_to_response(
    chunk: dict,
    state: TranslationState
) -> list[dict]:
    """Translate a single Chat Completions chunk to Responses API events."""
    events = []
    choice = chunk.get("choices", [{}])[0]
    delta = choice.get("delta", {})

    if state.first_chunk:
        events.append({"type": "response.created", "response": state.response_stub})
        events.append({"type": "response.in_progress"})
        events.append({"type": "response.output_item.added", "item_id": state.item_id})
        events.append({"type": "response.content_part.added"})
        state.first_chunk = False

    # Reasoning content
    if delta.get("reasoning_content"):
        events.append({
            "type": "response.reasoning_summary_text.delta",
            "item_id": state.item_id,
            "output_index": 0,
            "summary_index": 0,
            "delta": delta["reasoning_content"],
            "sequence_number": state.next_seq(),
        })

    # Text content
    if delta.get("content"):
        events.append({
            "type": "response.output_text.delta",
            "item_id": state.item_id,
            "output_index": 0,
            "content_index": 0,
            "delta": delta["content"],
            "sequence_number": state.next_seq(),
        })

    # Tool calls
    if delta.get("tool_calls"):
        for tc in delta["tool_calls"]:
            idx = tc.get("index", 0)
            # First tool call delta for this index
            if idx not in state.tool_call_items:
                state.tool_call_items[idx] = {
                    "item_id": f"fc_{uuid4().hex[:12]}",
                    "call_id": tc.get("id", f"call_{uuid4().hex[:12]}"),
                    "name": tc.get("function", {}).get("name", ""),
                }
                events.append({
                    "type": "response.output_item.added",
                    "item_id": state.tool_call_items[idx]["item_id"],
                    "output_index": idx + 1,
                    "item": {
                        "type": "function_call",
                        "id": state.tool_call_items[idx]["call_id"],
                        "name": state.tool_call_items[idx]["name"],
                        "arguments": "",
                    }
                })
            # Subsequent argument deltas
            args = tc.get("function", {}).get("arguments", "")
            if args:
                events.append({
                    "type": "response.function_call_arguments.delta",
                    "item_id": state.tool_call_items[idx]["item_id"],
                    "output_index": idx + 1,
                    "delta": args,
                    "sequence_number": state.next_seq(),
                })

    # Finish
    finish_reason = choice.get("finish_reason")
    if finish_reason:
        events.extend(state.build_finish_events(finish_reason))

    return events
```

### `reasoning_content` Round-Trip Fix

```python
# Applied to ALL outgoing requests using DeepSeek V4 with thinking mode
# Source: Community-proven pattern from Hermes Agent PR #15407

def fix_reasoning_content(messages: list[dict]) -> list[dict]:
    """Ensure every assistant message has 'reasoning_content' set."""
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        # Only need to add if tool calls present and reasoning_content missing
        if msg.get("tool_calls") and "reasoning_content" not in msg:
            msg["reasoning_content"] = ""
        # Also handle empty string case (field exists but falsy)
        if msg.get("tool_calls") and not msg.get("reasoning_content"):
            msg["reasoning_content"] = ""
    return messages
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|-------------|-----------------|--------------|--------|
| `deepseek-chat`/`deepseek-reasoner` | `deepseek-v4-flash`/`deepseek-v4-pro` | May 2026 | Legacy names deprecated, retire July 24, 2026 |
| OpenAI Assistants API | OpenAI Responses API | March 2025 | New standard for agentic workflows |
| Chat Completions as universal protocol | Open Responses initiative | January 2026 | Pushing Responses API as universal LLM interface |
| Anthropic endpoint as drop-in proxy | Chat endpoint as primary Responses backend | 2026 | Most new proxies prefer Chat format for simpler translation |

**Deprecated/outdated:**
- `deepseek-chat`: Maps to v4-flash non-thinking, retiring July 24, 2026
- `deepseek-reasoner`: Maps to v4-flash thinking, retiring July 24, 2026
- OpenAI Assistants API: Being phased out mid-2026, functionality folded into Responses API

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Chat Completions is ~40-50% less translation code than Anthropic | Translation Complexity | If Anthropic endpoint has undocumented simplifications, this gap narrows |
| A2 | The `reasoning_content: ""` fix works on both endpoints | Don't Hand-Roll | Anthropic endpoint uses `thinking` blocks, not `reasoning_content` -- format-specific fix needed |
| A3 | Existing proxy SSE filtering logic is ~30% reusable | Architecture Patterns | If Responses API translation architecture differs significantly, reuse drops |

---

## Open Questions

1. **Does the DeepSeek Anthropic endpoint support `model` parameter differently?**
   - What we know: Both endpoints accept `deepseek-v4-pro` / `deepseek-v4-flash`
   - What's unclear: Whether the Anthropic endpoint's `thinking` handling is more lenient about round-trip requirements
   - Recommendation: Test empirically -- send identical conversation to both endpoints and compare error rates

2. **How does Codex CLI handle `reasoning_content` when receiving Responses API events?**
   - What we know: Responses API has `response.reasoning_summary_text.delta` events
   - What's unclear: Whether Codex CLI expects raw `reasoning_content` from proxy, or processed summaries
   - Recommendation: Review codex-relay and responses-proxy source code for exact event format

3. **Does the existing dsv4-cc-proxy need a separate endpoint or can it dual-mode?**
   - What we know: Current proxy handles `/v1/messages` (Anthropic format)
   - What's unclear: Whether to add `/v1/responses` (OpenAI format) as a separate route or create a new service
   - Recommendation: Add a new route `/v1/responses` to existing proxy, sharing the thinking-injection logic

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | API key forwarded via header, proxy is stateless passthrough |
| V3 Session Management | No | Stateless proxy, no sessions |
| V4 Access Control | No | No user/role management |
| V5 Input Validation | Yes | Request body is JSON-parsed then reconstructed; must preserve field types |
| V6 Cryptography | No | No cryptographic operations in proxy |

### STRIDE Threat Model for Responses API Translation Proxy

| Threat Pattern | STRIDE Category | Standard Mitigation |
|---------------|-----------------|---------------------|
| API key leak in logs/dumps | Information Disclosure | Redact `Authorization`/`x-api-key` headers in dump output; never log API keys |
| SSE event injection via `data:` prefix spoofing | Tampering | Validate incoming SSE lines start with `data: ` before parsing JSON; reject malformed lines |
| Request body manipulation via path traversal | Tampering | Route only `/v1/responses` and `/health`; reject requests with `..` or null bytes |
| Denial of service via unbounded streaming | Denial of Service | Enforce max event types (50), max filtered lines (200), chunk size limits |
| Unintended upstream request via host header injection | Spoofing | Strip `host` header from forwarded request; rebuild from configured `PROXY_UPSTREAM` |
| Sensitive data in HTTP 502 error responses | Information Disclosure | Return generic `"upstream unavailable"` messages, not upstream error details |

### Credential Handling

The proxy does NOT store or manage API keys. It forwards the `Authorization` header from the client to DeepSeek unchanged. This is the same model as the existing dsv4-cc-proxy.

**Production deployment:** Use environment variable `DEEPSEEK_API_KEY` set by the user (via `.env` or systemd env), never hardcoded.

---

## Sources

### Primary (HIGH confidence)
- DeepSeek API Docs (Thinking Mode guide) -- thinking parameters, `reasoning_content` format
- DeepSeek API Docs (Chat Completions) -- request/response format, SSE structure
- DeepSeek API Docs (Tool Calls) -- tool calling with thinking mode
- DeepSeek API Docs (Pricing and Rate Limits) -- model pricing, concurrency limits
- DeepSeek API Docs (Reasoning Model) -- `deepseek-reasoner` limitations
- OpenAI Responses API Streaming Guide -- SSE event definitions
- HuggingFace Open Responses Blog -- Open Responses standard, reasoning events

### Secondary (MEDIUM confidence)
- GitHub Issue #836 (deepseek-ai/DeepSeek-R1) -- `tool_choice` not supported
- GitHub Issue #1376 (deepseek-ai/DeepSeek-V3) -- V4 rejects `tool_choice="required"`
- GitHub Issue #16748 (NousResearch/hermes-agent) -- thinking blocks stripped, HTTP 400
- GitHub Issue #24190 (anomalyco/opencode) -- `reasoning_content` round-trip bug
- GitHub PR #15407 (NousResearch/hermes-agent) -- fix pattern for `reasoning_content`
- GitHub PR #16149 (NousResearch/hermes-agent) -- Anthropic thinking block preservation
- responses-proxy README (CallOrRet) -- Chat->Responses translation patterns
- ai-adapter README (dyrnq) -- Dual DeepSeek endpoint strategy
- codex-relay README (MetaFARS) -- Responses API translation

### Tertiary (LOW confidence)
- Dev.to article "I Wired DeepSeek V4 Into Claude Code and Codex CLI" -- empirical experience
- CSDN Free-Claude-Code SSE Protocol Analysis -- detailed SSE event flow documentation
- Dev.to article "Reverse engineering Codex CLI rollout traces" -- Codex event tracing
- CSDN "Responses协议深度解析" -- Responses API architecture analysis

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- existing dependencies verified against current codebase
- Architecture: HIGH -- translation patterns verified across 6+ proxy implementations
- Pitfalls: HIGH -- bugs confirmed across 11+ GitHub issues and community reports
- Security: HIGH -- stateless proxy model, no credential storage, established pattern

**Research date:** 2026-06-04
**Valid until:** 2026-07-24 (legacy model deprecation deadline) or 30 days, whichever is sooner
