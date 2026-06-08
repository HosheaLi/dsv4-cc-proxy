# dsv4-cc-proxy / codex — SSE 流式事件翻译 (Chat delta → Responses API)
#
# translate_sse_stream() 将 DeepSeek Chat Completions 的 delta chunk 流
# 翻译为 OpenAI Responses API 标准 SSE 事件流。
#
# 环境变量: (无 — 纯函数，无外部依赖)
#
# 职责:
#   - Chat delta chunk → Responses API SSE 事件翻译 (CODX-05, CODX-06)
#   - reasoning_content → reasoning_text.delta 翻译 (CODX-13)
#   - tool_calls → function_call_arguments.delta 翻译 (CODX-08)
#   - 类型转换: reasoning/→/text/→/tool_call 触发 item done + added (CODX-15)
#   - 多工具并行调用独立事件流 (CODX-09)

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterable
from dataclasses import dataclass, field
from uuid import uuid4

logger = logging.getLogger("deepseek-proxy")


@dataclass
class _ToolCallState:
    """追踪翻译过程中活跃工具调用的所有状态。

    封装原本作为独立 dict 存在的 6 个映射，使得
    _close_active_tool_calls 和类型转换逻辑更清晰。
    """

    active_indices: set[int] = field(default_factory=set)
    call_ids: dict[int, str] = field(default_factory=dict)
    names: dict[int, str] = field(default_factory=dict)
    arguments: dict[int, str] = field(default_factory=dict)
    item_ids: dict[int, str] = field(default_factory=dict)
    output_indices: dict[int, int] = field(default_factory=dict)

    def clear(self) -> None:
        self.active_indices.clear()
        self.call_ids.clear()
        self.names.clear()
        self.arguments.clear()
        self.item_ids.clear()
        self.output_indices.clear()


# ---- SSE 事件构建底层工具 ----


def _build_sse_event(event_type: str, data: dict) -> str:
    """构建完整 SSE 事件字符串（含 event: 前缀 + data: JSON + 空行终止）。

    Args:
        event_type: SSE 事件类型（如 "response.output_text.delta"）。
        data: JSON 可序列化的事件荷载。

    Returns:
        完整 SSE 事件字符串，格式:
        event: {event_type}
        data: {json}

    """
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_response_created(response_id: str, model: str) -> str:
    """构建 response.created SSE 事件。

    Args:
        response_id: 响应唯一标识符。
        model: 模型名称。

    Returns:
        SSE 事件字符串。
    """
    data = {
        "type": "response.created",
        "response": {
            "id": response_id,
            "object": "response",
            "created": int(time.time()),
            "model": model,
            "status": "in_progress",
            "usage": None,
        },
    }
    return _build_sse_event("response.created", data)


def _build_response_in_progress(response_id: str) -> str:
    """构建 response.in_progress SSE 事件。

    Args:
        response_id: 响应唯一标识符。

    Returns:
        SSE 事件字符串。
    """
    data = {
        "type": "response.in_progress",
        "response": {
            "id": response_id,
            "object": "response",
            "status": "in_progress",
        },
    }
    return _build_sse_event("response.in_progress", data)


def _build_output_item_added(output_index: int, item_type: str, **fields) -> str:
    """构建 response.output_item.added SSE 事件。

    根据 item_type 自动设置不同的 item 结构:
    - reasoning: 含 summary: []
    - message: 含 role: "assistant", content: []
    - function_call: 含 name, call_id, arguments: ""

    Args:
        output_index: 输出项序号。
        item_type: 项类型 ("reasoning" | "message" | "function_call")。
        **fields: 额外字段 (item_id, name, call_id 等)。

    Returns:
        SSE 事件字符串。
    """
    item = {
        "id": fields.get("item_id", f"item_{output_index}"),
        "type": item_type,
        "status": "in_progress",
    }
    if item_type == "reasoning":
        item["summary"] = []
    elif item_type == "message":
        item["role"] = "assistant"
        item["content"] = []
    elif item_type == "function_call":
        item["name"] = fields.get("name", "unknown")
        item["call_id"] = fields.get("call_id", f"call_{output_index}")
        item["arguments"] = ""

    data = {
        "type": "response.output_item.added",
        "item": item,
        "output_index": output_index,
    }
    return _build_sse_event("response.output_item.added", data)


def _build_content_part_added(
    item_id: str, output_index: int, content_index: int = 0,
) -> str:
    """构建 response.content_part.added SSE 事件。

    Args:
        item_id: 所属 item 的 id。
        output_index: 输出项序号。
        content_index: content part 序号（固定为 0）。

    Returns:
        SSE 事件字符串。
    """
    data = {
        "type": "response.content_part.added",
        "item_id": item_id,
        "output_index": output_index,
        "content_index": content_index,
        "part": {"type": "output_text", "text": ""},
    }
    return _build_sse_event("response.content_part.added", data)


