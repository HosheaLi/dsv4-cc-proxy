"""dsv4-cc-proxy codex translate 单元测试。

覆盖: instruction/developer 合并、input item 类型分发、content 提取、
      function_call 到 tool_calls 附加、reasoning 折叠、空字符串注入。

运行: python3 -m pytest tests/test_translate.py -v
"""

import copy
import json
from importlib import reload

import dsv4_cc_proxy.codex.config as codex_config
import dsv4_cc_proxy.codex.translate as codex_translate

# =============================================================================
# 组 1: 基础消息翻译
# =============================================================================


def test_simple_user_message():
    """验证简单用户消息 + instructions 翻译为 system + user 消息。"""
    body = {
        "model": "test-model",
        "input": [
            {"role": "user", "content": "Hello"}
        ],
        "instructions": "Be helpful.",
    }
    result = codex_translate.translate_request(body)

    assert len(result["messages"]) == 2
    assert result["messages"][0] == {"role": "system", "content": "Be helpful."}
    assert result["messages"][1] == {"role": "user", "content": "Hello"}


def test_string_content():
    """验证字符串 content 直接通过。"""
    body = {
        "model": "test-model",
        "input": [
            {"role": "user", "content": "plain string"}
        ],
    }
    result = codex_translate.translate_request(body)

    assert len(result["messages"]) == 1
    assert result["messages"][0]["content"] == "plain string"


def test_message_content_array():
    """验证 content 数组（input_text 类型）拼接为字符串。"""
    body = {
        "model": "test-model",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Part1"},
                    {"type": "input_text", "text": "Part2"},
                ],
            }
        ],
    }
    result = codex_translate.translate_request(body)

    assert result["messages"][0]["content"] == "Part1\nPart2"


def test_message_content_none():
    """验证 content 为 None 时透传。"""
    body = {
        "model": "test-model",
        "input": [
            {"role": "user", "content": None}
        ],
    }
    result = codex_translate.translate_request(body)

    assert result["messages"][0]["content"] is None


def test_assistant_message():
    """验证 assistant 消息正确翻译。"""
    body = {
        "model": "test-model",
        "input": [
            {"role": "assistant", "content": "I think so"}
        ],
    }
    result = codex_translate.translate_request(body)

    assert len(result["messages"]) == 1
    assert result["messages"][0]["role"] == "assistant"
    assert result["messages"][0]["content"] == "I think so"


def test_no_input_empty():
    """验证空 input 且无 instructions 时 messages 为空列表。"""
    body = {
        "model": "test-model",
        "input": [],
    }
    result = codex_translate.translate_request(body)

    assert result["messages"] == []


# =============================================================================
# 组 2: System 消息合并
# =============================================================================


def test_merge_instructions_and_developer(monkeypatch):
    """验证 instructions + developer role 合并为 system 消息 (CODX-04)。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_config)
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Hi"},
            {"type": "message", "role": "developer", "content": "Use Python"},
        ],
        "instructions": "Be concise",
    }
    result = codex_translate.translate_request(body)

    assert result["messages"][0]["role"] == "system"
    assert result["messages"][0]["content"] == "Be concise\n\nUse Python"

    # developer 消息不应出现在翻译后的 messages 中
    dev_roles = [m for m in result["messages"] if m.get("role") == "developer"]
    assert len(dev_roles) == 0


def test_no_system_when_empty(monkeypatch):
    """验证 instructions 和 developer 皆空时无 system 消息 (CODX-04, Pitfall 4)。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_config)
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Hello"}
        ],
    }
    result = codex_translate.translate_request(body)

    system_msgs = [m for m in result["messages"] if m.get("role") == "system"]
    assert len(system_msgs) == 0

    # user 消息直接是第一条
    assert result["messages"][0]["role"] == "user"


