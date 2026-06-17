# tests/test_models.py — codex/models.py 纯函数单元测试

import json

from dsv4_cc_proxy.codex.models import (
    MODEL_DEFINITIONS,
    get_codex_catalog,
    get_openai_models_list,
)


class TestGetCodexCatalog:
    """get_codex_catalog() 的格式和内容测试。"""

    def test_returns_list(self):
        """返回 list 类型。"""
        catalog = get_codex_catalog()
        assert isinstance(catalog, list)

    def test_contains_both_models(self):
        """包含 deepseek-v4-pro 和 deepseek-v4-flash。"""
        slugs = {m["slug"] for m in get_codex_catalog()}
        assert "deepseek-v4-pro" in slugs
        assert "deepseek-v4-flash" in slugs

    def test_required_fields_present(self):
        """每个条目包含所有必需字段。"""
        required = {
            "slug", "display_name", "provider", "context_window",
            "max_context_window", "supports_parallel_tool_calls",
            "supports_reasoning_summaries", "default_reasoning_level",
            "supported_reasoning_levels", "family", "max_output",
            "input_modalities", "pricing",
        }
        for model in get_codex_catalog():
            missing = required - set(model.keys())
            assert not missing, f"模型 {model['slug']} 缺少字段: {missing}"

    def test_provider_field_consistent(self):
        """所有条目的 provider 字段值一致。"""
        providers = {m["provider"] for m in get_codex_catalog()}
        assert providers == {"deepseek-proxy"}

    def test_context_window_positive(self):
        """context_window 为正整数。"""
        for model in get_codex_catalog():
            assert model["context_window"] > 0
            assert model["max_context_window"] > 0

    def test_input_modalities_non_empty(self):
        """input_modalities 非空。"""
        for model in get_codex_catalog():
            assert len(model["input_modalities"]) >= 1

    def test_pricing_present(self):
        """pricing 字典包含 input 和 output。"""
        for model in get_codex_catalog():
            assert "input" in model["pricing"]
            assert "output" in model["pricing"]

    def test_supported_reasoning_levels_are_objects(self):
        """supported_reasoning_levels 是对象数组 (含 effort + description)。"""
        for model in get_codex_catalog():
            for level in model["supported_reasoning_levels"]:
                assert "effort" in level
                assert "description" in level

    def test_immutable_copies(self):
        """重复调用返回独立副本 (非同一引用)。"""
        a = get_codex_catalog()
        b = get_codex_catalog()
        assert a is not b
        assert a[0] is not b[0]

    def test_serializable_to_json(self):
        """输出可序列化为 JSON。"""
        json.dumps(get_codex_catalog())


class TestGetOpenaiModelsList:
    """get_openai_models_list() 的格式和内容测试。"""

    def test_returns_list(self):
        assert isinstance(get_openai_models_list(), list)

    def test_contains_both_models(self):
        ids = {m["id"] for m in get_openai_models_list()}
        assert "deepseek-v4-pro" in ids
        assert "deepseek-v4-flash" in ids

    def test_correct_fields(self):
        """每个模型包含 id, object, created, owned_by。"""
        for model in get_openai_models_list():
            assert "id" in model
            assert model["object"] == "model"
            assert "created" in model
            assert model["owned_by"] == "deepseek"

    def test_created_is_positive_int(self):
        for model in get_openai_models_list():
            assert isinstance(model["created"], int)
            assert model["created"] > 0

    def test_serializable_to_json(self):
        json.dumps(get_openai_models_list())


class TestModelDefinitions:
    """MODEL_DEFINITIONS 静态数据完整性测试。"""

    def test_non_empty(self):
        assert len(MODEL_DEFINITIONS) >= 2

    def test_unique_slugs(self):
        slugs = [m["slug"] for m in MODEL_DEFINITIONS]
        assert len(slugs) == len(set(slugs)), "slug 重复"

    def test_all_have_display_name(self):
        for m in MODEL_DEFINITIONS:
            assert m.get("display_name"), f"{m['slug']} 缺少 display_name"
