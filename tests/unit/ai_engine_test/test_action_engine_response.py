import pytest

from ai_engine.action_engine import ActionEngine
from ai_engine.config import ResponseConfig, ResponseValue


@pytest.fixture
def minimal_agent_path(write_temp_json):
    return write_temp_json({
        "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
        "global_defaults": {}
    }, "agent.json")


class TestResponseParsing:
    def test_jsonpath_extraction(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        config = ResponseConfig(
            mode="json",
            values={
                "status": ResponseValue(type="string", path="data.order.status"),
                "total": ResponseValue(type="string", path="data.order.payment.total")
            },
            template="Status: {{status}}, Total: {{total}}"
        )
        data = {
            "data": {
                "order": {
                    "status": "shipped",
                    "payment": {"total": "99.99"}
                }
            }
        }
        result = engine._parse_response(data, config)
        assert result == "Status: shipped, Total: 99.99"

    def test_missing_jsonpath_returns_na(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        config = ResponseConfig(
            mode="json",
            values={
                "missing": ResponseValue(type="string", path="data.not.here")
            },
            template="Value: {{missing}}"
        )
        result = engine._parse_response({"data": {}}, config)
        assert "N/A" in result

    def test_raw_mode_returns_string(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        config = ResponseConfig(mode="raw")
        data = {"key": "value"}
        result = engine._parse_response(data, config)
        assert result == str(data)

    def test_template_with_value_placeholder_dict(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        config = ResponseConfig(
            mode="json",
            template="Raw: {{value}}"
        )
        data = {"key": "value"}
        result = engine._parse_response(data, config)
        assert "Raw:" in result
        assert '"key": "value"' in result

    def test_template_with_value_placeholder_str(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        config = ResponseConfig(
            mode="raw",
            template="Data: {{value}}"
        )
        result = engine._parse_response("plain text", config)
        assert result == "Data: plain text"

    def test_no_config_returns_str(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        result = engine._parse_response({"a": 1}, None)
        assert result == str({"a": 1})

    def test_bad_jsonpath_returns_error_parsing(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        config = ResponseConfig(
            mode="json",
            values={
                "bad": ResponseValue(type="string", path="invalid[")
            },
            template="Bad: {{bad}}"
        )
        result = engine._parse_response({}, config)
        assert "ErrorParsing" in result

    def test_no_template_returns_str(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        config = ResponseConfig(mode="json", values={"x": ResponseValue(type="string", path="y")})
        result = engine._parse_response({"y": "z"}, config)
        assert result == str({"y": "z"})

    def test_multiple_substitutions(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        config = ResponseConfig(
            mode="json",
            values={
                "a": ResponseValue(type="string", path="x.a"),
                "b": ResponseValue(type="string", path="x.b")
            },
            template="A={{a}}, B={{b}}"
        )
        result = engine._parse_response({"x": {"a": "1", "b": "2"}}, config)
        assert result == "A=1, B=2"

    def test_nested_jsonpath_array(self, minimal_agent_path):
        engine = ActionEngine(minimal_agent_path, actions_list=[])
        config = ResponseConfig(
            mode="json",
            values={
                "first": ResponseValue(type="string", path="items[0].name")
            },
            template="First: {{first}}"
        )
        result = engine._parse_response({"items": [{"name": "alpha"}, {"name": "beta"}]}, config)
        assert "First: alpha" == result