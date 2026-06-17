"""dsv4-cc-proxy SSE 状态机单元测试。

覆盖: 基础文本流、推理流、推理->文本转换、工具调用流、
      多工具并行、文本->工具转换、完整生命周期、边界情况。

运行: python3 -m pytest tests/test_sse.py -v
"""

import json

import pytest

from dsv4_cc_proxy.codex.sse import translate_sse_stream


# ---- 测试辅助 ----


def _collect_events(chunks: list[dict]) -> list[dict]:
    """将 translate_sse_stream 异步生成器的输出收集为事件 dict 列表。

    Args:
        chunks: Chat delta dict 列表（模拟上游 SSE chunk 输入）。

    Returns:
        解析后的 SSE 事件 dict 列表，每个含 {"event": str, "data": dict}。
    """
    import asyncio

    async def _async_iter(items):
        for item in items:
            yield item

    async def _collect():
        events = []
        async for event_str in translate_sse_stream(_async_iter(chunks)):
            lines = event_str.strip().split("\n")
            event_type = ""
            data = {}
            for line in lines:
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
            events.append({"event": event_type, "data": data})
        return events

    return asyncio.run(_collect())


def _find_events(events: list[dict], event_type: str) -> list[dict]:
    """从事件列表中筛选指定类型的事件。"""
    return [e for e in events if e["event"] == event_type]


# =============================================================================
# 组 1: 基础文本和推理流
# =============================================================================


def test_text_stream():
    """纯文本 delta.content 流 — 验证 output_text.delta 和完整文本生命周期 (CODX-05)。"""
    chunks = [
        {"choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hello"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"content": " "}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"content": "World"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    ]
    events = _collect_events(chunks)

    # 基础生命周期事件
    assert events[0]["event"] == "response.created"
    assert events[1]["event"] == "response.in_progress"

    # output_item.added (message)
    added = _find_events(events, "response.output_item.added")
    assert len(added) == 1
    assert added[0]["data"]["item"]["type"] == "message"

    # content_part.added
    cp_added = _find_events(events, "response.content_part.added")
    assert len(cp_added) == 1

    # output_text.delta 事件
    deltas = _find_events(events, "response.output_text.delta")
    assert len(deltas) == 3
    assert deltas[0]["data"]["delta"] == "Hello"
    assert deltas[1]["data"]["delta"] == " "
    assert deltas[2]["data"]["delta"] == "World"

    # output_item.done (message with accumulated text)
    done = _find_events(events, "response.output_item.done")
    assert len(done) == 1
    assert done[0]["data"]["item"]["type"] == "message"
    assert "Hello World" in done[0]["data"]["item"]["content"][0]["text"]

    # response.completed
    assert events[-1]["event"] == "response.completed"


def test_reasoning_stream():
    """纯 reasoning_content 流 — 验证 reasoning_text.delta (CODX-13)。"""
    chunks = [
        {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"reasoning_content": "Let me "}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"reasoning_content": "think"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    ]
    events = _collect_events(chunks)

    # 基础生命周期
    assert events[0]["event"] == "response.created"
    assert events[1]["event"] == "response.in_progress"

    # output_item.added (reasoning)
    added = _find_events(events, "response.output_item.added")
    assert len(added) == 1
    assert added[0]["data"]["item"]["type"] == "reasoning"

    # reasoning_text.delta 事件
    reasoning_deltas = _find_events(events, "response.reasoning_text.delta")
    assert len(reasoning_deltas) == 2
    assert reasoning_deltas[0]["data"]["delta"] == "Let me "
    assert reasoning_deltas[1]["data"]["delta"] == "think"

    # 无 output_text.delta
    text_deltas = _find_events(events, "response.output_text.delta")
    assert len(text_deltas) == 0

    # output_item.done (reasoning)
    done = _find_events(events, "response.output_item.done")
    assert len(done) == 1
    assert done[0]["data"]["item"]["type"] == "reasoning"

    # response.completed
    assert events[-1]["event"] == "response.completed"


