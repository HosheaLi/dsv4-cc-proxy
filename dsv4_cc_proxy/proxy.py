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
#   PROXY_UPSTREAM_FALLBACK    上游不可达时回退 URL (默认空=关闭)
#   PROXY_UPSTREAM_RETRY_COUNT 上游请求重试次数 (默认 2)
#   PROXY_UPSTREAM_RETRY_BASE_DELAY 重试基础延迟秒数 (默认 1.0)
#
# 参考: https://api-docs.deepseek.com/guides/thinking_mode

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from dsv4_cc_proxy._version import VERSION
from dsv4_cc_proxy.codex.config import CODEX_UPSTREAM
from dsv4_cc_proxy.codex.models import get_codex_catalog, get_openai_models_list
from dsv4_cc_proxy.codex.sse import translate_sse_stream
from dsv4_cc_proxy.codex.translate import translate_request

# ---- 配置 ----

DEEPSEEK_BASE = os.getenv("PROXY_UPSTREAM", "https://api.deepseek.com/anthropic")
UPSTREAM_FALLBACK = os.getenv("PROXY_UPSTREAM_FALLBACK", "")
UPSTREAM_RETRY_COUNT = int(os.getenv("PROXY_UPSTREAM_RETRY_COUNT", "2"))
UPSTREAM_RETRY_BASE_DELAY = float(os.getenv("PROXY_UPSTREAM_RETRY_BASE_DELAY", "1.0"))
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
            trust_env=False,  # 禁用系统代理 (Windows 上 httpx 默认使用 IE 代理设置)
        )
    return _shared_client


# ---- 上游请求重试 ----

_UPSTREAM_RETRYABLE = (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError)
_UPSTREAM_CONNECT_RETRYABLE = (httpx.ConnectError, httpx.ConnectTimeout)


async def _send_with_retry(
    method: str, url: str, headers: dict, content: bytes,
) -> httpx.Response | None:
    """带重试+回退的非流式上游请求。所有尝试失败返回 None。"""
    client = _get_client()
    urls = [url]
    if UPSTREAM_FALLBACK:
        urls.append(UPSTREAM_FALLBACK)

    last_error = None
    for target in urls:
        max_attempts = UPSTREAM_RETRY_COUNT + 1
        for attempt in range(max_attempts):
            try:
                req = client.build_request(method=method, url=target, headers=headers, content=content)
                resp = await client.send(req, stream=False)
                return resp
            except _UPSTREAM_RETRYABLE as e:
                last_error = e
                if attempt < UPSTREAM_RETRY_COUNT or (target != urls[-1] and UPSTREAM_FALLBACK):
                    delay = UPSTREAM_RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning("[RETRY] %s attempt %d/%d failed: %s",
                                   target, attempt + 1, max_attempts, e)
                    await asyncio.sleep(delay)
            except httpx.HTTPStatusError as e:
                return e.response  # HTTP 错误不重试，返回响应对象让调用方翻译

    logger.error("All upstream targets exhausted. Last error: %s", last_error)
    return None


async def _connect_with_retry(
    method: str, url: str, headers: dict, content: bytes,
) -> httpx.Response | None:
    """仅对连接建立阶段重试（流式请求）。一旦开始接收数据，不再重试。"""
    client = _get_client()
    urls = [url]
    if UPSTREAM_FALLBACK:
        urls.append(UPSTREAM_FALLBACK)

    last_error = None
    for target in urls:
        max_attempts = UPSTREAM_RETRY_COUNT + 1
        for attempt in range(max_attempts):
            try:
                req = client.build_request(method=method, url=target, headers=headers, content=content)
                resp = await client.send(req, stream=True)
                return resp
            except _UPSTREAM_CONNECT_RETRYABLE as e:
                last_error = e
                if attempt < UPSTREAM_RETRY_COUNT or (target != urls[-1] and UPSTREAM_FALLBACK):
                    delay = UPSTREAM_RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning("[RETRY] %s connect attempt %d/%d failed: %s",
                                   target, attempt + 1, max_attempts, e)
                    await asyncio.sleep(delay)
            # stream=True 时 httpx 不因 4xx/5xx 抛 HTTPStatusError，
            # 由调用方通过 upstream_resp.status_code 自行处理

    logger.error("All upstream targets exhausted. Last error: %s", last_error)
    return None


# ---- 健康检查 ----


