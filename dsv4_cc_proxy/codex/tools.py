# dsv4-cc-proxy / codex — 工具定义格式转换
#
# convert_tools() 将 OpenAI Responses API 扁平工具格式转换为
# DeepSeek Chat Completions 嵌套格式，并递归剥离不兼容 JSON Schema 字段。
#
# 环境变量: (无 — 纯函数，无外部依赖)
#
# 职责:
#   - 扁平 → 嵌套格式转换: {type, name, description, parameters}
#     → {type, function: {name, description, parameters}} (CODX-07)
#   - JSON Schema 递归清理: 剥离 default/readOnly/writeOnly/examples/
#     minLength/maxLength/minItems/maxItems, 移除空 enum 数组 (CODX-10)

from __future__ import annotations

import copy
import logging

logger = logging.getLogger("deepseek-proxy")


# ---- 常量 ----


REMOVED_KEYS = frozenset({
    "default", "readOnly", "writeOnly", "examples",
    "minLength", "maxLength", "minItems", "maxItems",
})


# ---- 内部辅助函数 ----


def _convert_tool_format(tool: dict) -> dict:
    """扁平工具格式 → 嵌套格式转换。

    处理:
    - 已嵌套（有 function 键）→ 原样通过
    - 未知 type → WARNING + 原样透传
    - function type 扁平 → {type, function: {name, desc, params, strict}}
    """
    # 1. 若已有 "function" 键 → 直接返回（D-08 已嵌套处理）
    if "function" in tool:
        return tool

    # 2. 未知 type 记录 WARNING 并原样透传
    tool_type = tool.get("type", "")
    if tool_type != "function":
        logger.warning("[CODEX] unknown tool type: %s, passing through", tool_type)
        return tool

    # 3. function type 扁平格式 → 嵌套包装
    #    需要移到 function 下的键: name, description, parameters, strict
    function_fields = {}
    for key in ("name", "description", "parameters", "strict"):
        if key in tool:
            function_fields[key] = tool.pop(key)

    # 4. 构建嵌套格式（保留 type + 其他可能的顶层字段）
    tool["function"] = function_fields
    return tool


def _clean_schema(schema: dict) -> dict:
    """递归剥离 DeepSeek 不兼容的 JSON Schema 字段。

    在 convert_tools 的 deepcopy 保护下安全地原地修改输入（效率优化）。
    """
    # 1. 剥离不兼容字段（D-05 精确字段清单）
    for key in REMOVED_KEYS:
        schema.pop(key, None)

    # 2. 移除空 enum 数组
    if "enum" in schema and isinstance(schema["enum"], list) and len(schema["enum"]) == 0:
        del schema["enum"]

    # 3. 递归: properties（D-06 必须处理的路径）
    if "properties" in schema and isinstance(schema["properties"], dict):
        for sub_schema in schema["properties"].values():
            if isinstance(sub_schema, dict):
                _clean_schema(sub_schema)

    # 4. 递归: $defs
    if "$defs" in schema and isinstance(schema["$defs"], dict):
        for sub_schema in schema["$defs"].values():
            if isinstance(sub_schema, dict):
                _clean_schema(sub_schema)

    # 5. 递归: anyOf
    if "anyOf" in schema and isinstance(schema["anyOf"], list):
        for item in schema["anyOf"]:
            if isinstance(item, dict):
                _clean_schema(item)

    # 6. 递归: items
    if "items" in schema and isinstance(schema["items"], dict):
        _clean_schema(schema["items"])

    return schema


# ---- 公开 API ----


def convert_tools(tools: list[dict]) -> list[dict]:
    """Responses API 工具列表 → DeepSeek Chat 兼容格式。

    Pure function: 不修改输入（deepcopy 保护）。

    Args:
        tools: 工具定义字典列表（不会被修改）。

    Returns:
        格式转换 + schema 清理后的工具定义列表。

    处理步骤:
    1. 深拷贝输入（None → []）
    2. 对每个工具调用 _convert_tool_format()
    3. 若有 parameters 且为 dict → 调用 _clean_schema()
    4. 若有 parameters 且非 dict → 抛出 ValueError
    5. 返回处理后的列表
    """
    if not tools:
        return []

    result = copy.deepcopy(tools)

    for i, tool in enumerate(result):
        if not isinstance(tool, dict):
            logger.warning("[CODEX] non-dict tool at index %d, skipping", i)
            continue

        # 格式转换
        converted = _convert_tool_format(tool)

        # Schema 修复（在 function 内的 parameters 或顶层的 parameters）
        params = converted.get("parameters")
        # 如果已嵌套，parameters 在 function 里
        if "function" in converted:
            params = converted["function"].get("parameters")

        if params is not None:
            if isinstance(params, dict):
                _clean_schema(params)
            elif isinstance(params, list):
                # D-07: list 类型也视为无效 — schema 必须是 dict
                tool_name = converted.get("function", {}).get("name", "?") if "function" in converted else converted.get("name", "?")
                raise ValueError(
                    f"Invalid tool parameters schema for '{tool_name}': "
                    f"expected dict, got list"
                )
            else:
                # D-07: 非 dict 非 None 的 parameters → 抛出异常（Pitfall 4）
                tool_name = converted.get("function", {}).get("name", "?") if "function" in converted else converted.get("name", "?")
                raise ValueError(
                    f"Invalid tool parameters schema for '{tool_name}': "
                    f"expected dict, got {type(params).__name__}"
                )

    return result
