"""dsv4-cc-proxy 单元测试。

覆盖 pure functions: 请求端注入、thinking 标准化、SSE 过滤。
运行: python3 -m pytest tests/test_proxy.py -v
"""

import json

from dsv4_cc_proxy.proxy import (
    _consolidate_system_messages,
    _has_thinking,
    _has_tool_use,
    _inject_thinking_blocks,
    _normalize_thinking,
    _translate_anthropic_structured_output,
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


def test_normalize_adaptive_converts_to_disabled():
    """adaptive/auto → disabled（避免 DeepSeek 无限思考循环）。"""
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
    # disabled 模式需剥离历史 thinking 块
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
    assert data["thinking"]["type"] == "disabled"


def test_normalize_no_thinking_key():
    assert not _normalize_thinking({"max_tokens": 100})


# === proxy.py 边缘情况补充 ===


def test_normalize_thinking_no_messages_key():
    """data 无 messages 键 -> True（thinking 被修改为 disabled）。"""
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


# =============================================================================
# 组 2: Anthropic 结构化输出翻译 (CODX-17)
# =============================================================================


def test_translate_output_config_json_schema():
    """验证 output_config.format.json_schema → schema 注入 system prompt。"""
    schema = {
        "type": "object",
        "required": ["verdict", "summary"],
        "properties": {
            "verdict": {"type": "string", "enum": ["approve", "needs-attention"]},
            "summary": {"type": "string"},
        },
    }
    data = {
        "model": "deepseek-v4-pro",
        "system": "You are a code reviewer.",
        "messages": [{"role": "user", "content": "Review"}],
        "output_config": {
            "format": {
                "type": "json_schema",
                "name": "review_output",
                "schema": schema,
            }
        },
    }
    assert _translate_anthropic_structured_output(data)
    # output_config 应被移除
    assert "output_config" not in data
    # system prompt 应包含 schema 指令
    assert "JSON Schema" in data["system"]
    assert "verdict" in data["system"]


def test_translate_output_format_beta():
    """验证 output_format (beta) 同样被翻译。"""
    data = {
        "model": "deepseek-v4-flash",
        "system": "System prompt.",
        "messages": [{"role": "user", "content": "x"}],
        "output_format": {
            "format": {
                "type": "json_schema",
                "schema": {"type": "object", "properties": {"x": {"type": "string"}}},
            }
        },
    }
    assert _translate_anthropic_structured_output(data)
    assert "output_format" not in data
    assert "JSON Schema" in data["system"]


def test_translate_named_tool_choice_to_auto():
    """验证 named tool_choice → auto 降级 + schema 提取。"""
    schema = {"type": "object", "properties": {"result": {"type": "string"}}}
    data = {
        "model": "deepseek-v4-pro",
        "system": "System.",
        "messages": [{"role": "user", "content": "Go"}],
        "tool_choice": {"type": "tool", "name": "submit_output"},
        "tools": [
            {
                "name": "submit_output",
                "description": "Output tool",
                "input_schema": schema,
            },
            {"name": "Bash", "description": "Run commands"},
        ],
    }
    assert _translate_anthropic_structured_output(data)
    # tool_choice 降级为 auto
    assert data["tool_choice"] == {"type": "auto"}
    # schema 从 tool input_schema 提取并注入 system
    assert "JSON Schema" in data["system"]
    assert "result" in data["system"]


def test_translate_noop_for_non_deepseek():
    """验证非 deepseek 模型不做翻译。"""
    data = {
        "model": "claude-sonnet-4-6",
        "system": "System.",
        "messages": [{"role": "user", "content": "x"}],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": {"type": "object"},
            }
        },
    }
    assert not _translate_anthropic_structured_output(data)
    # output_config 保持原样
    assert "output_config" in data


def test_translate_noop_when_nothing_to_translate():
    """验证无结构化输出字段时不做翻译。"""
    data = {
        "model": "deepseek-v4-flash",
        "system": "System.",
        "messages": [{"role": "user", "content": "x"}],
    }
    assert not _translate_anthropic_structured_output(data)