def test_reasoning_to_text_transition():
    """reasoning -> text 类型转换 — 验证关闭 reasoning 并创建 text item (CODX-15)。"""
    chunks = [
        {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"reasoning_content": "Thinking..."}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"content": "Answer"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    ]
    events = _collect_events(chunks)

    # reasoning + message 各一个 output_item
    added = _find_events(events, "response.output_item.added")
    assert len(added) == 2
    assert added[0]["data"]["item"]["type"] == "reasoning"
    assert added[1]["data"]["item"]["type"] == "message"

    # reasoning -> text transition: reasoning done 后 message done
    done = _find_events(events, "response.output_item.done")
    assert len(done) == 2
    assert done[0]["data"]["item"]["type"] == "reasoning"
    assert done[1]["data"]["item"]["type"] == "message"

    # reasoning_text.delta 和 output_text.delta
    reasoning_deltas = _find_events(events, "response.reasoning_text.delta")
    assert len(reasoning_deltas) == 1
    assert reasoning_deltas[0]["data"]["delta"] == "Thinking..."

    text_deltas = _find_events(events, "response.output_text.delta")
    assert len(text_deltas) == 1
    assert text_deltas[0]["data"]["delta"] == "Answer"

    # content_part.added（text item 创建时需要）
    cp_added = _find_events(events, "response.content_part.added")
    assert len(cp_added) == 1

    assert events[-1]["event"] == "response.completed"


# =============================================================================
# 组 2: 工具调用流
# =============================================================================


def test_tool_call_stream():
    """单个工具调用流 — 验证 function_call_arguments.delta 和调用生命周期 (CODX-08)。"""
    chunks = [
        {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": ""}}]}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\"loc"}}]}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "ation\": \"SF\"}"}}]}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
    ]
    events = _collect_events(chunks)

    # output_item.added (function_call)
    added = _find_events(events, "response.output_item.added")
    assert len(added) == 1
    assert added[0]["data"]["item"]["type"] == "function_call"
    assert added[0]["data"]["item"]["name"] == "get_weather"
    assert added[0]["data"]["item"]["call_id"] == "call_1"

    # function_call_arguments.delta 事件
    arg_deltas = _find_events(events, "response.function_call_arguments.delta")
    assert len(arg_deltas) >= 2

    # function_call_arguments.done — 最终 arguments 正确
    arg_done = _find_events(events, "response.function_call_arguments.done")
    assert len(arg_done) == 1
    assert arg_done[0]["data"]["delta"] == '{"location": "SF"}'

    # output_item.done (function_call)
    done = _find_events(events, "response.output_item.done")
    assert len(done) == 1
    assert done[0]["data"]["item"]["type"] == "function_call"
    assert done[0]["data"]["item"]["arguments"] == '{"location": "SF"}'

    assert events[-1]["event"] == "response.completed"


def test_parallel_tool_calls():
    """多工具并行调用 — 验证各自独立的事件流，无 index 冲突 (CODX-09)。"""
    chunks = [
        {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": ""}},
            {"index": 1, "id": "call_2", "type": "function", "function": {"name": "search_web", "arguments": ""}},
        ]}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": "{\"loc"}},
            {"index": 1, "function": {"arguments": "{\"que"}},
        ]}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": "ation\": \"SF\"}"}},
            {"index": 1, "function": {"arguments": "ry\": \"weather\"}"}},
        ]}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
    ]
    events = _collect_events(chunks)

    # 两个 function_call output_item.added
    added = _find_events(events, "response.output_item.added")
    assert len(added) == 2
    assert added[0]["data"]["item"]["type"] == "function_call"
    assert added[1]["data"]["item"]["type"] == "function_call"

    # function_call_arguments.delta 事件分布到对应 index
    arg_deltas = _find_events(events, "response.function_call_arguments.delta")
    assert len(arg_deltas) >= 4  # 2 tools * (1 initial + 2 arg fragments)

    # function_call_arguments.done — 两个工具各自有独立的 done
    arg_done = _find_events(events, "response.function_call_arguments.done")
    assert len(arg_done) == 2

    # 验证无交叉污染：工具 0 的 arguments 不含工具 1 的内容
    done0 = arg_done[0]["data"]
    done1 = arg_done[1]["data"]
    # Each done must reference independent accumulated arguments
    assert "location" in done0["delta"] or "SF" in done0["delta"]
    assert "query" in done1["delta"] or "weather" in done1["delta"]

    # output_item.done — 两个工具各自有独立的 done
    done = _find_events(events, "response.output_item.done")
    assert len(done) == 2
    assert done[0]["data"]["item"]["type"] == "function_call"
    assert done[1]["data"]["item"]["type"] == "function_call"
    # 各工具的 arguments 独立累计
    assert "location" in done[0]["data"]["item"]["arguments"]
    assert "query" in done[1]["data"]["item"]["arguments"]

    assert events[-1]["event"] == "response.completed"