def test_instructions_only_no_developer(monkeypatch):
    """验证仅有 instructions 时 system 消息来自 instructions。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Hello"}
        ],
        "instructions": "Helpful",
    }
    result = codex_translate.translate_request(body)

    assert result["messages"][0]["role"] == "system"
    assert result["messages"][0]["content"] == "Helpful"


def test_developer_only_no_instructions(monkeypatch):
    """验证仅有 developer 消息时 system 消息来自 developer。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Hi"},
            {"type": "message", "role": "developer", "content": "Be Pythonic"},
        ],
    }
    result = codex_translate.translate_request(body)

    assert result["messages"][0]["role"] == "system"
    assert result["messages"][0]["content"] == "Be Pythonic"


# =============================================================================
# 组 3: 工具调用翻译
# =============================================================================


def test_function_call_to_tool_calls(monkeypatch):
    """验证 function_call 附加到前一条 assistant 的 tool_calls (CODX-11)。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Run bash"},
            {"role": "assistant", "content": "I will run it"},
            {
                "type": "function_call",
                "id": "call_1",
                "name": "Bash",
                "arguments": "{}",
                "status": "completed",
            },
        ],
    }
    result = codex_translate.translate_request(body)

    # function_call 附加到现有 assistant，共 2 条消息
    assert len(result["messages"]) == 2
    assert result["messages"][1]["role"] == "assistant"
    assert result["messages"][1]["content"] == "I will run it"
    assert "tool_calls" in result["messages"][1]
    assert len(result["messages"][1]["tool_calls"]) == 1
    assert result["messages"][1]["tool_calls"][0]["id"] == "call_1"
    assert result["messages"][1]["tool_calls"][0]["type"] == "function"
    assert result["messages"][1]["tool_calls"][0]["function"]["name"] == "Bash"


def test_synthetic_assistant(monkeypatch):
    """验证 function_call 前无 assistant 时创建合成 assistant (CODX-11, D-06)。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Read file"},
            {
                "type": "function_call",
                "id": "call_1",
                "name": "Bash",
                "arguments": '{"cmd": "ls"}',
                "status": "completed",
            },
        ],
    }
    result = codex_translate.translate_request(body)

    assert len(result["messages"]) == 2
    assert result["messages"][0]["role"] == "user"
    assert result["messages"][1]["role"] == "assistant"
    assert result["messages"][1]["content"] is None
    assert len(result["messages"][1]["tool_calls"]) == 1
    assert result["messages"][1]["tool_calls"][0]["id"] == "call_1"


