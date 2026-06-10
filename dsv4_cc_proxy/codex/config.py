# dsv4-cc-proxy / codex — 模型映射配置
#
# 环境变量:
#   CODEX_DEFAULT_MODEL   默认 DeepSeek 模型名 (默认 deepseek-v4-flash)
#   CODEX_MODEL_MAP       JSON 格式的模型名映射表 (默认 {})
#   CODEX_UPSTREAM        DeepSeek Chat Completions API 地址 (默认 https://api.deepseek.com/v1)
#
# resolve_model() 解析顺序:
#   1. 精确匹配 CODEX_MODEL_MAP 键
#   2. 最长前缀匹配
#   3. CODEX_DEFAULT_MODEL 回退

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("deepseek-proxy")

# ---- 配置 ----

CODEX_DEFAULT_MODEL = os.getenv("CODEX_DEFAULT_MODEL", "deepseek-v4-pro")
CODEX_UPSTREAM = os.getenv("CODEX_UPSTREAM", "https://api.deepseek.com/v1")
_RAW_MODEL_MAP = os.getenv("CODEX_MODEL_MAP", "{}")


# ---- 内部辅助函数 ----


def _parse_model_map(raw: str) -> dict[str, str]:
    """解析 CODEX_MODEL_MAP JSON 字符串为字典。

    解析失败时返回空字典（记录警告）。从不抛出异常。
    """
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            logger.warning("[CODEX] CODEX_MODEL_MAP is not a JSON object, ignoring")
            return {}
        return parsed
    except json.JSONDecodeError:
        logger.warning("[CODEX] CODEX_MODEL_MAP parse error, using empty map")
        return {}


# ---- 公开 API ----


def _is_deepseek_model(name: str) -> bool:
    """检查模型名是否是 DeepSeek 原生模型。"""
    return name.startswith("deepseek-")


def resolve_model(model_name: str) -> str:
    """将 Codex 模型名解析为 DeepSeek 模型字符串。

    解析顺序:
    1. 已是 DeepSeek 原生模型名（deepseek-*）→ 原样透传
    2. CODEX_MODEL_MAP 精确匹配
    3. CODEX_MODEL_MAP 最长前缀匹配
    4. CODEX_DEFAULT_MODEL 回退

    从不返回 None 或空字符串。
    """
    # 0. DeepSeek 原生模型名直接透传
    if _is_deepseek_model(model_name):
        logger.debug("[CODEX] passthrough: %s", model_name)
        return model_name

    model_map = _parse_model_map(_RAW_MODEL_MAP)

    # 1. 精确匹配
    if model_name in model_map:
        resolved = model_map[model_name]
        logger.debug("[CODEX] exact match: %s → %s", model_name, resolved)
        return resolved

    # 2. 最长前缀匹配
    prefix_matches = {
        key: model_map[key]
        for key in model_map
        if model_name.startswith(key)
    }
    if prefix_matches:
        best_key = max(prefix_matches, key=len)
        resolved = prefix_matches[best_key]
        logger.debug("[CODEX] prefix match: %s → %s (via %r)", model_name, resolved, best_key)
        return resolved

    # 3. 默认回退
    logger.debug("[CODEX] default: %s → %s", model_name, CODEX_DEFAULT_MODEL)
    return CODEX_DEFAULT_MODEL