def test_translate_system_list_format():
    """验证 system 为 list (Anthropic content blocks) 时正确注入。"""
    data = {
        "model": "deepseek-v4-pro",
        "system": [{"type": "text", "text": "Helper."}],
        "messages": [{"role": "user", "content": "x"}],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": {"type": "object"},
            }
        },
    }
    assert _translate_anthropic_structured_output(data)
    assert len(data["system"]) == 2
    assert data["system"][1]["type"] == "text"
    assert "JSON Schema" in data["system"][1]["text"]


def test_translate_output_config_without_schema_noop():
    """验证 output_config 不含有效 schema 时不做注入。"""
    data = {
        "model": "deepseek-v4-pro",
        "system": "System.",
        "messages": [{"role": "user", "content": "x"}],
        "output_config": {"format": {"type": "text"}},
    }
    assert not _translate_anthropic_structured_output(data)


# =============================================================================
# 组 3: Unicode 引号标准化
# =============================================================================

from dsv4_cc_proxy.proxy import _normalize_quotes


def test_normalize_quotes_plain_string():
    """验证字符串中的排版引号被替换为 ASCII 单引号。"""
    assert _normalize_quotes("it’s") == "it's"
    assert _normalize_quotes("donʼt") == "don't"
    assert _normalize_quotes("xʹy") == "x'y"


def test_normalize_quotes_mixed_characters():
    """验证混合多种引号字符的字符串全部被替换。"""
    result = _normalize_quotes("a’bʼcʹd")
    assert result == "a'b'c'd"


def test_normalize_quotes_no_quotes():
    """验证不含目标引号的字符串原样返回。"""
    assert _normalize_quotes("hello world") == "hello world"
    assert _normalize_quotes("it's fine") == "it's fine"  # ASCII 单引号不变
    assert _normalize_quotes("") == ""


def test_normalize_quotes_nested_dict():
    """验证嵌套 dict 中的引号被替换。"""
    data = {
        "messages": [
            {"role": "user", "content": "it’s a test"},
            {"role": "assistant", "content": "donʼt worry"},
        ],
        "system": "you’re helpful",
    }
    result = _normalize_quotes(data)
    assert result["messages"][0]["content"] == "it's a test"
    assert result["messages"][1]["content"] == "don't worry"
    assert result["system"] == "you're helpful"


def test_normalize_quotes_nested_list():
    """验证嵌套 list 中的引号被替换。"""
    data = ["a’b", ["cʼd", "eʹf"]]
    result = _normalize_quotes(data)
    assert result == ["a'b", ["c'd", "e'f"]]


def test_normalize_quotes_non_string_passthrough():
    """验证非字符串类型原样返回。"""
    assert _normalize_quotes(42) == 42
    assert _normalize_quotes(3.14) == 3.14
    assert _normalize_quotes(True) is True
    assert _normalize_quotes(None) is None


def test_normalize_quotes_immutable_input():
    """验证不修改原始输入。"""
    original = {"msg": "it’s ok"}
    result = _normalize_quotes(original)
    assert result["msg"] == "it's ok"
    assert original["msg"] == "it’s ok"  # 原始不变


def test_normalize_quotes_tool_call_arguments():
    """验证工具调用参数中的引号被替换。"""
    data = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"cmd": "echo ’hello’"}}
                ],
            }
        ],
    }
    result = _normalize_quotes(data)
    input_block = result["messages"][0]["content"][0]["input"]
    assert input_block["cmd"] == "echo 'hello'"


def test_normalize_quotes_all_targets():
    """验证三个目标字符都被正确替换。"""
    # U+2019: RIGHT SINGLE QUOTATION MARK
    assert _normalize_quotes("’") == "'"
    # U+02BC: MODIFIER LETTER APOSTROPHE
    assert _normalize_quotes("ʼ") == "'"
    # U+02B9: MODIFIER LETTER PRIME
    assert _normalize_quotes("ʹ") == "'"


