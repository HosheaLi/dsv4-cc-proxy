"""dsv4-cc-proxy codex config 单元测试。

覆盖: 模型映射解析、精确/前缀匹配、异常回退。
运行: python3 -m pytest tests/test_codex.py -v
"""

import json
from importlib import reload

import dsv4_cc_proxy.codex.config as codex_config


def test_exact_match_overrides_prefix(monkeypatch):
    """精确匹配优先于前缀匹配（当两者都匹配时）。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", json.dumps({
        "claude-sonnet-4-6": "deepseek-v4-pro",
        "claude-": "deepseek-v4-flash",
    }))
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("claude-sonnet-4-6") == "deepseek-v4-pro"


def test_prefix_match_longest_wins(monkeypatch):
    """最长前缀匹配优先于较短前缀。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", json.dumps({
        "claude-": "deepseek-v4-flash",
        "claude-sonnet-": "deepseek-v4-pro",
    }))
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("claude-sonnet-5") == "deepseek-v4-pro"


def test_fallback_to_default(monkeypatch):
    """无匹配模型时回退到 CODEX_DEFAULT_MODEL。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{}")
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("unknown-model") == "deepseek-v4-flash"


def test_empty_map_uses_default(monkeypatch):
    """空映射表始终返回默认模型。"""
    monkeypatch.delenv("CODEX_MODEL_MAP", raising=False)
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("anything") == "deepseek-v4-flash"


def test_invalid_json_map_falls_back(monkeypatch):
    """无效 JSON 在 CODEX_MODEL_MAP 中回退默认。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("CODEX_MODEL_MAP", "{invalid json}")
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("any") == "deepseek-v4-flash"


def test_prefix_not_matches_uses_default(monkeypatch):
    """无精确匹配且无前缀匹配时返回默认值。"""
    monkeypatch.setenv("CODEX_DEFAULT_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("CODEX_MODEL_MAP", json.dumps({
        "claude-": "deepseek-v4-flash",
    }))
    reload(codex_config)
    from dsv4_cc_proxy.codex.config import resolve_model
    assert resolve_model("gpt-5") == "deepseek-v4-pro"