def test_multiple_function_calls(monkeypatch):
    """验证多个 function_call 附加到同一 assistant 消息。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "assistant", "content": "Running commands"},
            {
                "type": "function_call",
                "id": "call_1",
                "name": "Bash",
                "arguments": "{}",
                "status": "completed",
            },
            {
                "type": "function_call",
                "id": "call_2",
                "name": "Edit",
                "arguments": "{}",
                "status": "completed",
            },
        ],
    }
    result = codex_translate.translate_request(body)

    asst_msgs = [m for m in result["messages"] if m.get("role") == "assistant"]
    assert len(asst_msgs) == 1
    assert len(asst_msgs[0]["tool_calls"]) == 2
    assert asst_msgs[0]["tool_calls"][0]["id"] == "call_1"
    assert asst_msgs[0]["tool_calls"][1]["id"] == "call_2"


def test_function_call_output_to_tool(monkeypatch):
    """验证 function_call_output 翻译为 tool 消息 (CODX-11)。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Read file"},
            {
                "type": "function_call",
                "id": "call_1",
                "name": "Bash",
                "arguments": "{}",
                "status": "completed",
            },
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": "file content",
            },
        ],
    }
    result = codex_translate.translate_request(body)

    tool_msgs = [m for m in result["messages"] if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_1"
    assert tool_msgs[0]["content"] == "file content"


def test_function_call_with_separate_id_and_call_id(monkeypatch):
    """验证 function_call 同时有 id 和 call_id 时使用 call_id (CODX-11, Pitfall 5)。

    Codex CLI 真实场景: function_call item 的 id (item 标识) 和
    call_id (工具调用匹配标识) 是不同的值。call_id 必须与
    function_call_output 的 call_id 匹配。
    """
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Read and save file"},
            # 模拟 Codex CLI 真实格式: id 和 call_id 不同
            {
                "type": "function_call",
                "id": "item_3",          # item 自身 ID
                "call_id": "call_abc123",  # 工具调用匹配 ID
                "name": "Bash",
                "arguments": '{"cmd": "cat file.txt"}',
                "status": "completed",
            },
            {
                "type": "function_call_output",
                "call_id": "call_abc123",  # 与 function_call.call_id 匹配
                "output": "file content here",
            },
        ],
    }
    result = codex_translate.translate_request(body)

    # tool_calls[].id 应该使用 call_id ("call_abc123") 而非 id ("item_3")
    asst_msgs = [m for m in result["messages"] if m.get("role") == "assistant"]
    assert len(asst_msgs) == 1
    assert len(asst_msgs[0]["tool_calls"]) == 1
    assert asst_msgs[0]["tool_calls"][0]["id"] == "call_abc123"

    # tool 消息的 tool_call_id 应该匹配
    tool_msgs = [m for m in result["messages"] if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_abc123"


# =============================================================================
# 组 4: Reasoning 处理
# =============================================================================


def test_reasoning_folds_to_next_assistant(monkeypatch):
    """验证 reasoning item 折叠到后续 assistant 的 reasoning_content (CODX-14, D-09, D-10)。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Analyze"},
            {
                "type": "reasoning",
                "id": "rs_1",
                "content": [
                    {"type": "reasoning_text", "text": "Let me analyze"}
                ],
            },
            {"role": "assistant", "content": "Here is my analysis"},
        ],
    }
    result = codex_translate.translate_request(body)

    asst_msgs = [m for m in result["messages"] if m.get("role") == "assistant"]
    assert len(asst_msgs) == 1
    assert asst_msgs[0].get("reasoning_content") == "Let me analyze"


def test_reasoning_content_extraction(monkeypatch):
    """验证多个 reasoning_text 块拼接为字符串。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Complex task"},
            {
                "type": "reasoning",
                "id": "rs_1",
                "content": [
                    {"type": "reasoning_text", "text": "Step 1"},
                    {"type": "reasoning_text", "text": "Step 2"},
                    {"type": "reasoning_text", "text": "Step 3"},
                ],
            },
            {"role": "assistant", "content": "Result"},
        ],
    }
    result = codex_translate.translate_request(body)

    asst_msgs = [m for m in result["messages"] if m.get("role") == "assistant"]
    assert asst_msgs[0].get("reasoning_content") == "Step 1\nStep 2\nStep 3"


def test_inject_reasoning_content(monkeypatch):
    """验证有 tool_calls 的 assistant 自动注入 reasoning_content: '' (CODX-14, D-11)。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "assistant", "content": "Let me check"},
            {
                "type": "function_call",
                "id": "call_1",
                "name": "Bash",
                "arguments": "{}",
                "status": "completed",
            },
        ],
    }
    result = codex_translate.translate_request(body)

    asst_msgs = [m for m in result["messages"] if m.get("role") == "assistant"]
    assert len(asst_msgs) == 1
    assert asst_msgs[0].get("reasoning_content") == ""


def test_reasoning_no_following_assistant(monkeypatch):
    """验证末尾 reasoning 无后续 assistant 时不抛出异常 (CODX-14, D-09)。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Think deeply"},
            {
                "type": "reasoning",
                "id": "rs_1",
                "content": [
                    {"type": "reasoning_text", "text": "Deep thoughts"}
                ],
            },
        ],
    }
    result = codex_translate.translate_request(body)

    # reasoning 不应被注入到 user 消息
    user_msgs = [m for m in result["messages"] if m.get("role") == "user"]
    assert len(user_msgs) == 1
    assert "reasoning_content" not in user_msgs[0]


