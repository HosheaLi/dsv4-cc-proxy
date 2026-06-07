"""dsv4-cc-proxy 单元测试。

覆盖 pure functions: 请求端注入、thinking 标准化、SSE 过滤。
运行: python3 -m pytest tests/test_proxy.py -v
"""

import json

from dsv4_cc_proxy.proxy import (
    _filter_sse_line,
    _has_thinking,
    _has_tool_use,
    _inject_thinking_blocks,
    _normalize_thinking,
    _thinking_requested,
)

# === 辅助函数 ===

def test_has_tool_use():
    assert _has_tool_use([{"type": "tool_use", "name": "Bash"}])
    assert not _has_tool_use([{"type": "text", "text": "hello"}])
    assert not _has_tool_use([])
    assert _has_tool_use([{"type": "text"}, {"type": "tool_use"}])


def test_has_thinking():
    assert _has_thinking([{"type": "thinking", "thinking": ""}])
    assert _has_thinking([{"type": "redacted_thinking", "data": "..."}])
    assert not _has_thinking([{"type": "tool_use"}])
    assert not _has_thinking([])


# === 修复 1: thinking 注入 ===

def test_inject_thinking_disabled():
    data = {
        "model": "deepseek-v4-pro",
        "thinking": {"type": "disabled"},
        "messages": [
            {"role": "assistant", "content": [{"type": "tool_use", "id": "call_1", "name": "Bash", "input": {}}]}
        ]
    }
    assert not _inject_thinking_blocks(data)


def test_inject_thinking_non_v4():
    data = {
        "model": "claude-sonnet-4-6",
        "thinking": {"type": "enabled"},
        "messages": [
            {"role": "assistant", "content": [{"type": "tool_use", "id": "call_1", "name": "Bash", "input": {}}]}
        ]
    }
    assert not _inject_thinking_blocks(data)


def test_inject_thinking_adds_block():
    data = {
        "model": "deepseek-v4-pro",
        "thinking": {"type": "enabled"},
        "messages": [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "call_1", "name": "Bash", "input": {"cmd": "ls"}}
            ]}
        ]
    }
    assert _inject_thinking_blocks(data)
    content = data["messages"][0]["content"]
    assert content[0]["type"] == "thinking"
    assert content[0]["thinking"] == ""
    assert content[1]["type"] == "tool_use"


def test_inject_thinking_skips_when_has_thinking():
    data = {
        "model": "deepseek-v4-pro",
        "thinking": {"type": "enabled"},
        "messages": [
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "already there"},
                {"type": "tool_use", "id": "call_1", "name": "Bash", "input": {}}
            ]}
        ]
    }
    data_copy = json.loads(json.dumps(data))
    assert not _inject_thinking_blocks(data)
    assert data == data_copy


def test_inject_thinking_string_content():
    data = {
        "model": "deepseek-v4-pro",
        "thinking": {"type": "enabled"},
        "messages": [
            {"role": "assistant", "content": "plain text content"}
        ]
    }
    assert not _inject_thinking_blocks(data)


# === 修复 2: thinking 标准化 ===

def test_normalize_enabled_unchanged():
    data = {"thinking": {"type": "enabled"}}
    assert not _normalize_thinking(data)
    assert data["thinking"]["type"] == "enabled"


def test_normalize_disabled_unchanged():
    data = {"thinking": {"type": "disabled"}}
    assert not _normalize_thinking(data)
    assert data["thinking"]["type"] == "disabled"


def test_normalize_adaptive_converts():
    data = {
        "thinking": {"type": "adaptive"},
        "messages": [
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "some thought"},
                {"type": "text", "text": "hello"}
            ]}
        ]
    }
    assert _normalize_thinking(data)
    assert data["thinking"]["type"] == "disabled"
    content = data["messages"][0]["content"]
    assert len(content) == 1
    assert content[0]["type"] == "text"


def test_normalize_adaptive_removes_effort():
    data = {"thinking": {"type": "adaptive"}, "reasoning_effort": "max"}
    _normalize_thinking(data)
    assert "reasoning_effort" not in data
    assert data["thinking"]["type"] == "disabled"


def test_normalize_adaptive_removes_output_config():
    data = {"thinking": {"type": "adaptive"}, "output_config": {"effort": "max"}}
    _normalize_thinking(data)
    assert "output_config" not in data


def test_normalize_no_thinking_key():
    assert not _normalize_thinking({"max_tokens": 100})


# === 修复 3: SSE 过滤 ===