# =============================================================================
# 组 4: 日期格式标准化
# =============================================================================

from dsv4_cc_proxy.proxy import _normalize_text


def test_normalize_date_slash_to_dash():
    """验证日期中的 / 被替换为 -。"""
    assert _normalize_text("Today's date is 2026/06/30.") == "Today's date is 2026-06-30."
    assert _normalize_text("Current date: 2025/01/01") == "Current date: 2025-01-01"


def test_normalize_date_already_dash():
    """验证已是 - 格式的日期不被修改。"""
    assert _normalize_text("Today's date is 2026-06-30.") == "Today's date is 2026-06-30."


def test_normalize_date_only_in_context():
    """验证只在日期上下文中替换 /，不替换其他地方的 /。"""
    result = _normalize_text("Path is /usr/bin and Today's date is 2026/07/06.")
    assert result == "Path is /usr/bin and Today's date is 2026-07-06."


def test_normalize_date_with_curly_quote():
    """验证包含排版引号的 "Today's date" 也能匹配。"""
    result = _normalize_text("Today’s date is 2026/06/30.")
    assert result == "Today's date is 2026-06-30."


def test_normalize_date_chinese():
    """验证中文日期前缀也能匹配。"""
    assert _normalize_text("今天的日期是 2026/07/06") == "今天的日期是 2026-07-06"


def test_normalize_date_multiple_in_string():
    """验证同一字符串中多处日期都被替换。"""
    result = _normalize_text(
        "Today's date is 2026/06/30. Current date: 2025/01/01."
    )
    assert result == "Today's date is 2026-06-30. Current date: 2025-01-01."


def test_normalize_date_nested_in_data():
    """验证嵌套数据中的日期也被替换。"""
    data = {
        "system": "You are helpful. Today's date is 2026/07/06.",
        "messages": [
            {"role": "user", "content": "what's the date? Current date: 2026/07/06"}
        ],
    }
    result = _normalize_quotes(data)
    assert "2026-07-06" in result["system"]
    assert "2026/07/06" not in result["system"]
    assert "2026-07-06" in result["messages"][0]["content"]


def test_normalize_date_unchanged_match():
    """验证不匹配日期前缀的 / 不被修改。"""
    # 其他位置的 / 不应被替换
    assert _normalize_text("2026/06/30") == "2026/06/30"  # 无前缀，不替换
    assert _normalize_text("date is 2026/06/30") == "date is 2026/06/30"  # 不全匹配


# =============================================================================
# 组 5: messages[] 中 role:system 消息合并到顶层 system
# =============================================================================


def test_consolidate_no_system_messages():
    """无 system 角色消息 → 不做修改。"""
    data = {"messages": [{"role": "user", "content": "hi"}]}
    modified, count = _consolidate_system_messages(data)
    assert not modified
    assert count == 0
    assert len(data["messages"]) == 1


def test_consolidate_single_system_at_start():
    """开头一条 system 消息 + 顶层 system 字符串 → 合并到 system。"""
    data = {
        "system": "You are a helper.",
        "messages": [
            {"role": "system", "content": "Use English only."},
            {"role": "user", "content": "hello"},
        ],
    }
    modified, count = _consolidate_system_messages(data)
    assert modified
    assert count == 1
    assert len(data["messages"]) == 1
    assert data["messages"][0]["role"] == "user"
    assert "You are a helper." in data["system"]
    assert "Use English only." in data["system"]


def test_consolidate_system_mid_conversation():
    """系统消息在对话中间 → 提取并追加到顶层 system。"""
    data = {
        "system": "Initial system prompt.",
        "messages": [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "system", "content": "Now switch to English."},
            {"role": "user", "content": "Q2"},
        ],
    }
    modified, count = _consolidate_system_messages(data)
    assert modified
    assert count == 1
    assert len(data["messages"]) == 3
    roles = [m["role"] for m in data["messages"]]
    assert "system" not in roles
    assert "Now switch to English." in data["system"]


