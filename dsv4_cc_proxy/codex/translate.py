# dsv4-cc-proxy / codex — Response → Chat 请求翻译
#
# translate_request() 将 OpenAI Responses API 请求体翻译为
# DeepSeek Chat Completions 请求体格式。
#
# 环境变量: (无 — 不使用 env var)
#
# 职责:
#   - instructions + developer role → system 消息合并 (D-05)
#   - input[] item 类型分发: message / function_call / function_call_output / reasoning (D-08)
#   - function_call → tool_calls 附加, 无前条 assistant 时创建合成消息 (D-06)
#   - function_call_output → tool role 消息
#   - reasoning → 折叠到后续 assistant 的 reasoning_content (D-09, D-10, D-13)
#   - 后处理: 有 tool_calls 的 assistant 注入 reasoning_content: "" (D-11)

from __future__ import annotations

import copy
import json
import logging
from typing import Any

from dsv4_cc_proxy.codex.config import CODEX_DEFAULT_MODEL, CODEX_UPSTREAM, resolve_model
from dsv4_cc_proxy.codex.tools import convert_tools

logger = logging.getLogger("deepseek-proxy")


# ---- 内部辅助函数 ----


def _extract_content_text(content: str | list | None) -> str | None:
    """从 content 字段提取文本。

    支持:
    - 字符串 → 直接返回
    - 数组 → 提取所有 type: "input_text" 的 text，用 \n 拼接
    - None → 返回 None
    - 意外类型 → 返回 None（不崩溃）
    """
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and block.get("type") == "input_text"
        ]
        return "\n".join(texts) if texts else None
    return None  # 意外类型返回 None 而非崩溃