def test_filter_sse_passes_non_data():
    assert _filter_sse_line("event: message_start", set()) == ("event: message_start", set())
    assert _filter_sse_line("", set()) == ("", set())
    assert _filter_sse_line(":comment", set()) == (":comment", set())


def test_filter_sse_passes_text():
    result, _ = _filter_sse_line(
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
        set()
    )
    assert result is not None


def test_filter_sse_passes_tool_use():
    result, _ = _filter_sse_line(
        'data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use",'
        '"id":"call_1","name":"Bash","input":{}}}',
        set()
    )
    assert result is not None


def test_filter_sse_filters_thinking_start():
    idx = set()
    result, idx = _filter_sse_line(
        'data: {"type":"content_block_start","index":0,"content_block":'
        '{"type":"thinking","thinking":"","signature":""}}',
        idx
    )
    assert result is None
    assert 0 in idx


def test_filter_sse_filters_thinking_delta():
    idx = {0}
    result, idx = _filter_sse_line(
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"Hello"}}',
        idx
    )
    assert result is None


def test_filter_sse_filters_signature_delta():
    idx = {0}
    result, idx = _filter_sse_line(
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"signature_delta","signature":"abc"}}',
        idx
    )
    assert result is None


def test_filter_sse_full_thinking_block():
    idx = set()
    lines = [
        'data: {"type":"content_block_start","index":0,"content_block":'
        '{"type":"thinking","thinking":"","signature":""}}',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"x"}}',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"signature_delta","signature":"sig"}}',
        'data: {"type":"content_block_stop","index":0}',
        'data: {"type":"content_block_start","index":1,"content_block":{"type":"text","text":""}}',
    ]
    results = []
    for line in lines:
        filtered, idx = _filter_sse_line(line, idx)
        results.append(filtered)
    assert results == [None, None, None, None, lines[4]]


def test_filter_sse_invalid_json():
    result, _ = _filter_sse_line("data: {invalid json}", set())
    assert result == "data: {invalid json}"


# === thinking_requested ===

def test_thinking_requested():
    assert _thinking_requested({"thinking": {"type": "enabled"}})
    assert not _thinking_requested({"thinking": {"type": "disabled"}})
    assert not _thinking_requested({"thinking": {"type": "adaptive"}})
    assert not _thinking_requested({})


# === proxy.py 边缘情况补充 ===


def test_thinking_requested_non_dict():
    """thinking 配置不是 dict -> False。"""
    assert not _thinking_requested({"thinking": "enabled"})


def test_thinking_requested_no_thinking_key():
    """data 中无 thinking 键 -> False。"""
    assert not _thinking_requested({"model": "deepseek-v4-pro"})


def test_thinking_requested_empty_data():
    """空 data -> False。"""
    assert not _thinking_requested({})


def test_normalize_thinking_no_messages_key():
    """data 无 messages 键 -> True（thinking 被修改）。"""
    data = {"thinking": {"type": "adaptive"}}
    assert _normalize_thinking(data)
    assert data["thinking"]["type"] == "disabled"


def test_normalize_thinking_unknown_type():
    """未知 thinking type -> 转换为 disabled。"""
    data = {"thinking": {"type": "auto"}, "messages": [{"role": "user", "content": "hi"}]}
    assert _normalize_thinking(data)
    assert data["thinking"]["type"] == "disabled"


def test_inject_thinking_blocks_non_dict_thinking():
    """thinking 不是 dict -> False。"""
    data = {
        "thinking": "enabled",
        "model": "deepseek-v4-pro",
        "messages": [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "call_1", "name": "Bash", "input": {}}
            ]}
        ],
    }
    assert not _inject_thinking_blocks(data)


def test_inject_thinking_blocks_no_messages():
    """无 messages -> False。"""
    data = {"thinking": {"type": "enabled"}, "model": "deepseek-v4-pro"}
    assert not _inject_thinking_blocks(data)


def test_filter_sse_thinking_delta_wrong_index():
    """thinking_delta 但 index 不在 thinking_indices 中 -> 透传。"""
    line = (
        'data: {"type":"content_block_delta","index":0,'
        '"delta":{"type":"thinking_delta","thinking":"Hello"}}'
    )
    result, indices = _filter_sse_line(line, set())
    assert result == line
    assert indices == set()


def test_filter_sse_content_block_stop_tracking():
    """content_block_stop 正确从 thinking_indices 清除 index。"""
    line = 'data: {"type":"content_block_stop","index":0}'
    result, indices = _filter_sse_line(line, {0})
    assert result is None
    assert 0 not in indices