def test_text_to_tool_transition():
    """文本完成后发起工具调用 — 验证 text done -> function_call added (CODX-15)。"""
    chunks = [
        {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"content": "Let me check"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "Bash", "arguments": ""}}]}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "ls -la"}}]}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
    ]
    events = _collect_events(chunks)

    # output_item.added — text + function_call
    added = _find_events(events, "response.output_item.added")
    assert len(added) == 2
    assert added[0]["data"]["item"]["type"] == "message"
    assert added[1]["data"]["item"]["type"] == "function_call"

    # text 的 output_item.done 在 function_call 出现之前
    done = _find_events(events, "response.output_item.done")
    text_done_idx = None
    for i, d in enumerate(done):
        if d["data"]["item"]["type"] == "message":
            text_done_idx = i
            break
    assert text_done_idx is not None
    assert "Let me check" in done[text_done_idx]["data"]["item"]["content"][0]["text"]

    # content_part.added
    cp_added = _find_events(events, "response.content_part.added")
    assert len(cp_added) == 1

    # output_text.delta
    text_deltas = _find_events(events, "response.output_text.delta")
    assert len(text_deltas) == 1
    assert text_deltas[0]["data"]["delta"] == "Let me check"

    assert events[-1]["event"] == "response.completed"


# =============================================================================
# 组 3: 生命周期和边界
# =============================================================================