async def health(request: Request):
    return JSONResponse({
        "status": "ok",
        "version": VERSION,
        "upstream": DEEPSEEK_BASE,
        "upstream_fallback": UPSTREAM_FALLBACK or None,
    })


# ---- 修复 0: Unicode 引号标准化 ----

import re

# 目标字符映射: 将排版引号统一转换为 ASCII 单引号 (U+0027)
_QUOTE_REPLACEMENTS = str.maketrans({
    '’': "'",   # 』 RIGHT SINGLE QUOTATION MARK
    'ʼ': "'",   # ʼ MODIFIER LETTER APOSTROPHE
    'ʹ': "'",   # ʹ MODIFIER LETTER PRIME
})

# 匹配 "Today's date is YYYY/MM/DD" 或 "Today's date is YYYY-MM-DD" 中的日期，
# 将 YYYY/MM/DD 中的 / 统一替换为 -
_DATE_PATTERN = re.compile(
    r"((?:Today'?s date is|Current date|今天的日期是)\s*[：:]?\s*)(\d{4})/(\d{2})/(\d{2})",
    re.IGNORECASE,
)


def _normalize_text(s: str) -> str:
    """对单个字符串应用所有标准化规则。

    1. 排版引号 → ASCII 单引号
    2. 日期中的 / → - (如 2026/06/30 → 2026-06-30)
    """
    s = s.translate(_QUOTE_REPLACEMENTS)
    s = _DATE_PATTERN.sub(r'\1\2-\3-\4', s)
    return s


