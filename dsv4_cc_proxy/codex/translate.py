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
import os
import tempfile
from typing import Any

from dsv4_cc_proxy.codex.config import CODEX_DEFAULT_MODEL, resolve_model
from dsv4_cc_proxy.codex.tools import convert_tools

logger = logging.getLogger("deepseek-proxy")


# ---- 内部辅助函数 ----


def _extract_content_text(content: str | list | None) -> str | None:
    """从 content 字段提取文本。

    支持:
    - 字符串 → 直接返回
    - 数组 → 提取所有 text 类型块的 text，用 \n 拼接
    - None → 返回 None
    - 意外类型 → 返回 None（不崩溃）

    注意: 同时兼容 OpenAI Responses API 的 output_text 和
    Anthropic Messages API 的 input_text 两种 content block 类型。
    Codex 在历史消息中发送 assistant 消息时 content 使用 output_text，
    而 user 消息使用 input_text。两种格式都需要正确提取。
    """
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict)
            and block.get("type") in ("input_text", "output_text")
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
            call_id = item.get("call_id") or item.get("id", "")
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


def _sanitize_assistant_messages(messages: list[dict[str, Any]]) -> None:
    """后处理：修复无效 assistant 消息。

    DeepSeek Chat API 拒绝 content 和 tool_calls 都为空的 assistant 消息，
    报错 "Invalid assistant message: content or tool_calls must be set"。

    场景:
    - assistant 消息的 content 为 None 或空字符串，且没有 tool_calls
      → 设置 content = ""（DeepSeek 接受空 content 的 assistant）

    注意: 有 tool_calls 但 content 为 None 的合成 assistant 不需要修复 —
    DeepSeek 允许 content 缺席当 tool_calls 存在时。
    """
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        has_tool_calls = bool(msg.get("tool_calls"))
        has_content = bool(msg.get("content"))
        if not has_tool_calls and not has_content:
            msg["content"] = ""
            logger.debug("[CODEX] sanitized assistant: content=None → ''")


def _reorder_tool_messages(messages: list[dict[str, Any]]) -> None:
    """后处理：确保 tool 消息紧跟在对应 assistant tool_calls 之后。

    DeepSeek Chat API 要求 assistant 的 tool_calls 后面紧跟对应的 tool 消息，
    中间不能有其他消息（如 user/system）。
    报错: "An assistant message with 'tool_calls' must be followed by
    tool messages responding to each 'tool_call_id'"

    当原始 input 序列中 user 消息被插入到 function_call 和
    function_call_output 之间时，翻译后会出现:
      assistant[tool_calls=[X]] → user → tool[tool_call_id=X]

    修复策略：对每个有 tool_calls 的 assistant，收集后续所有匹配其
    tool_call_ids 的 tool 消息，将它们移到 assistant 之后、其他消息之前。
    使用 stable reorder 保持 tool 消息的原有顺序。
    """
    # 在 list 上原地重排（避免多次扫描时索引偏移）
    reordered = False
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") != "assistant" or not msg.get("tool_calls"):
            i += 1
            continue

        tool_call_ids = {tc["id"] for tc in msg["tool_calls"]}

        # 收集后续的 tool 消息
        tool_msgs: list[dict[str, Any]] = []
        j = i + 1
        while j < len(messages):
            nxt = messages[j]
            if nxt.get("role") == "tool" and nxt.get("tool_call_id") in tool_call_ids:
                tool_msgs.append(nxt)
                messages.pop(j)
                tool_call_ids.discard(nxt["tool_call_id"])
                # j 不变（pop 后下一个元素移到了 j 位置）
                reordered = True
            elif nxt.get("role") == "assistant":
                # 遇到下一个 assistant，停止（新的 turn）
                break
            else:
                j += 1

        # 将收集的 tool 消息插入到 assistant 之后
        if tool_msgs:
            for k, tm in enumerate(tool_msgs):
                messages.insert(i + 1 + k, tm)
            logger.debug(
                "[CODEX] reordered %d tool messages after assistant[%d]",
                len(tool_msgs), i,
            )
            # 跳过刚插入的 tool 消息
            i += 1 + len(tool_msgs)
        else:
            i += 1

    if reordered:
        logger.warning("[CODEX] tool message reordering applied")