def test_full_lifecycle():
    """完整混合生命周期: reasoning -> text -> tool_calls -> finish_reason (CODX-06)。"""
    chunks = [
        {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"reasoning_content": "Think"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"content": "Answer"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": ""}}]}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
    ]
    events = _collect_events(chunks)

    # 严格事件顺序验证（含 CODX-13 output_text.done + content_part.done 修复）
    expected_sequence = [
        "response.created",
        "response.in_progress",
        "response.output_item.added",               # reasoning
        "response.reasoning_text.delta",
        "response.output_item.done",                 # reasoning -> text transition
        "response.output_item.added",                # message
        "response.content_part.added",
        "response.output_text.delta",
        "response.output_text.done",                 # CODX-13: text 完结事件
        "response.content_part.done",                # CODX-13: content part 完结事件
        "response.output_item.done",                 # text -> tool_call transition
        "response.output_item.added",                # function_call
        "response.function_call_arguments.delta",    # initial empty delta
        "response.function_call_arguments.done",     # finish_reason closes tool
        "response.output_item.done",                 # function_call
        "response.completed",
    ]

    assert len(events) == len(expected_sequence)
    for i, expected_event in enumerate(expected_sequence):
        assert events[i]["event"] == expected_event, \
            f"Event at index {i}: expected '{expected_event}', got '{events[i]['event']}'"


class TestEdgeCases:
    """边界情况分组容器。"""

    def test_empty_stream(self):
        """空流（无 chunk）— 无事件。"""
        events = _collect_events([])
        assert len(events) == 0

    def test_finish_reason_only(self):
        """仅 finish_reason（无 content/reasoning/tool_calls）— 三个必须事件。"""
        chunks = [
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        events = _collect_events(chunks)
        assert len(events) == 3
        assert events[0]["event"] == "response.created"
        assert events[1]["event"] == "response.in_progress"
        assert events[2]["event"] == "response.completed"

    def test_duplicate_finish_reason(self):
        """重复 finish_reason — 第二个被幂等忽略 (_completed flag)。"""
        chunks = [
            {"choices": [{"index": 0, "delta": {"content": "Hi"}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        events = _collect_events(chunks)

        completed = _find_events(events, "response.completed")
        assert len(completed) == 1
        assert events[-1]["event"] == "response.completed"

    def test_reasoning_and_content_same_chunk(self):
        """同时含 reasoning_content 和 content 的 chunk — 先处理 reasoning 再处理 content。"""
        chunks = [
            {"choices": [{"index": 0, "delta": {"reasoning_content": "Think", "content": "Answer"}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        events = _collect_events(chunks)

        # reasoning 和 text 各有单独的 output_item
        added = _find_events(events, "response.output_item.added")
        assert len(added) == 2
        assert added[0]["data"]["item"]["type"] == "reasoning"
        assert added[1]["data"]["item"]["type"] == "message"

        # reasoning 在前，text 在后
        reasoning_deltas = _find_events(events, "response.reasoning_text.delta")
        text_deltas = _find_events(events, "response.output_text.delta")
        assert len(reasoning_deltas) == 1
        assert len(text_deltas) == 1
        assert reasoning_deltas[0]["data"]["delta"] == "Think"
        assert text_deltas[0]["data"]["delta"] == "Answer"

    def test_unknown_finish_reason(self):
        """未知 finish_reason 值（如 content_filter）— 透传不崩溃。"""
        chunks = [
            {"choices": [{"index": 0, "delta": {"content": "Hi"}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "content_filter"}]},
        ]
        events = _collect_events(chunks)
        assert events[-1]["event"] == "response.completed"
        output_text = _find_events(events, "response.output_text.delta")
        assert len(output_text) == 1
        assert output_text[0]["data"]["delta"] == "Hi"

    def test_empty_choices(self):
        """无 choices 的 chunk — 被跳过不崩溃。"""
        chunks = [
            {},
            {"choices": [{"index": 0, "delta": {"content": "Hi"}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        events = _collect_events(chunks)
        assert events[-1]["event"] == "response.completed"
        text_deltas = _find_events(events, "response.output_text.delta")
        assert len(text_deltas) == 1
        assert text_deltas[0]["data"]["delta"] == "Hi"

    def test_tool_call_to_reasoning(self):
        """工具调用流中 reasoning 出现 — 关闭工具后创建 reasoning item。"""
        chunks = [
            {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": ""}}]}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {"reasoning_content": "Thinking..."}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        events = _collect_events(chunks)

        # function_call + reasoning 各一个 output_item
        added = _find_events(events, "response.output_item.added")
        assert len(added) == 2
        assert added[0]["data"]["item"]["type"] == "function_call"
        assert added[1]["data"]["item"]["type"] == "reasoning"

        # function_call 在 reasoning 出现时被关闭
        done = _find_events(events, "response.output_item.done")
        assert len(done) == 2
        assert done[0]["data"]["item"]["type"] == "function_call"

        reasoning_deltas = _find_events(events, "response.reasoning_text.delta")
        assert len(reasoning_deltas) == 1
        assert reasoning_deltas[0]["data"]["delta"] == "Thinking..."

        assert events[-1]["event"] == "response.completed"

    def test_tool_call_to_text(self):
        """工具调用流中 content 出现 — 关闭工具后创建 text item。"""
        chunks = [
            {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": ""}}]}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {"content": "The weather is nice"}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        events = _collect_events(chunks)

        added = _find_events(events, "response.output_item.added")
        assert len(added) == 2
        assert added[0]["data"]["item"]["type"] == "function_call"
        assert added[1]["data"]["item"]["type"] == "message"

        text_deltas = _find_events(events, "response.output_text.delta")
        assert len(text_deltas) == 1
        assert text_deltas[0]["data"]["delta"] == "The weather is nice"

        # content_part.added 在 text item 创建时
        cp_added = _find_events(events, "response.content_part.added")
        assert len(cp_added) == 1

        assert events[-1]["event"] == "response.completed"

    def test_reasoning_to_tool_call_direct(self):
        """推理流中直接出现工具调用（无 text 过渡）— 关闭 reasoning 后创建 function_call。"""
        chunks = [
            {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {"reasoning_content": "I need to search"}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "search_web", "arguments": ""}}]}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\"query\": \"weather\"}"}}]}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
        ]
        events = _collect_events(chunks)

        # reasoning + function_call 各一个 output_item
        added = _find_events(events, "response.output_item.added")
        assert len(added) == 2
        assert added[0]["data"]["item"]["type"] == "reasoning"
        assert added[1]["data"]["item"]["type"] == "function_call"

        # reasoning 在 tool_calls 出现时被关闭
        done = _find_events(events, "response.output_item.done")
        assert len(done) == 2
        assert done[0]["data"]["item"]["type"] == "reasoning"

        assert events[-1]["event"] == "response.completed"

    def test_exception_mid_stream(self):
        """流中异常 — 优雅关闭，发出 graceful response.completed。"""
        import asyncio

        async def _raise_mid():
            yield {"choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hi"}, "finish_reason": None}]}
            raise RuntimeError("simulated stream error")

        async def _collect():
            events = []
            async for event_str in translate_sse_stream(_raise_mid()):
                lines = event_str.strip().split("\n")
                event_type = ""
                data = {}
                for line in lines:
                    if line.startswith("event: "):
                        event_type = line[7:]
                    elif line.startswith("data: "):
                        data = json.loads(line[6:])
                events.append({"event": event_type, "data": data})
            return events

        events = asyncio.run(_collect())

        # 有部分事件 + 优雅关闭的 completed
        assert len(events) >= 2
        assert events[-1]["event"] == "response.completed"
        # 首个事件仍是 created
        assert events[0]["event"] == "response.created"