def _normalize_quotes(obj: Any) -> Any:
    """递归替换数据中的排版引号和日期格式。

    对 str 应用 _normalize_text，对 list/dict 递归遍历。
    不可变类型（int/float/bool/None）直接返回。
    不会修改原始对象（对可变类型返回新对象）。

    替换规则:
      - U+2019/U+02BC/U+02B9 → U+0027 (ASCII 单引号)
      - "Today's date is YYYY/MM/DD" → "Today's date is YYYY-MM-DD"
    """
    if isinstance(obj, str):
        return _normalize_text(obj)
    if isinstance(obj, dict):
        return {k: _normalize_quotes(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_quotes(item) for item in obj]
    return obj


# ---- 修复 3: messages[] 中 role:system 消息合并到顶层 system ----

SYSTEM_MESSAGE_SEPARATOR = "\n\n---\n\n"


def _consolidate_system_messages(data: dict) -> tuple:
    """将 messages[] 中的 ``role: "system"`` 消息合并到顶层 ``system`` 字段。

    从 messages 数组中提取所有 system 角色的消息，将其文本内容按出现
    顺序追加到顶层 system 字段中（或创建 system 字段），然后从 messages
    数组中移除这些消息。

    这样处理是因为 DeepSeek API 只接受 ``user`` 和 ``assistant`` 两种角色，
    无法识别 messages 数组中的 ``system`` 角色。而 Claude Code v2.1.154+
    的 ``mid_conversation_system`` 功能会在 messages 中插入 system 消息。

    Args:
        data: 完整的请求字典（会被原地修改）。

    Returns:
        ``(modified: bool, count: int)`` — 是否修改了数据，以及提取了多少
        条 system 消息。
    """
    if "messages" not in data or not isinstance(data["messages"], list):
        return False, 0

    system_texts = []
    remaining = []
    count = 0

    for msg in data["messages"]:
        if isinstance(msg, dict) and msg.get("role") == "system":
            content = msg.get("content")
            extracted = ""
            if isinstance(content, str):
                extracted = content
            elif isinstance(content, list):
                texts = [
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                extracted = "\n".join(texts)
            if extracted.strip():
                system_texts.append(extracted)
            count += 1
        else:
            remaining.append(msg)

    if count == 0:
        return False, 0

    data["messages"] = remaining

    if not system_texts:
        return True, count

    consolidated = SYSTEM_MESSAGE_SEPARATOR.join(system_texts)

    existing = data.get("system")
    if existing is None:
        data["system"] = consolidated
    elif isinstance(existing, str):
        data["system"] = existing + SYSTEM_MESSAGE_SEPARATOR + consolidated
    elif isinstance(existing, list):
        existing.append({"type": "text", "text": consolidated})
    else:
        data["system"] = str(existing) + SYSTEM_MESSAGE_SEPARATOR + consolidated

    return True, count


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
    """将非标准 thinking type 标准化为 DeepSeek 兼容格式。

    DeepSeek Anthropic API 只接受 enabled/disabled 两种 type。
    adaptive/auto 映射为 enabled（让 DeepSeek 自行决定何时思考）。

    同时清理 DeepSeek 不认识的字段：reasoning_effort、output_config。
    当映射目标为 disabled 时，剥离历史中的 thinking/redacted_thinking
    块（因为 DeepSeek 在 disabled 模式下不认识这些块）。
    """
    if "thinking" not in data:
        return False
    thinking_cfg = data["thinking"]
    if not isinstance(thinking_cfg, dict):
        return False

    thinking_type = thinking_cfg.get("type", "")
    if thinking_type in ("enabled", "disabled"):
        # enabled/disabled 模式下仍需清理 DeepSeek 不识别的字段
        cleaned = False
        for key in ("reasoning_effort", "output_config"):
            if data.pop(key, None) is not None:
                logger.info("[THINKING] removed %s (type=%s)", key, thinking_type)
                cleaned = True
        if thinking_type == "disabled":
            # disabled 模式还需剥离历史中的 thinking 块
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
            if stripped > 0:
                logger.info("[THINKING] stripped %d thinking blocks (type=disabled)", stripped)
                cleaned = True
        return cleaned

    # Not(2026-06-19): adaptive/auto → disabled。
    # 原因：DeepSeek 在 thinking=enabled 模式下容易陷入无限思考循环，
    # 消耗全部 max_tokens 而无法输出实际内容（尤其是结构化 JSON 输出和
    # 工具调用任务）。禁用 thinking 后模型直接输出，稳定性和可用性更好。
    target = "disabled"
    data["thinking"] = {"type": target}

    for key in ("reasoning_effort", "output_config"):
        val = data.pop(key, None)
        if val is not None:
            logger.info("[THINKING] removed %s=%s", key, val)

    # enabled 模式下 DeepSeek 支持 thinking 块，不需要剥离历史
    if target == "enabled":
        logger.info("[THINKING] converted %s → %s", thinking_type, target)
        return True

    # disabled 模式需剥离历史中的 thinking 块
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
        "[THINKING] converted %s → %s, stripped %d thinking blocks",
        thinking_type, target, stripped,
    )
    return True


def _translate_anthropic_structured_output(data: dict) -> bool:
    """将 Anthropic 结构化输出字段翻译为 DeepSeek 兼容格式。

    Anthropic Messages API 的结构化输出机制不被 DeepSeek 支持:
      - output_config.format (GA, 2025-11) → DeepSeek 不识此字段
      - output_format (beta) → DeepSeek 不识此字段
      - tool_choice: {type: "tool", name: "X"} → DeepSeek 返回错误

    翻译策略:
      1. 提取 JSON Schema (来自 output_config/output_format 或 tool input_schema)
      2. 注入 schema 到 system prompt
      3. 移除不支持的字段
      4. 将 named tool_choice 降级为 auto

    仅在模型为 deepseek-* 时生效。对原生 Anthropic 模型透明。
    """
    model = data.get("model", "")
    if not isinstance(model, str) or not model.startswith("deepseek-"):
        return False

    modified = False
    schema_json: str | None = None

    # 1. 提取 output_config.format / output_format 中的 JSON Schema
    for key in ("output_config", "output_format"):
        cfg = data.pop(key, None)
        if isinstance(cfg, dict):
            fmt = cfg.get("format", {})
            if isinstance(fmt, dict) and fmt.get("type") == "json_schema":
                schema = fmt.get("schema", {})
                name = fmt.get("name", "response")
                if schema:
                    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
                logger.info(
                    "[ANTHROPIC] removed %s (name=%s) → schema injected to system",
                    key, name,
                )
                modified = True

    # 2. 处理 named tool_choice → auto (DeepSeek 不支持)
    tool_choice = data.get("tool_choice")
    if isinstance(tool_choice, dict) and tool_choice.get("type") == "tool":
        tool_name = tool_choice.get("name", "?")
        data["tool_choice"] = {"type": "auto"}
        logger.info(
            "[ANTHROPIC] converted named tool_choice (%s) → auto",
            tool_name,
        )
        # 若步骤 1 未提取到 schema，从工具定义中提取
        if schema_json is None:
            for t in data.get("tools", []):
                if isinstance(t, dict) and t.get("name") == tool_name:
                    input_schema = t.get("input_schema", {})
                    if input_schema:
                        schema_json = json.dumps(
                            input_schema, ensure_ascii=False, indent=2,
                        )
                    break
        modified = True

    # 3. 注入 schema 到 system prompt
    if schema_json:
        schema_prompt = (
            "\n\n你 MUST 用符合以下 JSON Schema 的单个 JSON 对象回复:\n"
            f"```json\n{schema_json}\n```\n"
            "不要用 markdown 代码块包裹 JSON。"
            "只输出 JSON 对象，不要输出其他内容。"
        )

        system = data.get("system")
        if isinstance(system, str):
            data["system"] = system + schema_prompt
        elif isinstance(system, list):
            # Anthropic content blocks 格式
            system.append({"type": "text", "text": schema_prompt})
        else:
            data["system"] = [{"type": "text", "text": schema_prompt}]

        logger.info("[ANTHROPIC] schema instructions injected into system prompt")
        modified = True

    return modified


def _should_disable_thinking_for_structured_output(data: dict) -> bool:
    """若响应需要结构化 JSON 输出且 thinking 开启，则返回 True 以强制关闭。

    原因: DeepSeek 开启 thinking 时会先输出大量思考 token，当同时要求
    response_format: json_object 时，思考可能消耗全部 max_tokens 导致
    实际文本输出为空。此行为与 Anthropic 原版 API 一致（Anthropic 也禁止
    thinking + forced tool use 同时使用）。
    """
    model = data.get("model", "")
    if not isinstance(model, str) or not model.startswith("deepseek-"):
        return False

    thinking = data.get("thinking", {})
    if not isinstance(thinking, dict) or thinking.get("type") != "enabled":
        return False

    # 检查是否有结构化输出要求
    has_response_format = "response_format" in data
    has_output_config = "output_config" in data
    has_output_format = "output_format" in data

    if has_response_format or has_output_config or has_output_format:
        logger.info("[ANTHROPIC] disabling thinking for structured output request")
        return True

    return False


# ---- 响应端: thinking 透传 ----
# DeepSeek 返回的 thinking 块直接透传给客户端，
# Claude Code 本身支持展示思考过程。


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

    # 匹配所有 /messages 子路径（含 count_tokens 等），但仅对主端点
    # 做 thinking 标准化和注入 — 避免破坏子端点的请求体。
    is_messages_api = (method == "POST" and "/messages" in path.split("?")[0])
    is_chat_endpoint = (method == "POST" and path.rstrip("/").endswith("/messages"))

    body = await request.body() if is_messages_api else b""
    modified_body = body

    if is_messages_api:
        try:
            data = json.loads(body)
            # Unicode 引号标准化: 排版引号 → ASCII 单引号
            data = _normalize_quotes(data)
            # 仅主 chat 端点需要日志摘要
            if is_chat_endpoint:
                logger.info("[REQ] %s", json.dumps(_summarize_request(data), ensure_ascii=False))
            _dump_json("last_request.json", data)

            if is_chat_endpoint:
                # 将 messages[] 中的 role:system 合并到顶层 system 字段，
                # 因为 DeepSeek API 只接受 user/assistant 两种角色
                modified, sys_count = _consolidate_system_messages(data)
                if modified:
                    logger.info(
                        "[SYSTEM] consolidated %d system message(s) from messages array",
                        sys_count,
                    )

                thinking_normalized = _normalize_thinking(data)

                if _inject_thinking_blocks(data):
                    logger.info("[INJECT] added empty thinking block")
                    thinking_normalized = True

                # 翻译 Anthropic 结构化输出 → DeepSeek 兼容 (CODX-17)
                if _translate_anthropic_structured_output(data):
                    thinking_normalized = True

                # 若设置了 response_format 则禁用 thinking，避免模型
                # 陷入无限思考循环耗尽 max_tokens 而无法输出 JSON
                if _should_disable_thinking_for_structured_output(data):
                    data["thinking"] = {"type": "disabled"}
                    thinking_normalized = True

                if modified:
                    thinking_normalized = True

                if thinking_normalized:
                    modified_body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                    headers["content-length"] = str(len(modified_body))
                    _dump_json("last_request_modified.json", data)

        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    upstream_resp = await _connect_with_retry(method, upstream_url, headers, modified_body)
    if upstream_resp is None:
        return JSONResponse(
            {"error": {"message": "upstream unavailable after retries", "type": "proxy_error"}},
            status_code=502,
        )

    content_type = upstream_resp.headers.get("content-type", "")
    is_sse = "text/event-stream" in content_type
    logger.info("[RESP] status=%s sse=%s", upstream_resp.status_code, is_sse)

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


def _translate_usage(usage: dict[str, Any] | None) -> dict[str, int]:
    """将 DeepSeek Chat Completions usage → OpenAI Responses API usage。

    DeepSeek 返回 prompt_tokens/completion_tokens，
    Codex 期望 input_tokens/output_tokens。
    """
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    return {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


def _translate_chat_to_responses(chat_response: dict, model: str) -> dict:
    """将 Chat Completions JSON -> Responses API JSON (非流式)。"""
    # Unicode 引号标准化: 排版引号 → ASCII 单引号
    chat_response = _normalize_quotes(chat_response)
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
        "usage": _translate_usage(chat_response.get("usage")),
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

    upstream_resp = await _connect_with_retry(
        "POST", upstream_url, headers,
        json.dumps(chat_request, ensure_ascii=False).encode("utf-8"),
    )
    if upstream_resp is None:
        return _build_error(502, "proxy_error", "Failed to reach DeepSeek API after retries")

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

    upstream_resp = await _send_with_retry(
        "POST", upstream_url, headers,
        json.dumps(chat_request, ensure_ascii=False).encode("utf-8"),
    )
    if upstream_resp is None:
        return _build_error(502, "proxy_error", "Failed to reach DeepSeek API after retries")

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

    # Unicode 引号标准化: 排版引号 → ASCII 单引号
    request_body = _normalize_quotes(request_body)

    headers = {
        "content-type": "application/json",
        "authorization": request.headers.get("authorization", ""),
    }

    try:
        # 临时: dump 原始和翻译后的 Codex 请求
        import os as _os, tempfile as _tempfile
        _orig_path = _os.path.join(_tempfile.gettempdir(), "last_codex_original_request.json")
        with open(_orig_path, "w") as _f:
            json.dump(request_body, _f, ensure_ascii=False, indent=2, default=str)
        logger.warning("[CODEX] dumped original request to %s", _orig_path)

        chat_request = translate_request(request_body)
    except Exception:
        logger.exception("[CODEX] translate_request failed")
        return _build_error(400, "invalid_request_error", "Failed to translate request")

    # 临时: dump 翻译后的 Codex 请求
    if DUMP_DIR:
        _dump_path = os.path.join(DUMP_DIR, "last_codex_chat_request.json")
        with open(_dump_path, "w") as _f:
            json.dump(chat_request, _f, ensure_ascii=False, indent=2, default=str)
        logger.warning("[CODEX] dumped chat request to %s", _dump_path)

    upstream_url = f"{CODEX_UPSTREAM}/chat/completions"

    is_stream = request_body.get("stream", False)
    if is_stream:
        return await _handle_stream_response(chat_request, headers, upstream_url)
    else:
        return await _handle_non_stream_response(chat_request, headers, upstream_url)


# ---- Codex 模型目录端点 ----


async def models_handler(request: Request):
    """GET /v1/models -- 返回 OpenAI 标准格式的可用模型列表。"""
    logger.info("[MODELS] GET /v1/models")
    return JSONResponse({
        "object": "list",
        "data": get_openai_models_list(),
    })


async def codex_model_catalog_handler(request: Request):
    """GET /model-catalog -- 返回 Codex model_catalog_json 格式的模型目录。

    用户可将此端点输出保存为 JSON 文件，并在 Codex config.toml 中
    通过 model_catalog_json 字段引用。
    """
    logger.info("[MODELS] GET /model-catalog")
    return JSONResponse({"models": get_codex_catalog()})


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
    # 清理诊断转储文件
    for basename in ("last_codex_original_request.json", "last_codex_chat_request.json"):
        fpath = os.path.join(tempfile.gettempdir(), basename)
        try:
            os.unlink(fpath)
        except OSError:
            pass


def create_app() -> Starlette:
    return Starlette(
        lifespan=lifespan,
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/v1/responses/compact", compact_handler, methods=["POST"]),
            Route("/v1/responses", responses_handler, methods=["POST"]),
            Route("/v1/models", models_handler, methods=["GET"]),
            Route("/model-catalog", codex_model_catalog_handler, methods=["GET"]),
            Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]),
        ],
    )
