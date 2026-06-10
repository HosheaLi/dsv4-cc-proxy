# dsv4-cc-proxy / codex — 模型目录定义
#
# 提供 DeepSeek V4 模型的静态定义，生成两种格式的模型列表:
#   - Codex CLI model_catalog_json 格式 (用于 config.toml)
#   - OpenAI /v1/models 标准格式 (用于代理端点)
#
# 环境变量: (无 — 纯数据模块，无外部依赖)

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("deepseek-proxy")

# ---- 模型定义 (唯一数据源) ----

MODEL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "slug": "deepseek-v4-pro",
        "display_name": "DeepSeek V4 Pro",
        "provider": "deepseek-proxy",
        "description": "高质量推理模型，支持扩展思考。适合复杂编码、架构设计、深度分析。",
        "context_window": 131072,
        "max_context_window": 131072,
        "supports_parallel_tool_calls": True,
        "supports_reasoning_summaries": True,
        "default_reasoning_level": "medium",
        "supported_reasoning_levels": [
            {"effort": "low", "description": "快速响应，轻度推理"},
            {"effort": "medium", "description": "速度与推理深度的平衡，适合日常任务"},
            {"effort": "high", "description": "更深推理，适合复杂问题"},
        ],
        "family": "deepseek-v4",
        "max_output": 16384,
        "capabilities": {
            "vision": False,
            "function_calling": True,
            "parallel_tool_calls": True,
            "extended_thinking": True,
            "reasoning_summaries": True,
        },
        "pricing": {
            "input": 2.19,
            "output": 8.76,
        },
        "input_modalities": ["text"],
    },
    {
        "slug": "deepseek-v4-flash",
        "display_name": "DeepSeek V4 Flash",
        "provider": "deepseek-proxy",
        "description": "快速、高性价比模型。适合日常编码、编辑、大批量请求。",
        "context_window": 131072,
        "max_context_window": 131072,
        "supports_parallel_tool_calls": True,
        "supports_reasoning_summaries": True,
        "default_reasoning_level": "medium",
        "supported_reasoning_levels": [
            {"effort": "low", "description": "快速响应，轻度推理"},
            {"effort": "medium", "description": "速度与推理深度的平衡，适合日常任务"},
            {"effort": "high", "description": "更深推理，适合复杂问题"},
        ],
        "family": "deepseek-v4",
        "max_output": 16384,
        "capabilities": {
            "vision": True,
            "function_calling": True,
            "parallel_tool_calls": True,
            "extended_thinking": False,
            "reasoning_summaries": True,
        },
        "pricing": {
            "input": 0.44,
            "output": 1.76,
        },
        "input_modalities": ["text", "image"],
    },
]


# ---- 公开 API ----


def get_codex_catalog() -> list[dict[str, Any]]:
    """生成 Codex CLI model_catalog_json 格式的模型列表。

    每个条目的字段与 Codex CLI 0.137.0 兼容:
    - slug: 模型标识符 (API 调用和 /model 命令中使用)
    - display_name: TUI 中显示的可读名称
    - provider: 必须与 config.toml 中的 [model_providers.<id>] 名称匹配
    - context_window / max_context_window: 上下文窗口大小
    - supports_parallel_tool_calls / supports_reasoning_summaries: 能力标志
    - default_reasoning_level / supported_reasoning_levels: 推理配置
    - family: TUI 分组的模型族
    - max_output: 最大输出 token 数
    - input_modalities: 支持的输入类型
    - pricing: token 价格 (仅供参考展示)

    Returns:
        Codex 兼容的模型目录 JSON 数组 (可序列化为 JSON)。
    """
    return [
        {
            "slug": m["slug"],
            "display_name": m["display_name"],
            "provider": m["provider"],
            "context_window": m["context_window"],
            "max_context_window": m["max_context_window"],
            "supports_parallel_tool_calls": m["supports_parallel_tool_calls"],
            "supports_reasoning_summaries": m["supports_reasoning_summaries"],
            "default_reasoning_level": m["default_reasoning_level"],
            "supported_reasoning_levels": [dict(s) for s in m["supported_reasoning_levels"]],
            "family": m["family"],
            "max_output": m["max_output"],
            "input_modalities": list(m["input_modalities"]),
            "pricing": dict(m.get("pricing", {})),
        }
        for m in MODEL_DEFINITIONS
    ]


def get_openai_models_list() -> list[dict[str, Any]]:
    """生成 OpenAI /v1/models 标准格式的模型列表。

    Returns:
        模型对象列表，每项含 id, object, created, owned_by 字段。
    """
    import time
    now = int(time.time())
    return [
        {
            "id": m["slug"],
            "object": "model",
            "created": now,
            "owned_by": "deepseek",
        }
        for m in MODEL_DEFINITIONS
    ]