def test_consolidate_multiple_system_messages():
    """多条系统消息 → 全部提取并按顺序追加。"""
    data = {
        "system": "Base.",
        "messages": [
            {"role": "system", "content": "First."},
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "Second."},
        ],
    }
    modified, count = _consolidate_system_messages(data)
    assert modified
    assert count == 2
    assert len(data["messages"]) == 1
    first_pos = data["system"].index("First.")
    second_pos = data["system"].index("Second.")
    assert first_pos < second_pos


def test_consolidate_system_content_as_blocks():
    """系统消息 content 为内容块列表 → 提取 text 块。"""
    data = {
        "messages": [
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": "Block one."},
                    {"type": "text", "text": "Block two."},
                ],
            },
            {"role": "user", "content": "hello"},
        ],
    }
    modified, count = _consolidate_system_messages(data)
    assert modified
    assert count == 1
    assert "Block one." in data["system"]
    assert "Block two." in data["system"]


def test_consolidate_no_top_level_system():
    """无顶层 system 字段 → 创建新 system 字段。"""
    data = {
        "messages": [
            {"role": "system", "content": "Be helpful."},
            {"role": "user", "content": "hi"},
        ],
    }
    modified, count = _consolidate_system_messages(data)
    assert modified
    assert data["system"] == "Be helpful."
    assert len(data["messages"]) == 1


def test_consolidate_top_level_system_as_blocks():
    """顶层 system 为内容块列表 → 追加 text 块。"""
    data = {
        "system": [{"type": "text", "text": "Base."}],
        "messages": [
            {"role": "system", "content": "Extra."},
            {"role": "user", "content": "hi"},
        ],
    }
    modified, count = _consolidate_system_messages(data)
    assert modified
    assert len(data["system"]) == 2
    assert data["system"][1]["type"] == "text"
    assert "Extra." in data["system"][1]["text"]


def test_consolidate_empty_system_content():
    """系统消息 content 为空 → 不计入合并但仍从 messages 移除。"""
    data = {
        "messages": [
            {"role": "system", "content": ""},
            {"role": "user", "content": "hi"},
        ],
    }
    modified, count = _consolidate_system_messages(data)
    assert modified
    assert count == 1
    assert len(data["messages"]) == 1
    # system 字段不应被创建（空内容跳过）
    assert "system" not in data


def test_consolidate_system_with_non_text_blocks():
    """系统消息含非 text 块 → 只提取 text 块。"""
    data = {
        "messages": [
            {
                "role": "system",
                "content": [
                    {"type": "thinking", "thinking": "secret"},
                    {"type": "text", "text": "Visible."},
                ],
            },
            {"role": "user", "content": "hi"},
        ],
    }
    modified, count = _consolidate_system_messages(data)
    assert modified
    assert "Visible." in data["system"]
    assert "secret" not in data["system"]


def test_consolidate_no_messages_key():
    """无 messages 键 → 不做修改。"""
    data = {"system": "Base.", "model": "deepseek-v4-pro"}
    modified, count = _consolidate_system_messages(data)
    assert not modified
    assert count == 0


def test_consolidate_preserves_remaining_order():
    """移除系统消息后保留 user/assistant 消息的原始顺序。"""
    data = {
        "messages": [
            {"role": "system", "content": "S1"},
            {"role": "user", "content": "U1"},
            {"role": "assistant", "content": "A1"},
            {"role": "system", "content": "S2"},
            {"role": "user", "content": "U2"},
        ],
    }
    modified, count = _consolidate_system_messages(data)
    assert modified
    assert count == 2
    roles = [m["role"] for m in data["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert data["messages"][0]["content"] == "U1"
    assert data["messages"][1]["content"] == "A1"
    assert data["messages"][2]["content"] == "U2"


def test_consolidate_messages_not_a_list():
    """messages 不是 list → 不做修改。"""
    data = {"messages": "not a list"}
    modified, count = _consolidate_system_messages(data)
    assert not modified
    assert count == 0