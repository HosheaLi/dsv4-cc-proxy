# dsv4-cc-proxy / proxy — 核心代理逻辑
#
# 环境变量:
#   PROXY_UPSTREAM    DeepSeek API 地址 (默认 https://api.deepseek.com/anthropic)
#   PROXY_HOST        监听地址 (默认 127.0.0.1)
#   PROXY_PORT        监听端口 (默认 16889)
#   PROXY_LOG_LEVEL   日志级别 (默认 warning)
#   PROXY_LOG_FILE    日志文件路径 (默认空=仅 stdout)
#   PROXY_LOG_MAX_BYTES  日志文件最大字节数 (默认 10MB)
#   PROXY_LOG_BACKUP_COUNT 轮转备份数量 (默认 3)
#   PROXY_DUMP_DIR    流量捕获目录 (默认空=关闭, ⚠ 含敏感数据)
#
# 参考: https://api-docs.deepseek.com/guides/thinking_mode

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from dsv4_cc_proxy._version import VERSION
from dsv4_cc_proxy.codex.config import CODEX_UPSTREAM
from dsv4_cc_proxy.codex.sse import translate_sse_stream
from dsv4_cc_proxy.codex.translate import translate_request

# ---- 配置 ----

DEEPSEEK_BASE = os.getenv("PROXY_UPSTREAM", "https://api.deepseek.com/anthropic")
HOST = os.getenv("PROXY_HOST", "127.0.0.1")
def _get_port() -> int:
    """惰性解析 PORT 环境变量，避免模块级 import 时触发 sys.exit。"""
    try:
        return int(os.getenv("PROXY_PORT", "16889"))
    except (TypeError, ValueError):
        logger.critical("Error: PROXY_PORT must be an integer")
        sys.exit(1)


_PORT: int | None = None  # 惰性初始化缓存
LOG_LEVEL = os.getenv("PROXY_LOG_LEVEL", "warning")
DUMP_DIR = os.getenv("PROXY_DUMP_DIR", "")