def _build_reasoning_text_delta(
    item_id: str, output_index: int, delta: str, sequence: int,
) -> str:
    """构建 response.reasoning_text.delta SSE 事件。

    Args:
        item_id: 所属 item 的 id。
        output_index: 输出项序号。
        delta: reasoning 文本增量。
        sequence: 序列号（递增）。

    Returns:
        SSE 事件字符串。
    """
    data = {
        "type": "response.reasoning_text.delta",
        "item_id": item_id,
        "output_index": output_index,
        "content_index": 0,
        "delta": delta,
        "sequence_number": sequence,
    }
    return _build_sse_event("response.reasoning_text.delta", data)


def _build_output_text_delta(
    item_id: str, output_index: int, delta: str, sequence: int,
) -> str:
    """构建 response.output_text.delta SSE 事件。

    Args:
        item_id: 所属 item 的 id。
        output_index: 输出项序号。
        delta: 文本增量。
        sequence: 序列号（递增）。

    Returns:
        SSE 事件字符串。
    """
    data = {
        "type": "response.output_text.delta",
        "item_id": item_id,
        "output_index": output_index,
        "content_index": 0,
        "delta": delta,
        "sequence_number": sequence,
    }
    return _build_sse_event("response.output_text.delta", data)


def _build_function_call_arguments_delta(
    item_id: str, call_id: str, output_index: int, delta: str, sequence: int,
) -> str:
    """构建 response.function_call_arguments.delta SSE 事件。

    Args:
        item_id: 所属 item 的 id。
        call_id: 工具调用标识符。
        output_index: 输出项序号。
        delta: arguments 增量片段。
        sequence: 序列号（递增）。

    Returns:
        SSE 事件字符串。
    """
    data = {
        "type": "response.function_call_arguments.delta",
        "item_id": item_id,
        "call_id": call_id,
        "output_index": output_index,
        "delta": delta,
        "sequence_number": sequence,
    }
    return _build_sse_event("response.function_call_arguments.delta", data)


def _build_function_call_arguments_done(
    item_id: str, call_id: str, output_index: int, delta: str,
) -> str:
    """构建 response.function_call_arguments.done SSE 事件。

    Args:
        item_id: 所属 item 的 id。
        call_id: 工具调用标识符。
        output_index: 输出项序号。
        delta: 最终累计的 arguments 完整字符串。

    Returns:
        SSE 事件字符串。
    """
    data = {
        "type": "response.function_call_arguments.done",
        "item_id": item_id,
        "call_id": call_id,
        "output_index": output_index,
        "delta": delta,
    }
    return _build_sse_event("response.function_call_arguments.done", data)


def _build_output_item_done(
    output_index: int, item_type: str, item_id: str, **fields,
) -> str:
    """构建 response.output_item.done SSE 事件。

    根据 item_type 自动设置不同的 item 结构:
    - reasoning: {id, type, status}
    - message: {id, type, status, content} 含 accumulated_text
    - function_call: {id, type, name, call_id, arguments, status}

    Args:
        output_index: 输出项序号。
        item_type: 项类型 ("reasoning" | "message" | "function_call")。
        item_id: 项标识符。
        **fields: 额外字段 (accumulated_text, name, call_id, accumulated_arguments)。

    Returns:
        SSE 事件字符串。
    """
    item = {
        "id": item_id,
        "type": item_type,
        "status": "completed",
    }
    if item_type == "reasoning":
        pass
    elif item_type == "message":
        item["content"] = [
            {"type": "output_text", "text": fields.get("accumulated_text", "")},
        ]
    elif item_type == "function_call":
        item["name"] = fields.get("name", "unknown")
        item["call_id"] = fields.get("call_id", f"call_{output_index}")
        item["arguments"] = fields.get("accumulated_arguments", "")

    data = {
        "type": "response.output_item.done",
        "item": item,
        "output_index": output_index,
    }
    return _build_sse_event("response.output_item.done", data)


def _build_response_completed(
    response_id: str, usage: dict | None = None,
) -> str:
    """构建 response.completed SSE 事件。

    Args:
        response_id: 响应唯一标识符。
        usage: token 用量 dict，None 时使用空计数。

    Returns:
        SSE 事件字符串。
    """
    if usage is None:
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    data = {
        "type": "response.completed",
        "response": {
            "id": response_id,
            "object": "response",
            "status": "completed",
            "usage": usage,
        },
    }
    return _build_sse_event("response.completed", data)


# ---- 内部辅助：关闭活跃工具调用 ----