def test_reasoning_anomalous_sequence(monkeypatch):
    """验证 reasoning -> user 异常序列不抛出异常 (D-13)。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "First message"},
            {
                "type": "reasoning",
                "id": "rs_1",
                "content": [
                    {"type": "reasoning_text", "text": "Thinking..."}
                ],
            },
            {"role": "user", "content": "Second message"},
        ],
    }
    result = codex_translate.translate_request(body)

    # 两条 user 消息都应正常翻译
    user_msgs = [m for m in result["messages"] if m.get("role") == "user"]
    assert len(user_msgs) == 2


def test_reasoning_effort_mapping(monkeypatch):
    """验证 reasoning.effort -> thinking 参数映射 (CODX-12, D-10, D-11)。

    - low/medium/high 都映射为 thinking: {"type": "enabled"}
    - 映射后 reasoning 字段从 body 中移除
    - 无 reasoning.effort 时不添加 thinking
    """
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    # 1. effort=high 映射
    body = {
        "model": "gpt-5.3-codex",
        "reasoning": {"effort": "high"},
        "input": [{"role": "user", "content": "Hello"}],
    }
    result = codex_translate.translate_request(body)

    assert result["thinking"] == {"type": "enabled"}
    assert "reasoning" not in result

    # 2. effort=medium 映射
    body = {
        "model": "gpt-5.3-codex",
        "reasoning": {"effort": "medium"},
        "input": [{"role": "user", "content": "Hello"}],
    }
    result = codex_translate.translate_request(body)

    assert result["thinking"] == {"type": "enabled"}
    assert "reasoning" not in result

    # 3. effort=low 映射
    body = {
        "model": "gpt-5.3-codex",
        "reasoning": {"effort": "low"},
        "input": [{"role": "user", "content": "Hello"}],
    }
    result = codex_translate.translate_request(body)

    assert result["thinking"] == {"type": "enabled"}
    assert "reasoning" not in result

    # 4. 无 reasoning.effort — 不添加 thinking
    body = {
        "model": "gpt-5.3-codex",
        "input": [{"role": "user", "content": "Hello"}],
    }
    result = codex_translate.translate_request(body)

    assert "thinking" not in result

    # 5. reasoning 为空 dict — 不添加 thinking，移除 reasoning
    body = {
        "model": "gpt-5.3-codex",
        "reasoning": {},
        "input": [{"role": "user", "content": "Hello"}],
    }
    result = codex_translate.translate_request(body)

    assert "thinking" not in result
    assert "reasoning" not in result


# =============================================================================
# 组 5: 边界情况
# =============================================================================


def test_unknown_type_skipped(monkeypatch):
    """验证未知 item 类型被跳过 (D-08)。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Hello"},
            {"type": "unknown_type_xyz", "data": "something"},
            {"role": "user", "content": "World"},
        ],
    }
    result = codex_translate.translate_request(body)

    assert len(result["messages"]) == 2
    assert result["messages"][0]["content"] == "Hello"
    assert result["messages"][1]["content"] == "World"


def test_translate_request_immutable(monkeypatch):
    """验证 translate_request 不修改输入 dict。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [
            {"role": "user", "content": "Hello"},
            {
                "type": "function_call",
                "id": "call_1",
                "name": "Bash",
                "arguments": "{}",
                "status": "completed",
            },
        ],
        "instructions": "Be helpful.",
    }
    body_copy = copy.deepcopy(body)
    codex_translate.translate_request(body)
    assert body == body_copy


# =============================================================================
# 组 6: 模型解析
# =============================================================================


def test_model_resolved_via_config(monkeypatch):
    """验证 model 字段通过 resolve_model() 环境变量映射。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", json.dumps({
        "gpt-5.3-codex": "deepseek-v4-pro",
    }))
    reload(codex_config)
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "input": [{"role": "user", "content": "Hi"}],
    }
    result = codex_translate.translate_request(body)

    assert result["model"] == "deepseek-v4-pro"


def test_max_output_tokens_renamed(monkeypatch):
    """验证 max_output_tokens 重命名为 max_tokens。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_translate)

    body = {
        "model": "gpt-5.3-codex",
        "max_output_tokens": 8192,
        "input": [{"role": "user", "content": "Hello"}],
    }
    result = codex_translate.translate_request(body)

    assert result["max_tokens"] == 8192
    assert "max_output_tokens" not in result