def _merge_system_messages(
    instructions: str | None,
    developer_messages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """合并 instructions 和 developer role 消息为一条 system 消息。

    如果两者皆空则返回 None。非空时用 \n\n 连接各部分。
    """
    parts = []
    if instructions:
        parts.append(instructions)
    for msg in developer_messages:
        content = _extract_content_text(msg.get("content"))
        if content:
            parts.append(content)
    if not parts:
        return None
    return {"role": "system", "content": "\n\n".join(parts)}


def _translate_input_items(input_array: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 Responses API input 数组翻译为 Chat Completions messages 列表。

    处理 item 类型:
    - message → user/assistant 按 role 映射
    - function_call → 附加到前一条 assistant 的 tool_calls
    - function_call_output → tool role 消息
    - reasoning → 折叠到后续 assistant 的 reasoning_content
    - 未知类型 → WARNING + 跳过
    """
    messages: list[dict[str, Any]] = []
    pending_reasoning: list[str] = []

    for item in input_array:
        if not isinstance(item, dict):
            logger.warning("[CODEX] non-dict input item, skipping")
            continue

        item_type = item.get("type", item.get("role", ""))

        # ---- message type ----
        # 支持显式 type="message" 和 role-only 简写两种格式
        if item_type == "message" or item_type in ("user", "assistant", "developer"):
            # role-only 简写时, item_type 就是 role 值
            role = item.get("role", item_type)
            if role == "developer":
                # developer 消息由 _merge_system_messages 外部处理
                continue
            if role == "user":
                messages.append({
                    "role": "user",
                    "content": _extract_content_text(item.get("content")),
                })
            elif role == "assistant":
                messages.append({
                    "role": "assistant",
                    "content": _extract_content_text(item.get("content")),
                })
            else:
                logger.warning("[CODEX] unknown message role: %s, skipping", role)

        # ---- function_call type ----
        elif item_type == "function_call":
            # 使用 .get() 避免 KeyError — Codex 某些上下文中的 item 可能缺少字段
            call_id = item.get("id") or item.get("call_id", "")
            tool_entry = {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": item.get("name", "unknown"),
                    "arguments": item.get("arguments", ""),
                },
            }
            # 查找前一条 assistant 消息
            last_asst_idx = -1
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "assistant":
                    last_asst_idx = i
                    break
            if last_asst_idx >= 0:
                if "tool_calls" not in messages[last_asst_idx]:
                    messages[last_asst_idx]["tool_calls"] = []
                messages[last_asst_idx]["tool_calls"].append(tool_entry)
            else:
                # 无前条 assistant → 创建合成 assistant 消息
                synthetic = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_entry],
                }
                messages.append(synthetic)

        # ---- function_call_output type ----
        elif item_type == "function_call_output":
            # 使用 .get() 避免 KeyError — Codex 某些上下文中的 item 可能缺少字段
            messages.append({
                "role": "tool",
                "tool_call_id": item.get("call_id", ""),
                "content": item.get("output", ""),
            })

        # ---- reasoning type ----
        elif item_type == "reasoning":
            content_blocks = item.get("content", [])
            summary_blocks = item.get("summary", [])
            texts: list[str] = []
            # 提取 reasoning_text
            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "reasoning_text":
                    texts.append(block["text"])
            # 没有 reasoning_text 时回退到 summary
            if not texts:
                for block in summary_blocks:
                    if isinstance(block, dict) and block.get("type") == "summary_text":
                        texts.append(block["text"])
            combined = "\n".join(texts)
            if combined:
                pending_reasoning.append(combined)

        # ---- 未知类型 ----
        else:
            logger.warning("[CODEX] unknown input item type: %s, skipping", item_type)

    # ---- 后处理: pending_reasoning 折叠 ----
    if pending_reasoning:
        combined_reasoning = "\n".join(pending_reasoning)
        if not messages:
            # 没有消息可以注入 reasoning
            logger.warning("[CODEX] reasoning items found but no messages to attach to, skipping")
        else:
            last_msg = messages[-1]
            if last_msg.get("role") == "assistant":
                last_msg["reasoning_content"] = combined_reasoning
                logger.debug("[CODEX] folded reasoning into last assistant")
            else:
                # D-13: 异常序列 (reasoning → non-assistant)
                logger.warning(
                    "[CODEX] anomalous reasoning sequence: last message is %s, discarding reasoning",
                    last_msg.get("role", "unknown"),
                )

    return messages


def _ensure_reasoning_content(messages: list[dict[str, Any]]) -> None:
    """后处理：确保有 tool_calls 的 assistant 消息包含 reasoning_content。

    DeepSeek 要求：assistant 消息有 tool_calls 时必须同时有 reasoning_content 字段。
    如果缺失则注入空字符串。
    """
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        if "tool_calls" in msg and "reasoning_content" not in msg:
            msg["reasoning_content"] = ""
            logger.debug("[CODEX] injected reasoning_content: '' on assistant with tool_calls")


# ---- 公开 API ----


def translate_request(request_body: dict[str, Any]) -> dict[str, Any]:
    """将 Responses API 请求体翻译为 Chat Completions 请求体。

    Pure function: 不修改输入（deepcopy 保护）。
    返回全新字典。

    Args:
        request_body: Responses API 请求字典（不会被修改）。

    Returns:
        翻译后的 Chat Completions 请求字典。

    处理步骤:
    1. 深拷贝输入
    2. 提取 instructions + developer role 消息合并为 system 消息
    3. 翻译 input[] 数组中的每个 item:
       - message → 按 role 映射
       - function_call → 附加到前一条 assistant 的 tool_calls
       - function_call_output → tool role 消息
       - reasoning → 折叠到下一个 assistant 的 reasoning_content
       - 未知类型 → WARNING + 跳过
    4. Post-process: 检查所有 assistant 消息，有 tool_calls 缺
       reasoning_content 时注入空字符串
    5. 设置 model 字段 (调用 resolve_model)

    Notes:
        - assistant 消息的 content 可为 None (D-06)。如果 DeepSeek 对
          content: None 报错，替换为 content: ""。
        - 此函数只做结构性翻译。tool 定义格式转换 (type: function 包装等)
          由 Phase 3 处理。
    """
    body = copy.deepcopy(request_body)

    # 1. 提取并移除 Responses 独有字段
    instructions = body.pop("instructions", None)
    input_array = body.pop("input", [])

    # 2. 分离 developer 消息
    developer_msgs: list[dict[str, Any]] = []
    other_items: list[dict[str, Any]] = []
    for item in input_array:
        if (
            isinstance(item, dict)
            and item.get("type") == "message"
            and item.get("role") == "developer"
        ):
            developer_msgs.append(item)
        else:
            other_items.append(item)

    # 3. 翻译 items
    messages = _translate_input_items(other_items)

    # 4. 后处理: 确保有 tool_calls 的 assistant 包含 reasoning_content
    _ensure_reasoning_content(messages)

    # 5. 合并系统消息 (instructions + developer role)
    system_msg = _merge_system_messages(instructions, developer_msgs)
    if system_msg is not None:
        messages.insert(0, system_msg)

    # 6. 解析模型
    original_model = body.get("model", "")
    body["model"] = resolve_model(original_model) if original_model else CODEX_DEFAULT_MODEL

    # 7. 处理 max_output_tokens → max_tokens
    if "max_output_tokens" in body:
        body["max_tokens"] = body.pop("max_output_tokens")

    # 8. 移除 Responses-only 字段
    body.pop("include", None)

    # 9. reasoning.effort -> thinking 映射 (Phase 4, CODX-12, D-10)
    reasoning = body.get("reasoning", {})
    if isinstance(reasoning, dict) and reasoning.get("effort") in ("low", "medium", "high"):
        body["thinking"] = {"type": "enabled"}
    # D-11: remove reasoning field after mapping
    body.pop("reasoning", None)

    # 10. 工具定义格式转换 (Phase 3, CODX-07, CODX-10)
    if "tools" in body:
        body["tools"] = convert_tools(body["tools"])

    # 11. 设置 messages
    body["messages"] = messages

    return body
