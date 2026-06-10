"""dsv4-cc-proxy 单元测试。

覆盖 pure functions: 请求端注入、thinking 标准化、SSE 过滤。
运行: python3 -m pytest tests/test_proxy.py -v
"""

import json

from dsv4_cc_proxy.proxy import (
    _has_thinking,
    _has_tool_use,
    _inject_thinking_blocks,
    _normalize_thinking,
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


def test_normalize_adaptive_converts_to_enabled():
    """adaptive/auto → enabled，历史 thinking 块保留（enabled 模式 DeepSeek 支持）。"""
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
    assert data["thinking"]["type"] == "enabled"
    # enabled 模式不剥离历史 thinking 块
    content = data["messages"][0]["content"]
    assert len(content) == 2
    assert content[0]["type"] == "thinking"
    assert content[1]["type"] == "text"


def test_normalize_adaptive_removes_effort():
    data = {"thinking": {"type": "adaptive"}, "reasoning_effort": "max"}
    _normalize_thinking(data)
    assert "reasoning_effort" not in data
    assert data["thinking"]["type"] == "enabled"


def test_normalize_adaptive_removes_output_config():
    data = {"thinking": {"type": "adaptive"}, "output_config": {"effort": "max"}}
    _normalize_thinking(data)
    assert "output_config" not in data
    assert data["thinking"]["type"] == "enabled"


def test_normalize_no_thinking_key():
    assert not _normalize_thinking({"max_tokens": 100})


# === proxy.py 边缘情况补充 ===


def test_normalize_thinking_no_messages_key():
    """data 无 messages 键 -> True（thinking 被修改为 enabled）。"""
    data = {"thinking": {"type": "adaptive"}}
    assert _normalize_thinking(data)
    assert data["thinking"]["type"] == "enabled"


def test_normalize_thinking_unknown_type():
    """未知 thinking type -> 转换为 enabled。"""
    data = {"thinking": {"type": "auto"}, "messages": [{"role": "user", "content": "hi"}]}
    assert _normalize_thinking(data)
    assert data["thinking"]["type"] == "enabled"


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


