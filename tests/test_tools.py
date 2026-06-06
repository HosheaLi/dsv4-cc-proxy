"""dsv4-cc-proxy codex 工具转换单元测试。

覆盖: 格式转换、schema 字段剥离、递归清理、边界情况。
运行: python3 -m pytest tests/test_tools.py -v
"""

import copy

import pytest

import dsv4_cc_proxy.codex.tools as codex_tools


# =============================================================================
# 组 1: 格式转换
# =============================================================================


def test_convert_flat_to_nested():
    """验证扁平 {type, name, desc, params} → 嵌套 {type, function: {name, desc, params}}。"""
    body = [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get current weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
            },
        }
    ]
    result = codex_tools.convert_tools(body)

    assert len(result) == 1
    assert result[0]["type"] == "function"
    assert "function" in result[0]
    assert result[0]["function"]["name"] == "get_weather"
    assert result[0]["function"]["description"] == "Get current weather"
    assert "parameters" in result[0]["function"]
    assert "name" not in result[0]
    assert "description" not in result[0]


def test_convert_already_nested_pass_through():
    """验证已嵌套工具原样通过，无双重嵌套。"""
    body = [
        {"type": "function", "function": {"name": "get_weather", "description": "X"}}
    ]
    result = codex_tools.convert_tools(body)

    assert result[0] == body[0]
    assert "function" in result[0]
    assert result[0]["function"]["name"] == "get_weather"


def test_convert_empty_tools_list():
    """验证空 tools 列表返回空列表。"""
    result = codex_tools.convert_tools([])
    assert result == []


def test_convert_none_tools():
    """验证 None 输入返回空列表。"""
    result = codex_tools.convert_tools(None)
    assert result == []


def test_convert_multiple_tools():
    """验证多工具列表正确转换，混合扁平与已嵌套工具。"""
    body = [
        {"type": "function", "name": "fn1", "description": "tool 1", "parameters": {"type": "object"}},
        {"type": "function", "function": {"name": "fn2", "description": "tool 2"}},
        {"type": "function", "name": "fn3", "description": "tool 3", "parameters": {"type": "object"}},
    ]
    result = codex_tools.convert_tools(body)

    assert len(result) == 3
    # 扁平 → 嵌套
    assert result[0]["function"]["name"] == "fn1"
    # 已嵌套 → 原样
    assert result[1] == body[1]
    # 扁平 → 嵌套
    assert result[2]["function"]["name"] == "fn3"


def test_convert_tools_immutable():
    """验证 convert_tools 不修改输入列表。"""
    body = [
        {
            "type": "function",
            "name": "get_weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
            },
        }
    ]
    body_copy = copy.deepcopy(body)
    codex_tools.convert_tools(body)
    assert body == body_copy


# =============================================================================
# 组 2: Schema 字段剥离
# =============================================================================


def test_clean_schema_strips_all_unsupported():
    """验证所有 8 个不兼容字段都被剥离。"""
    params = {
        "type": "string",
        "default": "fallback",
        "readOnly": True,
        "writeOnly": True,
        "examples": ["ex1", "ex2"],
        "minLength": 0,
        "maxLength": 100,
        "minItems": 1,
        "maxItems": 10,
    }
    body = [{"type": "function", "name": "fn", "parameters": params}]
    result = codex_tools.convert_tools(body)
    cleaned = result[0]["function"]["parameters"]

    assert "type" in cleaned
    assert "default" not in cleaned
    assert "readOnly" not in cleaned
    assert "writeOnly" not in cleaned
    assert "examples" not in cleaned
    assert "minLength" not in cleaned
    assert "maxLength" not in cleaned
    assert "minItems" not in cleaned
    assert "maxItems" not in cleaned


def test_clean_schema_removes_empty_enum():
    """验证空 enum 数组被移除。"""
    body = [{"type": "function", "name": "fn", "parameters": {"type": "string", "enum": []}}]
    result = codex_tools.convert_tools(body)
    assert "enum" not in result[0]["function"]["parameters"]


def test_clean_schema_preserves_non_empty_enum():
    """验证非空 enum 数组被保留。"""
    body = [{"type": "function", "name": "fn", "parameters": {"type": "string", "enum": ["a", "b"]}}]
    result = codex_tools.convert_tools(body)
    assert result[0]["function"]["parameters"]["enum"] == ["a", "b"]


def test_clean_schema_keeps_valid_fields():
    """验证合法 schema 字段被保留。"""
    body = [{
        "type": "function",
        "name": "fn",
        "parameters": {
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        },
    }]
    result = codex_tools.convert_tools(body)
    cleaned = result[0]["function"]["parameters"]
    assert "type" in cleaned
    assert "properties" in cleaned
    assert "required" in cleaned