# SSE 流处理参数上限
MAX_EVENT_TYPES = 50
MAX_FILTERED_LINES = 200
DUMP_PREVIEW_LINES = 30
DUMP_MAX_BYTES = 500000
LOG_EVENT_PREVIEW = 15
LOG_FILE = os.getenv("PROXY_LOG_FILE", "")
LOG_MAX_BYTES = int(os.getenv("PROXY_LOG_MAX_BYTES", str(10 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("PROXY_LOG_BACKUP_COUNT", "3"))

log_format = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
log_level = getattr(logging, LOG_LEVEL.upper(), logging.WARNING)

_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(log_format)

_root = logging.getLogger()
_root.setLevel(log_level)
_root.handlers.clear()
_root.addHandler(_stream_handler)

if LOG_FILE:
    _file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    _file_handler.setFormatter(log_format)
    _root.addHandler(_file_handler)

logger = logging.getLogger("deepseek-proxy")

_shared_client: httpx.AsyncClient | None = None


# ---- httpx 客户端 ----


def _get_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=httpx.Timeout(600.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=8, max_connections=20),
        )
    return _shared_client


# ---- 健康检查 ----


async def health(request: Request):
    return JSONResponse({
        "status": "ok",
        "version": VERSION,
        "upstream": DEEPSEEK_BASE,
    })


# ---- 修复 1: 请求端 thinking 注入 ----


def _has_tool_use(content: list) -> bool:
    return any(
        isinstance(b, dict) and b.get("type") == "tool_use" for b in content
    )


def _has_thinking(content: list) -> bool:
    return any(
        isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking")
        for b in content
    )


def _inject_thinking_blocks(data: dict) -> bool:
    thinking_cfg = data.get("thinking", {})
    if not isinstance(thinking_cfg, dict):
        return False
    if thinking_cfg.get("type") != "enabled":
        return False

    model = data.get("model", "")
    if not isinstance(model, str) or not model.startswith("deepseek-v4"):
        return False

    modified = False
    for msg in data.get("messages", []):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if isinstance(content, str):
            continue
        if _has_tool_use(content) and not _has_thinking(content):
            for i, block in enumerate(content):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    content.insert(i, {"type": "thinking", "thinking": ""})
                    modified = True
                    break
    return modified


# ---- 修复 2: thinking 模式标准化 ----


def _normalize_thinking(data: dict) -> bool:
    if "thinking" not in data:
        return False
    thinking_cfg = data["thinking"]
    if not isinstance(thinking_cfg, dict):
        return False

    thinking_type = thinking_cfg.get("type", "")
    if thinking_type in ("enabled", "disabled"):
        return False

    data["thinking"] = {"type": "disabled"}

    for key in ("reasoning_effort", "output_config"):
        val = data.pop(key, None)
        if val is not None:
            logger.info("[THINKING] removed %s=%s", key, val)

    stripped = 0
    for msg in data.get("messages", []):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if isinstance(content, str):
            continue
        new_content = [
            b for b in content
            if not (isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking"))
        ]
        if len(new_content) != len(content):
            stripped += len(content) - len(new_content)
            msg["content"] = new_content

    logger.info(
        "[THINKING] converted %s → disabled, stripped %d thinking blocks",
        thinking_type, stripped,
    )
    return True


# ---- 修复 3: 响应端 thinking 剥离 ----


def _thinking_requested(data: dict) -> bool:
    thinking_cfg = data.get("thinking", {})
    return (
        isinstance(thinking_cfg, dict)
        and thinking_cfg.get("type") == "enabled"
    )


def _filter_sse_line(line: str, thinking_indices: set[int]) -> tuple[str | None, set[int]]:
    if not line.startswith("data: "):
        return line, thinking_indices

    try:
        data = json.loads(line[6:])
    except json.JSONDecodeError:
        return line, thinking_indices

    t = data.get("type", "")

    if t == "content_block_start":
        cb = data.get("content_block", {})
        if cb.get("type") == "thinking":
            thinking_indices.add(data["index"])
            return None, thinking_indices

    elif t in ("content_block_delta", "content_block_stop"):
        idx = data.get("index")
        if idx in thinking_indices:
            if t == "content_block_stop":
                thinking_indices.discard(idx)
            return None, thinking_indices

    return line, thinking_indices


# ---- 流量捕获 ----


if DUMP_DIR:
    logger.warning("⚠ PROXY_DUMP_DIR enabled — data saved to %s", DUMP_DIR)


def _dump_json(filename: str, data: Any) -> None:
    if not DUMP_DIR:
        return
    path = os.path.join(DUMP_DIR, filename)
    s = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    if len(s) > DUMP_MAX_BYTES:
        # 在字节边界安全截断，避免破坏多字节 Unicode 字符
        prefix = s.encode("utf-8", errors="ignore")[:DUMP_MAX_BYTES]
        s = prefix.decode("utf-8", errors="ignore") + "\n\n... [TRUNCATED at {}KB]".format(DUMP_MAX_BYTES // 1000)
    with open(path, "w") as f:
        f.write(s)
    logger.info("[DUMP] %s (%d bytes)", filename, len(s))


def _summarize_request(data: dict[str, Any]) -> dict[str, Any]:
    msgs = data.get("messages", [])
    tools = data.get("tools", [])
    system = data.get("system", "")
    if isinstance(system, list):
        system = " ".join(
            b.get("text", "") if isinstance(b, dict) else str(b)
            for b in system[:2]
        )
    return {
        "model": data.get("model", "?"),
        "stream": data.get("stream", False),
        "max_tokens": data.get("max_tokens", "?"),
        "thinking": data.get("thinking", "not set"),
        "messages": len(msgs),
        "tools": len(tools),
        "tool_names": [t.get("name", "?") for t in tools[:10]],
        "system_len": len(system),
    }


# ---- 请求处理 ----


def _build_response_headers(upstream_resp: httpx.Response, is_sse: bool) -> dict[str, str]:
    strip_keys = {"transfer-encoding", "content-encoding"}
    if is_sse:
        strip_keys.add("content-length")
    return {
        k: v for k, v in upstream_resp.headers.items()
        if k.lower() not in strip_keys
    }


async def proxy(request: Request):
    method = request.method
    path = "/" + request.url.path.lstrip("/")
    upstream_url = f"{DEEPSEEK_BASE}{path}"

    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host",)}

    is_messages = (method == "POST" and path.rstrip("/").endswith("/messages"))

    body = await request.body() if is_messages else b""
    modified_body = body
    strip_thinking = True

    if is_messages:
        try:
            data = json.loads(body)
            logger.info("[REQ] %s", json.dumps(_summarize_request(data), ensure_ascii=False))
            _dump_json("last_request.json", data)

            original_thinking_enabled = _thinking_requested(data)

            thinking_normalized = _normalize_thinking(data)

            if _inject_thinking_blocks(data):
                logger.info("[INJECT] added empty thinking block")
                thinking_normalized = True

            if original_thinking_enabled:
                strip_thinking = False
            else:
                logger.info("[STRIP] response filter enabled")

            if thinking_normalized:
                modified_body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                headers["content-length"] = str(len(modified_body))
                _dump_json("last_request_modified.json", data)

        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    client = _get_client()

    try:
        req = client.build_request(
            method=method,
            url=upstream_url,
            headers=headers,
            content=modified_body,
        )
        upstream_resp = await client.send(req, stream=True)
    except Exception:
        logger.exception("upstream request failed: %s %s", method, upstream_url)
        return JSONResponse(
            {"error": {"message": "upstream unavailable", "type": "proxy_error"}},
            status_code=502,
        )

    content_type = upstream_resp.headers.get("content-type", "")
    is_sse = "text/event-stream" in content_type
    logger.info("[RESP] status=%s sse=%s", upstream_resp.status_code, is_sse)

    if not strip_thinking or not is_sse:
        async def passthrough():
            try:
                async for chunk in upstream_resp.aiter_bytes():
                    yield chunk
            except Exception:
                logger.exception("upstream stream read error")
            finally:
                await upstream_resp.aclose()

        return StreamingResponse(
            passthrough(),
            status_code=upstream_resp.status_code,
            headers=_build_response_headers(upstream_resp, is_sse),
        )

    logger.info("[FILTER] stripping thinking from SSE stream")

    async def filtered_stream():
        thinking_indices = set()
        event_types = []
        all_filtered = []
        buffer = ""

        try:
            async for chunk in upstream_resp.aiter_bytes():
                text = chunk.decode("utf-8", errors="replace")
                buffer += text

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)

                    if line.startswith("data: ") and len(event_types) < MAX_EVENT_TYPES:
                        try:
                            d = json.loads(line[6:])
                            event_types.append(d.get("type", "?"))
                        except json.JSONDecodeError:
                            pass

                    filtered, thinking_indices = _filter_sse_line(line, thinking_indices)
                    if filtered is not None:
                        if len(all_filtered) < MAX_FILTERED_LINES:
                            all_filtered.append(filtered)
                        yield (filtered + "\n").encode("utf-8")

            if buffer.strip():
                if buffer.startswith("data: ") and len(event_types) < MAX_EVENT_TYPES:
                    try:
                        d = json.loads(buffer[6:])
                        event_types.append(d.get("type", "?"))
                    except json.JSONDecodeError:
                        pass
                filtered, thinking_indices = _filter_sse_line(buffer, thinking_indices)
                if filtered is not None:
                    yield (filtered + "\n").encode("utf-8")

        except Exception:
            logger.exception("upstream stream read error")
        finally:
            logger.info("[RESP-EVENTS] raw=%s", event_types[:LOG_EVENT_PREVIEW])
            logger.info("[RESP-FILTERED] lines=%d", len(all_filtered))
            _dump_json("last_response_events.json", {
                "raw_events": event_types,
                "filtered_count": len(all_filtered),
                "first_filtered": all_filtered[:DUMP_PREVIEW_LINES],
            })
            await upstream_resp.aclose()

    return StreamingResponse(
        filtered_stream(),
        status_code=upstream_resp.status_code,
        headers=_build_response_headers(upstream_resp, is_sse=True),
    )


# ---- Codex Responses API handler ----


ERROR_CODE_MAP = {
    400: ("invalid_request_error", "Bad request"),
    401: ("authentication_error", "Invalid API key"),
    403: ("permission_error", "Access denied"),
    404: ("invalid_request_error", "Endpoint not found"),
    408: ("timeout_error", "Request timeout"),
    422: ("invalid_request_error", "Unprocessable entity"),
    429: ("rate_limit_error", "Rate limit exceeded"),
    500: ("server_error", "DeepSeek server error"),
    502: ("server_error", "Upstream service unavailable"),
    503: ("server_error", "Service overloaded"),
}


def _build_error(status_code: int, error_type: str, message: str) -> JSONResponse:
    """构建 Responses API 标准错误响应。"""
    return JSONResponse(
        {"error": {"type": error_type, "code": str(status_code), "message": message, "param": None}},
        status_code=status_code,
    )


def _translate_upstream_error(status_code: int, body: bytes) -> JSONResponse:
    """将 DeepSeek 错误翻译为 Responses API 错误格式。"""
    error_type, default_message = ERROR_CODE_MAP.get(
        status_code, ("server_error", "Unknown error")
    )

    detail = default_message
    try:
        ds_error = json.loads(body)
        if isinstance(ds_error, dict):
            err_obj = ds_error.get("error", {})
            if isinstance(err_obj, dict):
                detail = err_obj.get("message", default_message)
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    return JSONResponse(
        {
            "error": {
                "type": error_type,
                "code": str(status_code),
                "message": detail,
                "param": None,
            }
        },
        status_code=status_code,
    )


def _translate_chat_to_responses(chat_response: dict, model: str) -> dict:
    """将 Chat Completions JSON -> Responses API JSON (非流式)。"""
    choices = chat_response.get("choices") or [{}]
    choice = choices[0] if choices else {}
    message = choice.get("message", {})

    output = []

    # reasoning_content -> output item
    reasoning = (message.get("reasoning_content") or "").strip()
    if reasoning:
        output.append({
            "id": f"item_{len(output)}",
            "type": "reasoning",
            "status": "completed",
            "content": [{"type": "reasoning_text", "text": reasoning}],
        })

    # content -> output item
    content = (message.get("content") or "").strip()
    if content:
        output.append({
            "id": f"item_{len(output)}",
            "type": "message",
            "status": "completed",
            "content": [{"type": "output_text", "text": content}],
            "role": "assistant",
        })

    # tool_calls -> output items
    for tc in message.get("tool_calls", []):
        tc_id = tc.get("id", "")
        func = tc.get("function", {})
        output.append({
            "id": tc_id,
            "type": "function_call",
            "status": "completed",
            "name": func.get("name", "unknown"),
            "arguments": func.get("arguments", ""),
            "call_id": tc_id,
        })

    return {
        "id": f"resp_{chat_response.get('id', 'unknown')}",
        "object": "response",
        "model": model,
        "status": "completed",
        "output": output,
        "usage": chat_response.get("usage", {
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        }),
    }


async def _iter_lines(response: httpx.Response):
    """将 httpx 流式响应拆行为异步行生成器。"""
    buffer = ""
    async for chunk in response.aiter_bytes():
        text = chunk.decode("utf-8", errors="replace")
        buffer += text
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            yield line
    if buffer.strip():
        yield buffer


async def _handle_stream_response(chat_request: dict, headers: dict, upstream_url: str):
    """流式: Chat delta chunk -> SSE 事件流。"""
    chat_request["stream"] = True
    client = _get_client()

    try:
        req = client.build_request(
            method="POST", url=upstream_url, headers=headers,
            content=json.dumps(chat_request, ensure_ascii=False).encode("utf-8"),
        )
        upstream_resp = await client.send(req, stream=True)
    except Exception:
        logger.exception("[CODEX] upstream request failed")
        return _build_error(502, "proxy_error", "Failed to reach DeepSeek API")

    if upstream_resp.status_code != 200:
        body = b""
        async for chunk in upstream_resp.aiter_bytes():
            body += chunk
        await upstream_resp.aclose()
        return _translate_upstream_error(upstream_resp.status_code, body)

    async def event_stream():
        async def json_stream():
            try:
                async for line in _iter_lines(upstream_resp):
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            yield chunk
                        except json.JSONDecodeError:
                            continue
                    elif line.strip() == "data: [DONE]":
                        continue
            finally:
                await upstream_resp.aclose()

        async for sse_event in translate_sse_stream(json_stream()):
            yield sse_event.encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        status_code=200,
    )


async def _handle_non_stream_response(chat_request: dict, headers: dict, upstream_url: str):
    """非流式: 获取完整 Chat JSON -> 翻译为 Responses API JSON。"""
    chat_request["stream"] = False
    client = _get_client()

    try:
        req = client.build_request(
            method="POST", url=upstream_url, headers=headers,
            content=json.dumps(chat_request, ensure_ascii=False).encode("utf-8"),
        )
        upstream_resp = await client.send(req, stream=False)
    except Exception:
        logger.exception("[CODEX] upstream request failed")
        return _build_error(502, "proxy_error", "Failed to reach DeepSeek API")

    if upstream_resp.status_code != 200:
        body = getattr(upstream_resp, 'content', b"")
        await upstream_resp.aclose()
        return _translate_upstream_error(upstream_resp.status_code, body)

    chat_response = upstream_resp.json()
    await upstream_resp.aclose()

    response_body = _translate_chat_to_responses(chat_response, chat_request.get("model", ""))
    return JSONResponse(response_body, status_code=200)


async def responses_handler(request: Request):
    """POST /v1/responses -- Codex CLI 协议代理入口。"""
    logger.info("[CODEX] POST /v1/responses")

    try:
        request_body = await request.json()
    except json.JSONDecodeError:
        return _build_error(400, "invalid_request_error", "Request body is not valid JSON")

    headers = {
        "content-type": "application/json",
        "authorization": request.headers.get("authorization", ""),
    }

    try:
        chat_request = translate_request(request_body)
    except Exception:
        logger.exception("[CODEX] translate_request failed")
        return _build_error(400, "invalid_request_error", "Failed to translate request")

    upstream_url = f"{CODEX_UPSTREAM}/chat/completions"

    is_stream = request_body.get("stream", False)
    if is_stream:
        return await _handle_stream_response(chat_request, headers, upstream_url)
    else:
        return await _handle_non_stream_response(chat_request, headers, upstream_url)


async def compact_handler(request: Request):
    """POST /v1/responses/compact -- 暂不支持,返回 501。"""
    logger.info("[CODEX] POST /v1/responses/compact -- 501 not_implemented")
    return JSONResponse(
        {
            "error": {
                "type": "not_supported",
                "message": "Compaction is not yet supported for Codex + DeepSeek V4",
                "code": "501",
                "param": None,
            }
        },
        status_code=501,
    )


# ---- 应用工厂 ----


@asynccontextmanager
async def lifespan(app):
    logger.info("started v%s (upstream=%s)", VERSION, DEEPSEEK_BASE)
    yield
    logger.info("shutting down")
    if _shared_client and not _shared_client.is_closed:
        await _shared_client.aclose()


def create_app() -> Starlette:
    return Starlette(
        lifespan=lifespan,
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/v1/responses/compact", compact_handler, methods=["POST"]),
            Route("/v1/responses", responses_handler, methods=["POST"]),
            Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]),
        ],
    )