def _translate_text_format(body: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """将 Responses API 的 text.format 翻译为 DeepSeek response_format + schema 提示文本。

    OpenAI Responses API 通过 text.format 指定结构化输出格式:
      - {"type": "json_object"} → 要求输出合法 JSON
      - {"type": "json_schema", "name": "...", "schema": {...}} → 按 schema 输出

    DeepSeek Chat API 只支持 response_format: {"type": "json_object"}，
    不支持完整的 json_schema strict mode。因此将 json_schema 翻译为:
      1. response_format: {"type": "json_object"} — 保证合法 JSON
      2. schema 提示文本 — 注入 system message 引导模型按 schema 输出

    Args:
        body: 翻译中的请求体（text 字段会被 pop 掉）。

    Returns:
        (response_format_dict | None, schema_prompt_str | None)
    """
    text_cfg = body.pop("text", None)
    if not isinstance(text_cfg, dict):
        return None, None

    format_cfg = text_cfg.get("format")
    if not isinstance(format_cfg, dict):
        return None, None

    # 检测未翻译的 text 子字段，避免静默丢信息
    extra_keys = [k for k in text_cfg if k != "format"]
    if extra_keys:
        logger.warning(
            "[CODEX] text object contains untranslated keys: %s — silently dropped",
            extra_keys,
        )

    format_type = format_cfg.get("type", "")

    if format_type == "json_object":
        logger.info("[CODEX] text.format: json_object → response_format")
        return {"type": "json_object"}, None

    if format_type == "json_schema":
        schema_name = format_cfg.get("name", "response")
        schema = format_cfg.get("schema", {})
        strict = format_cfg.get("strict", False)

        # DeepSeek 不支持 json_schema strict mode，降级为 json_object
        response_format = {"type": "json_object"}

        # 将 schema 转为系统提示文本，引导模型按 schema 输出
        schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
        schema_prompt = (
            f"你 MUST 用符合以下 JSON Schema 的单个 JSON 对象回复:\n"
            f"```json\n{schema_json}\n```\n"
            f"不要用 markdown 代码块包裹 JSON。"
            f"只输出 JSON 对象，不要输出其他内容。"
        )
        if strict:
            schema_prompt += (
                " JSON MUST 严格遵守 schema。不允许额外字段。"
            )

        logger.info(
            "[CODEX] text.format: json_schema (name=%s, strict=%s) → response_format + system prompt",
            schema_name, strict,
        )
        return response_format, schema_prompt

    # 未知 format 类型但显式指定了 — 保守起见只要求合法 JSON
    logger.warning(
        "[CODEX] unknown text.format type: %s, forcing json_object",
        format_type,
    )
    return {"type": "json_object"}, None


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

    # 4b. 后处理: 修复无效 assistant 消息（无 content 且无 tool_calls）
    _sanitize_assistant_messages(messages)

    # 4c. 后处理: 修复 tool_calls 与 tool 消息配对
    # 当 assistant 的 tool_calls 和后续 tool 响应之间有其他消息插入时，
    # DeepSeek 会报错 "tool_calls must be followed by tool messages"。
    # 修复：将 tool 消息移到紧接 assistant 的位置。
    _reorder_tool_messages(messages)

    # 5. 翻译 text.format → response_format (CODX-16)
    #    OpenAI Responses API 用 text.format 指定结构化输出，
    #    DeepSeek Chat API 用 response_format。此处做字段翻译。
    response_format, schema_prompt = _translate_text_format(body)
    if schema_prompt:
        if instructions:
            instructions = f"{instructions}\n\n{schema_prompt}"
        else:
            instructions = schema_prompt

    # 6. 合并系统消息 (instructions + developer role)
    system_msg = _merge_system_messages(instructions, developer_msgs)
    if system_msg is not None:
        messages.insert(0, system_msg)

    # 7. 解析模型
    original_model = body.get("model", "")
    body["model"] = resolve_model(original_model) if original_model else CODEX_DEFAULT_MODEL

    # 8. 处理 max_output_tokens → max_tokens
    if "max_output_tokens" in body:
        body["max_tokens"] = body.pop("max_output_tokens")

    # 9. 设置 response_format (来自 text.format 翻译)
    if response_format is not None:
        body["response_format"] = response_format

    # 10. 移除 Responses-only 字段
    body.pop("include", None)

    # 11. 强制禁用 DeepSeek thinking (CODX-19)
    #      DeepSeek 在 thinking=enabled 模式下容易陷入无限思考循环。
    #      无论 App Server 发来什么 thinking 配置，对 deepseek-* 模型
    #      一律禁用。对原生 OpenAI 模型保持原样。
    resolved_model = body.get("model", "")
    if resolved_model.startswith("deepseek-"):
        reasoning = body.pop("reasoning", None)
        if isinstance(reasoning, dict) and reasoning.get("effort") in ("low", "medium", "high"):
            logger.info("[CODEX] reasoning.effort=%s ignored, thinking forced to disabled", reasoning.get("effort"))
        body["thinking"] = {"type": "disabled"}

    # 12. 工具定义格式转换 (Phase 3, CODX-07, CODX-10)
    if "tools" in body:
        body["tools"] = convert_tools(body["tools"])

    # 13. 设置 messages
    body["messages"] = messages

    # 临时诊断 dump（所有路径都写）
    import json as _json
    _dump_path = os.path.join(tempfile.gettempdir(), "last_codex_chat_request.json")
    with open(_dump_path, "w") as _f:
        _json.dump(body, _f, ensure_ascii=False, indent=2, default=str)
    logger.warning("[CODEX] dumped chat request to %s", _dump_path)

    return body