# =============================================================================
# 组 3: 递归清理
# =============================================================================


def test_recursive_via_properties():
    """验证递归进入嵌套 properties 清理。"""
    body = [{"type": "function", "name": "fn", "parameters": {
        "type": "object",
        "properties": {
            "addr": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "default": "NYC"},
                },
            },
        },
    }}]
    result = codex_tools.convert_tools(body)
    inner = result[0]["function"]["parameters"]["properties"]["addr"]["properties"]["city"]
    assert "default" not in inner


def test_recursive_via_defs():
    """验证递归进入 $defs 清理。"""
    body = [{"type": "function", "name": "fn", "parameters": {
        "type": "object",
        "$defs": {
            "Address": {
                "type": "object",
                "properties": {"city": {"type": "string", "default": "NYC"}},
            },
        },
    }}]
    result = codex_tools.convert_tools(body)
    addr = result[0]["function"]["parameters"]["$defs"]["Address"]["properties"]["city"]
    assert "default" not in addr


def test_recursive_via_anyof():
    """验证递归进入 anyOf 分支清理。"""
    body = [{"type": "function", "name": "fn", "parameters": {
        "type": "object",
        "anyOf": [
            {"type": "string", "default": "fallback"},
            {"type": "integer", "default": 0},
        ],
    }}]
    result = codex_tools.convert_tools(body)
    for item in result[0]["function"]["parameters"]["anyOf"]:
        assert "default" not in item


def test_recursive_via_items():
    """验证递归进入 array items 清理。"""
    body = [{"type": "function", "name": "fn", "parameters": {
        "type": "array",
        "items": {"type": "string", "default": "item_default"},
    }}]
    result = codex_tools.convert_tools(body)
    assert "default" not in result[0]["function"]["parameters"]["items"]


# =============================================================================
# 组 4: 边界情况
# =============================================================================


def test_unknown_type_passes_through():
    """验证未知 type 字段原样通过。"""
    body = [{"type": "custom_type", "data": "test"}]
    result = codex_tools.convert_tools(body)
    assert result[0] == body[0]


def test_missing_parameters_skips_schema_repair():
    """验证缺少 parameters 字段时不崩溃，跳过 schema repair。"""
    body = [{"type": "function", "name": "fn", "description": "no params"}]
    result = codex_tools.convert_tools(body)
    assert "function" in result[0]
    assert result[0]["function"]["name"] == "fn"
    assert "parameters" not in result[0]["function"]


def test_tool_with_strict_field():
    """验证 strict 字段被移到 function 内。"""
    body = [{"type": "function", "name": "fn", "strict": True, "parameters": {"type": "object"}}]
    result = codex_tools.convert_tools(body)
    assert result[0]["function"]["strict"] is True
    assert "strict" not in result[0]


def test_unknown_tool_type_preserved():
    """验证混合工具列表中已知/未知类型工具正确处理。"""
    body = [
        {"type": "function", "name": "fn", "parameters": {"type": "object"}},
        {"type": "unknown_type_named_xyz"},
    ]
    result = codex_tools.convert_tools(body)
    assert len(result) == 2
    # function 工具正常转换
    assert "function" in result[0]
    assert result[0]["function"]["name"] == "fn"
    # 未知类型原样通过
    assert result[1] == body[1]


# =============================================================================
# 组 5: 错误处理
# =============================================================================


def test_invalid_parameters_type_raises_valueerror():
    """验证无效 parameters 类型抛出 ValueError (D-07)。"""
    # 字符串类型
    with pytest.raises(ValueError, match="Invalid tool parameters"):
        codex_tools.convert_tools([{"type": "function", "name": "bad", "parameters": "invalid_string"}])

    # 整数类型
    with pytest.raises(ValueError, match="Invalid tool parameters"):
        codex_tools.convert_tools([{"type": "function", "name": "bad", "parameters": 42}])


def test_invalid_parameters_none_skipped():
    """验证 parameters 为 None 时跳过不报错 (D-09)。"""
    result = codex_tools.convert_tools([{"type": "function", "name": "fn", "parameters": None}])
    assert result[0]["function"]["parameters"] is None


def test_non_dict_tool_skipped():
    """验证非 dict 元素被跳过，不抛出异常。"""
    result = codex_tools.convert_tools([
        {"type": "function", "name": "good", "parameters": {"type": "object"}},
        "not_a_dict",
    ])
    assert len(result) == 2
    assert "function" in result[0]
    assert result[0]["function"]["name"] == "good"