def _close_active_tool_calls(state: _ToolCallState) -> list[str]:
    """关闭所有活跃工具调用，返回 SSE 事件行列表。

    每个工具调用依次产生两个事件:
    1. function_call_arguments.done — 最终 arguments 完整片段
    2. output_item.done — 工具调用完成状态

    Args:
        state: 工具调用状态 dataclass，封装 6 个映射。

    Returns:
        SSE 事件字符串列表。
    """
    events: list[str] = []
    for idx in sorted(state.active_indices):
        call_id = state.call_ids[idx]
        item_id = state.item_ids[idx]
        output_idx = state.output_indices[idx]
        accumulated = state.arguments[idx]
        name = state.names[idx]
        events.append(
            _build_function_call_arguments_done(item_id, call_id, output_idx, accumulated),
        )
        events.append(
            _build_output_item_done(
                output_idx,
                "function_call",
                item_id,
                name=name,
                call_id=call_id,
                accumulated_arguments=accumulated,
            ),
        )
    return events


# ---- 公开 API ----


async def translate_sse_stream(
    upstream: AsyncIterable[dict],
) -> AsyncGenerator[str, None]:
    """将 DeepSeek Chat delta chunk 流翻译为 Responses API SSE 事件流。

    Pure function: 不修改输入 dict（只读迭代）。
    返回 Responses API SSE 事件字符串的异步生成器。

    Args:
        upstream: Chat Completions delta dict 的异步迭代器。

    Yields:
        Responses API SSE 事件字符串（含 event: + data: 行）。

    状态追踪:
        current_output_type: None | "reasoning" | "text" | "tool_call"
        tc_state: _ToolCallState — 工具调用状态 dataclass

    事件生命周期 (CODX-06):
        1. response.created — 响应开始
        2. response.in_progress — 处理中
        3. response.output_item.added — 输出项添加 (每次类型转换)
        4. delta 事件 × N — 内容增量
        5. response.output_item.done — 输出项完成
        6. response.completed — 响应完成
    """
    # 状态追踪（D-06 隐式状态）
    current_output_type: str | None = None  # None | "reasoning" | "text" | "tool_call"
    tc_state = _ToolCallState()             # D-07: 追踪活跃 tool_call indices
    is_first_chunk = True
    _completed = False                       # D-08: finish_reason 幂等保护
    sequence = 0                             # 递增序列号
    response_id = f"resp_{uuid4().hex[:12]}"
    item_id_counter = 0                      # 递增 item_id
    output_counter = -1                      # 递增 output_index (0-indexed)

    # 文本/推理内容累计（用于 output_item.done）
    accumulated_text = ""
    accumulated_reasoning = ""

    # 活跃 item id 追踪
    reasoning_item_id: str | None = None
    reasoning_output_index: int = 0
    text_item_id: str | None = None
    text_output_index: int = 0

    model_name = "deepseek-v4-pro"

    try:
        async for chunk in upstream:
            choices = chunk.get("choices", [])
            if not choices:
                logger.warning("[CODEX] Empty chunk received (no choices)")
                continue

            delta = choices[0].get("delta", {})
            finish_reason = choices[0].get("finish_reason")

            if _completed:
                # Pitfall 4: finish_reason 幂等保护
                continue

            # ---- 首个 chunk: created + in_progress (D-08) ----
            if is_first_chunk:
                model_name = chunk.get("model", "deepseek-v4-pro")
                yield _build_response_created(response_id, model_name)
                yield _build_response_in_progress(response_id)
                is_first_chunk = False
                logger.info("[CODEX] SSE stream started for %s", response_id)

            # ---- reasoning_content 处理 (D-08) ----
            reasoning = delta.get("reasoning_content")
            if reasoning:
                if current_output_type is not None and current_output_type != "reasoning":
                    # 类型转换：关闭当前 item
                    if current_output_type == "tool_call":
                        events = _close_active_tool_calls(tc_state)
                        for event in events:
                            yield event
                        tc_state.clear()
                    elif current_output_type == "text":
                        yield _build_output_item_done(
                            text_output_index, "message", text_item_id,
                            accumulated_text=accumulated_text,
                        )
                        accumulated_text = ""
                        text_item_id = None
                    # current_output_type == "reasoning" → 不触发 transition
                    logger.info(
                        "[CODEX] Type transition: %s -> reasoning",
                        current_output_type,
                    )

                if current_output_type != "reasoning":
                    # 创建新的 reasoning item
                    item_id_counter += 1
                    reasoning_item_id = f"item_{item_id_counter}"
                    output_counter += 1
                    reasoning_output_index = output_counter
                    yield _build_output_item_added(
                        output_counter, "reasoning",
                        item_id=reasoning_item_id,
                    )
                    current_output_type = "reasoning"

                sequence += 1
                accumulated_reasoning += reasoning
                yield _build_reasoning_text_delta(
                    reasoning_item_id, reasoning_output_index,
                    reasoning, sequence,
                )
                logger.debug("[CODEX] Delta: reasoning (%d chars)", len(reasoning))

            # ---- content (text) 处理 (D-09) ----
            content_text = delta.get("content")
            if content_text:  # 非空字符串（跳过角色声明的空 content）
                if current_output_type is not None and current_output_type != "text":
                    # 类型转换：关闭当前 item
                    if current_output_type == "tool_call":
                        events = _close_active_tool_calls(tc_state)
                        for event in events:
                            yield event
                        tc_state.clear()
                    elif current_output_type == "reasoning":
                        yield _build_output_item_done(
                            reasoning_output_index, "reasoning",
                            reasoning_item_id,
                        )
                        reasoning_item_id = None
                        accumulated_reasoning = ""
                    # current_output_type == "text" → 不触发 transition
                    logger.info(
                        "[CODEX] Type transition: %s -> text",
                        current_output_type,
                    )

                if current_output_type != "text":
                    # 创建新的 text item
                    item_id_counter += 1
                    text_item_id = f"item_{item_id_counter}"
                    output_counter += 1
                    text_output_index = output_counter
                    yield _build_output_item_added(
                        output_counter, "message",
                        item_id=text_item_id,
                    )
                    yield _build_content_part_added(
                        text_item_id, output_counter, 0,
                    )
                    current_output_type = "text"

                sequence += 1
                accumulated_text += content_text
                yield _build_output_text_delta(
                    text_item_id, text_output_index,
                    content_text, sequence,
                )
                logger.debug("[CODEX] Delta: text (%d chars)", len(content_text))

            # ---- tool_calls 处理 (D-07/D-08) ----
            tool_calls = delta.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    idx = tc.get("index")

                    if idx not in tc_state.active_indices:
                        # 新工具调用 (D-07)
                        # 如果当前有 text 或 reasoning item，先关闭
                        if current_output_type == "text":
                            yield _build_output_item_done(
                                text_output_index, "message", text_item_id,
                                accumulated_text=accumulated_text,
                            )
                            accumulated_text = ""
                            text_item_id = None
                            logger.info(
                                "[CODEX] Type transition: text -> tool_call",
                            )
                        elif current_output_type == "reasoning":
                            yield _build_output_item_done(
                                reasoning_output_index, "reasoning",
                                reasoning_item_id,
                            )
                            reasoning_item_id = None
                            accumulated_reasoning = ""
                            logger.info(
                                "[CODEX] Type transition: reasoning -> tool_call",
                            )

                        # 提取工具信息
                        call_id = tc.get("id", f"call_{idx}")
                        name = tc.get("function", {}).get("name", "unknown")

                        tc_state.active_indices.add(idx)
                        tc_state.call_ids[idx] = call_id
                        tc_state.names[idx] = name
                        tc_state.arguments[idx] = ""

                        item_id_counter += 1
                        tc_state.item_ids[idx] = f"fc_{item_id_counter}"
                        output_counter += 1
                        tc_state.output_indices[idx] = output_counter

                        yield _build_output_item_added(
                            output_counter, "function_call",
                            name=name, call_id=call_id,
                            item_id=tc_state.item_ids[idx],
                        )
                        current_output_type = "tool_call"

                    # 收获 arguments 片段（含首次空字符串）
                    arg_fragment = tc.get("function", {}).get("arguments", "")
                    tc_state.arguments[idx] += arg_fragment

                    sequence += 1
                    yield _build_function_call_arguments_delta(
                        tc_state.item_ids[idx], tc_state.call_ids[idx],
                        tc_state.output_indices[idx], arg_fragment, sequence,
                    )
                    logger.debug(
                        "[CODEX] Delta: tool_call idx=%s (%d chars)",
                        idx, len(arg_fragment),
                    )

            # ---- finish_reason 处理 ----
            if finish_reason:
                # 关闭所有活跃工具调用
                if tc_state.active_indices:
                    events = _close_active_tool_calls(tc_state)
                    for event in events:
                        yield event
                    tc_state.clear()

                # 关闭当前 text 或 reasoning item
                if current_output_type == "text" and text_item_id:
                    yield _build_output_item_done(
                        text_output_index, "message", text_item_id,
                        accumulated_text=accumulated_text,
                    )
                elif current_output_type == "reasoning" and reasoning_item_id:
                    yield _build_output_item_done(
                        reasoning_output_index, "reasoning",
                        reasoning_item_id,
                    )

                # 获取 usage
                usage = chunk.get("usage")
                yield _build_response_completed(response_id, usage)
                _completed = True
                logger.info("[CODEX] SSE stream completed: %s", response_id)

    except Exception:
        logger.exception("[CODEX] SSE stream translation error")
        if not _completed:
            yield _build_response_completed(response_id, None)
            logger.info(
                "[CODEX] SSE stream gracefully closed after error: %s",
                response_id,
            )
